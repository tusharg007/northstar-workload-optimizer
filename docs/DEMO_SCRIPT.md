# Interview demo script

## 30-second version

I built North Star, a governed expense-operations reference system. n8n owns visible orchestration and durable human waits, while FastAPI and versioned Python logic make deterministic policy, risk, and routing decisions against authoritative context. PostgreSQL preserves operational truth, outbox recovery, and immutable provenance; Metabase observes through a read-only boundary; and MCP exposes trusted reads and n8n-routed actions. The release is backed by exact deterministic benchmarks and clean-start/restart verification rather than AI-generated policy decisions.

## Elevator pitch

North Star demonstrates how I would automate a governed enterprise decision without hiding policy inside a workflow or an LLM. It resolves certified policy and business context, executes deterministic expense rules, and uses n8n for visible orchestration and durable human approval. PostgreSQL stores operational truth, immutable decision evidence, and a transactional outbox for recoverable at-least-once effects. A versioned evaluation harness release-gates safety and provenance behavior. Metabase provides read-only operational views, while an official MCP interface lets compatible clients inspect trusted context and invoke existing n8n workflows without bypassing controls. The complete local stack is reproducible from source.

## Before the interview

```powershell
Copy-Item .env.example .env
# Replace every change-me value with a disposable local secret.
.\.venv\Scripts\python.exe scripts\release_check.py
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

Keep n8n at `http://127.0.0.1:5679`, Metabase at `http://127.0.0.1:3000`, and FastAPI docs at `http://127.0.0.1:8000/docs` open. Use only clearly synthetic expense and approver identities.

Prepare a unique suspicious expense and submit it through the public n8n webhook:

```powershell
$expense = Get-Content -Raw demo_payloads\suspicious_expense.json | ConvertFrom-Json
$expense.expense_id = "DEMO-INTERVIEW-$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"
$expense.employee_name = "Jordan Demo"
$expenseId = $expense.expense_id
$submitted = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5679/webhook/northstar-expense -ContentType application/json -Body ($expense | ConvertTo-Json -Depth 10)
$submitted | Format-List expense_id,status,risk_level,approver_role,anomaly_flags
```

Prepare the approval but do not run it until the waiting execution is visible:

```powershell
$decision = @{expense_id=$expenseId; decision="approve"; approver="Demo Finance Director"; comment="Synthetic interview demonstration"} | ConvertTo-Json
$approved = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:5679/webhook/northstar-approval -ContentType application/json -Body $decision
$approved | Format-List expense_id,status,decision,decided_by
```

Fetch explanation and provenance after approval:

```powershell
$explanation = Invoke-RestMethod "http://127.0.0.1:8000/api/expenses/$expenseId/explanation"
$trace = Invoke-RestMethod "http://127.0.0.1:8000/api/provenance/expenses/$expenseId/trace"
$provenanceId = $trace.provenance_id
$verification = Invoke-RestMethod "http://127.0.0.1:8000/api/provenance/decisions/$provenanceId/verify"
$explanation
$verification
```

## Five-minute demo

1. **0:00–0:30 — Problem and architecture.** Show the diagram in [`FINAL_ARCHITECTURE.md`](architecture/FINAL_ARCHITECTURE.md). State the ownership boundaries: n8n orchestrates, deterministic Python decides, PostgreSQL owns truth, Metabase is read-only, and MCP cannot bypass writes.
2. **0:30–1:20 — Suspicious expense.** Run the prepared submission. Highlight `ESCALATED`, `CRITICAL`, and `Finance Director + Compliance`; explain that these are deterministic results.
3. **1:20–2:00 — Durable orchestration.** Open the n8n Approval Orchestrator execution and point to the Wait state persisted by n8n in PostgreSQL.
4. **2:00–2:45 — Human decision.** Run the prepared approval. Show `APPROVED`, the synthetic approver evidence, and the n8n execution completing.
5. **2:45–3:30 — Governed evidence.** Run the explanation/trace/verify commands. Point out policy version, context trust, exact risk signals, human evidence, and hash `PASS`.
6. **3:30–4:15 — MCP boundary.** In MCP Inspector, use a policy lookup or decision-trace read. Explain that write tools still route through n8n.
7. **4:15–4:45 — Read-only operations.** Show one populated Metabase dashboard, preferably Operations Overview. Mention the dedicated role and approved-view boundary.
8. **4:45–5:00 — Regression proof.** Show the Gate 9 evidence: Gate 5 `37/37`, unsafe actions `0/7`, and MCP FAST `17/17`.

## Ten-minute technical walkthrough

Use the five-minute sequence, then add:

- The outbox event/attempt lifecycle and why leases, retry, DLQ, replay, and idempotency produce recoverable at-least-once delivery.
- A governed-context trust or policy-binding case that causes abstention.
- Snapshot/reference provenance and historical policy meaning.
- MCP resources and the minimized error/output contract.
- Governed Context Health or Reliability & Recovery in Metabase.
- The exact distinction between pytest contracts, deterministic benchmarks, and fresh-stack/restart release evidence.

Do not try to show every workflow, dashboard, or test.

## Architecture story

I started with deterministic expense processing, then moved operational truth into PostgreSQL and separated orchestration from domain logic. Approvals became durable, and a transactional outbox closed the database/HTTP crash window. Governed context then established which policies and definitions were authoritative; decisions were bound to that context and stored with immutable provenance. Versioned deterministic evaluations turned those safety properties into release gates. Finally, read-only Metabase views and a governed MCP provider exposed operational insight and controlled client access, and Compose/locked dependencies made the complete system reproducible.

## Talk track for design questions

- **Why n8n?** It makes waits, schedules, retries, and operator-visible orchestration inspectable without turning the workflow canvas into a policy engine.
- **Why keep business logic out of n8n?** Versioned deterministic Python is easier to test, review, and regression-gate; workflows remain coordination code.
- **Why FastAPI?** It provides a typed, explicit boundary around domain operations and keeps n8n, MCP, and tests on the same contracts.
- **Why PostgreSQL?** Durable approvals, concurrent claims, immutable evidence, migrations, and restart recovery need shared transactions and row locking.
- **Why a transactional outbox?** A database commit and external HTTP call cannot be atomic. Persisting effect intent with business state prevents silent loss.
- **Why at-least-once rather than exactly-once?** Independent systems cannot credibly guarantee exactly-once delivery here. Stable delivery keys and idempotent effects make retries safe.
- **How does idempotency work?** Request keys bind to a canonical payload hash; changed reuse conflicts, exact replay returns stored truth, and outbox delivery keys deduplicate effects.
- **Why governed context?** Correct code is still unsafe if the policy definition, owner, certification, freshness, or effective version is unknown.
- **What causes abstention?** Missing, conflicting, stale, uncertified, ownerless, or engine-mismatched required context stops the decision before persistence.
- **How is policy drift detected?** Structured engine parameters are compared with the certified governed policy binding; mismatch produces a deterministic abstention.
- **Why immutable provenance?** A final status cannot prove which context, rule, signal, engine, or human action produced it. Snapshots, references, and hashes preserve that evidence.
- **Why deterministic evaluations?** Versioned golden cases and exact metrics turn policy and safety claims into reproducible gates without an opaque judge.
- **Why MCP?** It gives compatible AI clients a discoverable, minimized interface to trusted context and existing controlled actions.
- **Why are MCP writes routed through n8n?** The client must not bypass the established orchestration, HITL, idempotency, audit, and recovery path.
- **Why is Metabase read-only?** Observability should never become a mutation path or unrestricted operational-table query surface.
- **What would change for production?** Add authenticated identity, approver-bound RBAC, MCP OAuth, TLS/ingress, managed secrets, a real idempotent notification provider, cloud network controls, backups/HA, SLO monitoring, and broader representative evaluations.

## Limitations answer

This release proves the architecture locally, not production readiness. My next work would be identity-bound authentication and RBAC, MCP OAuth, TLS and network policy, managed secrets and rotation, a real notification provider with idempotency support, backup/restore and HA, production SLO telemetry, and larger representative evaluation datasets. Voice and additional agents are not required to harden the core system.
