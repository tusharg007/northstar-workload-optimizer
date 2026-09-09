"""Validate the source-controlled North Star n8n workflow exports."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = PROJECT_DIR / "n8n" / "workflows"

EXPECTED_FILES = {
    "01_expense_intake.json",
    "02_approval_decision.json",
    "10_process_expense_service.json",
    "11_record_decision_service.json",
    "20_approval_orchestrator.json",
    "21_approval_notification_service.json",
    "22_approval_sla_monitor.json",
    "23_reliability_dispatcher.json",
    "24_dead_letter_replay.json",
    "25_executive_briefing_agent.json",
    "30_policy_copilot.json",
    "31_forensic_audit_agent.json",
    "99_global_error_handler.json",
}
PUBLIC_WEBHOOKS = {
    "northstar-expense": "POST",
    "northstar-approval": "POST",
    "northstar-policy-query": "POST",
    "northstar-forensic-audit": "POST",
}
ALLOWED_ENV_REFS: dict[str, set[str]] = {}
SUPPORTED_NODE_TYPES = {
    "n8n-nodes-base.executeWorkflow",
    "n8n-nodes-base.errorTrigger",
    "n8n-nodes-base.executeWorkflowTrigger",
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.if",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.set",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.splitOut",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.wait",
}
TRIGGER_TYPES = {
    "n8n-nodes-base.executeWorkflowTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.errorTrigger",
}
NON_EXECUTABLE_TYPES = {"n8n-nodes-base.stickyNote"}
FORBIDDEN_DB_NODE_MARKERS = (
    "postgres",
    "mysql",
    "microsoftsql",
    "mongo",
    "redis",
)
SECRET_PATTERN = re.compile(
    r"(?i)(?:api[_-]?key|client[_-]?secret|password|private[_-]?key)"
    r"\s*[:=]\s*['\"]?[A-Za-z0-9+/=_-]{8,}"
)


def load_workflows() -> tuple[dict[str, dict[str, Any]], list[str]]:
    """Load every JSON workflow and return parse errors without raising."""
    workflows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for path in sorted(WORKFLOW_DIR.glob("*.json")):
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: invalid JSON: {exc}")
            continue
        if not isinstance(workflow, dict):
            errors.append(f"{path.name}: root must be a JSON object")
            continue
        workflows[path.name] = workflow
    return workflows, errors


def _workflow_refs(workflow: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for node in workflow.get("nodes", []):
        if node.get("type") != "n8n-nodes-base.executeWorkflow":
            continue
        value = node.get("parameters", {}).get("workflowId")
        if isinstance(value, dict):
            value = value.get("value")
        if isinstance(value, str) and value:
            refs.append(value)
    return refs


def _reachable_node_names(workflow: dict[str, Any]) -> set[str]:
    nodes = workflow.get("nodes", [])
    starts = {
        node.get("name") for node in nodes if node.get("type") in TRIGGER_TYPES
    }
    adjacency: dict[str, set[str]] = {}
    for source, outputs in workflow.get("connections", {}).items():
        adjacency.setdefault(source, set())
        for branches in outputs.values():
            for branch in branches:
                for connection in branch or []:
                    target = connection.get("node")
                    if target:
                        adjacency[source].add(target)
    reached: set[str] = set()
    pending = [name for name in starts if isinstance(name, str)]
    while pending:
        name = pending.pop()
        if name in reached:
            continue
        reached.add(name)
        pending.extend(adjacency.get(name, set()) - reached)
    return reached


def validate_workflows(
    workflows: dict[str, dict[str, Any]],
) -> list[str]:
    """Return all source-control contract violations."""
    errors: list[str] = []
    filenames = set(workflows)
    if filenames != EXPECTED_FILES:
        errors.append(
            "workflow inventory differs: expected "
            f"{sorted(EXPECTED_FILES)}, found {sorted(filenames)}"
        )

    ids: dict[str, str] = {}
    names: dict[str, str] = {}
    webhook_owners: dict[tuple[str, str], str] = {}
    workflow_ids = {
        str(workflow.get("id")) for workflow in workflows.values() if workflow.get("id")
    }

    for filename, workflow in workflows.items():
        workflow_id = workflow.get("id")
        workflow_name = workflow.get("name")
        if not isinstance(workflow_id, str) or not workflow_id:
            errors.append(f"{filename}: missing stable workflow id")
        elif workflow_id in ids:
            errors.append(f"{filename}: duplicate workflow id {workflow_id!r}")
        else:
            ids[workflow_id] = filename
        if not isinstance(workflow_name, str) or not workflow_name:
            errors.append(f"{filename}: missing workflow name")
        elif workflow_name in names:
            errors.append(f"{filename}: duplicate workflow name {workflow_name!r}")
        else:
            names[workflow_name] = filename

        serialized = json.dumps(workflow, sort_keys=True)
        env_refs = set(re.findall(r"\$env\.([A-Z][A-Z0-9_]*)", serialized))
        unexpected_env_refs = env_refs - ALLOWED_ENV_REFS.get(filename, set())
        if unexpected_env_refs:
            errors.append(
                f"{filename}: forbidden environment references "
                f"{sorted(unexpected_env_refs)}"
            )
        if SECRET_PATTERN.search(serialized):
            errors.append(f"{filename}: possible hard-coded secret")

        nodes = workflow.get("nodes")
        if not isinstance(nodes, list) or not nodes:
            errors.append(f"{filename}: nodes must be a non-empty list")
            continue
        node_names = [node.get("name") for node in nodes]
        if len(node_names) != len(set(node_names)):
            errors.append(f"{filename}: node names must be unique")

        reached = _reachable_node_names(workflow)
        for node in nodes:
            node_name = node.get("name", "<unnamed>")
            node_type = str(node.get("type", ""))
            if node_type not in SUPPORTED_NODE_TYPES:
                errors.append(f"{filename}: unsupported node type {node_type!r}")
            lowered = node_type.lower()
            if any(marker in lowered for marker in FORBIDDEN_DB_NODE_MARKERS):
                errors.append(f"{filename}: operational database node is forbidden")
            if "credentials" in node:
                errors.append(f"{filename}: credentials are not allowed")
            if node_type not in NON_EXECUTABLE_TYPES and node_name not in reached:
                errors.append(f"{filename}: disconnected executable node {node_name!r}")
            if node_type == "n8n-nodes-base.webhook":
                params = node.get("parameters", {})
                path = params.get("path")
                method = str(params.get("httpMethod", "GET")).upper()
                key = (method, str(path))
                if key in webhook_owners:
                    errors.append(
                        f"{filename}: duplicate webhook {method} /{path} also in "
                        f"{webhook_owners[key]}"
                    )
                webhook_owners[key] = filename

        for referenced_id in _workflow_refs(workflow):
            if referenced_id not in workflow_ids:
                errors.append(
                    f"{filename}: referenced workflow id {referenced_id!r} does not exist"
                )

    found_public = {
        path: method for (method, path), _owner in webhook_owners.items()
    }
    if found_public != PUBLIC_WEBHOOKS:
        errors.append(
            f"public webhooks differ: expected {PUBLIC_WEBHOOKS}, found {found_public}"
        )

    expense = json.dumps(workflows.get("10_process_expense_service.json", {}))
    decision = json.dumps(workflows.get("11_record_decision_service.json", {}))
    if "/api/expenses/process" not in expense:
        errors.append("process service endpoint is missing")
    if "/api/expenses/" not in decision or "/decision" not in decision:
        errors.append("decision service endpoint is missing")

    required_nodes = {
        "01_expense_intake.json": {
            "Expense Intake Webhook",
            "Normalize Expense Payload",
            "Build Orchestration Context",
            "Process Expense Service",
            "Map API Result",
            "Respond to Webhook",
        },
        "02_approval_decision.json": {
            "Approval Decision Webhook",
            "Normalize Approval Request",
            "Build Orchestration Context",
            "Record Decision Service",
            "Map API Result",
            "Respond to Webhook",
        },
        "10_process_expense_service.json": {
            "Service Input",
            "Runtime Configuration",
            "Call FastAPI Process Expense",
            "Return Service Envelope",
        },
        "11_record_decision_service.json": {
            "Service Input",
            "Runtime Configuration",
            "Call FastAPI Record Decision",
            "Return Service Envelope",
        },
        "20_approval_orchestrator.json": {
            "Approval Context Input",
            "Register n8n Orchestration Metadata",
            "Wait for Human Decision",
            "Mark Orchestration Completed",
            "Send Completion Notification",
        },
        "21_approval_notification_service.json": {
            "Notification Input",
            "Send to Notification Sink",
            "Persist Notification Sent",
        },
        "22_approval_sla_monitor.json": {
            "Approval SLA Schedule",
            "Reserve Due SLA Notifications",
            "Send SLA Notification",
        },
        "23_reliability_dispatcher.json": {
            "Reliability Schedule",
            "Run Reconciliation",
            "Claim Due Outbox Events",
            "For Each Claimed Event",
            "Resolve Resume Capability Just In Time",
            "Invoke Notification Service",
        },
        "24_dead_letter_replay.json": {
            "Replay Input",
            "Request Replay",
            "Invoke Reliability Dispatcher",
        },
        "25_executive_briefing_agent.json": {
            "Briefing Input",
            "Build Briefing Prompt",
            "Generate Briefing",
            "Extract Summary",
            "Return Briefing",
        },
        "30_policy_copilot.json": {
            "Policy Query Webhook",
            "Fetch All Policies",
            "Fetch All Terms",
            "Build Copilot Prompt",
            "Generate Answer",
            "Extract Answer",
            "Respond to Webhook",
        },
        "31_forensic_audit_agent.json": {
            "Audit Input",
            "Audit Report Webhook",
            "Fetch Expense",
            "Fetch Explanation",
            "Fetch Lineage",
            "Fetch Provenance",
            "Build Audit Prompt",
            "Generate Audit Report",
            "Extract Report",
            "Return Audit",
        },
        "99_global_error_handler.json": {
            "North Star Error Trigger",
            "Normalize Safe Failure Metadata",
            "Persist Workflow Failure Safely",
        },
    }
    for filename, expected in required_nodes.items():
        actual = {
            node.get("name") for node in workflows.get(filename, {}).get("nodes", [])
        }
        missing = expected - actual
        if missing:
            errors.append(f"{filename}: missing required nodes {sorted(missing)}")

    for filename in ("01_expense_intake.json", "02_approval_decision.json"):
        node_types = {
            node.get("type") for node in workflows.get(filename, {}).get("nodes", [])
        }
        if "n8n-nodes-base.respondToWebhook" not in node_types:
            errors.append(f"{filename}: Respond to Webhook node is required")

    global_error_id = "northstarGlobalErrorHandler"
    for filename, workflow in workflows.items():
        if filename == "99_global_error_handler.json":
            if workflow.get("settings", {}).get("errorWorkflow") == global_error_id:
                errors.append(f"{filename}: global error handler must not reference itself")
            continue
        if workflow.get("settings", {}).get("errorWorkflow") != global_error_id:
            errors.append(f"{filename}: Global Error Handler is not configured")

    replay_types = {
        node.get("type")
        for node in workflows.get("24_dead_letter_replay.json", {}).get("nodes", [])
    }
    if "n8n-nodes-base.webhook" in replay_types:
        errors.append("24_dead_letter_replay.json: replay must not expose a public webhook")

    handler_types = {
        node.get("type")
        for node in workflows.get("99_global_error_handler.json", {}).get("nodes", [])
    }
    if "n8n-nodes-base.errorTrigger" not in handler_types:
        errors.append("99_global_error_handler.json: Error Trigger is required")

    serialized_all = json.dumps(workflows)
    for path in (
        "/api/internal/outbox/claim",
        "/api/internal/reliability/reconcile",
        "/api/internal/workflow-failures",
    ):
        if path not in serialized_all:
            errors.append(f"Gate 3B internal path is missing: {path}")

    return errors


def main() -> int:
    workflows, errors = load_workflows()
    errors.extend(validate_workflows(workflows))
    if errors:
        print("N8N WORKFLOW VALIDATION: FAIL", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"N8N WORKFLOW VALIDATION: PASS ({len(workflows)} workflows)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
