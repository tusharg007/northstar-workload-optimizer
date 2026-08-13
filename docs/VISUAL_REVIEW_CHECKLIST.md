# Gate 10B visual review checklist

Gate 10A did not claim browser-based visual verification because no live portfolio stack was kept running for this documentation-only audit. Use this checklist on the verified Compose stack before publishing screenshots.

## Metabase

Open each dashboard and verify readable titles, sensible layout, nonempty synthetic demo data, no broken cards, no overlaps, useful visualization choices, and no sensitive values:

- North Star | Operations Overview
- North Star | Approval & SLA
- North Star | Reliability & Recovery
- North Star | Governed Context Health
- North Star | Decision Trace & Risk

Confirm the Decision Trace dashboard labels structural completeness accurately and does not imply that SQL performs hash verification.

## n8n

- Exactly ten workflows are present and their names are readable.
- The expense-intake flow is understandable from webhook to service call and response.
- The Approval Orchestrator visibly contains the durable Wait path.
- The Reliability Dispatcher clearly shows reconcile, lease, delivery, and result recording.
- The Global Error Handler is recognizable and separate from normal processing.
- Node groupings and annotations do not overlap or expose credentials, authorization headers, or Wait/resume capability URLs.

## Recommended public screenshots

1. The suspicious-expense Approval Orchestrator paused at Wait, with sensitive execution data hidden.
2. The Operations Overview dashboard populated with clearly synthetic demo records.
3. Either Governed Context Health or Decision Trace & Risk, whichever best supports the interview story without duplicating the first two.
