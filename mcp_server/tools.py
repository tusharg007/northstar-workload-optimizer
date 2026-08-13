"""Typed tool catalog for the North Star governed MCP provider."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Annotated, Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from mcp_server.adapters import adapter
from mcp_server.errors import NorthStarMCPError

ReadKey = Annotated[str, Field(min_length=1, max_length=128)]
AsOf = Annotated[str | None, Field(default=None, max_length=64)]
Limit = Annotated[int, Field(ge=1, le=100)]

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
SUBMIT = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)
APPROVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)
logger = logging.getLogger("northstar.mcp.tools")


def _observed(operation: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
    except NorthStarMCPError as exc:
        logger.warning(json.dumps({
            "event": "mcp_operation", "operation": operation,
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "success": False, "failure_category": exc.code,
            "correlation_id": exc.correlation_id,
        }, sort_keys=True))
        raise
    logger.info(json.dumps({
        "event": "mcp_operation", "operation": operation,
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "success": True,
        "correlation_id": result.get("correlation_id"),
    }, sort_keys=True))
    return result


def register_tools(server: MCPServer) -> None:
    @server.tool(annotations=SUBMIT, structured_output=True)
    def submit_expense(
        expense_id: ReadKey,
        employee_id: ReadKey,
        employee_name: Annotated[str, Field(min_length=1, max_length=255)],
        department: Annotated[str, Field(min_length=1, max_length=128)],
        transaction_date: Annotated[str, Field(min_length=1, max_length=32)],
        merchant: Annotated[str, Field(min_length=1, max_length=255)],
        category: Annotated[str, Field(min_length=1, max_length=128)],
        amount: Annotated[float, Field(gt=0, le=1_000_000_000)],
        description: Annotated[str, Field(max_length=2000)] = "",
        currency: Annotated[str, Field(min_length=3, max_length=16)] = "USD",
        payment_method: Annotated[str, Field(min_length=1, max_length=128)] = "Corporate Card",
        receipt_attached: bool = False,
    ) -> dict[str, Any]:
        """ORCHESTRATION BRIDGE: submit an expense through n8n's governed intake path; preserves context abstention and idempotency."""
        return _observed("submit_expense", lambda: adapter.submit_expense({
            "expense_id": expense_id, "employee_id": employee_id, "employee_name": employee_name,
            "department": department, "transaction_date": transaction_date, "merchant": merchant,
            "category": category, "amount": amount, "description": description, "currency": currency,
            "payment_method": payment_method, "receipt_attached": receipt_attached,
        }))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_expense_status(expense_id: ReadKey) -> dict[str, Any]:
        """READ: return the minimized durable status, risk, routing and final-decision state for one expense."""
        return _observed("get_expense_status", lambda: adapter.expense_status(expense_id))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def list_pending_approvals(limit: Limit = 20) -> dict[str, Any]:
        """READ: list a bounded set of expenses awaiting approval or escalated review."""
        return _observed("list_pending_approvals", lambda: adapter.pending_approvals(limit))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def explain_risk(expense_id: ReadKey) -> dict[str, Any]:
        """READ: return the stored deterministic risk flags and routing explanation; risk signals are not policy violations."""
        return _observed("explain_risk", lambda: adapter.explain_risk(expense_id))

    @server.tool(annotations=APPROVE, structured_output=True)
    def approve_expense(
        expense_id: ReadKey,
        approver: Annotated[str, Field(min_length=1, max_length=255)],
        comment: Annotated[str, Field(max_length=2000)] = "",
    ) -> dict[str, Any]:
        """CONSEQUENTIAL ACTION: record approval through n8n, durable HITL, immutable human evidence and outbox resume; trusted operators only."""
        return _observed("approve_expense", lambda: adapter.approve_expense(expense_id, approver, comment))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def search_policy_context(
        query: Annotated[str, Field(min_length=1, max_length=255)],
        as_of: AsOf = None,
        domain: Annotated[str | None, Field(default=None, max_length=128)] = None,
        trust_state: Annotated[str | None, Field(default=None, max_length=32)] = None,
        limit: Limit = 20,
    ) -> dict[str, Any]:
        """READ: deterministically rank governed policies and terms by exact/text match with optional UTC as-of, domain and trust filters."""
        return _observed("search_policy_context", lambda: adapter.search_policy_context(query, as_of, domain, trust_state, limit))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_policy_version(policy_key: ReadKey, version: Annotated[int | None, Field(default=None, ge=1)] = None, as_of: AsOf = None) -> dict[str, Any]:
        """READ: resolve one governed policy version, owner, effective interval, trust evidence and governed rules using Gate 4A semantics."""
        return _observed("get_policy_version", lambda: adapter.policy_version(policy_key, version, as_of))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_business_term(term_key: ReadKey, version: Annotated[int | None, Field(default=None, ge=1)] = None, as_of: AsOf = None) -> dict[str, Any]:
        """READ: resolve one governed business-term definition historically with ownership, certification, freshness and content hash."""
        return _observed("get_business_term", lambda: adapter.business_term(term_key, version, as_of))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_expense_context(expense_id: ReadKey) -> dict[str, Any]:
        """READ: return the expense's governed policy context separately from algorithmic risk-signal context."""
        return _observed("get_expense_context", lambda: adapter.expense_context(expense_id))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_decision_trace(expense_id: ReadKey | None = None, provenance_id: ReadKey | None = None) -> dict[str, Any]:
        """READ: return a minimized deterministic decision trace, approval state, evidence and provenance verification for exactly one identifier."""
        return _observed("get_decision_trace", lambda: adapter.decision_trace(expense_id, provenance_id))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def get_expense_lineage(expense_id: ReadKey) -> dict[str, Any]:
        """READ: return a timestamped sequence built only from persisted workflow, provenance, approval and outbox records."""
        return _observed("get_expense_lineage", lambda: adapter.expense_lineage(expense_id))

    @server.tool(annotations=READ_ONLY, structured_output=True)
    def verify_decision_provenance(expense_id: ReadKey | None = None, provenance_id: ReadKey | None = None) -> dict[str, Any]:
        """READ: recompute and verify immutable decision evidence hashes for exactly one expense or provenance identifier."""
        return _observed("verify_decision_provenance", lambda: adapter.verify_provenance(expense_id, provenance_id))
