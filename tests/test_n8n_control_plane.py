"""Gate 2 source-controlled n8n control-plane contracts."""

from __future__ import annotations

import json
import os
from uuid import uuid4
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from app.db.models import ApprovalTask, Expense, WorkflowEvent, WorkflowRun
from app.db.session import Database
from scripts.validate_n8n_workflows import load_workflows, validate_workflows

PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = PROJECT_DIR / "n8n" / "workflows"


def _workflows() -> dict[str, dict]:
    workflows, errors = load_workflows()
    assert not errors
    return workflows


def _serialized(filename: str) -> str:
    return (WORKFLOW_DIR / filename).read_text(encoding="utf-8")


def test_all_workflow_exports_parse_and_pass_validator() -> None:
    workflows = _workflows()
    assert len(workflows) == 10
    assert validate_workflows(workflows) == []


def test_workflow_ids_and_names_are_unique() -> None:
    workflows = _workflows().values()
    assert len({workflow["id"] for workflow in workflows}) == 10
    assert len({workflow["name"] for workflow in workflows}) == 10


def test_public_webhook_contracts_are_frozen() -> None:
    workflows = _workflows()
    paths: dict[str, str] = {}
    for workflow in workflows.values():
        for node in workflow["nodes"]:
            if node["type"] == "n8n-nodes-base.webhook":
                paths[node["parameters"]["path"]] = node["parameters"][
                    "httpMethod"
                ]
    assert paths == {"northstar-expense": "POST", "northstar-approval": "POST"}


def test_modular_workflow_references_resolve_to_stable_ids() -> None:
    workflows = _workflows()
    ids = {workflow["id"] for workflow in workflows.values()}
    referenced: set[str] = set()
    for workflow in workflows.values():
        for node in workflow["nodes"]:
            if node["type"] == "n8n-nodes-base.executeWorkflow":
                selector = node["parameters"]["workflowId"]
                assert selector["mode"] == "id"
                referenced.add(selector["value"])
    assert referenced == {
        "northstarProcessExpenseService",
        "northstarRecordDecisionService",
        "northstarApprovalOrchestrator",
        "northstarApprovalNotificationService",
        "northstarReliabilityDispatcher",
    }
    assert referenced <= ids


def test_service_endpoints_derive_from_runtime_configuration() -> None:
    for filename, node_name, suffix in (
        ("10_process_expense_service.json", "Call FastAPI Process Expense", "/api/expenses/process"),
        ("11_record_decision_service.json", "Call FastAPI Record Decision", "/decision"),
    ):
        workflow = _workflows()[filename]
        nodes = {node["name"]: node for node in workflow["nodes"]}
        assignments = nodes["Runtime Configuration"]["parameters"]["assignments"]
        assert assignments["assignments"][0]["value"] == "http://127.0.0.1:8000"
        http_node = nodes[node_name]
        assert "api_base_url" in http_node["parameters"]["url"]
        assert suffix in http_node["parameters"]["url"]


def test_correlation_and_idempotency_propagation_are_present() -> None:
    expense_public = _serialized("01_expense_intake.json")
    expense_service = _serialized("10_process_expense_service.json")
    approval_public = _serialized("02_approval_decision.json")
    approval_service = _serialized("11_record_decision_service.json")
    for content in (
        expense_public,
        expense_service,
        approval_public,
        approval_service,
    ):
        assert "correlation_id" in content
        assert "X-Correlation-ID" in content
    assert "idempotency-key" in expense_public
    assert "northstar:n8n:expense:" in expense_public
    assert "Idempotency-Key" in expense_service


def test_http_transport_has_bounded_timeout_and_no_retry() -> None:
    http_nodes = [
        node
        for workflow in _workflows().values()
        for node in workflow["nodes"]
        if node["type"] == "n8n-nodes-base.httpRequest"
    ]
    assert http_nodes
    for http_node in http_nodes:
        response = http_node["parameters"]["options"]["response"]["response"]
        assert http_node["parameters"]["options"]["timeout"] == 5000
        assert response["fullResponse"] is True
        assert response["responseFormat"] == "json"
        assert "neverError" in response
        assert "retryOnFail" not in http_node

    public_service_nodes = {
        "Call FastAPI Process Expense",
        "Call FastAPI Record Decision",
        "Resume Waiting Approval Orchestrator",
    }
    for http_node in http_nodes:
        if http_node["name"] in public_service_nodes:
            assert http_node["onError"] == "continueRegularOutput"


def test_response_nodes_return_json_status_and_correlation_header() -> None:
    for filename in ("01_expense_intake.json", "02_approval_decision.json"):
        workflow = _workflows()[filename]
        node = next(
            node
            for node in workflow["nodes"]
            if node["type"] == "n8n-nodes-base.respondToWebhook"
        )
        assert node["parameters"]["respondWith"] == "json"
        assert node["parameters"]["responseBody"]
        assert "response_status" in node["parameters"]["options"]["responseCode"]
        headers = {
            entry["name"].lower(): entry["value"]
            for entry in node["parameters"]["options"]["responseHeaders"][
                "entries"
            ]
        }
        assert headers["content-type"] == "application/json"
        assert "correlation_id" in headers["x-correlation-id"]


def test_no_env_secrets_credentials_code_or_database_nodes() -> None:
    forbidden_types = {
        "n8n-nodes-base.code",
        "n8n-nodes-base.executeCommand",
        "n8n-nodes-base.postgres",
    }
    for path in WORKFLOW_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        workflow = json.loads(text)
        assert "$env" not in text
        assert all("credentials" not in node for node in workflow["nodes"])
        assert forbidden_types.isdisjoint(
            {node["type"] for node in workflow["nodes"]}
        )


def test_gate3a_wait_schedule_and_resume_security_contracts() -> None:
    workflows = _workflows()
    orchestrator = workflows["20_approval_orchestrator.json"]
    wait_nodes = [
        node for node in orchestrator["nodes"] if node["type"] == "n8n-nodes-base.wait"
    ]
    assert len(wait_nodes) == 1
    assert wait_nodes[0]["parameters"]["resume"] == "webhook"
    assert wait_nodes[0]["parameters"]["httpMethod"] == "POST"
    assert "$execution.resumeUrl" in _serialized("20_approval_orchestrator.json")

    monitor = workflows["22_approval_sla_monitor.json"]
    assert any(
        node["type"] == "n8n-nodes-base.scheduleTrigger"
        for node in monitor["nodes"]
    )
    assert "northstarApprovalNotificationService" in _serialized(
        "22_approval_sla_monitor.json"
    )
    for filename in ("01_expense_intake.json", "02_approval_decision.json"):
        public = workflows[filename]
        responses = [
            node
            for node in public["nodes"]
            if node["type"] == "n8n-nodes-base.respondToWebhook"
        ]
        assert all("resume_url" not in node["parameters"]["responseBody"] for node in responses)
    error_handlers = [
        workflow for workflow in workflows.values()
        if any(node["type"] == "n8n-nodes-base.errorTrigger" for node in workflow["nodes"])
    ]
    assert [workflow["id"] for workflow in error_handlers] == ["northstarGlobalErrorHandler"]
    assert all(
        workflow.get("settings", {}).get("errorWorkflow") == "northstarGlobalErrorHandler"
        for workflow in workflows.values()
        if workflow["id"] != "northstarGlobalErrorHandler"
    )


def test_gate3b_dispatcher_replay_and_notification_idempotency_contracts() -> None:
    workflows = _workflows()
    dispatcher = _serialized("23_reliability_dispatcher.json")
    replay = workflows["24_dead_letter_replay.json"]
    notification = _serialized("21_approval_notification_service.json")
    assert "/api/internal/reliability/reconcile" in dispatcher
    assert "/api/internal/outbox/claim" in dispatcher
    assert "northstarApprovalNotificationService" in dispatcher
    assert all(node["type"] != "n8n-nodes-base.webhook" for node in replay["nodes"])
    assert "Idempotency-Key" in notification
    assert "northstar:notification:" in notification


@pytest.mark.skipif(
    os.getenv("NORTHSTAR_N8N_RUNTIME_TEST") != "1",
    reason="requires isolated running FastAPI, n8n, and PostgreSQL services",
)
def test_real_n8n_control_plane_runtime_matrix() -> None:
    """Exercise Gate 2 HTTP and database invariants against the release stack."""
    api_url = os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000")
    expense_url = os.getenv(
        "N8N_EXPENSE_WEBHOOK_URL",
        "http://127.0.0.1:5678/webhook/northstar-expense",
    )
    approval_url = os.getenv(
        "N8N_APPROVAL_WEBHOOK_URL",
        "http://127.0.0.1:5678/webhook/northstar-approval",
    )
    database_url = os.environ["NORTHSTAR_DATABASE_URL"]
    marker = uuid4().hex[:12]
    expense_id = f"G2-RUNTIME-{marker}"
    correlation_id = f"g2-correlation-{marker}"
    idempotency_key = f"g2-idempotency-{marker}"
    payload = {
        "expense_id": expense_id,
        "employee_id": "EMP-042",
        "employee_name": "Jordan Lee",
        "department": "IT",
        "transaction_date": "2025-01-18",
        "merchant": "Cloud Vendor",
        "category": "Software & Subscriptions",
        "description": "DUPLICATE annual platform renewal",
        "amount": 3000.0,
        "currency": "USD",
        "payment_method": "Corporate Card",
        "receipt_attached": False,
    }

    with httpx.Client(timeout=10.0) as client:
        supplied = client.post(
            expense_url,
            json=payload,
            headers={
                "X-Correlation-ID": correlation_id,
                "Idempotency-Key": idempotency_key,
            },
        )
        assert supplied.status_code == 200
        assert supplied.content
        assert supplied.headers["content-type"].startswith("application/json")
        assert supplied.headers["x-correlation-id"] == correlation_id
        assert supplied.json()["status"] == "ESCALATED"

        replay = client.post(
            expense_url,
            json=payload,
            headers={
                "X-Correlation-ID": correlation_id,
                "Idempotency-Key": idempotency_key,
            },
        )
        assert replay.status_code == 200
        assert replay.json() == supplied.json()

        changed = dict(payload, amount=3001.0)
        conflict = client.post(
            expense_url,
            json=changed,
            headers={"Idempotency-Key": idempotency_key},
        )
        assert conflict.status_code == 409
        assert conflict.content

        invalid = client.post(
            expense_url,
            json={"expense_id": f"G2-INVALID-{marker}"},
            headers={"X-Correlation-ID": f"g2-invalid-{marker}"},
        )
        assert invalid.status_code == 422
        assert invalid.content
        assert invalid.headers["x-correlation-id"] == f"g2-invalid-{marker}"

        generated_payload = dict(payload, expense_id=f"G2-GENERATED-{marker}")
        generated = client.post(expense_url, json=generated_payload)
        assert generated.status_code == 200
        generated_correlation = generated.headers["x-correlation-id"]
        assert generated_correlation.startswith("northstar-n8n-")
        generated_replay = client.post(expense_url, json=generated_payload)
        assert generated_replay.status_code == 200
        assert generated_replay.json() == generated.json()

        decision = {
            "expense_id": expense_id,
            "decision": "approve",
            "approver": "Finance Director",
            "comment": "Gate 2 release verification",
        }
        approval_correlation = f"g2-approval-{marker}"
        approved = client.post(
            approval_url,
            json=decision,
            headers={"X-Correlation-ID": approval_correlation},
        )
        assert approved.status_code == 200
        assert approved.content
        assert approved.headers["x-correlation-id"] == approval_correlation
        assert approved.json()["status"] == "APPROVED"

        duplicate = client.post(approval_url, json=decision)
        assert duplicate.status_code == 200
        assert duplicate.json()["status"] == "APPROVED"

        conflicting = client.post(
            approval_url,
            json={**decision, "decision": "reject"},
        )
        assert conflicting.status_code == 409
        assert conflicting.content

        stored = client.get(f"{api_url}/api/expenses/{expense_id}")
        assert stored.status_code == 200
        assert stored.json()["status"] == "APPROVED"

    database = Database(database_url)
    try:
        with database.session() as session:
            run = session.scalar(
                select(WorkflowRun).where(WorkflowRun.expense_id == expense_id)
            )
            assert run is not None
            assert run.correlation_id == correlation_id
            assert run.idempotency_key == idempotency_key
            assert session.scalar(
                select(func.count(Expense.id)).where(Expense.expense_id == expense_id)
            ) == 1
            assert session.scalar(
                select(func.count(WorkflowRun.id)).where(
                    WorkflowRun.expense_id == expense_id
                )
            ) == 1
            assert session.scalar(
                select(func.count(ApprovalTask.task_id)).where(
                    ApprovalTask.expense_id == expense_id
                )
            ) == 1
            events = session.scalars(
                select(WorkflowEvent).where(
                    WorkflowEvent.workflow_run_id == run.id
                )
            ).all()
            assert events
            assert {event.workflow_run_id for event in events} == {run.id}

            generated_run = session.scalar(
                select(WorkflowRun).where(
                    WorkflowRun.expense_id == generated_payload["expense_id"]
                )
            )
            assert generated_run is not None
            assert generated_run.correlation_id == generated_correlation
            assert generated_run.idempotency_key == (
                f"northstar:n8n:expense:{generated_payload['expense_id']}"
            )
            assert session.scalar(
                select(func.count(WorkflowRun.id)).where(
                    WorkflowRun.expense_id == generated_payload["expense_id"]
                )
            ) == 1
            assert session.scalar(
                select(func.count(ApprovalTask.task_id)).where(
                    ApprovalTask.expense_id == generated_payload["expense_id"]
                )
            ) == 1
    finally:
        database.dispose()
