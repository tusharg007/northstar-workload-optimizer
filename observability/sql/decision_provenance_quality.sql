CREATE VIEW observability.decision_provenance_quality AS
SELECT dp.provenance_id, dp.expense_id, dp.workflow_run_id, dp.correlation_id,
  dp.automated_status, dp.risk_level, dp.approver_role, dp.context_trust_state,
  dp.decision_engine_version, dp.risk_engine_version, dp.risk_catalog_hash, dp.created_at,
  (SELECT COUNT(*) FROM decision_policy_evidence x WHERE x.provenance_id=dp.provenance_id) AS policy_evidence_count,
  (SELECT COUNT(*) FROM decision_term_evidence x WHERE x.provenance_id=dp.provenance_id) AS term_evidence_count,
  (SELECT COUNT(*) FROM decision_rule_evidence x WHERE x.provenance_id=dp.provenance_id) AS rule_evidence_count,
  (SELECT COUNT(*) FROM decision_trust_evidence x WHERE x.provenance_id=dp.provenance_id) AS trust_evidence_count,
  (SELECT COUNT(*) FROM decision_risk_evidence x WHERE x.provenance_id=dp.provenance_id) AS risk_evidence_count,
  (SELECT COUNT(*) FROM decision_human_evidence x WHERE x.provenance_id=dp.provenance_id) AS human_evidence_count,
  EXISTS (SELECT 1 FROM decision_policy_evidence x WHERE x.provenance_id=dp.provenance_id) AS has_policy_evidence,
  EXISTS (SELECT 1 FROM decision_rule_evidence x WHERE x.provenance_id=dp.provenance_id) AS has_rule_evidence,
  EXISTS (SELECT 1 FROM decision_trust_evidence x WHERE x.provenance_id=dp.provenance_id) AS has_trust_evidence,
  EXISTS (SELECT 1 FROM decision_risk_evidence x WHERE x.provenance_id=dp.provenance_id) AS has_risk_evidence,
  (EXISTS (SELECT 1 FROM decision_policy_evidence x WHERE x.provenance_id=dp.provenance_id)
   AND EXISTS (SELECT 1 FROM decision_rule_evidence x WHERE x.provenance_id=dp.provenance_id)
   AND EXISTS (SELECT 1 FROM decision_trust_evidence x WHERE x.provenance_id=dp.provenance_id)
   AND EXISTS (SELECT 1 FROM decision_risk_evidence x WHERE x.provenance_id=dp.provenance_id)) AS structurally_complete
FROM decision_provenance dp;
