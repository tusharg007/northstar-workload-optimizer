SELECT COUNT(*) AS requiring_review FROM observability.context_policy_health WHERE is_latest_version AND (review_overdue OR NOT owner_active OR trust_state <> 'TRUSTED');
