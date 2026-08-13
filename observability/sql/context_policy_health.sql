CREATE VIEW observability.context_policy_health AS
WITH signal_rollup AS (
  SELECT policy_version_id,
    COUNT(DISTINCT signal_type) FILTER (
      WHERE observed_at <= CURRENT_TIMESTAMP
        AND signal_type IN ('CERTIFICATION','FRESHNESS','OWNERSHIP','SOURCE_VERIFICATION')
    ) AS observed_required_count,
    BOOL_OR(status = 'FAIL' AND observed_at <= CURRENT_TIMESTAMP) AS has_failure,
    BOOL_OR(status <> 'PASS' AND observed_at <= CURRENT_TIMESTAMP) AS has_non_pass,
    BOOL_OR(signal_type = 'FRESHNESS' AND observed_at <= CURRENT_TIMESTAMP AND expires_at < CURRENT_TIMESTAMP) AS freshness_expired,
    BOOL_OR(signal_type <> 'FRESHNESS' AND observed_at <= CURRENT_TIMESTAMP AND expires_at < CURRENT_TIMESTAMP) AS other_signal_expired,
    MAX(expires_at) FILTER (WHERE signal_type = 'FRESHNESS') AS freshness_expires_at
  FROM trust_signals WHERE policy_version_id IS NOT NULL
  GROUP BY policy_version_id
), versions AS (
  SELECT pv.*, ROW_NUMBER() OVER (PARTITION BY pv.policy_id ORDER BY pv.version_number DESC) = 1 AS is_latest_version
  FROM policy_versions pv
)
SELECT pd.policy_key, pd.policy_name, pd.domain, v.policy_version_id, v.version_number, v.status,
  go.owner_key, go.display_name AS owner_display_name, go.active AS owner_active,
  v.effective_from, v.effective_to, v.review_due_at, v.certified_at, v.content_hash,
  v.is_latest_version,
  (v.effective_from <= CURRENT_TIMESTAMP AND (v.effective_to IS NULL OR v.effective_to >= CURRENT_TIMESTAMP)) AS currently_effective,
  (v.review_due_at IS NOT NULL AND v.review_due_at < CURRENT_TIMESTAMP) AS review_overdue,
  (go.owner_id IS NULL) AS owner_missing,
  COALESCE(sr.freshness_expired, false) AS freshness_expired,
  sr.freshness_expires_at,
  CASE
    WHEN COALESCE(sr.has_failure, false) THEN 'CONFLICTED'
    WHEN (v.review_due_at IS NOT NULL AND v.review_due_at < CURRENT_TIMESTAMP) OR COALESCE(sr.freshness_expired, false) THEN 'STALE'
    WHEN v.status <> 'CERTIFIED' OR NOT COALESCE(go.active, false)
      OR COALESCE(sr.observed_required_count, 0) < 4
      OR COALESCE(sr.has_non_pass, false) OR COALESCE(sr.other_signal_expired, false) THEN 'UNVERIFIED'
    ELSE 'TRUSTED'
  END AS trust_state,
  CASE WHEN COALESCE(sr.has_failure, false) THEN false
       WHEN (v.review_due_at IS NOT NULL AND v.review_due_at < CURRENT_TIMESTAMP) OR COALESCE(sr.freshness_expired, false) THEN false
       WHEN v.status <> 'CERTIFIED' OR NOT COALESCE(go.active, false) OR COALESCE(sr.observed_required_count, 0) < 4 OR COALESCE(sr.has_non_pass, false) OR COALESCE(sr.other_signal_expired, false) THEN false
       ELSE true END AS trusted,
  ((v.review_due_at IS NOT NULL AND v.review_due_at < CURRENT_TIMESTAMP) OR COALESCE(sr.freshness_expired, false)) AS stale,
  (v.status <> 'CERTIFIED' OR NOT COALESCE(go.active, false) OR COALESCE(sr.observed_required_count, 0) < 4 OR COALESCE(sr.has_non_pass, false) OR COALESCE(sr.other_signal_expired, false)) AS unverified
FROM policy_definitions pd
JOIN versions v ON v.policy_id = pd.policy_id
LEFT JOIN governance_owners go ON go.owner_id = pd.owner_id
LEFT JOIN signal_rollup sr ON sr.policy_version_id = v.policy_version_id;
