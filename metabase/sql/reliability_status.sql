SELECT status, COUNT(*) AS event_count FROM observability.reliability_outbox GROUP BY status ORDER BY event_count DESC;
