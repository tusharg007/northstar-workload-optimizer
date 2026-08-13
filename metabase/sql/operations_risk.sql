SELECT COALESCE(risk_level, 'UNCLASSIFIED') AS risk_level, COUNT(*) AS expense_count FROM observability.expense_operations GROUP BY risk_level ORDER BY expense_count DESC;
