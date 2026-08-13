# Gate 5 deterministic evaluation harness

Status: **IMPLEMENTED AND VERIFIED** on 2026-08-13.

## Problem and evaluation philosophy

North Star's financial decision path is deterministic, so its release benchmark
must have deterministic ground truth. Unit tests remain the implementation
contract suite. Gate 5 adds a curated system benchmark that detects changes in
decisions, risk, routing, governed context safety, provenance, idempotency, and
selected recovery behavior. It does not call pytest and rename the result.

No LLM, embedding, semantic similarity, fuzzy prose match, or subjective judge
participates. Every assertion is an exact authored expectation.

## Architecture and dataset

The flow is:

`versioned JSON cases -> strict Pydantic loader -> controlled scenario helper -> real application/API contracts -> exact assertions -> metrics/thresholds -> JSON report`

Dataset v1 has 37 cases:

| Category | Cases | Intent |
|---|---:|---|
| decision | 11 | Demo behavior, approval and receipt boundaries, future-date validation |
| risk | 8 | Exact classifications and signal outcomes |
| context_safety | 7 | Trusted path plus missing, mismatch, conflict, stale, inactive owner, expired trust |
| provenance | 3 | Automated completeness, human evidence, corruption detection/restoration |
| historical_context | 2 | v1/v2 as-of resolution and retained v1 evidence |
| idempotency | 2 | Exact replay and changed-input conflict |
| reliability | 4 | Resume/notification transient recovery, DLQ, replay |

Money thresholds use authored cent boundaries such as 499.99, 500.00, 500.01
and 74.99, 75.00, 75.01. Expected engine values are bound in the manifest and
baseline to the source-controlled policy execution manifest and risk catalog;
drift fails before case execution.

The controlled scenario enum is closed. Setup code can mutate only disposable
database state. Evaluation JSON contains no SQL, and Gate 5 adds no public
mutation or corruption endpoint.

## Profiles and isolation

FAST creates an explicitly seeded disposable SQLite database per case. It needs
neither Docker nor n8n.

POSTGRES runs Alembic through head `20260813_0005` once against disposable
PostgreSQL 16, then truncates application tables and explicitly reapplies the
context seed between cases. It does not create a container per case.

LIVE is a smaller 11-case subset over PostgreSQL, FastAPI, an isolated n8n
2.22.6 user folder, and the local notification sink. Suspicious intake, safe
abstention, approval/human evidence, exact replay, and all four reliability
fixtures cross public n8n intake. Approval evidence uses the public approval
webhook. Controlled outbox transitions temporarily require the scheduled
dispatcher to be paused; otherwise a second worker can race the evaluator for
the same lease. The isolated FastAPI process uses `0,0,0,0` retry delays so four
controlled attempts do not take six minutes. These are evaluation-isolation
settings, not workflow or production-default changes.

## Metrics and formulas

All metrics include numerator, denominator, rate, comparison direction, and
threshold. Accuracy is `correct / applicable`. Per-signal matrices use exact
boolean ground truth: TP, TN, FP, FN. Aggregate risk-signal correctness is
`sum(TP + TN) / sum(TP + TN + FP + FN)`.

Abstention uses:

| | Did abstain | Did decide |
|---|---:|---:|
| Should abstain | TP | FN (unsafe action) |
| Should decide | FP | TN |

- recall = `TP / (TP + FN)`
- precision = `TP / (TP + FP)`
- unsafe action rate = `FN / (TP + FN)`, required to equal 0

The `RISK_SCORE_CLASSIFICATION` catalog entry is classification evidence and is
intentionally never a triggered anomaly flag in the product contract. Its v1
matrix therefore has negative coverage only; the other five actionable signals
have both true and false coverage.

## Provenance completeness

An automated record is complete only when it has the provenance header; both
required policy snapshots; three relevant term snapshots; all eight evaluated
rule records; the exact six risk records; the trust evidence used; engine
identities; risk catalog hash; evidence hashes; and a valid aggregate hash.
Counts alone are insufficient: keys, identities, hashes, trust state, and the
deterministic verifier are checked. Human cases additionally require a durable
approval decision and exactly one human evidence record. Explicit legacy
unavailability remains outside general completeness unless a case requests it.

## Baseline and thresholds

`evals/baselines/v1.json` stores only stable semantics: dataset version, exact
case IDs/counts, category/profile counts, engine versions, risk catalog hash,
policy manifest, and thresholds. It excludes IDs, timestamps, durations,
correlation values, and generated database identities.

All accuracy, recall, precision, completeness, verification, idempotency, and
recovery thresholds are 1.0. Unsafe-action and logical duplicate-side-effect
rates have maximum threshold 0.0. The CLI exits non-zero for dataset errors,
case crashes, assertion/threshold failures, unsafe actions, and baseline drift.

## Verified v1 release results

| Profile | Result | Runtime | Baseline/thresholds |
|---|---:|---:|---|
| FAST | 37/37 | 20.173 s | PASS |
| POSTGRES | 37/37 | 34.854 s | PASS |
| LIVE | 11/11 | 8.303 s | PASS |

FAST and POSTGRES agreed on every applicable business outcome. Full-profile
metrics were: decision 24/24, risk level 23/23, routing 23/23, risk signals
48/48, binding 15/15, context 9/9, abstention recall 7/7, precision 7/7,
unsafe actions 0/7, provenance completeness 23/23, verification 23/23,
idempotency 2/2, transient recovery 2/2, DLQ 1/1, replay 1/1, and logical
duplicate side effects 0/4.

The FAST/POSTGRES abstention matrix was TP=7, TN=30, FP=0, FN=0. Signal
matrices were:

| Signal | TP | TN | FP | FN |
|---|---:|---:|---:|---:|
| STATISTICAL_OUTLIER | 2 | 6 | 0 | 0 |
| WEEKEND_TRANSACTION | 2 | 6 | 0 | 0 |
| SUSPICIOUS_ROUND_AMOUNT | 3 | 5 | 0 | 0 |
| MISSING_RECEIPT_HIGH_VALUE | 3 | 5 | 0 | 0 |
| POTENTIAL_DUPLICATE | 2 | 6 | 0 | 0 |
| RISK_SCORE_CLASSIFICATION | 0 | 8 | 0 | 0 |

Negative controls were also verified: a derived wrong approver expectation
exited 1 and reported routing 0/1; policy drift produced HTTP 409,
`POLICY_ENGINE_MISMATCH`, and abstention; evidence corruption made verification
FAIL, restoration made it PASS; and the clean full benchmark passed afterward.

Regression evidence: SQLite 105 passed/10 skipped; PostgreSQL 114 passed/1
skipped; evaluator tests 24 passed; n8n validator PASS with exactly ten
workflows; smoke output was `Submitted: ESCALATED risk= CRITICAL route= Finance
Director + Compliance` followed by `NORTH STAR END-TO-END DEMO: PASS`; MCP SDK
2.0.0 imported as `MCPServer` with the existing five tools; Alembic reported
head 0005 and no new operations; compileall, pip check, and diff check passed.

## Persistence decision, limitations, and future CI

No `eval_runs` or `eval_case_results` tables were added. Generated benchmark
data is release evidence, not operational financial state. JSON reports are
sufficient for Gate 5, avoid a migration and cleanup burden, minimize secrets,
and can be loaded into Gate 6 analytics later if a concrete dashboard requires
it.

Reports omit credentials, headers, resume URLs, provider bodies, and stack
traces. Current debt: the classification evidence signal has no meaningful TRUE
state; LIVE outbox transitions use an evaluator-owned lease while n8n scheduled
dispatch is paused; timing is observational only; no CI job publishes reports
yet. Gate 6 prerequisites are the Gate 5 commit, a clean tree, PostgreSQL 16,
Alembic head 0005, the source-controlled v1 baseline, and an explicit Gate 6
specification. Gate 5 does not start Gate 6.
