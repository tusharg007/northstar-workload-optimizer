CREATE VIEW observability.delivery_attempts AS
SELECT
    oda.attempt_id,
    oda.outbox_event_id,
    oe.event_type,
    oe.correlation_id,
    oda.attempt_number,
    oda.outcome,
    oda.worker_id,
    oda.error_category,
    oda.started_at,
    oda.completed_at,
    ROUND(EXTRACT(EPOCH FROM (oda.completed_at - oda.started_at)) * 1000)::bigint AS duration_ms
FROM outbox_delivery_attempts oda
JOIN outbox_events oe ON oe.outbox_event_id = oda.outbox_event_id;
