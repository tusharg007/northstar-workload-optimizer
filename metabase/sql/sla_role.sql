SELECT approver_role, COUNT(*) AS pending_count FROM observability.approval_sla WHERE status = 'PENDING' GROUP BY approver_role ORDER BY pending_count DESC;
