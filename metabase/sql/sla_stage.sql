SELECT sla_stage, COUNT(*) AS task_count FROM observability.approval_sla GROUP BY sla_stage ORDER BY task_count DESC;
