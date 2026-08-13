CREATE VIEW observability.expense_operations AS
SELECT
    e.expense_id,
    e.department,
    e.category,
    e.amount,
    e.currency,
    e.created_at,
    e.updated_at,
    e.status,
    e.risk_level,
    e.approver_role,
    wr.id AS workflow_run_id,
    wr.correlation_id,
    wr.started_at AS workflow_started_at,
    wr.completed_at AS workflow_completed_at,
    CASE WHEN wr.completed_at IS NULL THEN NULL
         ELSE ROUND(EXTRACT(EPOCH FROM (wr.completed_at - wr.started_at)) * 1000)::bigint
    END AS processing_duration_ms,
    EXISTS (
        SELECT 1 FROM approval_tasks at
        WHERE at.workflow_run_id = wr.id
    ) AS requires_human_review,
    COALESCE(ad.decision, e.current_decision) AS final_decision
FROM expenses e
LEFT JOIN workflow_runs wr ON wr.expense_id = e.expense_id
LEFT JOIN approval_decisions ad ON ad.workflow_run_id = wr.id;
