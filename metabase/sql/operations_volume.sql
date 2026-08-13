SELECT DATE_TRUNC('day', created_at) AS day, COUNT(*) AS expense_count FROM observability.expense_operations GROUP BY day ORDER BY day;
