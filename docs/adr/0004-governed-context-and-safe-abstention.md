# ADR 0004: Governed context and safe abstention

## Status

Accepted.

## Context

Correct policy logic is unsafe when its definition, ownership, certification, or freshness is unknown.

## Decision

Resolve versioned policy and business-term context before a policy-dependent decision. If trust checks fail or engine bindings disagree, abstain without persisting a financial decision.

## Consequences

Context failures become explicit, testable outcomes. Certified versions remain immutable and changes require new versions.
