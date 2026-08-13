SELECT COUNT(*) AS dead_letter_events FROM observability.reliability_outbox WHERE status = 'DEAD_LETTER';
