SELECT DATE_TRUNC('day', started_at) AS day, outcome, COUNT(*) AS attempt_count FROM observability.delivery_attempts GROUP BY day, outcome ORDER BY day;
