# ADR 0007: Read-only Metabase observability

## Status

Accepted.

## Context

Operators need visibility without granting a dashboard product access to mutate or broadly query operational tables.

## Decision

Metabase uses its own application database and a separate North Star source role with `SELECT` only on approved `observability.*` views. Dashboards and questions are reconciled by logical keys.

## Consequences

Analytics cannot become a write path. Schema changes must preserve the approved view contract and the 36-question/5-dashboard manifest.
