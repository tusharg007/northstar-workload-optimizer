SELECT status, COUNT(*) AS expense_count FROM observability.expense_operations GROUP BY status ORDER BY expense_count DESC;
