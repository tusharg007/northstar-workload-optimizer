# ADR 0002: PostgreSQL operational source of truth

## Status

Accepted.

## Context

Durable approvals, concurrent claims, audit evidence, and restarts require transactional state shared across processes.

## Decision

PostgreSQL owns North Star operational truth. North Star, n8n, and Metabase use separate databases and principals. SQLite remains a fast local/test mode, not the release persistence backend.

## Consequences

Transactions and row locking protect invariants. Alembic manages only `northstar`; n8n and Metabase manage their own application schemas.
