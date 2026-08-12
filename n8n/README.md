# North Star n8n workflows

Tested with n8n **2.22.6**.

| File | Kind | Calls |
|---|---|---|
| `workflows/01_expense_intake.json` | Public | `northstarProcessExpenseService` |
| `workflows/02_approval_decision.json` | Public | `northstarRecordDecisionService` |
| `workflows/10_process_expense_service.json` | Internal | FastAPI process endpoint |
| `workflows/11_record_decision_service.json` | Internal | FastAPI decision endpoint |

Public contracts are `POST /webhook/northstar-expense` and
`POST /webhook/northstar-approval`.

Validate and import from Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\validate_n8n_workflows.py
npx.cmd --yes n8n import:workflow --separate --input="n8n\workflows"
```

Publish internal workflows before public workflows, then start n8n:

```powershell
npx.cmd --yes n8n publish:workflow --id=northstarProcessExpenseService
npx.cmd --yes n8n publish:workflow --id=northstarRecordDecisionService
npx.cmd --yes n8n publish:workflow --id=northstarExpenseIntake
npx.cmd --yes n8n publish:workflow --id=northstarApprovalDecision
npx.cmd --yes n8n start
```

The local FastAPI base URL is set once in each internal workflow's `Runtime
Configuration` node. The source-controlled value is
`http://127.0.0.1:8000`. Do not add `$env`, secrets, credentials, or database
nodes to these exports.
