# ADR 0003: Transactional outbox and at-least-once delivery

## Status

Accepted.

## Context

Writing business state and invoking an external system cannot be made atomic with a normal database transaction.

## Decision

Persist external-effect intent in the same transaction as the business change, then deliver through leased outbox workers with retries, dead letters, replay, and reconciliation.

## Consequences

Committed effects are not silently lost. Delivery is at least once, not exactly once, so delivery keys and consumers must be idempotent.
