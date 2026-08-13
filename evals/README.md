# North Star deterministic evaluations

The Gate 5 evaluator asks a different question from pytest. Pytest asks whether
an implementation unit satisfies its contract. This benchmark asks whether the
complete decision, governed-context, provenance, idempotency, and selected
reliability system still produces the intended representative behavior and
meets release safety thresholds.

It uses explicit JSON ground truth and exact comparisons. It has no LLM judge,
embedding, fuzzy match, or prose grader.

## Windows commands

From the repository root:

```powershell
# Full SQLite benchmark; baseline comparison is default for full runs.
.\.venv\Scripts\python.exe scripts\run_evals.py --profile fast --compare-baseline

# Full PostgreSQL benchmark after starting a disposable PostgreSQL 16 database.
$env:NORTHSTAR_EVAL_POSTGRES_URL="postgresql+psycopg://northstar:password@127.0.0.1:5432/northstar_eval"
.\.venv\Scripts\python.exe scripts\run_evals.py --profile postgres --compare-baseline

# Focused live benchmark after PostgreSQL, FastAPI, isolated n8n 2.22.6,
# and the notification sink are running.
$env:NORTHSTAR_OUTBOX_RETRY_SECONDS="0,0,0,0" # set before starting evaluation FastAPI
.\.venv\Scripts\python.exe scripts\run_evals.py --profile live --compare-baseline

# Optional explicit report path.
.\.venv\Scripts\python.exe scripts\run_evals.py --profile fast --report .\evals\reports\manual.json

# Expected to exit 1: proves a derived wrong route is detected. The v1 JSON is unchanged.
.\.venv\Scripts\python.exe scripts\run_evals.py --profile fast --case-id decision_department_above_500 --negative-control wrong-expectation
```

`NORTHSTAR_EVAL_POSTGRES_URL`, `NORTHSTAR_API_BASE_URL`,
`N8N_EXPENSE_WEBHOOK_URL`, and `N8N_APPROVAL_WEBHOOK_URL` are supported. The
CLI never writes database credentials to reports.

## Layout and versioning

- `datasets/v1/` is authored, immutable release ground truth.
- `baselines/v1.json` freezes case IDs/counts, categories, engine identities,
  risk catalog hash, policy manifest, and strict thresholds.
- `reports/` contains generated machine-readable runs and is gitignored.
- scenario names map to trusted Python setup functions; JSON cannot contain SQL.

Material benchmark changes require `datasets/v2/` and a v2 baseline. Before v1
release, corrections are reviewed in the same Gate 5 change. After release, v1
must not be silently rewritten.

FAST uses one disposable SQLite database per case. POSTGRES migrates one
disposable PostgreSQL database once and truncates/reseeds between cases. LIVE
uses PostgreSQL and public n8n intake/approval webhooks for the representative
subset. During controlled outbox transition cases, the scheduled dispatcher is
paused in the isolated n8n profile so the evaluator is the sole lease owner,
and the evaluation FastAPI uses zero retry delays. Each reliability expense
still enters through public n8n intake. These settings are test isolation only;
the source-controlled workflow and production retry defaults remain unchanged.

See `docs/architecture/G5_EVALUATION_HARNESS.md` for formulas, completeness,
release evidence, and limitations.

## Separate Gate 7 MCP interface benchmark

Gate 7 does not modify `datasets/v1/` or `baselines/v1.json`. Its small,
deterministic MCP contract dataset lives in `datasets/mcp_v1/` and uses the
official MCP client without an LLM judge.

```powershell
# Disposable SQLite plus direct in-memory MCP client.
.\.venv\Scripts\python.exe scripts\run_mcp_evals.py --profile fast

# Real stdio MCP subprocess against configured live FastAPI and n8n services.
.\.venv\Scripts\python.exe scripts\run_mcp_evals.py --profile stdio
```

The interface metrics are `tool_contract_accuracy`,
`resource_contract_accuracy`, `trace_fidelity`, `error_contract_accuracy`,
`write_path_integrity`, `sensitive_data_leak_rate`, and
`bounded_output_compliance`. Accuracy/compliance thresholds are 1.0; sensitive
data leak rate must be 0.0. The benchmark includes a deliberate forbidden-data
negative control without committing an unsafe fixture.
