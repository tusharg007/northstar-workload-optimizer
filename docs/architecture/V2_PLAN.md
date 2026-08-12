# North Star v2 Implementation Plan

Status: **PLANNED FOR V2 — PLAN ONLY**. No item in this document is implemented
by Gate 0.

The current working baseline remains the compatibility reference. Each gate is
intended to be independently reviewable, testable, and reversible before the
next gate starts.

## Non-negotiable architectural constraints

1. n8n owns workflow orchestration.
2. FastAPI/Python owns deterministic domain logic.
3. PostgreSQL will own durable operational state.
4. Analytics and BI must not mutate operational truth.
5. LLMs must not make final financial-policy decisions.
6. Privileged write actions must be deterministic and/or human-governed.
7. MCP, if retained, is an interface to governed capabilities, not the workflow
   engine.
8. Voice, if added, is an interface, not a second source of business logic.
9. Existing ETL, Power BI/analytics, proposal, diagrams, notebooks, and business
   analysis assets must not be destroyed.
10. No LangGraph or multi-agent architecture will be added to North Star.

## Gate sequence

```mermaid
flowchart LR
    G0["G0 Baseline"] --> G1["G1 PostgreSQL"]
    G1 --> G2["G2 n8n architecture"]
    G2 --> G3["G3 HITL + reliability"]
    G3 --> G4["G4 Context + provenance"]
    G4 --> G5["G5 Evaluations"]
    G5 --> G6["G6 Metabase"]
    G6 --> G7["G7 MCP"]
    G7 --> G8["G8 Voice"]
    G8 --> G9["G9 Packaging / CI / release"]
```

Optional interface gates G7 and G8 may be deferred without changing the
operational core. Every gate begins only after the preceding required gate's
acceptance criteria pass.

## G1 — PostgreSQL foundation

**Purpose.** Make PostgreSQL the durable operational source of truth while
preserving current API behavior. Introduce SQLAlchemy 2.x repositories and
Alembic migrations, including idempotency keys, workflow correlation IDs, and
decision provenance fields. Keep the analytical database logically separate.

**Files/components affected.** New database configuration, SQLAlchemy models and
repositories, Alembic environment and initial migrations, FastAPI dependency
wiring, persistence contract tests, local database migration documentation, and
an explicit one-time SQLite-to-PostgreSQL demo-data migration utility if needed.
`etl/` and `data/northstar.db` remain outside the operational repository.

**Acceptance criteria.** A clean PostgreSQL instance migrates from zero to head;
all Gate 0 API contracts pass against PostgreSQL; duplicate idempotency keys do
not create duplicate operational records; restart persistence and approval
transitions pass; analytical jobs cannot write operational tables; migration
upgrade/downgrade behavior is tested; SQLite baseline data is either preserved
by an explicit migration or deliberately left intact and documented.

**Main risks.** Schema design prematurely encoding workflow details, SQLite and
PostgreSQL behavioral differences, timestamp/time-zone errors, duplicate events,
loss of existing demo state, and accidentally coupling analytics queries to the
operational schema.

**Rollback/compatibility.** Retain the Gate 0 SQLite files untouched; keep the
public HTTP contract stable; select the repository through explicit
configuration during the transition; take a backup before any data migration;
document the last reversible migration revision. Do not run destructive ETL
operations against PostgreSQL.

## G2 — n8n workflow architecture

**Purpose.** Establish n8n as the professional workflow control plane with
environment-aware endpoints, explicit correlation propagation, deterministic
FastAPI calls, and versioned importable workflows.

**Files/components affected.** Versioned n8n workflow JSON, environment/config
templates, webhook schemas, correlation and idempotency headers/body fields,
FastAPI integration boundaries, and workflow contract tests.

**Acceptance criteria.** Workflows import without manual repair in the supported
local environment; dev/test/prod base URLs are supplied without prohibited n8n
expressions; every run carries a stable correlation ID and idempotency key;
intake and approval flows preserve Gate 0 responses; no third-party credentials
are required for baseline tests; ownership boundaries are documented.

**Main risks.** n8n version/export drift, configuration access restrictions,
duplicate webhook deliveries, environment-specific URLs, and business rules
leaking into workflow expressions.

**Rollback/compatibility.** Preserve the two Gate 0 workflow exports and webhook
paths; version new workflows separately; allow a controlled switch back to the
baseline workflows; keep deterministic rules in Python throughout migration.

## G3 — Human approval and reliability

**Purpose.** Make approval durable and operable with explicit human tasks, SLA
timers, escalation, bounded retries, and dead-letter handling.

**Files/components affected.** Operational approval/task tables and migrations,
n8n approval/retry/escalation workflows, deterministic decision endpoints,
worker-safe status transitions, operational runbooks, and failure-injection
tests.

**Acceptance criteria.** Approval tasks survive process restarts; decisions are
idempotent and auditable; unauthorized or invalid transitions are rejected;
timeouts escalate according to versioned policy; retries are bounded with
backoff; exhausted failures enter a queryable dead-letter state; replay does not
duplicate financial decisions; recovery procedures are demonstrated.

**Main risks.** Double decisions, retry storms, race conditions, orphaned human
tasks, timer drift, and privilege escalation through workflow callbacks.

**Rollback/compatibility.** Use additive schema migrations and feature flags;
keep the Gate 0 synchronous approval path available only for controlled rollback;
never delete decision history; provide pause/drain/replay procedures for n8n
executions.

## G4 — Governed context and decision provenance

**Purpose.** Add a governed registry for policies, business definitions,
ownership, trust/freshness signals, and versioned context. Persist exactly which
inputs and policy versions produced each deterministic outcome.

**Files/components affected.** Policy/context schemas and migrations, a
deterministic policy resolution service, provenance records, administrative
import/validation tooling, ownership metadata, freshness jobs, and read APIs.

**Acceptance criteria.** Policies are immutable once used or changes create a
new version; effective dates and owners are required; every decision references
its policy version and normalized inputs; stale/untrusted context is visible and
can deterministically block privileged action; LLM output cannot override final
financial rules; provenance is reconstructable end to end.

**Main risks.** Conflicting policy versions, unclear ownership, mutable history,
silent stale context, ambiguous business definitions, and introducing an
unreviewed rules engine.

**Rollback/compatibility.** Seed a version representing Gate 0 behavior; retain
raw inputs and earlier decisions; roll back by selecting the prior active policy
version, never by rewriting provenance; support a read-only context mode during
cutover.

## G5 — Evaluation harness

**Purpose.** Create repeatable regression, policy, workflow, reliability, and
interface evaluations before optional AI-facing capabilities expand.

**Files/components affected.** Versioned evaluation datasets, deterministic
expected outcomes, API/workflow integration harnesses, database fixtures,
failure scenarios, scoring/report scripts, and CI-ready commands.

**Acceptance criteria.** Gate 0 normal, suspicious, invalid, persistence,
approval, and explanation cases remain green; duplicate, retry, SLA, provenance,
and policy-version cases have expected outcomes; evaluation data contains no
secrets or uncontrolled personal data; results are machine-readable and
reproducible from a clean environment; regression thresholds block release.

**Main risks.** Tests mirroring implementation bugs, unstable fixtures,
production-data leakage, overly broad mocked coverage, and metrics that hide
financially significant failures.

**Rollback/compatibility.** Evals are additive and do not mutate production
state; retain previous datasets and result formats; keep the Gate 0 pytest suite
as an independent compatibility signal.

## G6 — Metabase

**Purpose.** Provide operational and contextual dashboards without granting BI
tools authority to mutate operational truth.

**Files/components affected.** Read-only database role/views, curated metrics and
business definitions, Metabase provisioning/configuration, dashboards for
workflow health, approvals, SLA, dead letters, policy versions, and freshness,
plus access documentation.

**Acceptance criteria.** Metabase connects with read-only credentials; dashboard
queries cannot write operational tables; displayed definitions match the
governed registry; freshness and lineage are visible; representative dashboard
queries meet agreed latency; no sensitive fields are exposed beyond their
intended audience.

**Main risks.** Expensive queries on operational tables, metric-definition drift,
excessive data access, confusing operational and analytical truth, and dashboard
coupling to unstable schemas.

**Rollback/compatibility.** Use versioned read-only views as the compatibility
layer; removing Metabase must not affect transaction processing; preserve
existing Power BI/analytics assets and keep them isolated from operational
writes.

## G7 — Governed MCP interface (optional)

**Purpose.** Decide whether to retain MCP and, if retained, expose only governed
capabilities through the current official Python MCP SDK. MCP remains an
interface; n8n remains the workflow engine.

**Files/components affected.** Existing `mcp_server/`, capability allowlists,
authentication/authorization integration, audited tool schemas, correlation and
provenance propagation, transport configuration, error contracts, and MCP evals.

**Acceptance criteria.** A keep/remove decision is documented; retained tools
use the supported SDK line and Inspector development workflow; read and write
capabilities are least-privileged; privileged writes route through deterministic
and/or human-governed paths; timeouts and safe error handling pass; no tool can
bypass n8n or policy enforcement; tool actions are correlated and auditable.

**Main risks.** Treating MCP as an orchestrator, over-broad tool authority,
transport exposure, prompt-driven privilege misuse, duplicated business logic,
and SDK/API drift.

**Rollback/compatibility.** Keep MCP optional and separately deployable; preserve
HTTP APIs and n8n workflows as the stable core; disable write tools independently;
retain the Gate 0 five-tool contract until a versioned replacement is accepted.

## G8 — Voice operations interface (optional)

**Purpose.** Add a LiveKit-based voice interface only if there is a validated
operations use case. Voice translates user intent into governed capabilities and
never owns business rules or durable truth.

**Files/components affected.** Separate voice adapter/service, LiveKit session
configuration, identity and consent controls, governed MCP/HTTP client boundary,
confirmation UX, transcripts/audit metadata, and voice-specific evaluations.

**Acceptance criteria.** Voice is optional and failure-isolated; sensitive or
privileged actions require explicit confirmation and deterministic/human
governance; identity and authorization are enforced outside the model; every
action maps to an existing versioned capability and correlation ID; transcript
retention and consent are documented; text-only operations remain complete.

**Main risks.** Speech recognition errors, mistaken approvals, identity spoofing,
privacy/retention exposure, latency, model hallucination, and creation of a
second business-logic path.

**Rollback/compatibility.** Disable the adapter without changing workflows or
state; default to read-only capabilities during rollout; preserve text/UI
alternatives; never store authoritative decisions only in voice-session state.

## G9 — Packaging, CI, and release

**Purpose.** Make the approved architecture reproducible and releasable with
Docker Compose, dependency locking, automated migrations, CI regression gates,
security checks, backups, and operator runbooks.

**Files/components affected.** Container definitions, Compose services and
health checks, locked Python/Node dependencies, environment templates, CI
workflows, migration and seed jobs, release/version metadata, backup/restore and
incident runbooks, observability configuration, and release evidence.

**Acceptance criteria.** A clean machine can start the supported stack with one
documented Compose workflow; health checks gate dependencies; migrations run
safely and exactly once; unit, contract, integration, workflow-import, eval, and
security checks pass in CI; secrets are not committed; backup/restore and
rollback are rehearsed; release artifacts are versioned and traceable.

**Main risks.** Container/local behavior differences, unpinned supply-chain
changes, unsafe automatic migrations, secret leakage, flaky integration tests,
and a release process that cannot restore operational state.

**Rollback/compatibility.** Publish immutable versioned images and workflow
exports; maintain a compatibility matrix and database backup for every release;
support rollback to the previous application/workflow version when its schema is
compatible; use expand/migrate/contract database changes for zero-loss rollback.

## Gate 1 entry recommendation

Begin with a schema-and-migration design task, not code deployment: specify the
PostgreSQL operational data model, repository boundary, idempotency semantics,
correlation identifiers, provenance requirements, and a reversible migration
path from `northstar_runtime.db`. Review and accept that design against every
Gate 0 contract before implementing G1.
