"""Transactional outbox, lease, DLQ, reconciliation, and incident persistence."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select

from app.db.base import ensure_utc, utc_now
from app.db.models import (
    ApprovalNotification,
    ApprovalTask,
    OutboxDeliveryAttempt,
    OutboxEvent,
    WorkflowFailure,
    WorkflowRun,
)
from app.db.session import Database
from app.reliability import ReliabilityPolicy


class OutboxNotFoundError(Exception):
    pass


class OutboxConflictError(Exception):
    pass


class OutboxRepository:
    EVENT_RESUME = "APPROVAL_RESUME_REQUIRED"
    EVENT_NOTIFICATION = "NOTIFICATION_DELIVERY_REQUIRED"

    def __init__(self, database: Database) -> None:
        self.database = database
        self.policy = ReliabilityPolicy()

    @staticmethod
    def ensure_event(
        session,
        *,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        delivery_key: str,
        payload: dict,
        correlation_id: str | None,
        now: datetime | None = None,
        max_attempts: int | None = None,
    ) -> OutboxEvent:
        existing = session.scalar(select(OutboxEvent).where(OutboxEvent.delivery_key == delivery_key))
        if existing is not None:
            return existing
        current = ensure_utc(now) or utc_now()
        event = OutboxEvent(
            outbox_event_id=str(uuid4()),
            event_type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            correlation_id=correlation_id,
            delivery_key=delivery_key,
            payload=payload,
            status="PENDING",
            attempt_count=0,
            max_attempts=max_attempts or ReliabilityPolicy().max_attempts,
            next_attempt_at=current,
            created_at=current,
            updated_at=current,
        )
        session.add(event)
        session.flush()
        return event

    @staticmethod
    def _state(event: OutboxEvent, *, include_attempts: bool = False, attempts=()) -> dict:
        state = {
            "outbox_event_id": event.outbox_event_id,
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": event.aggregate_id,
            "correlation_id": event.correlation_id,
            "delivery_key": event.delivery_key,
            "payload": event.payload,
            "status": event.status,
            "attempt_count": event.attempt_count,
            "max_attempts": event.max_attempts,
            "next_attempt_at": event.next_attempt_at,
            "lease_owner": event.lease_owner,
            "lease_acquired_at": event.lease_acquired_at,
            "lease_expires_at": event.lease_expires_at,
            "last_error_category": event.last_error_category,
            "last_error_message": event.last_error_message,
            "created_at": event.created_at,
            "delivered_at": event.delivered_at,
            "dead_lettered_at": event.dead_lettered_at,
            "replay_count": event.replay_count,
            "updated_at": event.updated_at,
        }
        if include_attempts:
            state["attempts"] = [OutboxRepository._attempt_state(item) for item in attempts]
        return state

    @staticmethod
    def _attempt_state(attempt: OutboxDeliveryAttempt) -> dict:
        return {column.name: getattr(attempt, column.name) for column in OutboxDeliveryAttempt.__table__.columns}

    def get(self, event_id: str, *, include_attempts: bool = True) -> dict:
        with self.database.session() as session:
            event = session.get(OutboxEvent, event_id)
            if event is None:
                raise OutboxNotFoundError("Outbox event not found")
            attempts = session.scalars(
                select(OutboxDeliveryAttempt)
                .where(OutboxDeliveryAttempt.outbox_event_id == event_id)
                .order_by(OutboxDeliveryAttempt.attempt_number)
            ).all()
            return self._state(event, include_attempts=include_attempts, attempts=attempts)

    def get_by_delivery_key(self, delivery_key: str) -> dict:
        with self.database.session() as session:
            event = session.scalar(select(OutboxEvent).where(OutboxEvent.delivery_key == delivery_key))
            if event is None:
                raise OutboxNotFoundError("Outbox event not found")
            return self._state(event)

    def delivery_target(self, event_id: str) -> dict:
        with self.database.session() as session:
            event = session.get(OutboxEvent, event_id)
            if event is None:
                raise OutboxNotFoundError("Outbox event not found")
            if event.event_type == self.EVENT_RESUME:
                task = session.get(ApprovalTask, event.payload["approval_task_id"])
                if task is None:
                    raise OutboxNotFoundError("Approval task not found")
                return {
                    "event_type": event.event_type,
                    "approval_task_id": task.task_id,
                    "expense_id": task.expense_id,
                    "already_completed": task.orchestration_status == "COMPLETED",
                    "resume_url": task.n8n_wait_resume_url if task.orchestration_status == "WAITING" else None,
                }
            if event.event_type == self.EVENT_NOTIFICATION:
                notification = session.get(ApprovalNotification, event.payload["notification_id"])
                if notification is None:
                    raise OutboxNotFoundError("Approval notification not found")
                return {
                    "event_type": event.event_type,
                    "notification_id": notification.notification_id,
                    "already_completed": notification.status == "SENT",
                }
            raise OutboxConflictError("Unsupported outbox event type")

    def claim_due(self, worker_id: str, limit: int, lease_seconds: int | None = None, *, now: datetime | None = None) -> list[dict]:
        current = ensure_utc(now) or utc_now()
        duration = lease_seconds or self.policy.lease_seconds
        eligible = or_(
            and_(OutboxEvent.status == "PENDING", OutboxEvent.next_attempt_at <= current),
            and_(OutboxEvent.status == "IN_FLIGHT", OutboxEvent.lease_expires_at <= current),
        )
        with self.database.transaction() as session:
            statement = select(OutboxEvent).where(eligible).order_by(OutboxEvent.next_attempt_at, OutboxEvent.created_at).limit(limit)
            if self.database.engine.dialect.name == "postgresql":
                statement = statement.with_for_update(skip_locked=True)
            else:
                statement = statement.with_for_update()
            events = session.scalars(statement).all()
            expires = current + timedelta(seconds=duration)
            for event in events:
                event.status = "IN_FLIGHT"
                event.lease_owner = worker_id
                event.lease_acquired_at = current
                event.lease_expires_at = expires
                event.updated_at = current
            session.flush()
            return [self._state(event) for event in events]

    def claim_one(self, event_id: str, worker_id: str, lease_seconds: int | None = None, *, now: datetime | None = None) -> dict:
        current = ensure_utc(now) or utc_now()
        duration = lease_seconds or self.policy.lease_seconds
        with self.database.transaction() as session:
            event = session.scalar(select(OutboxEvent).where(OutboxEvent.outbox_event_id == event_id).with_for_update())
            if event is None:
                raise OutboxNotFoundError("Outbox event not found")
            eligible = (
                (event.status == "PENDING" and ensure_utc(event.next_attempt_at) <= current)
                or (event.status == "IN_FLIGHT" and ensure_utc(event.lease_expires_at) <= current)
            )
            if not eligible:
                raise OutboxConflictError("Outbox event is not currently claimable")
            event.status = "IN_FLIGHT"
            event.lease_owner = worker_id
            event.lease_acquired_at = current
            event.lease_expires_at = current + timedelta(seconds=duration)
            event.updated_at = current
            session.flush()
            return self._state(event)

    def _locked(self, session, event_id: str, worker_id: str) -> OutboxEvent:
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.outbox_event_id == event_id).with_for_update())
        if event is None:
            raise OutboxNotFoundError("Outbox event not found")
        if event.status != "IN_FLIGHT" or event.lease_owner != worker_id:
            raise OutboxConflictError("Outbox event is not leased by this worker")
        return event

    def _append_attempt(self, session, event: OutboxEvent, worker_id: str, outcome: str, *, status_code: int | None, category: str | None, message: str | None, now: datetime) -> None:
        attempt_number = (session.scalar(select(func.max(OutboxDeliveryAttempt.attempt_number)).where(OutboxDeliveryAttempt.outbox_event_id == event.outbox_event_id)) or 0) + 1
        session.add(OutboxDeliveryAttempt(
            attempt_id=str(uuid4()), outbox_event_id=event.outbox_event_id,
            attempt_number=attempt_number, worker_id=worker_id,
            started_at=event.lease_acquired_at or now, completed_at=now,
            outcome=outcome, status_code=status_code, error_category=category,
            safe_error_message=message, created_at=now,
        ))
        event.attempt_count += 1

    @staticmethod
    def _clear_lease(event: OutboxEvent) -> None:
        event.lease_owner = None
        event.lease_acquired_at = None
        event.lease_expires_at = None

    def success(self, event_id: str, worker_id: str, *, status_code: int | None = None, now: datetime | None = None) -> dict:
        current = ensure_utc(now) or utc_now()
        with self.database.transaction() as session:
            event = self._locked(session, event_id, worker_id)
            self._append_attempt(session, event, worker_id, "SUCCESS", status_code=status_code, category=None, message=None, now=current)
            event.status = "DELIVERED"
            event.delivered_at = current
            event.dead_lettered_at = None
            event.last_error_category = None
            event.last_error_message = None
            event.updated_at = current
            self._clear_lease(event)
            session.flush()
            return self._state(event)

    def failure(self, event_id: str, worker_id: str, *, status_code: int | None = None, error_category: str | None = None, error_message: str | None = None, now: datetime | None = None) -> dict:
        current = ensure_utc(now) or utc_now()
        classification = self.policy.classify(status_code, error_category, error_message)
        with self.database.transaction() as session:
            event = self._locked(session, event_id, worker_id)
            self._append_attempt(session, event, worker_id, classification.outcome, status_code=status_code, category=classification.category, message=classification.safe_message, now=current)
            event.last_error_category = classification.category
            event.last_error_message = classification.safe_message
            event.updated_at = current
            exhausted = event.attempt_count >= event.max_attempts
            if classification.outcome == "PERMANENT_FAILURE" or exhausted:
                event.status = "DEAD_LETTER"
                event.dead_lettered_at = current
            else:
                event.status = "PENDING"
                event.next_attempt_at = self.policy.next_attempt_at(event.attempt_count, current)
            self._clear_lease(event)
            session.flush()
            return self._state(event)

    def dead_letters(self) -> list[dict]:
        with self.database.session() as session:
            events = session.scalars(select(OutboxEvent).where(OutboxEvent.status == "DEAD_LETTER").order_by(OutboxEvent.dead_lettered_at.desc())).all()
            return [self._state(event) for event in events]

    def replay(self, event_id: str, *, now: datetime | None = None) -> dict:
        current = ensure_utc(now) or utc_now()
        with self.database.transaction() as session:
            event = session.scalar(select(OutboxEvent).where(OutboxEvent.outbox_event_id == event_id).with_for_update())
            if event is None:
                raise OutboxNotFoundError("Outbox event not found")
            if event.status != "DEAD_LETTER":
                raise OutboxConflictError("Only dead-letter events may be replayed")
            event.status = "PENDING"
            event.attempt_count = 0
            event.next_attempt_at = current
            event.dead_lettered_at = None
            event.replay_count += 1
            event.updated_at = current
            self._clear_lease(event)
            session.flush()
            return self._state(event)

    def reconcile(self) -> dict[str, int]:
        created_resume = 0
        created_notification = 0
        with self.database.transaction() as session:
            tasks = session.scalars(select(ApprovalTask).where(ApprovalTask.status.in_(("APPROVED", "REJECTED", "CANCELLED")), ApprovalTask.orchestration_status != "COMPLETED")).all()
            for task in tasks:
                key = f"approval-resume:{task.task_id}"
                if session.scalar(select(OutboxEvent.outbox_event_id).where(OutboxEvent.delivery_key == key)) is None:
                    run = session.get(WorkflowRun, task.workflow_run_id)
                    self.ensure_event(session, event_type=self.EVENT_RESUME, aggregate_type="approval_task", aggregate_id=task.task_id, delivery_key=key, payload={"approval_task_id": task.task_id, "expense_id": task.expense_id}, correlation_id=run.correlation_id if run else None)
                    created_resume += 1
            notifications = session.scalars(select(ApprovalNotification).where(ApprovalNotification.status != "SENT")).all()
            for notification in notifications:
                key = f"notification:{notification.notification_id}"
                if session.scalar(select(OutboxEvent.outbox_event_id).where(OutboxEvent.delivery_key == key)) is None:
                    task = session.get(ApprovalTask, notification.approval_task_id)
                    run = session.get(WorkflowRun, task.workflow_run_id) if task else None
                    self.ensure_event(session, event_type=self.EVENT_NOTIFICATION, aggregate_type="approval_notification", aggregate_id=notification.notification_id, delivery_key=key, payload={"notification_id": notification.notification_id}, correlation_id=run.correlation_id if run else None)
                    created_notification += 1
        return {"resume_events_created": created_resume, "notification_events_created": created_notification}

    def record_workflow_failure(self, data: dict) -> dict:
        now = utc_now()
        safe = self.policy.sanitize(data.get("safe_message"))
        with self.database.transaction() as session:
            failure = session.scalar(select(WorkflowFailure).where(WorkflowFailure.workflow_id == data["workflow_id"], WorkflowFailure.execution_id == data["execution_id"]).with_for_update())
            if failure is None:
                failure = WorkflowFailure(failure_id=str(uuid4()), workflow_id=data["workflow_id"], workflow_name=data["workflow_name"], execution_id=data["execution_id"], failed_node=data.get("failed_node"), error_class=data.get("error_class"), safe_message=safe, correlation_id=data.get("correlation_id"), expense_id=data.get("expense_id"), first_seen_at=now, last_seen_at=now, occurrence_count=1, status="OPEN")
                session.add(failure)
            else:
                failure.last_seen_at = now
                failure.occurrence_count += 1
                failure.safe_message = safe
            session.flush()
            return {column.name: getattr(failure, column.name) for column in WorkflowFailure.__table__.columns}

    def workflow_failures(self, status: str | None = None) -> list[dict]:
        with self.database.session() as session:
            statement = select(WorkflowFailure).order_by(WorkflowFailure.last_seen_at.desc())
            if status:
                statement = statement.where(WorkflowFailure.status == status)
            return [
                {column.name: getattr(failure, column.name) for column in WorkflowFailure.__table__.columns}
                for failure in session.scalars(statement).all()
            ]
