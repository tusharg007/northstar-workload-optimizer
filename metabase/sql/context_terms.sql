SELECT trust_state, COUNT(*) AS term_count FROM observability.context_term_health WHERE is_latest_version GROUP BY trust_state ORDER BY term_count DESC;
