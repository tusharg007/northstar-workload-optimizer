"""Gate 7 governed MCP contracts using the official in-memory v2 client."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from mcp import Client
import pytest

from app.main import create_app
from mcp_server.adapters import adapter
from mcp_server.server import mcp

ROOT = Path(__file__).resolve().parents[1]
UTC = timezone.utc
FORBIDDEN = (
    "n8n_wait_resume_url", "input_payload", "payment_method", "decision_comment",
    "DATABASE_URL", "authorization", "postgresql://", "password", "resume_url",
)


@pytest.fixture
def api(tmp_path: Path, monkeypatch) -> TestClient:
    client = TestClient(create_app(tmp_path / "gate7.db"))
    original_request = adapter.request

    def request(method: str, url: str, **kwargs: Any) -> Any:
        if url == adapter.expense_webhook_url:
            response = client.post("/api/expenses/process", **kwargs)
        elif url == adapter.approval_webhook_url:
            body = kwargs["json"]
            response = client.post(
                f"/api/expenses/{body['expense_id']}/decision",
                json={key: body[key] for key in ("decision", "approver", "comment")},
            )
        else:
            path = url.removeprefix(adapter.api_base_url)
            response = client.request(method, path, **kwargs)
        if response.status_code >= 400:
            # Exercise the real normalization path with a response compatible object.
            from unittest.mock import patch
            with patch("mcp_server.adapters.httpx.request", return_value=response):
                return original_request(method, url, **kwargs)
        return response.json()

    monkeypatch.setattr(adapter, "request", request)
    return client


async def _call(name: str, arguments: dict[str, Any]) -> Any:
    async with Client(mcp) as client:
        result = await client.call_tool(name, arguments)
        assert result.is_error is False
        assert result.structured_content is not None
        return result.structured_content


def _payload(expense_id: str) -> dict[str, Any]:
    value = json.loads((ROOT / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    value["expense_id"] = expense_id
    return value


def test_catalog_annotations_resources_and_prompt() -> None:
    async def exercise() -> None:
        async with Client(mcp) as client:
            tools = (await client.list_tools()).tools
            resources = (await client.list_resource_templates()).resource_templates
            prompts = (await client.list_prompts()).prompts
            assert len(tools) == 12 and len(resources) == 5 and [item.name for item in prompts] == ["investigate_expense"]
            by_name = {item.name: item for item in tools}
            assert by_name["get_decision_trace"].annotations.read_only_hint is True
            assert by_name["submit_expense"].annotations.idempotent_hint is True
            assert by_name["approve_expense"].annotations.destructive_hint is True
    asyncio.run(exercise())


def test_governed_reads_trace_lineage_and_resource_consistency(api: TestClient) -> None:
    api.post("/api/expenses/process", json=_payload("G7-TRACE")).raise_for_status()
    api.post("/api/expenses/G7-TRACE/decision", json={"decision": "approve", "approver": "Gate 7", "comment": "not exposed"}).raise_for_status()
    policy = asyncio.run(_call("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING"}))
    term_key = policy["rules"][0]["business_term_key"]
    term = asyncio.run(_call("get_business_term", {"term_key": term_key}))
    context = asyncio.run(_call("get_expense_context", {"expense_id": "G7-TRACE"}))
    trace = asyncio.run(_call("get_decision_trace", {"expense_id": "G7-TRACE"}))
    lineage = asyncio.run(_call("get_expense_lineage", {"expense_id": "G7-TRACE"}))
    verified = asyncio.run(_call("verify_decision_provenance", {"expense_id": "G7-TRACE"}))
    assert policy["trust"]["state"] == "TRUSTED" and term["trust"]["state"] == "TRUSTED"
    assert "governed_policy_context" in context and "algorithmic_risk_signal_context" in context
    assert trace["final_status"] == "APPROVED" and trace["verification"]["status"] == "PASS"
    assert verified["verification_passed"] is True
    assert {item["source"] for item in lineage["events"]} >= {"workflow", "provenance", "approval", "outbox"}

    async def resource_check() -> None:
        async with Client(mcp) as client:
            result = await client.read_resource("northstar://policies/EXPENSE_APPROVAL_ROUTING")
            resource_policy = json.loads(result.contents[0].text)
            assert {key: value for key, value in resource_policy.items() if key != "as_of"} == {
                key: value for key, value in policy.items() if key != "as_of"
            }
    asyncio.run(resource_check())

    serialized = json.dumps({"policy": policy, "term": term, "context": context, "trace": trace, "lineage": lineage, "verified": verified})
    assert not any(token.casefold() in serialized.casefold() for token in FORBIDDEN)


def test_deterministic_search_is_bounded_and_ranked(api: TestClient) -> None:
    result = asyncio.run(_call("search_policy_context", {"query": "EXPENSE_APPROVAL_ROUTING", "limit": 1}))
    assert result["count"] == 1 and result["limit"] == 1
    assert result["results"][0]["key"] == "EXPENSE_APPROVAL_ROUTING"


def test_historical_policy_v1_v2_resolution_matches_gate4a(api: TestClient) -> None:
    repository = api.app.state.store.context.repository
    resolved = api.app.state.store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING")
    repository.update_policy_version(resolved["policy_version_id"], status="RETIRED")
    start = datetime(2027, 1, 1, tzinfo=UTC)
    repository.create_policy_version("EXPENSE_APPROVAL_ROUTING", {
        "version_number": 2, "status": "CERTIFIED", "effective_from": start,
        "effective_to": None, "review_due_at": datetime(2030, 1, 1, tzinfo=UTC),
        "certified_at": start, "source_reference": "Gate 7 historical MCP test", "metadata": {"test": "v2"},
    }, resolved["rules"])
    for signal_type in ("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"):
        repository.add_trust_signal({
            "target_kind": "policy", "target_key": "EXPENSE_APPROVAL_ROUTING", "version_number": 2,
            "signal_type": signal_type, "status": "PASS", "observed_at": start,
            "expires_at": datetime(2030, 1, 1, tzinfo=UTC), "source": f"g7-{signal_type}", "details": {},
        })
    first = asyncio.run(_call("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING", "as_of": "2026-06-01T00:00:00Z"}))
    second = asyncio.run(_call("get_policy_version", {"policy_key": "EXPENSE_APPROVAL_ROUTING", "as_of": (start + timedelta(days=1)).isoformat()}))
    assert first["version_number"] == 1 and second["version_number"] == 2
    assert second["trust"]["state"] == "TRUSTED"


def test_error_contract_negative_controls(api: TestClient) -> None:
    async def exercise() -> None:
        async with Client(mcp) as client:
            unknown = await client.call_tool("get_policy_version", {"policy_key": "UNKNOWN_POLICY"})
            invalid = await client.call_tool("search_policy_context", {"query": "", "limit": 101})
            assert unknown.is_error and "NOT_FOUND" in unknown.content[0].text
            assert invalid.is_error and ("INVALID_INPUT" in invalid.content[0].text or "validation error" in invalid.content[0].text)
    asyncio.run(exercise())


def test_static_mcp_package_has_no_database_access() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "mcp_server").glob("*.py"))
    assert "sqlalchemy" not in source.casefold()
    assert "psycopg" not in source.casefold()
    assert ".execute(" not in source
