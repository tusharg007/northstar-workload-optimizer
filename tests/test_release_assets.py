"""Regression checks for importable demo assets and Windows commands."""

from __future__ import annotations

import json
from pathlib import Path

from app.main import DEFAULT_RUNTIME_DB
from etl.etl_pipeline import DB_PATH as ANALYTICAL_DB

PROJECT_DIR = Path(__file__).resolve().parents[1]


def _workflow(name: str) -> dict:
    return json.loads(
        (PROJECT_DIR / "n8n" / "workflows" / name).read_text(encoding="utf-8")
    )


def test_n8n_workflows_have_import_ids_and_expected_topology() -> None:
    intake = _workflow("01_expense_intake.json")
    approval = _workflow("02_approval_decision.json")
    process_service = _workflow("10_process_expense_service.json")
    decision_service = _workflow("11_record_decision_service.json")
    orchestrator = _workflow("20_approval_orchestrator.json")

    assert intake["id"] == "northstarExpenseIntake"
    assert approval["id"] == "northstarApprovalDecision"
    assert process_service["id"] == "northstarProcessExpenseService"
    assert decision_service["id"] == "northstarRecordDecisionService"
    assert orchestrator["id"] == "northstarApprovalOrchestrator"
    assert any(node["type"] == "n8n-nodes-base.wait" for node in orchestrator["nodes"])
    assert intake["nodes"][0]["type"] == "n8n-nodes-base.webhook"
    assert approval["nodes"][0]["type"] == "n8n-nodes-base.webhook"

    intake_nodes = {node["name"]: node for node in intake["nodes"]}
    approval_nodes = {node["name"]: node for node in approval["nodes"]}
    assert intake_nodes["Expense Intake Webhook"]["parameters"]["path"] == (
        "northstar-expense"
    )
    assert approval_nodes["Approval Decision Webhook"]["parameters"]["path"] == (
        "northstar-approval"
    )
    process_nodes = {node["name"]: node for node in process_service["nodes"]}
    decision_nodes = {node["name"]: node for node in decision_service["nodes"]}
    process_url = process_nodes["Call FastAPI Process Expense"]["parameters"]["url"]
    assert "$json.api_base_url" in process_url
    assert "/api/expenses/process" in process_url
    approval_url = decision_nodes["Call FastAPI Record Decision"]["parameters"]["url"]
    assert "$env" not in approval_url
    assert "api_base_url" in approval_url
    assert "encodeURIComponent($('Service Input').item.json.expense_id)" in approval_url
    approval_body = decision_nodes["Call FastAPI Record Decision"]["parameters"][
        "jsonBody"
    ]
    assert approval_body == "={{ $('Service Input').item.json.payload }}"


def test_n8n_workflows_need_no_credentials() -> None:
    for path in (PROJECT_DIR / "n8n" / "workflows").glob("*.json"):
        workflow = _workflow(path.name)
        assert all("credentials" not in node for node in workflow["nodes"])
        assert "$env" not in json.dumps(workflow)


def test_operational_and_analytical_databases_are_isolated() -> None:
    analytical = Path(ANALYTICAL_DB).resolve()
    operational = DEFAULT_RUNTIME_DB.resolve()
    assert analytical.name == "northstar.db"
    assert operational.name == "northstar_runtime.db"
    assert analytical != operational


def test_demo_uses_execution_policy_safe_windows_commands() -> None:
    demo = (PROJECT_DIR / "DEMO.md").read_text(encoding="utf-8")
    assert "npx.cmd --yes n8n" in demo
    assert ".\\.venv\\Scripts\\python.exe" in demo
    assert ".\\.venv\\Scripts\\uv.exe run mcp dev" in demo
    assert "$env:UV_CACHE_DIR" in demo
    assert "Activate.ps1" not in demo
