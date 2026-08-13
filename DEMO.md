# North Star Automation v2 Demo

The reproducible interview path is the Gate 9 Compose stack:

```powershell
Copy-Item .env.example .env
# Replace every change-me value in .env.
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

This automatically provisions PostgreSQL, migrations, governed context, all
ten n8n workflows, Metabase's 36 questions/five dashboards, and the demo
notification sink. It uses n8n on port 5679. See `docs\DEMO_SCRIPT.md` for the
five-minute walkthrough.

The rest of this runbook preserves the non-Docker local path:

`MCP client -> n8n public workflow -> n8n service workflow -> FastAPI -> Python pipeline -> operational database`

Approval decisions return through a second n8n webhook. The analytical
`data/northstar.db` is not used or changed by this demo.

## 1. One-Time Windows Setup

Open PowerShell in the repository root:

```powershell
python --version  # must report 3.13.9 for the verified release environment
node --version
npx.cmd --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install uv==0.12.3
.\.venv\Scripts\uv.exe pip sync --python .\.venv\Scripts\python.exe --require-hashes requirements.lock
npx.cmd --yes n8n --version
```

These commands use the release-tested Python 3.13.9 and Node.js. The runbook
deliberately uses explicit `.venv` executables
and `npx.cmd`, so it works even when PowerShell script execution is disabled.
Docker is not required.

## 2. Start FastAPI (Terminal 1)

```powershell
$env:NORTHSTAR_DATABASE_URL="sqlite:///data/northstar_runtime.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The SQLAlchemy operational schema and source-controlled governed context are
created automatically for the SQLite development fallback at
`data/northstar_runtime.db` and are never deleted on startup. Existing
Gate 0 `runtime_expenses` rows are copied once into the new tables while the
legacy source table remains intact. PostgreSQL deployments must run Alembic and
explicitly provision governed context before starting FastAPI; ordinary request
handling never seeds or mutates certified policy context.

To use local PostgreSQL instead:

```powershell
$env:NORTHSTAR_DATABASE_URL="postgresql+psycopg://northstar:northstar@localhost:5432/northstar"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_context_registry.py --write
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## 3. Start the Local Notification Sink (Terminal 2)

```powershell
.\.venv\Scripts\python.exe -m uvicorn scripts.notification_sink:app --port 9010
```

This test/demo adapter keeps notifications only in memory. Check it with
`Invoke-RestMethod http://127.0.0.1:9010/test/notifications`.

## 4. Start and Configure n8n (Terminal 3)

Validate, import all ten workflows, and publish dependencies before public
workflows while n8n is stopped:

```powershell
.\.venv\Scripts\python.exe scripts\validate_n8n_workflows.py
npx.cmd --yes n8n import:workflow --separate --input="n8n\workflows"
npx.cmd --yes n8n publish:workflow --id=northstarGlobalErrorHandler
npx.cmd --yes n8n publish:workflow --id=northstarApprovalNotificationService
npx.cmd --yes n8n publish:workflow --id=northstarReliabilityDispatcher
npx.cmd --yes n8n publish:workflow --id=northstarDeadLetterReplay
npx.cmd --yes n8n publish:workflow --id=northstarProcessExpenseService
npx.cmd --yes n8n publish:workflow --id=northstarRecordDecisionService
npx.cmd --yes n8n publish:workflow --id=northstarApprovalOrchestrator
npx.cmd --yes n8n publish:workflow --id=northstarApprovalSLAMonitor
npx.cmd --yes n8n publish:workflow --id=northstarExpenseIntake
npx.cmd --yes n8n publish:workflow --id=northstarApprovalDecision
npx.cmd --yes n8n start
```

If n8n is already installed globally, the equivalent executable is `n8n.cmd`.
In the n8n UI, confirm ten distinct workflows:

1. `North Star | 01 Expense Intake` (public).
2. `North Star | 02 Approval Decision` (public).
3. `North Star | 10 Process Expense Service` (internal).
4. `North Star | 11 Record Decision Service` (internal).
5. `North Star | 20 Approval Orchestrator` (internal durable Wait).
6. `North Star | 21 Approval Notification Service` (internal adapter).
7. `North Star | 22 Approval SLA Monitor` (scheduled).
8. `North Star | 23 Reliability Dispatcher` (scheduled/internal).
9. `North Star | 24 Dead Letter Replay` (internal only; no public webhook).
10. `North Star | 99 Global Error Handler` (Error Trigger).
11. Confirm each relevant internal `Runtime Configuration` node contains
   `http://127.0.0.1:8000`.
12. Confirm notification service contains one sink URL:
   `http://127.0.0.1:9010/notifications`.
13. Confirm the production webhook URLs end in `/webhook/northstar-expense` and
   `/webhook/northstar-approval` (not `/webhook-test/`).

If n8n runs in Docker, change only the `api_base_url` field in each relevant
`Runtime Configuration` node before publishing:

```text
http://host.docker.internal:8000
```

Also change the notification sink URL to a host/container-reachable address.
The workflow files contain no credential-dependent, database, or Code nodes.

## 5. Configure Governed MCP (Terminal 4)

```powershell
$env:NORTHSTAR_API_BASE_URL="http://127.0.0.1:8000"
$env:N8N_EXPENSE_WEBHOOK_URL="http://127.0.0.1:5678/webhook/northstar-expense"
$env:N8N_APPROVAL_WEBHOOK_URL="http://127.0.0.1:5678/webhook/northstar-approval"
$env:UV_CACHE_DIR="$PWD\.venv\uv-cache"
.\.venv\Scripts\uv.exe run mcp dev mcp_server/server.py
```

This is the official SDK's development command and opens MCP Inspector. The
server uses the stable v2 `MCPServer` API. For a client that launches a local
stdio server, the equivalent direct command is:

```powershell
.\.venv\Scripts\python.exe -m mcp_server.server
```

Local Streamable HTTP is also supported and rejects non-loopback hosts:

```powershell
.\.venv\Scripts\python.exe -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8765
```

The original five tools remain: `submit_expense`, `get_expense_status`,
`list_pending_approvals`, `explain_risk`, and `approve_expense`. Gate 7 adds
`search_policy_context`, `get_policy_version`, `get_business_term`,
`get_expense_context`, `get_decision_trace`, `get_expense_lineage`, and
`verify_decision_provenance`. Five read-only `northstar://...` resource
templates and the optional `investigate_expense` prompt are discoverable.

Stdio assumes a trusted local operator. `approve_expense` is a consequential
privileged action that still traverses n8n, the immutable FastAPI approval
transaction, human evidence, the outbox, and Wait/resume. Do not expose the
local HTTP mode to an untrusted network without a real authorization layer.

Validate the contract and run the deterministic in-memory benchmark:

```powershell
.\.venv\Scripts\python.exe scripts\validate_mcp_server.py
.\.venv\Scripts\python.exe scripts\run_mcp_evals.py --profile fast
```

## Manual Verification Commands

Health:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Submit the normal sample through n8n:

```powershell
$expense = Get-Content -Raw demo_payloads\normal_expense.json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5678/webhook/northstar-expense -ContentType "application/json" -Body $expense
```

Query durable status:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/expenses/DEMO-NORMAL-001
```

Approve through n8n:

```powershell
$decision = @{expense_id="DEMO-NORMAL-001"; decision="approve"; approver="Finance Director"; comment="Reviewed and approved"} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5678/webhook/northstar-approval -ContentType "application/json" -Body $decision
```

Run the automated end-to-end smoke test after FastAPI, the notification sink,
and all workflows are active:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

It prints `NORTH STAR END-TO-END DEMO: PASS` only after the n8n intake,
persistence, n8n approval, and final-state checks all succeed.

## Optional Metabase Observability Demo

This PostgreSQL-only view is independent of the operational demo above. In a
new PowerShell window, use local-only credentials and the Docker CLI path that
is installed with Docker Desktop:

```powershell
$env:NORTHSTAR_POSTGRES_ADMIN_PASSWORD="choose-a-local-admin-password"
$env:NORTHSTAR_METABASE_DB_PASSWORD="choose-a-distinct-readonly-password"
$env:METABASE_ADMIN_PASSWORD="choose-a-local-metabase-password"
$env:NORTHSTAR_DATABASE_URL="postgresql+psycopg://northstar:$env:NORTHSTAR_POSTGRES_ADMIN_PASSWORD@localhost:55432/northstar"
$env:METABASE_URL="http://localhost:3000"
$env:NORTHSTAR_METABASE_DB_HOST="postgres"

docker compose -p northstar-g6 -f infra\metabase\docker-compose.metabase.yml up -d postgres
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_context_registry.py --write
.\.venv\Scripts\python.exe scripts\create_metabase_readonly_role.py
.\.venv\Scripts\python.exe -m scripts.seed_observability_demo
.\.venv\Scripts\python.exe -m metabase.prepare_artifact
docker compose -p northstar-g6 -f infra\metabase\docker-compose.metabase.yml up -d metabase
.\.venv\Scripts\python.exe -m metabase.bootstrap
.\.venv\Scripts\python.exe -m metabase.live_validate
```

Open `http://localhost:3000` and show the five `North Star | ...` dashboards.
The validator executes all 36 questions and independently checks headline
results and read-only database permissions. Bootstrap is safe to rerun.

## 5-Minute Interview Demo

1. Show the ten n8n workflows. Briefly point out stable-ID dispatch, the
   non-blocking orchestrator launch, the real Wait node, notification adapter,
   scheduled SLA monitor, transactional-outbox dispatcher, internal DLQ replay,
   and Error Trigger handler.
2. Check FastAPI health with `Invoke-RestMethod
   http://127.0.0.1:8000/health`.
3. In MCP Inspector, call `submit_expense` with the fields from
   `demo_payloads/suspicious_expense.json`.
4. Highlight `CRITICAL` risk, deterministic anomaly flags, `ESCALATED` status,
   and routing to `Finance Director + Compliance`.
5. Call `explain_risk("DEMO-SUSPICIOUS-001")` and show that the explanation is
   deterministic rather than LLM-generated.
6. Call `list_pending_approvals()` and show the persisted expense.
7. Show the Approval Orchestrator waiting execution, then call
   `approve_expense("DEMO-SUSPICIOUS-001", "Finance Director",
   "Reviewed in interview demo")`.
8. Call `get_expense_status("DEMO-SUSPICIOUS-001")` and show `APPROVED`, the
   approver, comment, and timestamps.
9. Show the execution completed and query the local sink for initial and
    completion notifications.
10. Optionally show the five read-only Metabase dashboards and the successful
   `python -m metabase.live_validate` result.
11. Optionally run `.\.venv\Scripts\python.exe scripts\smoke_test.py` as a
   single-command proof of the complete n8n-to-SQLite round trip.

## Troubleshooting

- `Could not connect`: verify FastAPI is on port 8000 and n8n is on port 5678.
- n8n returns 404: activate the workflow and use `/webhook/`, not
  `/webhook-test/`.
- n8n cannot reach FastAPI from Docker: set every relevant internal `Runtime
  Configuration` node to `http://host.docker.internal:8000`, republish, and
  restart n8n.
- n8n cannot call FastAPI on Windows: confirm every relevant internal `Runtime
  Configuration` node still uses `http://127.0.0.1:8000`.
- HTTP 422: inspect FastAPI's response; category, department, date, and amount
  are validated by the existing `ExpenseSubmission` model.

## Known Demo Limits

- Local services have no authentication or authorization.
- Decision roles are recorded but not identity-verified.
- Runtime SQLite is appropriate for a small single-machine demo, not a
  multi-worker production deployment.
- `/api/internal/...` is unauthenticated and trusted-network-only in Gate 3A.
- Wait resume URLs are sensitive capability URLs and must never be shared.
- The local notification sink is volatile demo infrastructure; no Gmail,
  Slack, or Teams credentials are required.
- Automatic resume retry, global error handling, DLQ, and reconciliation are
  implemented through the Gate 3B transactional outbox. Provider-level
  exactly-once delivery is not claimed.
- Metabase is PostgreSQL-only, read-only, and optional. The committed dashboard
  version has no global filters; tested cross-card filters remain observability
  debt.
