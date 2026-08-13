SELECT context_trust_state, COUNT(*) AS decision_count FROM observability.decision_provenance_quality GROUP BY context_trust_state ORDER BY decision_count DESC;
