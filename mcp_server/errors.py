"""Safe, stable error contracts for the North Star MCP provider."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NorthStarMCPError(RuntimeError):
    code: str
    message: str
    reason_code: str | None = None
    correlation_id: str | None = None

    def __str__(self) -> str:
        parts = [self.code, self.message]
        if self.reason_code:
            parts.append(f"reason_code={self.reason_code}")
        if self.correlation_id:
            parts.append(f"correlation_id={self.correlation_id}")
        return ": ".join(parts)


def invalid(message: str) -> NorthStarMCPError:
    return NorthStarMCPError("INVALID_INPUT", message)
