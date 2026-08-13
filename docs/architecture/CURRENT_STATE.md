# North Star current released baseline

Status: **CURRENT IMPLEMENTED** at Gate 9 commit `1627dcbd4c89e2603e789cba47d8f32249df8c70`, verified on 2026-08-13.

This file is the concise runtime inventory. [FINAL_ARCHITECTURE.md](FINAL_ARCHITECTURE.md) explains the current boundaries, while files named `G*.md` preserve historical implementation and release evidence.

## Verified release inventory

| Area | Current baseline |
|---|---|
| Runtime | Python 3.13.9; PostgreSQL 16.14 |
| Schema | Alembic head `20260813_0006` |
| API/domain | FastAPI plus deterministic validation, risk, routing, approvals, context, provenance, and reliability |
| Orchestration | n8n 2.22.6; exactly ten workflows |
| Observability | Metabase OSS 0.63.2.7; five dashboards and 36 questions |
| MCP | Python SDK 2.0.0; 12 tools, five resource templates, one prompt; stdio and loopback Streamable HTTP |
| Tests | SQLite 122 passed/13 skipped; PostgreSQL 134 passed/1 skipped |
| Evaluations | Gate 5 FAST/PostgreSQL 37/37; MCP FAST 17/17; MCP PostgreSQL+n8n stdio 16/16 |
| Release | Fresh-volume start twice, full-stack restart persistence, and n8n waiting-approval restart passed |

## Ownership boundaries

- **n8n owns orchestration:** public webhooks, service coordination, durable approval Wait/resume, schedules, notification dispatch, reliability dispatch, DLQ replay, and global workflow error capture.
- **FastAPI/domain owns deterministic behavior:** validation, financial policy, risk signals, routing, approvals, idempotency, governed-context resolution, provenance, and reliability state transitions.
- **PostgreSQL owns operational truth:** North Star, n8n, and Metabase use separate databases and principals. SQLite remains a fast compatibility/test mode, not the release persistence backend.
- **MCP is an interface adapter:** reads use bounded FastAPI APIs; consequential writes use public n8n webhooks. It has no direct database or Wait-resume access.
- **Metabase is read-only:** `northstar_metabase_ro` can select only approved `observability.*` views and cannot read base tables or write application state.

Financial decisions do not use an LLM. Voice is intentionally deferred and optional; it is not unfinished release work.

## Write and approval path

1. A client submits an expense to `POST /webhook/northstar-expense` in n8n.
2. n8n normalizes the request and invokes FastAPI's process contract.
3. FastAPI resolves required policy/business context at one effective time and verifies ownership, certification, freshness, trust, and engine bindings.
4. Missing, conflicted, stale, untrusted, or mismatched required context returns a safe HTTP 409 abstention before a financial decision is persisted.
5. Deterministic engines perform validation, exact risk-signal evaluation, classification, and routing.
6. One transaction commits expense state, workflow/audit state, approval task when required, immutable automated provenance, and any external-effect intent.
7. Escalated work starts an n8n approval child, which registers its execution and Wait capability in PostgreSQL and waits.
8. `POST /webhook/northstar-approval` records the immutable human decision through FastAPI. A transactional outbox event resumes the waiting execution with retry/recovery support.

Capability URLs and Wait/resume URLs remain internal and are never returned through public or MCP responses.

## Reliability and evidence

The transactional outbox commits effect intent with business state. Workers reconcile, claim with leases, record attempts, retry transient failures, and dead-letter exhausted events for explicit replay. Delivery is at least once; stable delivery keys and idempotent consumers/effects make replay safe. Exactly-once external delivery is not claimed.

Each persisted automated decision includes immutable policy, business-term, rule, trust, risk-signal, and engine evidence. Later human evidence is append-only and has its own verified hash. Application verification recomputes canonical evidence hashes; Metabase reports structural completeness only.

## Governed context

The source-controlled seed provides versioned governance owners, policy definitions/versions/rules, business terms/versions, trust signals, and engine bindings. Certified versions are immutable. New meaning requires a new version, not an in-place edit. Context is currently administered from trusted source data; there is no authoring UI, interactive certification workflow, or production identity/RBAC.

## n8n inventory

| Workflow | Responsibility |
|---|---|
| `01_expense_intake` | Public expense webhook |
| `02_approval_decision` | Public approval webhook |
| `10_process_expense_service` | FastAPI process adapter |
| `11_record_decision_service` | FastAPI approval adapter |
| `20_approval_orchestrator` | Durable Wait/resume lifecycle |
| `21_approval_notification_service` | Configurable HTTP notification adapter |
| `22_approval_sla_monitor` | Scheduled reminder/escalation reservation |
| `23_reliability_dispatcher` | Reconcile, lease, deliver, and record outbox effects |
| `24_dead_letter_replay` | Explicit internal replay |
| `99_global_error_handler` | Sanitized unexpected workflow incidents |

Source exports remain portable; Compose bootstrap rewrites only runtime copies from host loopback URLs to service DNS.

## MCP inventory

The provider uses `mcp.server.MCPServer` from MCP Python SDK 2.0.0. It exposes 12 tools: submit/status/pending/explain/approve plus policy search/version, business term, expense context, decision trace, lineage, and provenance verification. It also exposes five `northstar://...` resource templates and the optional `investigate_expense` prompt.

HTTP calls use a configurable ten-second default timeout and normalize timeout, connection, HTTP, and invalid-JSON failures into safe errors. stdio is primary. Streamable HTTP refuses non-loopback bindings and remains demo/local only because MCP OAuth is not implemented.

## Observability inventory

Nine sanitized PostgreSQL views support five dashboards:

- Operations Overview
- Approval & SLA
- Reliability & Recovery
- Governed Context Health
- Decision Trace & Risk

The 36 questions and five dashboards are source-controlled and reconciled idempotently by logical keys. Metabase owns separate application state in `metabase_app`.

## Release topology and commands

Compose starts PostgreSQL; migration, context seed, analytics-role, n8n-import, and Metabase-bootstrap one-shots; FastAPI; notification sink; n8n; and Metabase on one private bridge network. Host mappings bind to loopback.

| Service | Host endpoint |
|---|---|
| FastAPI | `http://127.0.0.1:8000` |
| n8n | `http://127.0.0.1:5679` |
| Metabase | `http://127.0.0.1:3000` |
| PostgreSQL debugging | `127.0.0.1:55432` |

```powershell
Copy-Item .env.example .env
# Replace every change-me value with a disposable local secret.
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

`scripts/verify_stack.py` fails closed on service health, schema head, governed context, workflow/dashboard inventory, suspicious expense, approval, Wait completion, delivered resume outbox, human evidence, and provenance verification.

## Current limitations

- No production authentication, identity-bound approvers, RBAC, or tenant isolation.
- No MCP OAuth or safe remote HTTP exposure.
- No TLS termination, production ingress/firewall policy, or cloud deployment.
- No production secret manager/rotation, backup/restore automation, HA, or disaster recovery.
- The notification sink is volatile demo infrastructure; no real provider is integrated.
- Context/provenance immutability is enforced by application contracts and tests rather than database triggers or an external transparency log.
- SQLite compatibility mode is single-machine only; PostgreSQL is the verified durable release backend.
- The deterministic benchmark is a curated regression suite, not statistical evidence about production data.

The GitHub Actions definitions mirror locally verified commands, but a remote GitHub Actions run is not claimed.
