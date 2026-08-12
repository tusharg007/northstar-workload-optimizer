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

    assert intake["id"] == "northstarExpenseIntake"
    assert approval["id"] == "northstarApprovalDecision"
    assert [node["type"] for node in intake["nodes"]] == [
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.set",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.switch",
        "n8n-nodes-base.respondToWebhook",
    ]
    assert [node["type"] for node in approval["nodes"]] == [
        "n8n-nodes-base.webhook",
        "n8n-nodes-base.httpRequest",
        "n8n-nodes-base.respondToWebhook",
    ]

    intake_nodes = {node["name"]: node for node in intake["nodes"]}
    approval_nodes = {node["name"]: node for node in approval["nodes"]}
    assert intake_nodes["Expense Intake Webhook"]["parameters"]["path"] == (
        "northstar-expense"
    )
    assert approval_nodes["Approval Decision Webhook"]["parameters"]["path"] == (
        "northstar-approval"
    )
    assert intake_nodes["Process Expense in FastAPI"]["parameters"]["url"] == (
        "http://127.0.0.1:8000/api/expenses/process"
    )
    approval_url = approval_nodes["Record Decision in FastAPI"]["parameters"][
        "url"
    ]
    assert "$env" not in approval_url
    assert "http://127.0.0.1:8000/api/expenses/" in approval_url
    assert "encodeURIComponent($json.body.expense_id)" in approval_url
    approval_body = approval_nodes["Record Decision in FastAPI"]["parameters"][
        "body"
    ]
    assert "$json.body.decision" in approval_body
    assert "$json.body.approver" in approval_body
    assert "$json.body.comment" in approval_body


def test_n8n_workflows_need_no_credentials() -> None:
    for filename in ("01_expense_intake.json", "02_approval_decision.json"):
        workflow = _workflow(filename)
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
