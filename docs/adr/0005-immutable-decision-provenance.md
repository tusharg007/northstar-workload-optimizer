# ADR 0005: Immutable decision provenance

## Status

Accepted.

## Context

A final status alone cannot explain which policy, context, rule, risk signal, engine version, or human evidence produced a decision.

## Decision

Persist canonical immutable evidence with each decision and hash the canonical representation. Expose trace and verification APIs without rewriting historical evidence.

## Consequences

Decisions can be explained and tampering detected. References link current entities while snapshots preserve historical meaning.
