CREATE VIEW observability.risk_signal_activity AS
SELECT dp.provenance_id, dp.expense_id, dp.created_at AS decision_time,
  dre.signal_key, dre.canonical_name, dre.engine_component, dre.triggered,
  dp.risk_level, dp.automated_status
FROM decision_risk_evidence dre
JOIN decision_provenance dp ON dp.provenance_id = dre.provenance_id;
