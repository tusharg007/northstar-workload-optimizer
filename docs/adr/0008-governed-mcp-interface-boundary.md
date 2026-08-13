# ADR 0008: Governed MCP interface boundary

## Status

Accepted.

## Context

AI clients need useful context and controlled actions without direct database access or exposure of workflow capabilities and secrets.

## Decision

The official MCP Python SDK exposes minimized tools/resources. Reads call FastAPI; consequential writes call the established n8n webhooks. stdio is primary and Streamable HTTP is loopback-only.

## Consequences

MCP inherits application governance and audit trails. Production authentication, identity binding, and remote HTTP exposure remain explicitly out of scope.
