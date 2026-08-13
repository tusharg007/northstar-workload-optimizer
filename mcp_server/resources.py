"""Read-only MCP resource templates backed by the shared application adapter."""

from __future__ import annotations

import json

from mcp.server import MCPServer

from mcp_server.adapters import adapter


def _json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))


def register_resources(server: MCPServer) -> None:
    @server.resource(
        "northstar://policies/{policy_key}", name="governed-policy",
        description="Read-only current governed policy, rules and trust state.", mime_type="application/json",
    )
    def policy_resource(policy_key: str) -> str:
        return _json(adapter.policy_version(policy_key))

    @server.resource(
        "northstar://terms/{term_key}", name="governed-business-term",
        description="Read-only current governed business-term definition and trust state.", mime_type="application/json",
    )
    def term_resource(term_key: str) -> str:
        return _json(adapter.business_term(term_key))

    @server.resource(
        "northstar://expenses/{expense_id}/context", name="expense-context",
        description="Read-only governed policy and algorithmic risk context for an expense.", mime_type="application/json",
    )
    def context_resource(expense_id: str) -> str:
        return _json(adapter.expense_context(expense_id))

    @server.resource(
        "northstar://expenses/{expense_id}/trace", name="decision-trace",
        description="Read-only minimized decision trace and provenance verification.", mime_type="application/json",
    )
    def trace_resource(expense_id: str) -> str:
        return _json(adapter.decision_trace(expense_id=expense_id))

    @server.resource(
        "northstar://expenses/{expense_id}/lineage", name="expense-lineage",
        description="Read-only persisted workflow, provenance, approval and reliability timeline.", mime_type="application/json",
    )
    def lineage_resource(expense_id: str) -> str:
        return _json(adapter.expense_lineage(expense_id))
