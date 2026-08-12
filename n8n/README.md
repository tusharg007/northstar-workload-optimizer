# North Star n8n workflows

Tested with n8n **2.22.6**.

| File | Kind | Calls |
|---|---|---|
| `workflows/01_expense_intake.json` | Public | `northstarProcessExpenseService` |
| `workflows/02_approval_decision.json` | Public | `northstarRecordDecisionService` |
| `workflows/10_process_expense_service.json` | Internal | FastAPI process endpoint |
| `workflows/11_record_decision_service.json` | Internal | FastAPI decision endpoint |
| `workflows/20_approval_orchestrator.json` | Internal | Durable Wait/resume approval lifecycle |
| `workflows/21_approval_notification_service.json` | Internal | Configurable HTTP notification adapter |
| `workflows/22_approval_sla_monitor.json` | Scheduled | Due-notification reservation and dispatch |
| `workflows/23_reliability_dispatcher.json` | Scheduled/internal | Reconcile, lease, and deliver outbox events |
| `workflows/24_dead_letter_replay.json` | Internal | Explicit replay of one dead-letter event |
| `workflows/99_global_error_handler.json` | Error Trigger | Persist sanitized workflow incidents |

Public contracts are `POST /webhook/northstar-expense` and
`POST /webhook/northstar-approval`.

Validate and import from Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe scripts\validate_n8n_workflows.py
npx.cmd --yes n8n import:workflow --separate --input="n8n\workflows"
```

Publish internal workflows before public workflows, then start n8n:

```powershell
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

The local FastAPI base URL is set once in each relevant internal workflow's
`Runtime Configuration` node. The notification service also defines its sink
once as `http://127.0.0.1:9010/notifications`. Do not add `$env`, secrets,
credentials, or database nodes to these exports. The Wait resume URL is an
internal capability URL: never expose it in a public response or notification.
All workflows except Workflow 99 reference `northstarGlobalErrorHandler` in
`settings.errorWorkflow`; Workflow 99 deliberately does not reference itself.
Workflow 24 has no Webhook node and can only be invoked internally.
