SELECT COUNT(*) AS pending_events FROM observability.reliability_outbox WHERE status = 'PENDING';
