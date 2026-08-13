# ADR 0006: Deterministic evaluation harness

## Status

Accepted.

## Context

Safety and policy regressions need repeatable evidence rather than subjective demonstrations.

## Decision

Use versioned golden cases, deterministic metrics, immutable baselines, FAST and PostgreSQL profiles, and explicit negative controls. No LLM judge participates.

## Consequences

Regressions fail reproducibly in CI. Dataset changes require a new version and reviewed baseline rather than silent edits.
