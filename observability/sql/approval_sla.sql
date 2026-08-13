CREATE VIEW observability.approval_sla AS
SELECT
    at.task_id,
    at.expense_id,
    at.workflow_run_id,
    at.approver_role,
    at.approval_level,
    at.status,
    e.risk_level,
    at.created_at,
    at.due_at,
    ad.decided_at AS completed_at,
    at.reminder_count,
    at.escalation_level,
    at.orchestration_status,
    GREATEST(0, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - at.created_at)))::bigint AS age_seconds,
    ROUND(GREATEST(0, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - at.created_at))) / 60)::bigint AS age_minutes,
    CASE WHEN at.due_at IS NULL OR at.status <> 'PENDING' THEN NULL
         ELSE EXTRACT(EPOCH FROM (at.due_at - CURRENT_TIMESTAMP))::bigint
    END AS sla_remaining_seconds,
    (at.status = 'PENDING' AND at.due_at IS NOT NULL AND CURRENT_TIMESTAMP >= at.due_at) AS overdue,
    CASE
      WHEN at.status <> 'PENDING' THEN 'COMPLETED'
      WHEN at.due_at IS NULL THEN 'UNSCHEDULED'
      WHEN at.due_at <= at.created_at THEN 'ESCALATION'
      WHEN CURRENT_TIMESTAMP >= at.created_at + ((at.due_at - at.created_at) * 1.5) THEN 'ESCALATION'
      WHEN CURRENT_TIMESTAMP >= at.due_at THEN 'OVERDUE'
      WHEN CURRENT_TIMESTAMP >= at.created_at + ((at.due_at - at.created_at) * 0.5) THEN 'REMINDER'
      ELSE 'ON_TRACK'
    END AS sla_stage
FROM approval_tasks at
JOIN expenses e ON e.expense_id = at.expense_id
LEFT JOIN approval_decisions ad ON ad.approval_task_id = at.task_id;
