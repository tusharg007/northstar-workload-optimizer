"""
North Star Workload Optimizer — Automation Flow
=================================================
Simulates a Power Automate expense approval workflow in Python.

Pipeline: Trigger → Validate → Detect Anomalies → Route → Notify

Each component maps directly to a Power Automate action, documented
in flow_design.md alongside the TO-BE process diagram.

Author : North Star Analytics Team
Version: 1.0.0
"""

import json
import csv
import os
import sys
import logging
from datetime import datetime, date
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from automation.policy_manifest import (
    APPROVAL_TIERS,
    CATEGORY_LIMITS,
    DESCRIPTION_MINIMUM_CHARACTERS,
    DESCRIPTION_REQUIRED_ABOVE,
    RECEIPT_REQUIRED_ABOVE,
    REVIEW_REQUIRED_ABOVE,
)

# ── Logging Setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)]
)
log = logging.getLogger("automation_flow")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)


# ══════════════════════════════════════════════════════════════════
#  DATA MODELS (Pydantic Validation)
#  Maps to: Power Automate → "Parse JSON" action
# ══════════════════════════════════════════════════════════════════

class ExpenseSubmission(BaseModel):
    """Validated expense submission record."""
    expense_id: str = Field(..., min_length=1, description="Unique expense identifier")
    employee_id: str = Field(..., min_length=1, description="Employee identifier")
    employee_name: str = Field(..., min_length=1, description="Full employee name")
    department: str = Field(..., description="Department name")
    transaction_date: str = Field(..., description="Date of transaction (YYYY-MM-DD)")
    merchant: str = Field(..., min_length=1, description="Merchant/vendor name")
    category: str = Field(..., description="Expense category")
    description: str = Field(default="", description="Business purpose")
    amount: float = Field(..., gt=0, description="Expense amount (must be positive)")
    currency: str = Field(default="USD", description="Currency code")
    payment_method: str = Field(default="Corporate Card", description="Payment method used")
    receipt_attached: bool = Field(default=False, description="Whether receipt is attached")

    @field_validator("transaction_date")
    @classmethod
    def validate_date_format(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError(f"Invalid date format: {v}. Expected YYYY-MM-DD")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        valid = [
            "Travel", "Meals & Entertainment", "Office Supplies",
            "Software & Subscriptions", "Training & Development",
            "Client Entertainment", "Transportation", "Telecommunications",
            "Equipment", "Miscellaneous"
        ]
        if v not in valid:
            raise ValueError(f"Invalid category: {v}")
        return v

    @field_validator("department")
    @classmethod
    def validate_department(cls, v):
        valid = ["Sales", "IT", "Marketing", "Finance", "HR", "Operations"]
        if v not in valid:
            raise ValueError(f"Invalid department: {v}")
        return v


class ValidationResult(BaseModel):
    """Result of field-level validation."""
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    policy_evaluations: list[dict] = Field(default_factory=list, exclude=True)


class AnomalyResult(BaseModel):
    """Result of anomaly detection."""
    is_anomalous: bool
    confidence_score: float = Field(ge=0, le=1)
    flags: list[str] = []
    risk_level: str = "LOW"  # LOW, MEDIUM, HIGH, CRITICAL
    risk_evaluations: list[dict] = Field(default_factory=list, exclude=True)


class ApprovalDecision(BaseModel):
    """Approval routing decision."""
    approver_role: str
    approver_level: int
    auto_approved: bool = False
    requires_review: bool = False
    reason: str = ""
    policy_evaluations: list[dict] = Field(default_factory=list, exclude=True)


class NotificationPayload(BaseModel):
    """Formatted notification payload (simulates Teams/Outlook message)."""
    notification_id: str
    timestamp: str
    channel: str  # "teams", "email", "both"
    recipient: str
    subject: str
    body: str
    priority: str  # "low", "normal", "high", "urgent"
    action_required: bool
    expense_summary: dict
    metadata: dict


# ══════════════════════════════════════════════════════════════════
#  STEP 1: TRIGGER
#  Maps to: Power Automate → "When a new item is created"
#           (SharePoint list / Microsoft Forms / Email attachment)
# ══════════════════════════════════════════════════════════════════

class ExpenseTrigger:
    """Monitors for new expense submissions (simulates email/form trigger)."""

    def __init__(self, source_path: str = None):
        self.source_path = source_path
        self.processed_count = 0

    def poll_new_submissions(self, csv_path: str = None) -> list[dict]:
        """Read new expense submissions from a CSV file (simulates trigger)."""
        path = csv_path or self.source_path
        if not path or not os.path.exists(path):
            log.warning(f"TRIGGER | No source file found: {path}")
            return []

        submissions = []
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                submissions.append(row)

        log.info(f"TRIGGER | Detected {len(submissions)} new expense submission(s)")
        self.processed_count += len(submissions)
        return submissions

    def simulate_single_submission(self, record: dict) -> dict:
        """Simulate receiving a single expense submission."""
        log.info(f"TRIGGER | New submission received: {record.get('expense_id', 'UNKNOWN')}")
        return record


# ══════════════════════════════════════════════════════════════════
#  STEP 2: VALIDATE
#  Maps to: Power Automate → "Condition" + "Parse JSON" actions
# ══════════════════════════════════════════════════════════════════

class ExpenseValidator:
    """Validates expense submissions against business rules."""

    AMOUNT_LIMITS = CATEGORY_LIMITS

    def validate(self, record: dict) -> tuple[Optional[ExpenseSubmission], ValidationResult]:
        """Validate a single expense record."""
        errors = []
        warnings = []
        evaluations = []

        # Step 1: Pydantic structural validation
        try:
            expense = ExpenseSubmission(**record)
        except Exception as e:
            error_msg = str(e)
            log.error(f"VALIDATE | Structural validation failed: {error_msg[:100]}")
            return None, ValidationResult(is_valid=False, errors=[error_msg])

        # Step 2: Business rule validation
        # Check amount against category limit
        limit = self.AMOUNT_LIMITS.get(expense.category, 1000)
        category_triggered = expense.amount > limit
        if category_triggered:
            warnings.append(
                f"Amount ${expense.amount:.2f} exceeds category limit "
                f"${limit:.2f} for '{expense.category}'"
            )
        evaluations.append({
            "rule_key": "CATEGORY_SPENDING_LIMITS",
            "evaluation_status": "TRIGGERED" if category_triggered else "PASSED",
            "triggered": category_triggered,
            "observed_value": {"category": expense.category, "amount": expense.amount, "limit": limit},
            "evaluation_details": {"effect": "WARNING"},
        })

        # Check receipt requirement for amounts > $75
        receipt_triggered = expense.amount > RECEIPT_REQUIRED_ABOVE and not expense.receipt_attached
        if receipt_triggered:
            warnings.append(
                f"Receipt required for expenses > $75 (amount: ${expense.amount:.2f})"
            )
        evaluations.append({
            "rule_key": "RECEIPT_REQUIRED_THRESHOLD",
            "evaluation_status": "TRIGGERED" if receipt_triggered else "PASSED",
            "triggered": receipt_triggered,
            "observed_value": {"amount": expense.amount, "receipt_attached": expense.receipt_attached},
            "evaluation_details": {"threshold": RECEIPT_REQUIRED_ABOVE, "effect": "WARNING"},
        })

        # Check future dates
        try:
            txn_date = datetime.strptime(expense.transaction_date, "%Y-%m-%d").date()
            future_triggered = txn_date > date.today()
            if future_triggered:
                errors.append(f"Transaction date {expense.transaction_date} is in the future")
        except ValueError:
            future_triggered = False
        evaluations.append({
            "rule_key": "FUTURE_TRANSACTION_DATE_REJECTED",
            "evaluation_status": "FAILED" if future_triggered else "PASSED",
            "triggered": future_triggered,
            "observed_value": {"transaction_date": expense.transaction_date, "processing_date": date.today().isoformat()},
            "evaluation_details": {"effect": "ERROR"},
        })

        # Check description requirement for amounts > $500
        description_triggered = (
            expense.amount > DESCRIPTION_REQUIRED_ABOVE
            and len(expense.description.strip()) < DESCRIPTION_MINIMUM_CHARACTERS
        )
        if description_triggered:
            warnings.append("Detailed description required for expenses > $500")
        evaluations.append({
            "rule_key": "DESCRIPTION_REQUIRED_THRESHOLD",
            "evaluation_status": "TRIGGERED" if description_triggered else "PASSED",
            "triggered": description_triggered,
            "observed_value": {"amount": expense.amount, "trimmed_characters": len(expense.description.strip())},
            "evaluation_details": {"effect": "WARNING"},
        })

        is_valid = len(errors) == 0
        result = ValidationResult(is_valid=is_valid, errors=errors, warnings=warnings)
        result.policy_evaluations = evaluations

        status = "PASS" if is_valid else "FAIL"
        log.info(
            f"VALIDATE | {expense.expense_id}: {status} "
            f"({len(errors)} errors, {len(warnings)} warnings)"
        )
        return expense, result


# ══════════════════════════════════════════════════════════════════
#  STEP 3: ANOMALY DETECTION
#  Maps to: Power Automate → "Condition" + Azure AI / Custom Logic
# ══════════════════════════════════════════════════════════════════

class AnomalyDetector:
    """Rule-based anomaly detection engine."""

    def __init__(self):
        self.category_stats = {
            "Travel":                 {"mean": 400, "std": 600},
            "Meals & Entertainment":  {"mean": 55,  "std": 45},
            "Office Supplies":        {"mean": 30,  "std": 25},
            "Software & Subscriptions": {"mean": 90, "std": 120},
            "Training & Development": {"mean": 310, "std": 280},
            "Client Entertainment":   {"mean": 175, "std": 200},
            "Transportation":         {"mean": 42,  "std": 35},
            "Telecommunications":     {"mean": 53,  "std": 30},
            "Equipment":              {"mean": 300, "std": 500},
            "Miscellaneous":          {"mean": 48,  "std": 60},
        }

    def detect(self, expense: ExpenseSubmission) -> AnomalyResult:
        """Run anomaly detection rules on an expense."""
        flags = []
        risk_score = 0.0
        evaluations = []

        # Rule 1: Statistical outlier (z-score > 2.5)
        stats = self.category_stats.get(expense.category, {"mean": 100, "std": 100})
        z_score = None
        outlier_triggered = False
        if stats["std"] > 0:
            z_score = (expense.amount - stats["mean"]) / stats["std"]
            outlier_triggered = abs(z_score) > 2.5
            if outlier_triggered:
                flags.append(f"STATISTICAL_OUTLIER (z={z_score:.2f})")
                risk_score += 0.3
        evaluations.append({"signal_key": "STATISTICAL_OUTLIER", "triggered": outlier_triggered,
            "observed_value": {"z_score": round(z_score, 6) if z_score is not None else None, "category_mean": stats["mean"], "category_std": stats["std"]},
            "threshold_or_reference": {"absolute_z_score_greater_than": 2.5}, "details": {"risk_score_increment": 0.3 if outlier_triggered else 0}})

        # Rule 2: Weekend transaction
        try:
            txn_date = datetime.strptime(expense.transaction_date, "%Y-%m-%d")
            weekend_triggered = txn_date.weekday() >= 5
            if weekend_triggered:
                flags.append("WEEKEND_TRANSACTION")
                risk_score += 0.15
        except ValueError:
            weekend_triggered = False
        evaluations.append({"signal_key": "WEEKEND_TRANSACTION", "triggered": weekend_triggered,
            "observed_value": {"weekday_index": txn_date.weekday() if 'txn_date' in locals() else None},
            "threshold_or_reference": {"weekday_index_at_least": 5}, "details": {"risk_score_increment": 0.15 if weekend_triggered else 0}})

        # Rule 3: Round amount (suspicious if > $500 and perfectly round)
        round_triggered = expense.amount > 500 and expense.amount % 100 == 0
        if round_triggered:
            flags.append(f"SUSPICIOUS_ROUND_AMOUNT (${expense.amount:.0f})")
            risk_score += 0.2
        evaluations.append({"signal_key": "SUSPICIOUS_ROUND_AMOUNT", "triggered": round_triggered,
            "observed_value": {"amount": expense.amount, "remainder": expense.amount % 100},
            "threshold_or_reference": {"amount_greater_than": 500, "multiple_of": 100}, "details": {"risk_score_increment": 0.2 if round_triggered else 0}})

        # Rule 4: Missing receipt for high value
        missing_receipt_triggered = not expense.receipt_attached and expense.amount > 200
        if missing_receipt_triggered:
            flags.append(f"MISSING_RECEIPT_HIGH_VALUE (${expense.amount:.2f})")
            risk_score += 0.25
        evaluations.append({"signal_key": "MISSING_RECEIPT_HIGH_VALUE", "triggered": missing_receipt_triggered,
            "observed_value": {"amount": expense.amount, "receipt_attached": expense.receipt_attached},
            "threshold_or_reference": {"amount_greater_than": 200, "receipt_attached": False}, "details": {"risk_score_increment": 0.25 if missing_receipt_triggered else 0}})

        # Rule 5: Duplicate pattern check (simplified — in production, check DB)
        duplicate_triggered = "DUPLICATE" in expense.description.upper()
        if duplicate_triggered:
            flags.append("POTENTIAL_DUPLICATE")
            risk_score += 0.35
        evaluations.append({"signal_key": "POTENTIAL_DUPLICATE", "triggered": duplicate_triggered,
            "observed_value": {"marker_detected": duplicate_triggered},
            "threshold_or_reference": {"description_contains": "DUPLICATE"}, "details": {"risk_score_increment": 0.35 if duplicate_triggered else 0}})

        # Determine risk level
        confidence = max(0.1, min(1.0, 1 - risk_score))
        if risk_score >= 0.6:
            risk_level = "CRITICAL"
        elif risk_score >= 0.4:
            risk_level = "HIGH"
        elif risk_score >= 0.2:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        is_anomalous = risk_score >= 0.2
        result = AnomalyResult(
            is_anomalous=is_anomalous,
            confidence_score=round(confidence, 3),
            flags=flags,
            risk_level=risk_level
        )
        evaluations.append({"signal_key": "RISK_SCORE_CLASSIFICATION", "triggered": False,
            "observed_value": {"risk_score": round(risk_score, 6), "risk_level": risk_level},
            "threshold_or_reference": {"medium_at": 0.2, "high_at": 0.4, "critical_at": 0.6}, "details": {}})
        result.risk_evaluations = evaluations

        if is_anomalous:
            log.warning(
                f"ANOMALY  | {expense.expense_id}: {risk_level} risk "
                f"(score={risk_score:.2f}, flags={flags})"
            )
        else:
            log.info(f"ANOMALY  | {expense.expense_id}: CLEAR (score={risk_score:.2f})")

        return result


# ══════════════════════════════════════════════════════════════════
#  STEP 4: APPROVAL ROUTING
#  Maps to: Power Automate → "Start and wait for an approval"
# ══════════════════════════════════════════════════════════════════

class ApprovalRouter:
    """Routes expenses to appropriate approvers based on amount and risk."""

    THRESHOLDS = [
        {**tier, "max_amount": tier["maximum_amount"] if tier["maximum_amount"] is not None else float("inf")}
        for tier in APPROVAL_TIERS
    ]

    def route(self, expense: ExpenseSubmission, anomaly: AnomalyResult) -> ApprovalDecision:
        """Determine the approval path for an expense."""

        # Find base routing tier
        for tier in self.THRESHOLDS:
            if expense.amount <= tier["max_amount"]:
                role = tier["role"]
                level = tier["level"]
                auto = tier["auto_approve"]
                break

        # Escalate if anomalous
        if anomaly.is_anomalous:
            if anomaly.risk_level in ("HIGH", "CRITICAL"):
                role = "Finance Director + Compliance"
                level = max(level, 3)
                auto = False
            elif anomaly.risk_level == "MEDIUM":
                auto = False  # Disable auto-approval

        requires_review = anomaly.is_anomalous or expense.amount > 2000

        reason = f"Amount: ${expense.amount:.2f} → {role}"
        if anomaly.is_anomalous:
            reason += f" [ESCALATED: {anomaly.risk_level} risk]"
        if auto:
            reason += " [AUTO-APPROVED]"

        decision = ApprovalDecision(
            approver_role=role,
            approver_level=level,
            auto_approved=auto and not anomaly.is_anomalous,
            requires_review=requires_review,
            reason=reason
        )
        decision.policy_evaluations = [
            {"rule_key": "AMOUNT_APPROVAL_TIERS", "evaluation_status": "TRIGGERED", "triggered": True,
             "observed_value": {"amount": expense.amount, "selected_role": role, "selected_level": level}, "evaluation_details": {}},
            {"rule_key": "HIGH_RISK_ESCALATION_ROUTE", "evaluation_status": "TRIGGERED" if anomaly.risk_level in ("HIGH", "CRITICAL") else "NOT_APPLICABLE", "triggered": anomaly.risk_level in ("HIGH", "CRITICAL"),
             "observed_value": {"risk_level": anomaly.risk_level}, "evaluation_details": {}},
            {"rule_key": "MEDIUM_RISK_REQUIRES_HUMAN", "evaluation_status": "TRIGGERED" if anomaly.risk_level == "MEDIUM" else "NOT_APPLICABLE", "triggered": anomaly.risk_level == "MEDIUM",
             "observed_value": {"risk_level": anomaly.risk_level}, "evaluation_details": {}},
            {"rule_key": "REVIEW_REQUIRED_THRESHOLD", "evaluation_status": "TRIGGERED" if requires_review else "PASSED", "triggered": requires_review,
             "observed_value": {"is_anomalous": anomaly.is_anomalous, "amount": expense.amount}, "evaluation_details": {"amount_threshold": REVIEW_REQUIRED_ABOVE}},
        ]

        log.info(f"ROUTE    | {expense.expense_id}: -> {role} (Level {level}, Auto: {decision.auto_approved})")
        return decision


# ══════════════════════════════════════════════════════════════════
#  STEP 5: NOTIFICATION ENGINE
#  Maps to: Power Automate → "Post message in Teams" / "Send email"
# ══════════════════════════════════════════════════════════════════

class NotificationEngine:
    """Generates formatted notification payloads for Teams/Outlook."""

    def __init__(self):
        self.notification_count = 0

    def generate_notification(
        self,
        expense: ExpenseSubmission,
        validation: ValidationResult,
        anomaly: AnomalyResult,
        decision: ApprovalDecision
    ) -> NotificationPayload:
        """Generate a Teams/Outlook notification payload."""
        self.notification_count += 1
        notif_id = f"NOTIF-{self.notification_count:04d}"

        # Determine priority
        if anomaly.risk_level == "CRITICAL":
            priority = "urgent"
            channel = "both"
        elif anomaly.risk_level == "HIGH":
            priority = "high"
            channel = "both"
        elif decision.requires_review:
            priority = "normal"
            channel = "teams"
        else:
            priority = "low"
            channel = "email"

        # Build subject
        if decision.auto_approved:
            subject = f"✅ Auto-Approved: {expense.category} - ${expense.amount:.2f}"
        elif anomaly.is_anomalous:
            subject = f"⚠️ Review Required: {expense.category} - ${expense.amount:.2f} [{anomaly.risk_level}]"
        else:
            subject = f"📋 Approval Needed: {expense.category} - ${expense.amount:.2f}"

        # Build body
        body_lines = [
            f"Expense ID: {expense.expense_id}",
            f"Submitted by: {expense.employee_name} ({expense.department})",
            f"Category: {expense.category}",
            f"Merchant: {expense.merchant}",
            f"Amount: ${expense.amount:.2f} {expense.currency}",
            f"Date: {expense.transaction_date}",
            f"Receipt: {'Attached' if expense.receipt_attached else 'Missing'}",
            f"",
            f"Routing: {decision.reason}",
        ]

        if validation.warnings:
            body_lines.append(f"\nWarnings:")
            for w in validation.warnings:
                body_lines.append(f"  - {w}")

        if anomaly.flags:
            body_lines.append(f"\nAnomaly Flags:")
            for f_item in anomaly.flags:
                body_lines.append(f"  - {f_item}")

        payload = NotificationPayload(
            notification_id=notif_id,
            timestamp=datetime.now().isoformat(),
            channel=channel,
            recipient=decision.approver_role,
            subject=subject,
            body="\n".join(body_lines),
            priority=priority,
            action_required=not decision.auto_approved,
            expense_summary={
                "expense_id": expense.expense_id,
                "employee": expense.employee_name,
                "department": expense.department,
                "amount": expense.amount,
                "category": expense.category,
                "risk_level": anomaly.risk_level,
                "auto_approved": decision.auto_approved,
            },
            metadata={
                "validation_status": "PASS" if validation.is_valid else "FAIL",
                "anomaly_detected": anomaly.is_anomalous,
                "confidence_score": anomaly.confidence_score,
                "approver_level": decision.approver_level,
            }
        )

        log.info(
            f"NOTIFY   | {notif_id}: {channel.upper()} -> {decision.approver_role} "
            f"[{priority.upper()}]"
        )
        return payload


# ══════════════════════════════════════════════════════════════════
#  PIPELINE ORCHESTRATOR
#  Maps to: Power Automate → Full flow with error handling
# ══════════════════════════════════════════════════════════════════

class AutomationPipeline:
    """Orchestrates the full expense approval automation flow."""

    def __init__(self):
        self.trigger = ExpenseTrigger()
        self.validator = ExpenseValidator()
        self.detector = AnomalyDetector()
        self.router = ApprovalRouter()
        self.notifier = NotificationEngine()
        self.results = []

    def process_single(self, record: dict) -> dict:
        """Process a single expense through the full pipeline."""
        expense_id = record.get("expense_id", "UNKNOWN")
        log.info(f"\n{'-' * 60}")
        log.info(f"PIPELINE | Processing {expense_id}")
        log.info(f"{'-' * 60}")

        result = {
            "expense_id": expense_id,
            "status": "PROCESSING",
            "validation": None,
            "anomaly": None,
            "decision": None,
            "notification": None,
        }

        # Step 1: Trigger acknowledgment
        self.trigger.simulate_single_submission(record)

        # Step 2: Validate
        expense, validation = self.validator.validate(record)
        validation_evaluations = getattr(validation, "policy_evaluations", [])
        result["validation"] = validation.model_dump()
        result["policy_evaluations"] = validation_evaluations

        if not validation.is_valid:
            result["status"] = "REJECTED_VALIDATION"
            log.error(f"PIPELINE | {expense_id}: REJECTED (validation failure)")
            self.results.append(result)
            return result

        # Step 3: Detect anomalies
        anomaly = self.detector.detect(expense)
        risk_evaluations = getattr(anomaly, "risk_evaluations", [])
        result["anomaly"] = anomaly.model_dump()
        result["risk_evaluations"] = risk_evaluations

        # Step 4: Route for approval
        decision = self.router.route(expense, anomaly)
        result["decision"] = decision.model_dump()
        result["policy_evaluations"].extend(getattr(decision, "policy_evaluations", []))

        # Step 5: Generate notification
        notification = self.notifier.generate_notification(
            expense, validation, anomaly, decision
        )
        result["notification"] = notification.model_dump()

        # Final status
        if decision.auto_approved:
            result["status"] = "AUTO_APPROVED"
        elif anomaly.risk_level in ("HIGH", "CRITICAL"):
            result["status"] = "ESCALATED"
        else:
            result["status"] = "PENDING_APPROVAL"

        log.info(f"PIPELINE | {expense_id}: Final status -> {result['status']}")
        self.results.append(result)
        return result

    def process_batch(self, csv_path: str) -> list[dict]:
        """Process a batch of expenses from CSV."""
        submissions = self.trigger.poll_new_submissions(csv_path)

        if not submissions:
            log.warning("PIPELINE | No submissions to process")
            return []

        log.info(f"\n{'=' * 60}")
        log.info(f"  NORTH STAR AUTOMATION PIPELINE - BATCH PROCESSING")
        log.info(f"  Records: {len(submissions)}")
        log.info(f"{'=' * 60}")

        for record in submissions:
            try:
                self.process_single(record)
            except Exception as e:
                log.error(f"PIPELINE | Error processing {record.get('expense_id', '?')}: {e}")
                self.results.append({
                    "expense_id": record.get("expense_id", "UNKNOWN"),
                    "status": "ERROR",
                    "error": str(e),
                })

        self._print_summary()
        return self.results

    def _print_summary(self):
        """Print pipeline execution summary."""
        total = len(self.results)
        auto_approved = sum(1 for r in self.results if r["status"] == "AUTO_APPROVED")
        pending = sum(1 for r in self.results if r["status"] == "PENDING_APPROVAL")
        escalated = sum(1 for r in self.results if r["status"] == "ESCALATED")
        rejected = sum(1 for r in self.results if r["status"] == "REJECTED_VALIDATION")
        errors = sum(1 for r in self.results if r["status"] == "ERROR")

        log.info(f"\n{'=' * 60}")
        log.info(f"  PIPELINE SUMMARY")
        log.info(f"{'=' * 60}")
        log.info(f"  Total processed   : {total}")
        log.info(f"  Auto-approved     : {auto_approved} ({auto_approved/max(total,1)*100:.0f}%)")
        log.info(f"  Pending approval  : {pending} ({pending/max(total,1)*100:.0f}%)")
        log.info(f"  Escalated         : {escalated} ({escalated/max(total,1)*100:.0f}%)")
        log.info(f"  Rejected          : {rejected} ({rejected/max(total,1)*100:.0f}%)")
        log.info(f"  Errors            : {errors}")
        log.info(f"  Notifications sent: {self.notifier.notification_count}")
        log.info(f"{'=' * 60}")


# ══════════════════════════════════════════════════════════════════
#  DEMO EXECUTION
# ══════════════════════════════════════════════════════════════════

def run_demo():
    """Run the automation pipeline with sample expense submissions."""
    pipeline = AutomationPipeline()

    # Sample submissions simulating various scenarios
    sample_expenses = [
        {
            "expense_id": "DEMO-001",
            "employee_id": "EMP-1001",
            "employee_name": "Sarah Chen",
            "department": "Sales",
            "transaction_date": "2026-03-15",
            "merchant": "Marriott Hotels",
            "category": "Travel",
            "description": "Client site visit — Q1 review meeting",
            "amount": "342.50",
            "currency": "USD",
            "payment_method": "Corporate Card",
            "receipt_attached": "True",
        },
        {
            "expense_id": "DEMO-002",
            "employee_id": "EMP-1015",
            "employee_name": "James Rodriguez",
            "department": "Marketing",
            "transaction_date": "2026-03-16",
            "merchant": "The Capital Grille",
            "category": "Client Entertainment",
            "description": "Prospect dinner — enterprise pipeline",
            "amount": "1850.00",
            "currency": "USD",
            "payment_method": "Corporate Card",
            "receipt_attached": "True",
        },
        {
            "expense_id": "DEMO-003",
            "employee_id": "EMP-1042",
            "employee_name": "Emily Watson",
            "department": "IT",
            "transaction_date": "2026-03-17",
            "merchant": "Amazon Business",
            "category": "Equipment",
            "description": "DUPLICATE — laptop docking station",
            "amount": "4500.00",
            "currency": "USD",
            "payment_method": "Personal Card",
            "receipt_attached": "False",
        },
        {
            "expense_id": "DEMO-004",
            "employee_id": "EMP-1078",
            "employee_name": "Michael Park",
            "department": "Finance",
            "transaction_date": "2026-03-18",
            "merchant": "Starbucks",
            "category": "Meals & Entertainment",
            "description": "Team coffee",
            "amount": "28.50",
            "currency": "USD",
            "payment_method": "Corporate Card",
            "receipt_attached": "True",
        },
        {
            "expense_id": "DEMO-005",
            "employee_id": "EMP-1090",
            "employee_name": "Lisa Thompson",
            "department": "HR",
            "transaction_date": "2026-03-22",  # Saturday
            "merchant": "Unknown Vendor",
            "category": "Miscellaneous",
            "description": "",
            "amount": "3000.00",
            "currency": "USD",
            "payment_method": "Cash",
            "receipt_attached": "False",
        },
    ]

    print("\n" + "=" * 60)
    print("  NORTH STAR WORKLOAD OPTIMIZER")
    print("  Automation Flow — Demo Execution")
    print("=" * 60)

    for record in sample_expenses:
        # Convert string booleans
        if isinstance(record.get("receipt_attached"), str):
            record["receipt_attached"] = record["receipt_attached"].lower() == "true"
        if isinstance(record.get("amount"), str):
            record["amount"] = float(record["amount"])

        pipeline.process_single(record)

    pipeline._print_summary()

    # Save results to JSON
    output_path = os.path.join(BASE_DIR, "demo_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pipeline.results, f, indent=2, default=str)

    print(f"\nResults saved to: {output_path}")
    print("Done.")


if __name__ == "__main__":
    run_demo()
