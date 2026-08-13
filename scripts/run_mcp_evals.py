"""Deterministic Gate 7 MCP interface benchmark; no LLM judge."""

from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Any, Iterator

from fastapi.testclient import TestClient
import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.models import ApprovalDecision, ApprovalTask, DecisionHumanEvidence, DecisionProvenance, Expense, PolicyRule, WorkflowRun
from app.main import create_app
from mcp_server.adapters import NorthStarAdapter, adapter
from mcp_server.server import mcp

MANIFEST = ROOT / "evals" / "datasets" / "mcp_v1" / "manifest.json"
FORBIDDEN = (
    "n8n_wait_resume_url", "resume_url", "input_payload", "payment_method",
    "decision_comment", "database_url", "postgresql://", "authorization: bearer",
    "metabase_admin_password", "northstar_metabase_db_password", "password",
)


def payload(expense_id: str) -> dict[str, Any]:
    value = json.loads((ROOT / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    value["expense_id"] = expense_id
    return value


def tool_arguments(expense_id: str) -> dict[str, Any]:
    return payload(expense_id)


def error_text(result: Any) -> str:
    return " ".join(getattr(item, "text", "") for item in result.content)


async def wait_for_orchestration(expense_id: str, expected: str, timeout_seconds: float = 20) -> dict[str, Any]:
    """Poll the integration-only task view without exposing its capability data."""
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    url = f"{adapter.api_base_url}/api/internal/approval-tasks/by-expense/{expense_id}"
    async with httpx.AsyncClient(timeout=2) as client:
        while asyncio.get_running_loop().time() < deadline:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    task = response.json()
                    if task.get("orchestration_status") == expected:
                        return {"task_id": task["task_id"], "orchestration_status": expected}
            except httpx.RequestError:
                pass
            await asyncio.sleep(0.2)
    raise RuntimeError(f"orchestration did not reach {expected} within {timeout_seconds:g}s")


async def get_resume_outbox(task_id: str) -> dict[str, Any]:
    url = f"{adapter.api_base_url}/api/internal/outbox/by-delivery-key/approval-resume:{task_id}"
    async with httpx.AsyncClient(timeout=2) as client:
        response = await client.get(url)
    response.raise_for_status()
    body = response.json()
    return {"event_type": body.get("event_type"), "status": body.get("status")}


@contextmanager
def fast_environment() -> Iterator[tuple[TestClient, Any]]:
    with TemporaryDirectory(prefix="northstar-mcp-eval-") as temporary:
        api = TestClient(create_app(Path(temporary) / "mcp.db"))
        original = adapter.request

        def request(method: str, url: str, **kwargs: Any) -> Any:
            if url == adapter.expense_webhook_url:
                response = api.post("/api/expenses/process", **kwargs)
            elif url == adapter.approval_webhook_url:
                body = kwargs["json"]
                response = api.post(f"/api/expenses/{body['expense_id']}/decision", json={key: body[key] for key in ("decision", "approver", "comment")})
            else:
                response = api.request(method, url.removeprefix(adapter.api_base_url), **kwargs)
            if response.status_code < 400:
                body = response.json()
                correlation = response.headers.get("X-Correlation-ID")
                return {**body, "correlation_id": correlation} if correlation and isinstance(body, dict) else body
            import unittest.mock
            with unittest.mock.patch("mcp_server.adapters.httpx.request", return_value=response):
                return original(method, url, **kwargs)

        adapter.request = request  # type: ignore[method-assign]
        try:
            yield api, api.app.state.store
        finally:
            adapter.request = original  # type: ignore[method-assign]
            api.close()
            api.app.state.store.database.engine.dispose()


async def run_cases(client: Client, profile: str, store: Any | None = None) -> tuple[dict[str, bool], list[Any]]:
    expense_id = "G7-MCP-EVAL-001" if profile == "fast" else os.getenv("NORTHSTAR_MCP_EVAL_EXPENSE_ID", "G7-MCP-LIVE-001")
    outcomes: dict[str, bool] = {}
    scanned: list[Any] = []
    catalog = await client.list_tools()
    templates = await client.list_resource_templates()
    outcomes["tool_discovery"] = len(catalog.tools) == 12 and len(templates.resource_templates) == 5 and all(item.description for item in catalog.tools)

    policy = await client.call_tool("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING", "as_of": "2025-06-01T00:00:00Z"})
    scanned.append(policy.structured_content)
    outcomes["policy_lookup"] = not policy.is_error and policy.structured_content["policy_key"] == "EXPENSE_APPROVAL_ROUTING" and policy.structured_content["trust"]["state"] == "TRUSTED"
    outcomes["historical_policy_lookup"] = not policy.is_error and policy.structured_content["version_number"] == 1 and policy.structured_content["as_of"].startswith("2025-06-01")

    term = await client.call_tool("get_business_term", {"term_key": "APPROVAL_REQUIRED", "as_of": "2025-06-01T00:00:00Z"})
    scanned.append(term.structured_content)
    outcomes["business_term_lookup"] = not term.is_error and term.structured_content["version_number"] == 1 and term.structured_content["trust"]["state"] == "TRUSTED"

    search = await client.call_tool("search_policy_context", {"query": "EXPENSE_APPROVAL_ROUTING", "limit": 1})
    scanned.append(search.structured_content)
    outcomes["search_ranking"] = not search.is_error and search.structured_content["results"][0]["key"] == "EXPENSE_APPROVAL_ROUTING"
    outcomes["bounded_output"] = (
        not search.is_error
        and search.structured_content["count"] <= search.structured_content["limit"] == 1
    )

    submitted = await client.call_tool("submit_expense", tool_arguments(expense_id))
    scanned.append(submitted.structured_content)
    outcomes["submit_expense"] = not submitted.is_error and submitted.structured_content["status"] == "ESCALATED" and submitted.structured_content["risk_level"] == "CRITICAL" and submitted.structured_content["approver_role"] == "Finance Director + Compliance"
    replay = await client.call_tool("submit_expense", tool_arguments(expense_id))
    scanned.append(replay.structured_content)
    outcomes["submit_idempotency"] = not replay.is_error and replay.structured_content["status"] == "ESCALATED"

    context = await client.call_tool("get_expense_context", {"expense_id": expense_id})
    scanned.append(context.structured_content)
    outcomes["expense_context"] = not context.is_error and "governed_policy_context" in context.structured_content and "algorithmic_risk_signal_context" in context.structured_content

    live_task = None
    if profile == "stdio":
        live_task = await wait_for_orchestration(expense_id, "WAITING")
        # Registration is committed just before the n8n execution enters its
        # Wait node. Give that asynchronous transition a small bounded margin.
        await asyncio.sleep(0.5)

    approved = await client.call_tool("approve_expense", {"expense_id": expense_id, "approver": "Gate 7 MCP Evaluator", "comment": "deterministic benchmark"})
    scanned.append(approved.structured_content)
    outcomes["approve_expense"] = not approved.is_error and approved.structured_content["status"] == "APPROVED"
    if profile == "stdio" and live_task is not None:
        completed = await wait_for_orchestration(expense_id, "COMPLETED")
        outbox = await get_resume_outbox(live_task["task_id"])
        outcomes["approve_expense"] = outcomes["approve_expense"] and all((
            completed["orchestration_status"] == "COMPLETED",
            outbox["event_type"] == "APPROVAL_RESUME_REQUIRED",
            outbox["status"] == "DELIVERED",
        ))

    trace = await client.call_tool("get_decision_trace", {"expense_id": expense_id})
    scanned.append(trace.structured_content)
    outcomes["decision_trace"] = not trace.is_error and trace.structured_content["final_status"] == "APPROVED" and trace.structured_content["verification"]["status"] == "PASS" and any(item["triggered"] for item in trace.structured_content["risk_signal_evaluations"])
    lineage = await client.call_tool("get_expense_lineage", {"expense_id": expense_id})
    scanned.append(lineage.structured_content)
    outcomes["expense_lineage"] = not lineage.is_error and {item["source"] for item in lineage.structured_content["events"]} >= {"workflow", "provenance", "approval", "outbox"}
    verified = await client.call_tool("verify_decision_provenance", {"expense_id": expense_id})
    scanned.append(verified.structured_content)
    outcomes["provenance_verification"] = not verified.is_error and verified.structured_content["verification_passed"] is True

    resource = await client.read_resource("northstar://policies/EXPENSE_APPROVAL_ROUTING")
    resource_value = json.loads(resource.contents[0].text)
    scanned.append(resource_value)
    outcomes["resource_consistency"] = resource_value["policy_key"] == policy.structured_content["policy_key"] and resource_value["version_number"] == policy.structured_content["version_number"]

    unknown = await client.call_tool("get_policy_version", {"policy_key": "UNKNOWN_POLICY"})
    invalid = await client.call_tool("search_policy_context", {"query": "", "limit": 101})
    outcomes["error_contracts"] = unknown.is_error and "NOT_FOUND" in error_text(unknown) and invalid.is_error

    if profile == "fast" and store is not None:
        with store.database.transaction() as session:
            rule = session.scalar(select(PolicyRule).where(PolicyRule.rule_key == "RECEIPT_REQUIRED_THRESHOLD"))
            original_parameters = dict(rule.parameters)
            rule.parameters = {**rule.parameters, "amount_greater_than": 100}
        abstained = await client.call_tool("submit_expense", tool_arguments("G7-MCP-ABSTAIN"))
        with store.database.transaction() as session:
            rule = session.scalar(select(PolicyRule).where(PolicyRule.rule_key == "RECEIPT_REQUIRED_THRESHOLD"))
            rule.parameters = original_parameters
        with store.database.session() as session:
            no_expense = session.get(Expense, "G7-MCP-ABSTAIN") is None
        outcomes["context_abstention"] = abstained.is_error and "CONTEXT_NOT_AUTHORITATIVE" in error_text(abstained) and "POLICY_ENGINE_MISMATCH" in error_text(abstained) and no_expense
        with store.database.session() as session:
            outcomes["submit_idempotency"] = outcomes["submit_idempotency"] and all((
                session.scalar(select(func.count()).select_from(Expense).where(Expense.expense_id == expense_id)) == 1,
                session.scalar(select(func.count()).select_from(WorkflowRun).where(WorkflowRun.expense_id == expense_id)) == 1,
                session.scalar(select(func.count()).select_from(ApprovalTask).where(ApprovalTask.expense_id == expense_id)) == 1,
                session.scalar(select(func.count()).select_from(DecisionProvenance).where(DecisionProvenance.expense_id == expense_id)) == 1,
            ))
            outcomes["approve_expense"] = outcomes["approve_expense"] and session.scalar(select(func.count()).select_from(ApprovalDecision).where(ApprovalDecision.expense_id == expense_id)) == 1 and session.scalar(select(func.count()).select_from(DecisionHumanEvidence)) == 1

    serialized = json.dumps(scanned, sort_keys=True, default=str).casefold()
    deliberate_fixture = {"n8n_wait_resume_url": "forbidden-control"}
    detector_works = any(token in json.dumps(deliberate_fixture).casefold() for token in FORBIDDEN)
    outcomes["sensitive_data_scan"] = detector_works and not any(token in serialized for token in FORBIDDEN)
    return outcomes, scanned


def summarize(outcomes: dict[str, bool], profile: str) -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    cases = [item for item in manifest["cases"] if profile in item.get("profiles", ["fast", "stdio"])]
    missing = {item["id"] for item in cases} - set(outcomes)
    if missing:
        raise RuntimeError(f"benchmark did not execute cases: {sorted(missing)}")
    metrics: dict[str, float] = {}
    for metric, threshold in manifest["thresholds"].items():
        selected = [item for item in cases if item["metric"] == metric]
        if not selected:
            continue
        passed = sum(outcomes[item["id"]] for item in selected)
        value = (len(selected) - passed) / len(selected) if metric == "sensitive_data_leak_rate" else passed / len(selected)
        metrics[metric] = value
    passed = all(outcomes[item["id"]] for item in cases) and all(
        value <= manifest["thresholds"][name] if name == "sensitive_data_leak_rate" else value >= manifest["thresholds"][name]
        for name, value in metrics.items()
    )
    print(f"Gate 7 MCP {profile.upper()} evaluation: {'PASS' if passed else 'FAIL'}")
    print(f"Cases: {sum(outcomes[item['id']] for item in cases)}/{len(cases)} passed")
    for item in cases:
        print(f"  [{'PASS' if outcomes[item['id']] else 'FAIL'}] {item['id']}")
    for name, value in metrics.items():
        comparator = "<=" if name == "sensitive_data_leak_rate" else ">="
        print(f"  metric {name}={value:.3f} ({comparator} {manifest['thresholds'][name]:.3f})")
    return 0 if passed else 1


async def run_fast() -> int:
    with fast_environment() as (_, store):
        async with Client(mcp) as client:
            outcomes, _ = await run_cases(client, "fast", store)
    return summarize(outcomes, "fast")


async def run_stdio() -> int:
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"], cwd=ROOT,
        env={key: value for key, value in os.environ.items() if key.startswith(("NORTHSTAR_", "N8N_"))},
    )
    async with Client(stdio_client(parameters)) as client:
        outcomes, _ = await run_cases(client, "stdio")
    return summarize(outcomes, "stdio")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("fast", "stdio"), default="fast")
    args = parser.parse_args()
    try:
        return asyncio.run(run_fast() if args.profile == "fast" else run_stdio())
    except Exception as exc:
        print(
            f"Gate 7 MCP {args.profile.upper()} evaluation: FAIL: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
