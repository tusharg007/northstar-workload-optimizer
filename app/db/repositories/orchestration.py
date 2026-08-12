"""Durable approval orchestration and notification persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.approval_sla import ApprovalSLAService
from app.db.base import ensure_utc, utc_now
from app.db.models import ApprovalNotification, ApprovalTask, Expense
from app.db.session import Database


class ApprovalTaskNotFoundError(Exception):
    """The requested approval task does not exist."""


class OrchestrationConflictError(Exception):
    """A different n8n execution already owns the approval orchestration."""


@dataclass(frozen=True)
class ClaimOutcome:
    task: dict
    launch_required: bool


@dataclass(frozen=True)
class RegistrationOutcome:
    task: dict
    should_wait: bool
    replayed: bool


TERMINAL_TASK_STATUSES = {"APPROVED", "REJECTED", "CANCELLED"}


class ApprovalOrchestrationRepository:
    """Own transactional HITL lifecycle state; n8n remains the executor."""

    def __init__(self, database: Database) -> None:
        self.database = database
        self.sla = ApprovalSLAService()

    @staticmethod
    def _task_state(task: ApprovalTask, expense: Expense, *, reveal_resume: bool) -> dict:
        return {
            "task_id": task.task_id,
            "expense_id": task.expense_id,
            "workflow_run_id": task.workflow_run_id,
            "status": task.status,
            "is_terminal": task.status in TERMINAL_TASK_STATUSES,
            "orchestration_status": task.orchestration_status,
            "n8n_execution_id": task.n8n_execution_id,
            "resume_url": (
                task.n8n_wait_resume_url
                if reveal_resume and task.orchestration_status == "WAITING"
                else None
            ),
            "wait_registered_at": task.wait_registered_at,
            "orchestration_completed_at": task.orchestration_completed_at,
            "last_notification_at": task.last_notification_at,
            "reminder_count": task.reminder_count,
            "escalation_level": task.escalation_level,
            "approver_role": task.approver_role,
            "approval_level": task.approval_level,
            "risk_level": expense.risk_level,
            "due_at": task.due_at,
            "created_at": task.created_at,
            "safe_summary": {
                "expense_id": expense.expense_id,
                "employee_name": expense.employee_name,
                "department": expense.department,
                "amount": float(expense.amount),
                "currency": expense.currency,
                "category": expense.category,
                "risk_level": expense.risk_level,
                "approver_role": task.approver_role,
            },
        }

    @staticmethod
    def _notification_state(notification: ApprovalNotification) -> dict:
        return {
            "notification_id": notification.notification_id,
            "task_id": notification.approval_task_id,
            "type": notification.notification_type,
            "escalation_level": notification.escalation_level,
            "status": notification.status,
            "target_role": notification.target_role,
            **notification.payload,
        }

    @staticmethod
    def _task_and_expense(session, task_id: str, *, for_update: bool = False):
        statement = select(ApprovalTask).where(ApprovalTask.task_id == task_id)
        if for_update:
            statement = statement.with_for_update()
        task = session.scalar(statement)
        if task is None:
            raise ApprovalTaskNotFoundError("Approval task not found")
        expense = session.scalar(
            select(Expense).where(Expense.expense_id == task.expense_id)
        )
        if expense is None:
            raise RuntimeError("Approval task has no expense")
        return task, expense

    def get_by_expense(self, expense_id: str, *, reveal_resume: bool = True) -> dict:
        with self.database.session() as session:
            task = session.scalar(
                select(ApprovalTask)
                .where(ApprovalTask.expense_id == expense_id)
                .order_by(ApprovalTask.created_at.desc())
            )
            if task is None:
                raise ApprovalTaskNotFoundError("Approval task not found")
            expense = session.scalar(
                select(Expense).where(Expense.expense_id == expense_id)
            )
            if expense is None:
                raise RuntimeError("Approval task has no expense")
            return self._task_state(task, expense, reveal_resume=reveal_resume)

    def claim_by_expense(self, expense_id: str) -> ClaimOutcome:
        now = utc_now()
        with self.database.transaction() as session:
            task = session.scalar(
                select(ApprovalTask)
                .where(ApprovalTask.expense_id == expense_id)
                .order_by(ApprovalTask.created_at.desc())
                .with_for_update()
            )
            if task is None:
                raise ApprovalTaskNotFoundError("Approval task not found")
            expense = session.scalar(
                select(Expense).where(Expense.expense_id == expense_id)
            )
            assert expense is not None
            launch_required = False
            if task.status in TERMINAL_TASK_STATUSES:
                task.orchestration_status = "COMPLETED"
                task.orchestration_completed_at = (
                    task.orchestration_completed_at or now
                )
            elif task.orchestration_status == "NOT_STARTED":
                task.orchestration_status = "STARTING"
                task.orchestration_claimed_at = now
                launch_required = True
            session.flush()
            return ClaimOutcome(
                self._task_state(task, expense, reveal_resume=False),
                launch_required,
            )

    def register(
        self, task_id: str, execution_id: str, resume_url: str
    ) -> RegistrationOutcome:
        now = utc_now()
        with self.database.transaction() as session:
            task, expense = self._task_and_expense(
                session, task_id, for_update=True
            )
            if task.status in TERMINAL_TASK_STATUSES:
                if task.n8n_execution_id not in {None, execution_id}:
                    raise OrchestrationConflictError(
                        "Approval orchestration belongs to another execution"
                    )
                task.n8n_execution_id = execution_id
                task.orchestration_status = "COMPLETED"
                task.orchestration_completed_at = (
                    task.orchestration_completed_at or now
                )
                session.flush()
                return RegistrationOutcome(
                    self._task_state(task, expense, reveal_resume=False),
                    False,
                    False,
                )
            if task.n8n_execution_id == execution_id:
                return RegistrationOutcome(
                    self._task_state(task, expense, reveal_resume=True),
                    task.orchestration_status == "WAITING",
                    True,
                )
            if task.n8n_execution_id is not None or task.orchestration_status not in {
                "NOT_STARTED",
                "STARTING",
            }:
                raise OrchestrationConflictError(
                    "Approval orchestration is already registered"
                )
            task.n8n_execution_id = execution_id
            task.n8n_wait_resume_url = resume_url
            task.wait_registered_at = now
            task.orchestration_status = "WAITING"
            session.flush()
            return RegistrationOutcome(
                self._task_state(task, expense, reveal_resume=True), True, False
            )

    def complete(self, task_id: str, execution_id: str) -> dict:
        now = utc_now()
        with self.database.transaction() as session:
            task, expense = self._task_and_expense(
                session, task_id, for_update=True
            )
            if task.status not in TERMINAL_TASK_STATUSES:
                raise OrchestrationConflictError(
                    "Cannot complete orchestration while approval is pending"
                )
            if task.n8n_execution_id not in {None, execution_id}:
                raise OrchestrationConflictError(
                    "Approval orchestration belongs to another execution"
                )
            task.n8n_execution_id = execution_id
            task.orchestration_status = "COMPLETED"
            task.orchestration_completed_at = task.orchestration_completed_at or now
            session.flush()
            return self._task_state(task, expense, reveal_resume=False)

    def pending(self) -> list[dict]:
        with self.database.session() as session:
            rows = session.execute(
                select(ApprovalTask, Expense)
                .join(Expense, Expense.expense_id == ApprovalTask.expense_id)
                .where(ApprovalTask.status == "PENDING")
                .order_by(ApprovalTask.due_at.asc())
            ).all()
            return [
                self._task_state(task, expense, reveal_resume=False)
                for task, expense in rows
            ]

    def reserve_notification(
        self,
        task_id: str,
        notification_type: str,
        *,
        escalation_level: int = 0,
    ) -> dict:
        now = utc_now()
        with self.database.transaction() as session:
            task, expense = self._task_and_expense(
                session, task_id, for_update=True
            )
            existing = session.scalar(
                select(ApprovalNotification).where(
                    ApprovalNotification.approval_task_id == task_id,
                    ApprovalNotification.notification_type == notification_type,
                    ApprovalNotification.escalation_level == escalation_level,
                )
            )
            if existing is not None:
                return self._notification_state(existing)
            payload = {
                "expense_id": expense.expense_id,
                "approver_role": task.approver_role,
                "risk_level": expense.risk_level,
                "due_at": (
                    ensure_utc(task.due_at).isoformat() if task.due_at else None
                ),
                "safe_summary": self._task_state(
                    task, expense, reveal_resume=False
                )["safe_summary"],
            }
            notification = ApprovalNotification(
                notification_id=str(uuid4()),
                approval_task_id=task_id,
                notification_type=notification_type,
                escalation_level=escalation_level,
                status="PENDING",
                target_role=task.approver_role,
                payload=payload,
                created_at=now,
            )
            session.add(notification)
            try:
                session.flush()
            except IntegrityError:
                raise
            return self._notification_state(notification)

    def reserve_sla_notifications(self, *, now: datetime | None = None) -> list[dict]:
        current = ensure_utc(now) or utc_now()
        pending = self.pending()
        notifications: list[dict] = []
        for state in pending:
            if state["due_at"] is None:
                continue
            notification_type, level = self.sla.stage(
                state["created_at"], state["due_at"], current
            )
            if notification_type is None:
                continue
            notification = self.reserve_notification(
                state["task_id"], notification_type, escalation_level=level
            )
            if notification["status"] == "PENDING":
                notifications.append(notification)
        return notifications

    def mark_notification_sent(
        self, notification_id: str, provider_message_id: str | None = None
    ) -> dict:
        now = utc_now()
        with self.database.transaction() as session:
            notification = session.scalar(
                select(ApprovalNotification)
                .where(ApprovalNotification.notification_id == notification_id)
                .with_for_update()
            )
            if notification is None:
                raise ApprovalTaskNotFoundError("Approval notification not found")
            if notification.status == "SENT":
                return self._notification_state(notification)
            notification.status = "SENT"
            notification.sent_at = now
            notification.provider_message_id = provider_message_id
            task = session.get(ApprovalTask, notification.approval_task_id)
            assert task is not None
            task.last_notification_at = now
            if notification.notification_type == "REMINDER":
                task.reminder_count += 1
            if notification.notification_type == "ESCALATION":
                task.escalation_level = max(
                    task.escalation_level, notification.escalation_level
                )
            session.flush()
            return self._notification_state(notification)
