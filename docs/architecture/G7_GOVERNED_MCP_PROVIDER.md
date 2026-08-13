# Gate 7: Governed MCP Context and Provenance Provider

## 1. Role in North Star

The North Star Governed Context Server is a deterministic MCP v2 interface over
existing North Star capabilities. It lets trusted MCP clients inspect governed
policy context, business definitions, expense state, risk evidence, decision
provenance, and persisted lineage. It also retains the two existing controlled
write operations for expense intake and approval.

The server contains no LLM. Reasoning and tool selection belong to the MCP host;
North Star remains the source of stored facts and decision evidence.

## 2. Why MCP is not orchestration

MCP does not own workflow state, policy execution, retries, Wait/resume, SLA
scheduling, outbox claiming, or notification delivery. It calls the existing
HTTP boundaries:

```text
read:  MCP -> FastAPI read endpoints -> application repositories -> database
write: MCP -> n8n public webhook -> FastAPI -> governed transaction -> database
```

n8n remains the orchestration control plane. FastAPI remains the application
boundary. PostgreSQL remains the durable source of truth.

## 3. Tool, resource, and prompt design

Tools are model-invoked actions or parameterized queries. Resource templates
provide read-only navigation to stable business records. The single optional
prompt is a user-invoked investigation template and contains no authoritative
decision logic. All tools return MCP structured content and use explicit,
bounded inputs.

## 4. Read and write boundaries

Read tools expose only stored or deterministically resolved facts. They never
recalculate a financial decision with an LLM. `submit_expense` is an
orchestration bridge. `approve_expense` is a privileged consequential action.
Neither MCP write handler imports a repository, creates a SQLAlchemy session, or
executes SQL.

## 5. Final tool inventory

| Tool | Classification | Boundary |
|---|---|---|
| `submit_expense` | ORCHESTRATION_BRIDGE | Consequential, idempotent intake through n8n |
| `get_expense_status` | READ | Minimized durable state |
| `list_pending_approvals` | READ | Bounded pending/escalated list |
| `explain_risk` | READ | Stored deterministic risk explanation |
| `approve_expense` | WRITE_PRIVILEGED | Consequential approval through n8n/HITL |
| `search_policy_context` | READ | Deterministic bounded policy/term search |
| `get_policy_version` | READ | Current or historical governed policy |
| `get_business_term` | READ | Current or historical governed term |
| `get_expense_context` | READ | Policy context separated from risk signals |
| `get_decision_trace` | READ | Minimized complete stored decision trace |
| `get_expense_lineage` | READ | Persisted workflow/provenance/approval/outbox timeline |
| `verify_decision_provenance` | READ | Recomputed evidence and aggregate hashes |

The original five names and argument names remain available. The security
correction is output minimization: raw input payloads, comments, notification
payloads, and Wait capability URLs are not returned.

## 6. Final resource inventory

- `northstar://policies/{policy_key}`
- `northstar://terms/{term_key}`
- `northstar://expenses/{expense_id}/context`
- `northstar://expenses/{expense_id}/trace`
- `northstar://expenses/{expense_id}/lineage`

Resources use stable JSON serialization and the same adapter methods as their
equivalent tools. Dynamic records are templates rather than an unbounded
enumeration.

Prompt inventory: `investigate_expense(expense_id)`. It instructs the client to
read North Star evidence and distinguish policy facts from algorithmic signals;
it does not decide or approve anything.

## 7. Governed policy lookup

`search_policy_context` uses transparent exact-key, canonical-name, token, and
text matching with optional domain, trust-state, and UTC `as_of` filters. It has
no embeddings or semantic-similarity claims. The default limit is 20 and the
maximum is 100. `get_policy_version` returns stable keys, resolved version,
owner, effective interval, content hash, trust evidence, and governed rules.

## 8. Provenance and trace access

`get_decision_trace` reads the existing immutable provenance endpoints and
returns expense/correlation/workflow identity, `context_as_of`, policy and term
evidence, trust evidence, rule evaluations, risk-signal evaluations, automated
outcome, approval state, human evidence when present, final state, provenance
hash, and verification. It strips raw request and comment fields. No LLM
summary is involved.

## 9. Lineage model

The application exposes a read-only lineage endpoint assembled solely from
persisted workflow events, the provenance record, immutable approval decision,
and correlated outbox events. MCP normalizes those records into a timestamped
sequence with correlation and workflow-run identity. It does not synthesize
unrecorded lifecycle steps.

## 10. Privileged write pathway

`approve_expense` remains direct for backwards compatibility because MCP hosts
do not provide a universally reliable confirmation-intent protocol. Its tool
description and annotations mark it as a consequential, destructive write for
trusted operators. The call goes to the public n8n approval webhook, then the
existing FastAPI immutable approval transaction writes human evidence and an
outbox resume intent before n8n resumes the durable Wait execution.

## 11. Idempotency

The MCP adapter generates a correlation identifier and delegates expense
idempotency to the existing public intake path. North Star derives a stable key
from source, expense ID, and canonical payload hash when no explicit key is
available. Exact replay returns the existing logical operation and does not
duplicate expense, workflow run, approval task, or provenance records.

## 12. Safe error model

The adapter normalizes failures to stable safe codes:

- `NOT_FOUND`
- `INVALID_INPUT`
- `CONTEXT_NOT_AUTHORITATIVE`
- `CONFLICT`
- `UPSTREAM_UNAVAILABLE`
- `PROVENANCE_UNAVAILABLE`
- `PERMISSION_BOUNDARY` / privileged-action language where applicable

Timeouts and connection failures are distinct from domain 404/409 responses.
Errors may include a safe reason code and correlation ID, but never a stack
trace, local path, DSN, authorization header, or upstream body dump.

## 13. Data minimization

Tool and resource results exclude database URLs, credentials, authorization
headers, provider tokens, Metabase secrets, Wait resume URLs, raw input
payloads, payment details, notification payloads, and decision comments. The
Gate 7 benchmark scans every collected response and contains a deliberate
forbidden fixture proving the scanner fails closed.

## 14. Stdio architecture

Stdio is the required/default transport. Structured operational logging uses
Python logging on stderr, leaving stdout exclusively for MCP protocol frames.
The real-process smoke test initializes the official client, discovers tools
and resource templates, calls status/policy/trace, and reads a resource.

## 15. Streamable HTTP architecture

The official SDK's Streamable HTTP transport is supported for local demos at
`http://127.0.0.1:8765/mcp`. The CLI rejects non-loopback bindings. The server
runs stateless JSON responses for a small local test footprint. A self-cleaning
runtime smoke launches the real server process and verifies discovery, calls,
and resource reads with the official client.

## 16. Authorization limitations

Local stdio assumes a trusted operator and trusted client process. The local
Streamable HTTP mode is not production-ready authentication and must not be
internet-exposed. A shared deployment requires a real authorization layer,
identity-to-approver binding, least privilege, and the MCP HTTP authorization
security model. Gate 7 deliberately does not add a cosmetic API key or
pseudo-OAuth implementation.

## 17. MCP v2 SDK and server metadata

Implementation and tests use the installed official `mcp` Python package
version `2.0.0`, `MCPServer`, tool annotations, structured output, resource
templates, prompts, the in-memory `Client(server)` path, stdio client/server,
and Streamable HTTP client/server. The source-controlled server identity is
`north-star-governed-context`, title `North Star Governed Context Server`,
version `1.0.0`.

## 18. MCP evaluation

`evals/datasets/mcp_v1/manifest.json` is a separate deterministic interface
dataset; Gate 5 v1 data and baseline are unchanged. Run:

```powershell
.\.venv\Scripts\python.exe scripts\run_mcp_evals.py --profile fast
.\.venv\Scripts\python.exe scripts\run_mcp_evals.py --profile stdio
```

The FAST profile uses the official in-memory client with disposable SQLite.
The stdio profile uses a real server subprocess against configured live
FastAPI/n8n services. Metrics are exact contract accuracy, trace fidelity,
write-path integrity, bounded output, and sensitive-data leakage; there is no
LLM judge. Every accuracy threshold is 1.0 and leak rate is 0.0.

## 19. Runtime verification

Static validation is provided by `scripts/validate_mcp_server.py`. Runtime
coverage includes official in-memory client tests, a real stdio subprocess
smoke, a loopback Streamable HTTP subprocess smoke, and the MCP FAST benchmark.
The release integration additionally requires disposable PostgreSQL 16,
FastAPI, isolated n8n 2.22.6, and the stdio MCP benchmark to prove both writes
traverse the complete governed workflow.

Verified release results on 2026-08-13:

- MCP FAST/in-memory benchmark: 17/17 PASS.
- MCP real stdio benchmark over PostgreSQL 16.14 and isolated n8n 2.22.6:
  16/16 PASS.
- Every accuracy, fidelity, integrity, and bounds metric: 1.000.
- Sensitive-data leak rate: 0.000.
- Live submit: `ESCALATED`, `CRITICAL`, `Finance Director + Compliance`.
- Live approval: `APPROVED`; durable orchestration `COMPLETED`; resume outbox
  `DELIVERED`.
- PostgreSQL evidence: one expense, workflow run, approval task, immutable
  approval decision, provenance aggregate, and human-evidence record.
- Existing end-to-end smoke: `NORTH STAR END-TO-END DEMO: PASS`.

## 20. Limitations and remaining security debt

- No production identity, RBAC, or MCP OAuth layer exists.
- The recorded approver string is not bound to an authenticated identity.
- Streamable HTTP is localhost-only and intended for development.
- Search is deterministic lexical search, not semantic retrieval.
- MCP operation logs are process logs, not a new audit table.
- Production deployment needs transport authorization, secret management,
  network policy, rate limits, and operator/tool entitlements.
- Gate 8 must start only from a fully verified and committed Gate 7 baseline.

## Windows commands

From the repository root:

```powershell
# Default stdio server
.\.venv\Scripts\python.exe -m mcp_server.server

# Local-only Streamable HTTP
.\.venv\Scripts\python.exe -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8765

# Official SDK development mode / MCP Inspector
$env:UV_CACHE_DIR="$PWD\.venv\uv-cache"
.\.venv\Scripts\uv.exe run mcp dev mcp_server\server.py

# Contract and runtime checks
.\.venv\Scripts\python.exe scripts\validate_mcp_server.py
.\.venv\Scripts\python.exe scripts\smoke_mcp_transport.py --transport stdio --expense-id <persisted-expense-id>
.\.venv\Scripts\python.exe scripts\smoke_mcp_http_runtime.py --expense-id <persisted-expense-id>
```

Set `NORTHSTAR_API_BASE_URL`, `N8N_EXPENSE_WEBHOOK_URL`, and
`N8N_APPROVAL_WEBHOOK_URL` for the active environment. All adapter HTTP calls
use `NORTHSTAR_MCP_HTTP_TIMEOUT_SECONDS` (safe default: 10 seconds).
