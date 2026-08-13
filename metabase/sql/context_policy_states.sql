SELECT trust_state, COUNT(*) AS policy_count FROM observability.context_policy_health WHERE is_latest_version GROUP BY trust_state ORDER BY policy_count DESC;
