# North Star — Governed Expense Operations Platform

> **An enterprise-grade expense automation platform demonstrating deterministic policy enforcement, durable n8n orchestration, AI sub-agents with guardrails, multi-channel notifications (Email + Slack), Human-in-the-Loop approvals, immutable SHA-256 decision provenance, and a polished React operations dashboard.**

[![CI](https://github.com/tusharg007/northstar-workload-optimizer/actions/workflows/ci.yml/badge.svg)](https://github.com/tusharg007/northstar-workload-optimizer/actions/workflows/ci.yml)
![Python 3.13](https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5.6-3178C6?logo=typescript&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![n8n](https://img.shields.io/badge/n8n-2.22.6-EA4B71?logo=n8n&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## Table of Contents

- [What This Is](#what-this-is)
- [Architecture](#architecture)
- [Key Features](#key-features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Services & Ports](#services--ports)
- [Frontend Pages](#frontend-pages)
- [n8n Workflows (13)](#n8n-workflows)
- [AI Sub-Agents](#ai-sub-agents)
- [Multi-Channel Notifications](#multi-channel-notifications)
- [API Reference](#api-reference)
- [Demo Flow](#demo-flow)
- [MCP Server](#mcp-server)
- [Development](#development)
- [Verification](#verification)
- [Environment Variables](#environment-variables)
- [Design Principles](#design-principles)
- [Scope and Security](#scope-and-security)

---

## What This Is

North Star is a full-stack expense approval automation platform built to demonstrate production-grade patterns:

- **Deterministic policy enforcement** — FastAPI owns all validation, risk scoring, and routing. No LLM decides financial outcomes.
- **Durable workflow orchestration** — 13 n8n workflows manage multi-step approval lifecycles with real `Wait` nodes.
- **AI sub-agents with guardrails** — Executive Briefing Agent, Policy Compliance Copilot, and Forensic Audit Agent operate in strictly advisory roles (Rule 9: no LLM determines financial policy).
- **Multi-channel notifications** — Real Email (Resend) + Slack (Block Kit) with risk-based channel routing and HTML templates.
- **Human-in-the-loop approvals** — Escalated expenses wait indefinitely until a human approves or rejects via the UI.
- **Immutable provenance** — Every automated decision is cryptographically hashed (SHA-256) and independently verifiable.
- **Real-time updates** — Server-Sent Events (SSE) push state changes to all connected browsers in under 1 second.
- **Governed context** — Versioned, certified policy documents and business terms with temporal "as-of" resolution.
- **Professional React UI** — shadcn/ui design system, TanStack Table, dark mode, skeleton loaders, toast notifications, analytics charts.
- **Transactional outbox** — Distributed PostgreSQL leases (`SELECT FOR UPDATE SKIP LOCKED`), exponential backoff retries, and Dead Letter Queue with operator replay.
- **Model Context Protocol (MCP)** — 12 typed tools, 5 resources, and 1 prompt for governed AI agent integration.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                    React Frontend (nginx)                            │
│                    http://localhost:5173                              │
│  Dashboard · Submit · Approvals · Detail · Analytics · Context ·    │
│  Health · Dark Mode · SSE Real-Time · TanStack Table                │
└──────────────┬──────────────────────┬───────────────────────────────┘
               │ /api/*               │ /webhook/*
               ▼                      ▼
┌─────────────────────────┐    ┌───────────────────────────────────────┐
│   FastAPI (Python)      │◄───│         n8n Workflows (13)            │
│   localhost:8000        │    │         localhost:5679                 │
│                         │    │                                       │
│ • Validation            │    │  01 Expense Intake                    │
│ • Risk scoring (20 sigs)│    │  02 Approval Decision                 │
│ • Policy engine         │    │  10 Process Expense Service           │
│ • Provenance (SHA-256)  │    │  20 Approval Orchestrator (WAIT)      │
│ • Context registry      │    │  21 Notification Service              │
│ • HITL decisions        │    │  22 SLA Monitor                       │
│ • SSE event streaming   │    │  23 Reliability Dispatcher            │
│ • Outbox + DLQ          │    │  24 Dead Letter Replay                │
└─────────┬───────────────┘    │  25 Executive Briefing Agent (AI)     │
          │                    │  30 Policy Copilot (AI)               │
          ▼                    │  31 Forensic Audit Agent (AI)         │
┌─────────────────────────┐    │  99 Global Error Handler              │
│    PostgreSQL 16        │    └─────────────────┬─────────────────────┘
│    localhost:55432      │                      │
│                         │                      ▼
│ • northstar (app)       │    ┌───────────────────────────────────────┐
│ • n8n_app               │    │     Notification Router               │
│ • metabase_app          │    │     (Email + Slack + Mock)            │
│ • observability views   │    │                                       │
└─────────────────────────┘    │  📧 Resend API (HTML templates)       │
                               │  💬 Slack Block Kit (risk routing)    │
┌─────────────────────────┐    │  🧪 In-memory mock (fallback)        │
│    Metabase BI          │    └───────────────────────────────────────┘
│    localhost:3000       │
│    36 questions          │
│    5 dashboards          │
└─────────────────────────┘
```

### Data Flow

```
User submits via UI
      ↓
POST /webhook/northstar-expense   (n8n Workflow 01)
      ↓
Normalize → Build Context → Call FastAPI policy engine
      ↓
FastAPI validates + scores risk (20 signals) + determines routing
      ↓
If AUTO_APPROVED → persist + notify (email/slack) → respond
If ESCALATED/PENDING → n8n Workflow 20 starts, reaches WAIT node
      ↓
Expense appears in UI Approvals inbox (real-time via SSE)
      ↓
Human clicks Approve/Reject → POST /webhook/northstar-approval
      ↓
n8n Workflow 02 records decision → resumes SAME Workflow 20 execution
      ↓
Workflow 20 continues → AI generates executive briefing → sends notification
      ↓
Dashboard updates in <1s (SSE push), provenance hash verifiable ✅
```

---

## Key Features

### 🛡️ Deterministic Policy Engine
- 20 risk signals: statistical outlier, weekend transaction, suspicious round amount, duplicate detection, missing receipt, category limit exceeded, and more
- 4-tier approval routing: ≤$500 Direct Manager → ≤$2K Dept Head → ≤$5K Finance Director → >$5K VP/C-Suite
- HIGH/CRITICAL risk auto-escalates to Finance Director + Compliance
- All rules are versioned, certified, and content-hashed

### 🤖 AI Sub-Agents (with Guardrails)
- **Executive Briefing Agent** — Generates 2-3 sentence natural language summaries for approval notifications
- **Policy Copilot** — Answers employee questions about expense policies before submission, citing specific policy versions
- **Forensic Audit Agent** — Autonomously investigates expenses: pulls lineage, verifies provenance, generates compliance memorandums
- ⚠️ **Guardrail**: No AI agent determines risk scores, routing decisions, or approval outcomes (Rule 9)

### 📧 Multi-Channel Notifications
- **Email** via Resend API with 4 responsive HTML templates (approval request, completion, SLA reminder, escalation)
- **Slack** via Incoming Webhooks with Block Kit formatting and "Review in Dashboard" deep links
- **Channel routing**: CRITICAL/HIGH → Email + Slack, MEDIUM/LOW → Email only
- Graceful fallback to in-memory mock when API keys are not configured

### 🔐 Cryptographic Decision Provenance
- SHA-256 hash over canonical JSON evidence (policies, terms, rules, trust signals, risk scores, human decisions)
- One-click **Verify Integrity** button recomputes and compares hashes in real-time
- Immutable lineage timeline from intake through final decision
- Forensic audit agent can autonomously verify provenance chains

### ⚡ Real-Time Architecture
- **Server-Sent Events (SSE)** push expense state changes to all connected browsers
- **Transactional Outbox** with distributed PostgreSQL leases and exponential backoff (0s → 15s → 60s → 300s)
- **Dead Letter Queue** with operator replay from the System Health UI
- **SLA Monitor** (10s polling) with automatic escalation notifications

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | React 18, TypeScript 5.6, Vite 6, Tailwind CSS 3, shadcn/ui (Radix), TanStack Table v8, Recharts, Sonner, Lucide React |
| **API** | FastAPI (Python 3.13), Pydantic v2, Uvicorn, SSE streaming |
| **Orchestration** | n8n 2.22.6 (self-hosted, 13 workflows including 3 AI sub-agents) |
| **Database** | PostgreSQL 16, Alembic migrations, observability SQL views |
| **Notifications** | Resend (Email), Slack Incoming Webhooks (Block Kit), Jinja2 HTML templates |
| **Analytics** | Metabase (36 questions, 5 dashboards), Recharts frontend analytics |
| **MCP Interface** | Python MCP SDK 2.0; 12 tools, 5 resources, 1 prompt |
| **AI Integration** | OpenAI-compatible API (GPT-4o-mini / Ollama) for advisory sub-agents |
| **Container** | Docker + Docker Compose, nginx reverse proxy, multi-stage builds |
| **Policy Engine** | Deterministic Python rules engine (automation/) |

---

## Project Structure

```
northstar-workload-optimizer/
├── app/                            # FastAPI application
│   ├── main.py                     # App factory, all routes, SSE streaming
│   ├── runtime_store.py            # Runtime persistence boundary
│   ├── reliability.py              # Outbox, retry, and dead-letter behavior
│   ├── approval_sla.py             # SLA deadline & escalation calculations
│   ├── context/                    # Governed context registry
│   ├── provenance/                 # Immutable decision provenance
│   └── db/repositories/            # PostgreSQL repository implementations
│
├── automation/                     # Deterministic policy engine
│   ├── automation_flow.py          # Main processing pipeline (20 risk signals)
│   ├── policy_manifest.py          # Policy definitions & routing tiers
│   └── flow_design.md              # Policy-flow design notes
│
├── frontend/                       # React operations dashboard
│   ├── src/
│   │   ├── components/ui/          # 14 shadcn/ui design system components
│   │   ├── components/             # ThemeProvider (dark mode)
│   │   ├── hooks/                  # useEventStream (SSE client)
│   │   ├── pages/                  # 7 pages: Dashboard, Submit, Approvals,
│   │   │                           #   ExpenseDetail, Analytics, Context, Health
│   │   ├── layouts/                # DashboardLayout with breadcrumbs
│   │   ├── lib/                    # api.ts (typed client), utils.ts
│   │   └── types.ts                # TypeScript types matching FastAPI schemas
│   ├── Dockerfile                  # Multi-stage: node build → nginx serve
│   └── nginx.conf                  # Reverse proxy + SPA fallback + SSE support
│
├── n8n/workflows/                  # 13 portable workflow definitions
│   ├── 01_expense_intake.json
│   ├── 02_approval_decision.json
│   ├── 10_process_expense_service.json
│   ├── 11_record_decision_service.json
│   ├── 20_approval_orchestrator.json
│   ├── 21_approval_notification_service.json
│   ├── 22_approval_sla_monitor.json
│   ├── 23_reliability_dispatcher.json
│   ├── 24_dead_letter_replay.json
│   ├── 25_executive_briefing_agent.json    # AI sub-agent
│   ├── 30_policy_copilot.json              # AI sub-agent
│   ├── 31_forensic_audit_agent.json        # AI sub-agent
│   └── 99_global_error_handler.json
│
├── scripts/
│   ├── stack.ps1                   # One-command stack management
│   ├── notification_sink.py        # Notification dispatch service
│   ├── notification_router.py      # Multi-channel router (Email + Slack)
│   └── templates/                  # Jinja2 HTML email templates
│       ├── approval_request.html
│       ├── approval_completed.html
│       ├── sla_reminder.html
│       └── sla_escalation.html
│
├── mcp_server/                     # MCP interface adapter (12 tools)
├── metabase/                       # Observability dashboard bootstrap
├── observability/                  # SQL views for Metabase
├── alembic/                        # Forward-only DB migrations
├── evals/                          # Immutable eval datasets and runner
├── tests/                          # Full test suite
├── infra/docker/                   # Dockerfiles and bootstrap scripts
├── docker-compose.yml              # Full stack definition (10 containers)
├── .env.example                    # Template for setup
└── STUDY_GUIDE_NOTION.md           # Comprehensive interview study guide
```

---

## Quick Start

### Prerequisites
- Docker Desktop (Windows/Mac/Linux)
- PowerShell 7+ (Windows) or bash
- Git

### 1. Clone and configure

```powershell
git clone https://github.com/tusharg007/northstar-workload-optimizer
cd northstar-workload-optimizer

# Copy the env template
Copy-Item .env.example .env
# Replace every change-me value with disposable local credentials
```

### 2. Launch everything

```powershell
.\scripts\stack.ps1 up
```

This single command:
- Builds the FastAPI app image and React frontend (Vite production build inside Docker)
- Runs Alembic migrations and seeds governed context
- Creates Metabase read-only role and imports all 13 n8n workflows
- Starts PostgreSQL, FastAPI, n8n, Metabase, notification router, nginx frontend

### 3. Open the dashboard

```
http://localhost:5173
```

### 4. (Optional) Enable real notifications

```env
# Add to .env for real email delivery (Resend free tier: 100/day)
RESEND_API_KEY=re_xxxxxxxxxxxx
NOTIFICATION_FROM_EMAIL=expenses@yourdomain.com

# Add for Slack notifications
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx

# Add for AI sub-agents
OPENAI_API_KEY=sk-...
```

---

## Services & Ports

| Service | URL | Description |
|---|---|---|
| **Frontend** | http://localhost:5173 | React dashboard (nginx) |
| **FastAPI** | http://localhost:8000 | REST API |
| **FastAPI Docs** | http://localhost:8000/docs | Interactive Swagger explorer |
| **n8n** | http://localhost:5679 | Workflow orchestration editor |
| **Metabase** | http://localhost:3000 | Analytics dashboards |
| **PostgreSQL** | localhost:55432 | Direct DB access |

---

## Frontend Pages

### 🏠 Dashboard (`/`)
- Live KPI metrics: Total, Auto-Approved (%), Pending Review, Escalated, Approved
- **TanStack Table** with global search, column sorting, row selection, pagination (10/25/50)
- CSV and JSON data export
- Status filter tabs with counts: Pending (3), Escalated (1), etc.
- Real-time updates via SSE (sub-second refresh)

### 📋 Submit Expense (`/submit`)
- 4 one-click demo presets: Auto-Approve Coffee ($28.50), Normal Travel ($640), Suspicious Software ($3,000), Invalid Future Date
- Full expense form with instant result panel (status, risk, anomaly flags, routing)
- **"Ask Policy Copilot"** dialog — AI answers policy questions citing certified documents
- Submission goes through **n8n Workflow 01** (not direct to FastAPI)

### ✅ Approvals (`/approvals`)
- HITL inbox with risk badges and anomaly flags
- **Inline approve/reject** with approver name and comment
- **Bulk approval** — select multiple low-risk items, approve in one click
- **"View Full Details"** link on each card
- Decision goes through **n8n Workflow 02** → resumes **Workflow 20**

### 🔍 Expense Detail (`/expenses/:id`)
- **Inline approval action** — approve/reject directly without navigating to Approvals page
- **"Generate Audit Report"** — AI forensic agent produces compliance memorandum
- Three tabs:
  - **Overview** — payload, risk score with confidence bar, anomaly flags, routing, provenance summary
  - **Lineage** — visual timeline of all workflow events (intake → evaluation → decision)
  - **Provenance** — SHA-256 hash, evidence counts, **Verify Integrity** button with pass/fail result

### 📊 Analytics (`/analytics`)
- 4 interactive Recharts visualizations:
  - Expenses by Status (donut chart)
  - Risk Distribution (donut chart)
  - Spend by Category (bar chart)
  - Volume Over Time (line chart)

### 📚 Governed Context (`/context`)
- Browse certified policies with expandable version history and rule parameters
- Browse business terms with definitions and certification metadata
- Content hashes and effective date ranges for compliance auditing

### 🩺 System Health (`/health`)
- Health tiles for FastAPI, n8n, PostgreSQL, Metabase
- **Dead Letter Queue** table with **Replay** buttons
- **Run Reconciliation** trigger for outbox integrity
- Workflow failures table with error details
- Quick links to Swagger, n8n Editor, Metabase

### 🌙 Design System
- **Dark mode** (system/light/dark with localStorage persistence)
- **Skeleton shimmer loaders** on all data-fetching components
- **Toast notifications** (Sonner) for all user actions
- **Breadcrumbs** (Dashboard > Expense Detail > EXP-xxx)
- **Error alerts** with retry buttons

---

## n8n Workflows

North Star includes **13 version-controlled n8n workflow definitions**:

| # | ID | Name | Purpose |
|---|---|---|---|
| 01 | `northstarExpenseIntake` | Expense Intake | Webhook → normalize → call FastAPI → launch orchestrator |
| 02 | `northstarApprovalDecision` | Approval Decision | Record decision → resume waiting Workflow 20 |
| 10 | `northstarProcessExpenseService` | Process Expense | FastAPI bridge: validate, score, route |
| 11 | `northstarRecordDecisionService` | Record Decision | Persist human decision, create resume event |
| 20 | `northstarApprovalOrchestrator` | Approval Orchestrator | **Durable HITL** — `Wait` node pauses until human decides |
| 21 | `northstarApprovalNotificationService` | Notification Service | Outbox-governed dispatch to Email/Slack/mock |
| 22 | `northstarApprovalSLAMonitor` | SLA Monitor | 10s cron: escalates overdue approvals |
| 23 | `northstarReliabilityDispatcher` | Reliability Dispatcher | 5s cron: at-least-once outbox delivery |
| 24 | `northstarDeadLetterReplay` | Dead Letter Replay | Operator tooling for failed event replay |
| 25 | `northstarExecutiveBriefingAgent` | **Executive Briefing Agent** | 🤖 AI generates notification summaries |
| 30 | `northstarPolicyCopilot` | **Policy Copilot** | 🤖 AI answers employee policy questions |
| 31 | `northstarForensicAuditAgent` | **Forensic Audit Agent** | 🤖 AI investigates and verifies provenance |
| 99 | `northstarGlobalErrorHandler` | Error Handler | Catches and sanitizes unhandled workflow errors |

---

## AI Sub-Agents

> ⚠️ **Guardrail (Rule 9):** No LLM determines financial policy, risk, routing, or approval outcomes. All AI agents operate in advisory/explanatory roles only.

| Agent | Trigger | What It Does | What It Cannot Do |
|---|---|---|---|
| **Executive Briefing** (WF 25) | Called by Workflow 20 before notifications | Generates 2-3 sentence summary explaining why an expense requires review | Cannot change risk score or routing |
| **Policy Copilot** (WF 30) | Webhook: `/webhook/northstar-policy-query` | Answers policy questions citing certified documents and version numbers | Cannot approve/reject expenses |
| **Forensic Auditor** (WF 31) | On-demand from Expense Detail page | Pulls lineage, verifies SHA-256 provenance, generates audit memorandum | Cannot modify any records |

If `OPENAI_API_KEY` is not configured, AI features gracefully degrade — notifications are sent without briefings, and copilot/audit buttons show appropriate messages.

---

## Multi-Channel Notifications

```
n8n Workflow 21 → POST /notifications → Notification Router
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    │                         │                         │
              CRITICAL/HIGH              MEDIUM/LOW              No API Keys
                    │                         │                         │
              Email + Slack              Email Only              In-Memory Mock
                    │                         │                         │
              Resend API +              Resend API              UUID stored
              Slack Block Kit                                   in memory
```

**4 HTML email templates** in `scripts/templates/`:
- `approval_request.html` — Risk badge, expense table, "Review Now" button
- `approval_completed.html` — Decision summary with reviewer details
- `sla_reminder.html` — Urgency notice with time remaining
- `sla_escalation.html` — Escalation alert with new reviewer role

---

## API Reference

Full interactive docs at **http://localhost:8000/docs**

### Key Endpoints

```
# Expense Operations
POST /api/expenses/process              Submit expense (FastAPI direct)
GET  /api/expenses                      List all expenses
GET  /api/expenses/{id}                 Get single expense
POST /api/expenses/{id}/decision        Submit approval decision
GET  /api/expenses/{id}/explanation     Risk explanation
GET  /api/expenses/{id}/lineage         Full event lineage

# Provenance
GET  /api/provenance/expenses/{id}      Immutable provenance record
GET  /api/provenance/expenses/{id}/trace Decision trace
GET  /api/provenance/decisions/{id}/verify  Verify SHA-256 integrity

# Governed Context
GET  /api/context/policies              List certified policies
GET  /api/context/policies/{key}/versions  Policy version history
GET  /api/context/policies/{key}/resolve   Temporal resolution
GET  /api/context/terms                 List business terms

# Real-Time
GET  /api/events/stream                 SSE event stream

# n8n Webhooks (via nginx at :5173 or directly at :5679)
POST /webhook/northstar-expense         Expense intake (→ Workflow 01)
POST /webhook/northstar-approval        Approval decision (→ Workflow 02)
POST /webhook/northstar-policy-query    Policy Copilot (→ Workflow 30)

# Health & Operations
GET  /health                            Service health
GET  /api/internal/outbox/dead-letter   Dead letter events
POST /api/internal/outbox/{id}/replay   Replay failed event
POST /api/internal/reliability/reconcile Run reconciliation
```

---

## Demo Flow

> **5-minute guided demo showing the complete governed expense cycle.**

### Step 1 — Start the stack

```powershell
.\scripts\stack.ps1 up
# Open http://localhost:5173
```

### Step 2 — Submit a suspicious expense

1. Click **Submit Expense** → click **🚨 Suspicious Software ($3,000)** preset
2. Click **Submit Expense**
3. **Result:** `ESCALATED` / `CRITICAL` risk / 5 anomaly flags (weekend, duplicate, missing receipt, round amount, category limit)
4. **Why it matters:** The deterministic engine caught 5 anomalies and escalated to Finance Director + Compliance — no LLM involved

### Step 3 — Approve from the UI

1. Click **Approvals** → expand the $3,000 expense
2. Enter approver name and comment → click **Approve**
3. **What happens under the hood:** Frontend → n8n Workflow 02 → FastAPI records decision → resumes the SAME Workflow 20 execution that was waiting → sends email/Slack notification

### Step 4 — Verify provenance (the WOW moment)

1. Click **Dashboard** → click **View** on the approved expense
2. **Lineage tab:** Visual timeline from intake to decision
3. **Provenance tab:** Click **Verify Integrity** → green **"Integrity Verified ✅"**
4. **What this proves:** SHA-256 hash recomputed over all evidence matches stored hash — mathematical proof that no one tampered with the decision after the fact

### Step 5 — Show the architecture

1. **Analytics** (`/analytics`) — 4 live charts
2. **Governed Context** (`/context`) — certified policies with versioned rules
3. **System Health** (`/health`) — DLQ replay, reconciliation, failure monitoring
4. **n8n Editor** (http://localhost:5679) — show 13 workflows, the Wait node in Workflow 20

### Bonus: Prove n8n is mandatory

```powershell
docker compose -p northstar-g9 stop n8n
# Try submitting via UI → error shown (no silent fallback)
docker compose -p northstar-g9 start n8n
```

---

## MCP Server

The MCP server (`mcp_server/`) exposes North Star to AI agents via Anthropic's Model Context Protocol:

- **12 Tools:** `submit_expense`, `get_expense_status`, `list_pending_approvals`, `explain_risk`, `approve_expense`, `search_policy_context`, `get_policy_version`, `get_business_term`, `get_expense_context`, `get_decision_trace`, `get_expense_lineage`, `verify_decision_provenance`
- **5 Resources:** Policy, Term, Context, Trace, and Lineage URI templates
- **1 Prompt:** `investigate_expense` guided investigation template
- **Safety:** Read-only tools use `READ_ONLY` annotation; writes route through n8n webhooks; context abstention when policy is stale

```powershell
# Launch MCP Inspector
uv run mcp dev mcp_server/server.py

# stdio mode
.\.venv\Scripts\python.exe -m mcp_server.server

# Streamable HTTP mode
.\.venv\Scripts\python.exe -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8765
```

---

## Development

### Local dev without Docker

```powershell
# Start FastAPI
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Start frontend dev server (Vite proxies to FastAPI + n8n)
cd frontend && npm install && npm run dev
# Open http://localhost:5173
```

### Run tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

### Run evaluations

```powershell
.\.venv\Scripts\python.exe -m scripts.run_evals --profile fast
.\.venv\Scripts\python.exe -m scripts.run_mcp_evals --profile fast
```

### Build frontend only

```powershell
cd frontend
npm run build          # Production build → dist/
npm run dev            # Dev server on :5173 with proxy
```

---

## Verification

```powershell
# Backend release checks and tests
.\.venv\Scripts\python.exe scripts\release_check.py
.\.venv\Scripts\python.exe -m pytest -q

# Deterministic and MCP evaluation gates
.\.venv\Scripts\python.exe -m scripts.run_evals --profile fast
.\.venv\Scripts\python.exe -m scripts.run_mcp_evals --profile fast

# Frontend type-check and production bundle
Push-Location frontend
npm install
npx tsc --noEmit
npm run build
Pop-Location

# Live Compose verification
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in the values:

```env
# PostgreSQL
NORTHSTAR_POSTGRES_ADMIN_USER=northstar_admin
NORTHSTAR_POSTGRES_ADMIN_PASSWORD=<your-password>
NORTHSTAR_APP_DB_USER=northstar_app
NORTHSTAR_APP_DB_PASSWORD=<your-password>

# n8n
N8N_DB_USER=northstar_n8n
N8N_DB_PASSWORD=<your-password>
N8N_ENCRYPTION_KEY=<32-char-minimum-key>

# Metabase
METABASE_APP_DB_USER=northstar_metabase
METABASE_APP_DB_PASSWORD=<your-password>
METABASE_ADMIN_EMAIL=admin@northstar.local
METABASE_ADMIN_PASSWORD=<your-password>

# Notifications (optional — falls back to in-memory mock)
RESEND_API_KEY=re_xxxxxxxxxxxx
NOTIFICATION_FROM_EMAIL=expenses@yourdomain.com
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../xxx

# AI Sub-Agents (optional — graceful degradation if unset)
OPENAI_API_KEY=sk-...
OPENAI_API_BASE=https://api.openai.com  # or http://host.docker.internal:11434/v1 for Ollama

# Ports (optional overrides)
NORTHSTAR_POSTGRES_PORT=55432
NORTHSTAR_API_PORT=8000
N8N_PORT=5679
METABASE_PORT=3000
NORTHSTAR_FRONTEND_PORT=5173
```

---

## Design Principles

1. **n8n owns orchestration** — workflow nodes coordinate services but do not own financial policy
2. **FastAPI owns policy** — all validation, risk scoring, routing, and approval outcomes are deterministic Python code, never LLM output
3. **PostgreSQL is the source of truth** — n8n and Metabase have separate application databases
4. **AI agents are strictly advisory** — they explain and summarize but never determine financial outcomes (Rule 9)
5. **Every decision has provenance** — immutable evidence record with SHA-256 cryptographic hash
6. **External effects use the outbox** — at-least-once delivery with exponential backoff, idempotent consumers
7. **Notifications are multi-channel** — Email + Slack with risk-based routing and graceful fallback
8. **Migrations are immutable** — applied Alembic migrations are never edited, only extended forward
9. **Context versions are immutable** — certified policies and terms get new versions, never mutated
10. **Frontend preserves domain ownership** — no financial policy or approval authority moves into browser code

---

## Scope and Security

North Star is a local/reference engineering release intended for evaluation,
portfolio review, and controlled demonstrations. It does not claim production
authentication, role-based access control, TLS termination, high availability,
or managed-secret infrastructure. For real-world deployment, add:

- **Authentication:** OAuth2/OIDC via Keycloak or Auth0
- **TLS:** Traefik or Certbot for HTTPS termination
- **Secrets:** Docker Secrets or HashiCorp Vault
- **Scaling:** Redis Pub/Sub for horizontal SSE, server-side pagination
- **Monitoring:** Prometheus + Grafana for infrastructure metrics

Use only disposable local credentials, keep published ports loopback-bound,
and add your organization's identity, authorization, secrets, network, and
operational controls before any real-world deployment.
