SELECT ROUND(100.0 * COUNT(*) FILTER (WHERE requires_human_review) / NULLIF(COUNT(*), 0), 2) AS human_review_percent FROM observability.expense_operations;
