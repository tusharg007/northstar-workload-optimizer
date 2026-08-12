# Gate 1 — PostgreSQL Operational Foundation

Status: **CURRENT IMPLEMENTED** on branch `feat/postgres-foundation`.

Gate 1 replaces direct operational `sqlite3` access with a synchronous
SQLAlchemy 2.x persistence boundary. PostgreSQL through psycopg 3 is the target
durable source of truth. SQLite remains a compatible test backend and local
fallback. The analytical ETL database `data/northstar.db` remains separate and
unchanged.

## Why the operational store changed

The Gate 0 SQLite table was sufficient for a single-machine interview demo but
could not provide a migration history, portable JSON typing, workflow-run audit
records, immutable approvals, or reliable idempotency. Gate 1 introduces those
foundations without changing the existing JSON response shapes or deterministic
expense rules.

The current public fields map to persistence as follows:

| Public field | Persistence source |
|---|---|
| `expense_id` | `expenses.expense_id` |
| `input_payload` | `expenses.input_payload` |
| `result` | `expenses.processing_result` |
| `status` | `expenses.status` |
| `risk_level` | `expenses.risk_level` |
| `approver_role` | `expenses.approver_role` |
| `decision` | `expenses.current_decision` |
| `decided_by` | `expenses.decided_by` |
| `decision_comment` | `expenses.decision_comment` |
| `decided_at` | `expenses.decided_at` |
| `created_at`, `updated_at` | `expenses.created_at`, `expenses.updated_at` |
| `anomaly_flags` | derived from `processing_result.anomaly.flags` |
| `message` | derived by FastAPI from current status and approver role |

## Repository boundary

`app/db/session.py` owns engines and explicit session/transaction scopes.
`app/db/models.py` defines only operational tables. Concrete repositories under
`app/db/repositories/` own queries and state transitions. FastAPI routes contain
no SQL, and `automation/automation_flow.py` remains independent of SQLAlchemy.

`app/runtime_store.py` is retained as a small Gate 0 compatibility facade. Its
normal runtime path delegates to `WorkflowRepository`; it no longer uses raw
`sqlite3`.

## Schema

```mermaid
erDiagram
    EXPENSES ||--o{ WORKFLOW_RUNS : has
    WORKFLOW_RUNS ||--o{ WORKFLOW_EVENTS : records
    EXPENSES ||--o{ WORKFLOW_EVENTS : concerns
    EXPENSES ||--o{ APPROVAL_TASKS : requires
    WORKFLOW_RUNS ||--o| APPROVAL_TASKS : creates
    APPROVAL_TASKS ||--o| APPROVAL_DECISIONS : resolves
    EXPENSES ||--o{ APPROVAL_DECISIONS : history
    WORKFLOW_RUNS ||--o{ APPROVAL_DECISIONS : traces

    EXPENSES {
        int id PK
        string expense_id UK
        numeric amount
        json input_payload
        json processing_result
        string status
        string payload_hash
        datetime created_at
        datetime updated_at
    }
    WORKFLOW_RUNS {
        uuid_string id PK
        string correlation_id
        string expense_id FK
        string idempotency_key UK
        string source_system
        string status
    }
    WORKFLOW_EVENTS {
        int id PK
        uuid_string workflow_run_id FK
        int sequence_number
        string event_type
        json payload
    }
    APPROVAL_TASKS {
        uuid_string task_id PK
        string expense_id FK
        uuid_string workflow_run_id FK
        string approver_role
        int approval_level
        string status
    }
    APPROVAL_DECISIONS {
        uuid_string decision_id PK
        uuid_string approval_task_id FK
        string decision
        string decided_by
        datetime decided_at
    }
```

`expense_id`, workflow idempotency keys, one task per workflow run, one decision
per task, and `(workflow_run_id, sequence_number)` are database-enforced
uniqueness contracts. Monetary values use `Numeric(18, 2)`. JSON uses SQLAlchemy
`JSON` with a PostgreSQL `JSONB` dialect variant. Application timestamps are
UTC-aware; the custom type restores UTC tzinfo after SQLite reads.

## Transaction boundaries

Successful expense processing commits one transaction containing:

- the materialized expense;
- one workflow run;
- its ordered workflow events;
- one pending approval task when review is required.

Successful approval commits one transaction containing:

- an immutable approval decision;
- approval task status;
- materialized expense status and decision fields;
- workflow run status;
- an `APPROVAL_DECIDED` event.

Exceptions roll back the entire session transaction. Tests inject a failure
after the expense/run are staged and prove no partial rows remain.

## Idempotency semantics

`POST /api/expenses/process` accepts optional `Idempotency-Key`.

- Supplied keys are used exactly.
- An omitted key is `api:{expense_id}:{sha256}`, where SHA-256 is calculated
  from canonical JSON (sorted keys, compact separators, UTF-8).
- Same key and payload returns the already-persisted state without running the
  domain pipeline or creating another run/task.
- Same key with different payload returns HTTP 409.
- Same `expense_id` with a materially different payload returns HTTP 409.
- Replaying after approval returns the approved materialized state and does not
  clear decision metadata.

The decision endpoint is also retry-safe. An identical callback after task
completion returns the current state and does not add a second history row. A
different callback after completion returns HTTP 409. One decision per approval
task is additionally enforced by a unique constraint.

## Correlation IDs

`POST /api/expenses/process` accepts optional `X-Correlation-ID`. It must be
1–128 characters and use the bounded identifier character set enforced by
FastAPI. If absent, the application generates a UUID. The selected value is
stored on `workflow_runs` and returned in the `X-Correlation-ID` response header.
It is deliberately not added to the frozen JSON response.

On idempotent replay, the original persisted correlation ID is returned even if
the retry supplies a different value. Events trace to the correlation ID through
their workflow run.

## Approval persistence

Processing creates one `PENDING` task for `PENDING_APPROVAL` or `ESCALATED`
expenses. A decision updates the task to `APPROVED` or `REJECTED`, materializes
the same external status on `expenses`, and appends an immutable decision row.
`due_at` is present only as a future schema field; Gate 1 implements no SLA
engine.

## Legacy SQLite migration

The safe standalone command is dry-run by default:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_runtime_sqlite.py
```

An explicit write and separate target are required:

```powershell
.\.venv\Scripts\python.exe scripts\migrate_runtime_sqlite.py `
  --source data\northstar_runtime.db `
  --target-url "postgresql+psycopg://northstar:northstar@localhost:5432/northstar" `
  --write
```

The script opens the legacy SQLite file read-only, validates its table/columns
and JSON, prints counts, never deletes or updates it, and imports all rows in one
target transaction. Reruns skip matching rows. Conflicting business IDs abort
and roll back. Synthetic records are explicitly labeled
`source_system="legacy_sqlite_migration"` and contain only a
`LEGACY_STATE_IMPORTED` event; the script does not invent historical steps.

For the exact default SQLite URL, `RuntimeStore` detects a preserved
`runtime_expenses` table and copies its rows idempotently into the new tables.
The legacy table and rows remain untouched. This makes an existing Gate 0 local
database immediately readable after the upgrade.

## PostgreSQL versus SQLite

| Concern | PostgreSQL | SQLite fallback/tests |
|---|---|---|
| JSON | JSONB | JSON |
| Concurrency | Target multi-connection operational backend | Small local/single-process use |
| Schema lifecycle | Alembic before app start | Auto-create for test/demo compatibility; Alembic also supported |
| Money | Numeric(18,2) | Numeric-compatible Decimal round trip |
| Time zone | Native timezone-aware timestamps | UTC tzinfo normalized by application type |
| Foreign keys | Enforced | Enabled per connection with `PRAGMA foreign_keys=ON` |

Select the database with `NORTHSTAR_DATABASE_URL`. The safe default is
`sqlite:///data/northstar_runtime.db`. The analytical `northstar.db` must never
be used as this URL.

## Alembic

Alembic reads `NORTHSTAR_DATABASE_URL`; credentials are not checked in.

```powershell
$env:NORTHSTAR_DATABASE_URL="sqlite:///data/northstar_runtime_g1.db"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic check
.\.venv\Scripts\python.exe -m alembic downgrade base
```

PostgreSQL uses the same commands with a `postgresql+psycopg://` URL.

## Verified test matrix

| Area | SQLite status | PostgreSQL status |
|---|---|---|
| Gate 0 API/domain contracts | Verified | Verified on PostgreSQL 16.14 |
| Schema/repository/JSON/timezone | Verified | Verified, including actual JSONB catalog types |
| Processing transaction rollback | Verified | Verified |
| Idempotency/conflicts/decision preservation | Verified | Verified, including concurrent callers |
| Correlation persistence/header | Verified | Verified |
| Approval/history/duplicate callback | Verified | Verified, including competing decisions |
| Event sequence/uniqueness | Verified | Verified |
| Legacy dry-run/write/replay | Verified | Verified with the three-row Gate 0 source |
| Alembic upgrade/check/downgrade | Verified | Verified against the live server |

The PostgreSQL contract test is included and runs when
`NORTHSTAR_TEST_POSTGRES_URL` is supplied. It remains skipped otherwise so the
normal SQLite suite does not require PostgreSQL.

## PostgreSQL Runtime Verification

Gate 1.5 verified the implementation against **PostgreSQL 16.14 (Debian
16.14-1.pgdg13+1)** in a disposable `postgres:16` container named
`northstar-g1-postgres-test`. Docker Desktop Client/Server 29.6.2 used the
`desktop-linux` context. The database was exposed only on
`127.0.0.1:55432`; the unrelated listener on port 5432 was untouched. The
container used Docker's anonymous writable layer and was removed after the
verification, with no named volume created.

Verified results:

- Alembic upgraded from base to `20260812_0001`, reported no model drift,
  downgraded to base, and upgraded again. PostgreSQL catalog queries confirmed
  all five operational tables plus `alembic_version`, every required foreign
  key and unique constraint, and the expected indexes.
- `input_payload`, `processing_result`, and event `payload` were confirmed as
  actual PostgreSQL `jsonb` columns.
- Seven PostgreSQL-specific contracts passed: normal and suspicious processing,
  reads and deterministic explanation, fresh-session persistence, approval and
  rejection, explicit and derived idempotency, correlation persistence,
  immutable decision history, event/task persistence, and transactional
  rollback.
- The three concurrency contracts were repeated five times. Simultaneous
  identical submissions produced one expense, run, and task with two safe HTTP
  results. Simultaneous identical approvals produced one immutable decision and
  two `APPROVED` results. Competing approve/reject calls produced one winner and
  one HTTP 409, with expense, task, and history agreeing on the winner.
- A real PostgreSQL run exposed one bug: the duplicate approval caller could
  return a stale pre-lock expense state. Gate 1.5 fixed this by acquiring a
  `SELECT ... FOR UPDATE` lock on the materialized expense before resolving its
  task. The focused concurrency suite then passed repeatedly.
- Forced failures during processing and approval left no partial state.
- The legacy migration dry run left PostgreSQL empty. The first write imported
  all three legacy rows; the second imported zero and skipped three. JSONB,
  `Numeric(18,2)`, UTC timestamps, decision metadata, and
  `source_system="legacy_sqlite_migration"` were verified. The source SQLite
  SHA-256 was identical before and after.
- Real Uvicorn HTTP verification passed health, suspicious `ESCALATED` /
  `CRITICAL` processing, persisted expense/run/five events/task, approval,
  persisted decision/sixth event, and an `APPROVED` read after restarting
  FastAPI against the same PostgreSQL database.
- The independent SQLite regression remained green. Repeated application
  startup over a legacy SQLite file preserved decision metadata and timestamps
  and did not duplicate or rewrite imported rows.
- The final combined suite, with the PostgreSQL URL enabled, completed with
  `38 passed`. Compilation, dependency integrity, Alembic model alignment, n8n
  JSON/import checks, MCP registration/startup, and Git whitespace checks also
  passed.

## Known limitations

- No authentication or authorization is introduced in Gate 1.
- Approval decisions use narrow row-level locks on the expense and actionable
  task. Broader retry/deadlock policy remains future operational work.
- No reprocessing contract exists; materially changed payloads are rejected.
- No retry/DLQ, SLA processor, outbox, context registry, or provenance graph is
  implemented.
- SQLite schema auto-creation is compatibility behavior, not the PostgreSQL
  deployment procedure.
- Legacy event history is intentionally limited because the old table stored
  materialized state rather than factual event chronology.

## What Gate 2 may assume

Gate 2 may assume stable public endpoints, optional idempotency/correlation
headers, transactional processing/approval repositories, durable workflow runs
and ordered events, and PostgreSQL-ready Alembic migrations. It must preserve
these contracts while redesigning n8n orchestration. Gate 2 must not move
deterministic business rules into n8n.
