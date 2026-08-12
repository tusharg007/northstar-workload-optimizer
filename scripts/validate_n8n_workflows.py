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
}
PUBLIC_WEBHOOKS = {
    "northstar-expense": "POST",
    "northstar-approval": "POST",
}
SUPPORTED_NODE_TYPES = {
    "n8n-nodes-base.executeWorkflow",
    "n8n-nodes-base.executeWorkflowTrigger",
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.set",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.webhook",
}
TRIGGER_TYPES = {
    "n8n-nodes-base.executeWorkflowTrigger",
    "n8n-nodes-base.webhook",
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
        if "$env" in serialized:
            errors.append(f"{filename}: forbidden $env expression")
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
