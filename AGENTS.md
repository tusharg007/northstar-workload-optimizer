# North Star agent guide

## Non-negotiable architecture

1. n8n owns orchestration; workflow nodes coordinate services but do not own financial policy.
2. FastAPI and the domain layer own deterministic validation, risk, routing, approvals, reliability, context, and provenance behavior.
3. PostgreSQL is the operational source of truth. n8n and Metabase have separate application databases.
4. MCP reads through the API and writes through existing n8n webhooks. It never bypasses normal write paths.
5. Metabase connects only as `northstar_metabase_ro` and may select only `observability.*` views.
6. Policy-dependent processing must abstain unless governed context is authoritative.
7. Every persisted decision requires immutable provenance evidence and a verifiable hash.
8. External effects use the transactional outbox and at-least-once delivery; consumers must be idempotent.
9. No LLM determines financial policy, risk, routing, or approval outcomes.
10. Gate 5 dataset and baseline v1 are immutable. Add a new version instead of editing v1.
11. Certified context versions are immutable. Publish a new version instead of mutating evidence.
12. Applied Alembic migrations are immutable. Add a forward migration.

## Ownership map

- `automation/`: deterministic expense engines and policy manifest.
- `app/`: API, persistence, context, provenance, approvals, and reliability.
- `n8n/workflows/`: exactly thirteen portable workflow definitions with stable IDs.
- `mcp_server/`: governed interface adapter, tools, resources, and prompt.
- `metabase/` and `observability/`: read-only analytics bootstrap and SQL.
- `evals/`: immutable versioned datasets, baselines, runner, and reports.
- `alembic/`: forward-only operational schema history.
- `infra/docker/`, `docker-compose.yml`, `scripts/stack.ps1`: release runtime only; no domain logic.

## Common verification

```powershell
.\.venv\Scripts\python.exe scripts\release_check.py
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m scripts.run_evals --profile fast
.\.venv\Scripts\python.exe -m scripts.run_mcp_evals --profile fast
.\scripts\stack.ps1 up
.\scripts\stack.ps1 verify
```

PostgreSQL checks require `NORTHSTAR_TEST_POSTGRES_URL` and `NORTHSTAR_EVAL_POSTGRES_URL`. Full live verification requires the Compose stack and disposable `.env` credentials.

## Release checklist

- Lock validates and installs in a fresh Python 3.13.9 environment.
- `compileall`, `pip check`, SQLite and PostgreSQL suites pass.
- Gate 5 FAST/PostgreSQL and MCP FAST/stdio evaluations pass.
- n8n validator reports exactly 13 workflows; Metabase reports 36 questions and 5 dashboards.
- Application image is non-root and contains no `.env`, `.git`, local DB, or mutable runtime profile.
- Fresh stack, restart persistence, and fresh-volume rebuild pass.
- `git diff --check` passes and no secret or generated report is staged.
