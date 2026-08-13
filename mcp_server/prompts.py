"""User-controlled investigation templates; no decision logic lives here."""

from __future__ import annotations

from mcp.server import MCPServer


def register_prompts(server: MCPServer) -> None:
    @server.prompt(name="investigate_expense", description="Guide a user-controlled review of governed context, trace and lineage.")
    def investigate_expense(expense_id: str) -> str:
        return (
            f"Investigate North Star expense {expense_id}. Read its context, decision trace, "
            "lineage and provenance verification. Keep governed policy evidence separate from "
            "algorithmic risk signals. Report stored facts and do not approve or modify anything."
        )
