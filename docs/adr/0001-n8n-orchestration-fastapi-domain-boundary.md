# ADR 0001: n8n orchestration and FastAPI domain boundary

## Status

Accepted.

## Context

Human waits, retries, schedules, and visible workflow control benefit from n8n, while financial decisions require deterministic, testable code.

## Decision

n8n coordinates webhooks and service calls. FastAPI and the Python domain layer own validation, policy evaluation, risk, routing, approvals, context, provenance, and reliability state transitions.

## Consequences

Workflows remain inspectable without becoming a second policy engine. API contracts are a deliberate boundary and must remain backward compatible with the source-controlled workflows.
