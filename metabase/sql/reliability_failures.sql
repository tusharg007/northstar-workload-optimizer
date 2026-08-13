SELECT workflow_name, COUNT(*) AS failure_records, SUM(occurrence_count) AS occurrences FROM observability.workflow_failures WHERE status = 'OPEN' GROUP BY workflow_name ORDER BY occurrences DESC;
