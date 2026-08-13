# Interview demo script

## Before the interview

```powershell
Copy-Item .env.example .env
# Replace every change-me value in .env.
.\.venv\Scripts\python.exe scripts\release_check.py
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

Keep the n8n editor at `http://127.0.0.1:5679`, Metabase at `http://127.0.0.1:3000`, and FastAPI docs at `http://127.0.0.1:8000/docs` open. The verifier creates a unique expense and prints its ID.

## Five-minute demo

1. **Architecture (40 seconds).** Show the diagram in `FINAL_ARCHITECTURE.md`: n8n orchestrates; FastAPI owns deterministic decisions; PostgreSQL owns truth; Metabase is read-only; MCP is a governed interface.
2. **Suspicious expense (45 seconds).** POST `demo_payloads/suspicious_expense.json` to `http://127.0.0.1:5679/webhook/northstar-expense`. Point out `ESCALATED`, `CRITICAL`, and `Finance Director + Compliance`.
3. **Durable approval (50 seconds).** In n8n, show the approval orchestrator waiting. POST an approval to `/webhook/northstar-approval`; show the execution complete. Explain that the Wait state is stored in n8n's PostgreSQL database.
4. **Evidence (50 seconds).** Open `/api/provenance/expenses/{expense_id}/trace`, then `/api/provenance/decisions/{provenance_id}/verify`. Show the context/rule/risk/human evidence and `PASS` hash verification.
5. **MCP (45 seconds).** Run the official SDK Inspector with `.\.venv\Scripts\uv.exe run mcp dev mcp_server\server.py` and call a policy or decision-trace read tool. State that stdio is primary and writes still pass through n8n.
6. **Operations (40 seconds).** Show the five Metabase dashboards and mention its source role can read only approved observability views.
7. **Evaluation (30 seconds).** Show `37/37`, unsafe action rate `0/7`, provenance `23/23`, and the MCP FAST `17/17` evidence from the verified release report.

## Ten-minute technical walkthrough

Use the five-minute flow, then spend one minute each on: database separation and migrations; governed context/abstention; provenance snapshots and references; outbox leasing/retry/DLQ; deterministic evaluations; and reproducible Compose/CI bootstrap. End by naming the security debts in `SECURITY_BOUNDARIES.md` rather than claiming production readiness.

## Talk track for design questions

- **Why n8n plus FastAPI?** n8n makes waits, schedules, retries, and operator-visible orchestration explicit. Deterministic Python keeps policy logic versioned, unit-testable, and independent of workflow editing.
- **Why PostgreSQL?** Approval tasks, concurrent outbox claims, immutable evidence, and restart recovery need shared transactional state and row locking.
- **Why an outbox?** A database commit and an HTTP call cannot be atomic. Persisting intent with the business transaction prevents silent loss.
- **Why at-least-once?** Exactly-once delivery across independent systems is not a credible guarantee here. Stable delivery keys plus idempotent consumers make retries safe.
- **Why governed context?** Correct code can still make an unsafe decision from stale, uncertified, or ownerless policy context.
- **Why abstain?** When authority or bindings cannot be established, no automatic financial action is safer and more auditable than guessing.
- **Why snapshots plus references?** References connect evidence to governed entities; snapshots preserve the exact historical meaning even after newer versions exist.
- **Why deterministic evaluations?** Golden cases and explicit metrics turn safety claims into repeatable regression gates without an opaque judge.
- **Why MCP?** It gives compatible clients a discoverable governed interface while preserving existing API and n8n boundaries.
- **Why read-only Metabase?** Observability should never become an accidental mutation path or unrestricted operational-table query surface.
