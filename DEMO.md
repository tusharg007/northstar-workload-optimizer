# North Star Automation v2 Demo

This runbook starts the complete local path:

`MCP client -> n8n public workflow -> n8n service workflow -> FastAPI -> Python pipeline -> operational database`

Approval decisions return through a second n8n webhook. The analytical
`data/northstar.db` is not used or changed by this demo.

## 1. One-Time Windows Setup

Open PowerShell in the repository root:

```powershell
python --version
node --version
npx.cmd --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npx.cmd --yes n8n --version
```

These commands require Python 3.10+ and Node.js. `uv` is installed from
`requirements.txt`. The runbook deliberately uses explicit `.venv` executables
and `npx.cmd`, so it works even when PowerShell script execution is disabled.
Docker is not required.

## 2. Start FastAPI (Terminal 1)

```powershell
$env:NORTHSTAR_DATABASE_URL="sqlite:///data/northstar_runtime.db"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

The SQLAlchemy operational schema is created automatically for the SQLite
fallback at `data/northstar_runtime.db` and is never deleted on startup. Existing
Gate 0 `runtime_expenses` rows are copied once into the new tables while the
legacy source table remains intact. PostgreSQL deployments should run Alembic
before starting FastAPI.

To use local PostgreSQL instead:

```powershell
$env:NORTHSTAR_DATABASE_URL="postgresql+psycopg://northstar:northstar@localhost:5432/northstar"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

## 3. Start and Configure n8n (Terminal 2)

Validate, import all four workflows, and publish internal workflows before
public workflows while n8n is stopped:

```powershell
.\.venv\Scripts\python.exe scripts\validate_n8n_workflows.py
npx.cmd --yes n8n import:workflow --separate --input="n8n\workflows"
npx.cmd --yes n8n publish:workflow --id=northstarProcessExpenseService
npx.cmd --yes n8n publish:workflow --id=northstarRecordDecisionService
npx.cmd --yes n8n publish:workflow --id=northstarExpenseIntake
npx.cmd --yes n8n publish:workflow --id=northstarApprovalDecision
npx.cmd --yes n8n start
```

If n8n is already installed globally, the equivalent executable is `n8n.cmd`.
In the n8n UI, confirm four distinct workflows:

1. `North Star | 01 Expense Intake` (public).
2. `North Star | 02 Approval Decision` (public).
3. `North Star | 10 Process Expense Service` (internal).
4. `North Star | 11 Record Decision Service` (internal).
5. Confirm each internal `Runtime Configuration` node contains
   `http://127.0.0.1:8000`.
6. Confirm the production webhook URLs end in `/webhook/northstar-expense` and
   `/webhook/northstar-approval` (not `/webhook-test/`).

If n8n runs in Docker, change only the `api_base_url` field in both internal
`Runtime Configuration` nodes before publishing:

```text
http://host.docker.internal:8000
```

The workflow files contain no credential-dependent, database, or Code nodes.

## 4. Configure MCP (Terminal 3)

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

The MCP tools are `submit_expense`, `get_expense_status`,
`list_pending_approvals`, `explain_risk`, and `approve_expense`.

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

Run the automated end-to-end smoke test after both services and workflows are
active:

```powershell
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

It prints `NORTH STAR END-TO-END DEMO: PASS` only after the n8n intake,
persistence, n8n approval, and final-state checks all succeed.

## 5-Minute Interview Demo

1. Show the two public and two internal n8n workflows. Briefly point out
   normalization, orchestration context, stable-ID dispatch, runtime
   configuration, HTTP transport, service envelope, and webhook response.
2. Check FastAPI health with `Invoke-RestMethod
   http://127.0.0.1:8000/health`.
3. In MCP Inspector, call `submit_expense` with the fields from
   `demo_payloads/suspicious_expense.json`.
4. Highlight `CRITICAL` risk, deterministic anomaly flags, `ESCALATED` status,
   and routing to `Finance Director + Compliance`.
5. Call `explain_risk("DEMO-SUSPICIOUS-001")` and show that the explanation is
   deterministic rather than LLM-generated.
6. Call `list_pending_approvals()` and show the persisted expense.
7. Call `approve_expense("DEMO-SUSPICIOUS-001", "Finance Director",
   "Reviewed in interview demo")`.
8. Call `get_expense_status("DEMO-SUSPICIOUS-001")` and show `APPROVED`, the
   approver, comment, and timestamps.
9. Optionally run `.\.venv\Scripts\python.exe scripts\smoke_test.py` as a
   single-command proof of the complete n8n-to-SQLite round trip.

## Troubleshooting

- `Could not connect`: verify FastAPI is on port 8000 and n8n is on port 5678.
- n8n returns 404: activate the workflow and use `/webhook/`, not
  `/webhook-test/`.
- n8n cannot reach FastAPI from Docker: set both internal `Runtime
  Configuration` nodes to `http://host.docker.internal:8000`, republish, and
  restart n8n.
- n8n cannot call FastAPI on Windows: confirm both internal `Runtime
  Configuration` nodes still use `http://127.0.0.1:8000`.
- HTTP 422: inspect FastAPI's response; category, department, date, and amount
  are validated by the existing `ExpenseSubmission` model.

## Known Demo Limits

- Local services have no authentication or authorization.
- Decision roles are recorded but not identity-verified.
- Runtime SQLite is appropriate for a small single-machine demo, not a
  multi-worker production deployment.
- Notifications remain generated payloads; no Gmail, Slack, or Teams credentials
  are required.
