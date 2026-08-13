SELECT COALESCE(risk_level, 'UNCLASSIFIED') AS risk_level, COUNT(*) AS pending_count FROM observability.approval_sla WHERE status = 'PENDING' GROUP BY risk_level ORDER BY pending_count DESC;
