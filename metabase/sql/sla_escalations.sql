SELECT SUM(reminder_count) AS reminders, SUM(CASE WHEN escalation_level > 0 THEN 1 ELSE 0 END) AS escalated_tasks FROM observability.approval_sla;
