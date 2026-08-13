CREATE VIEW observability.workflow_failures AS
SELECT
    failure_id,
    workflow_id,
    workflow_name,
    failed_node,
    error_class,
    occurrence_count,
    status,
    first_seen_at,
    last_seen_at,
    correlation_id,
    expense_id
FROM workflow_failures;
