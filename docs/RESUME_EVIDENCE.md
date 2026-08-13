# Verified resume evidence

Raw facts only; these are not polished resume bullets.

- Python 3.13.9, PostgreSQL 16.14, and Alembic head `20260813_0006` form the verified release baseline.
- SQLite suite: 122 passed, 13 skipped.
- PostgreSQL suite: 134 passed, 1 skipped.
- Gate 5 deterministic benchmark: 37/37 FAST and 37/37 PostgreSQL.
- Safety cases: unsafe action rate 0/7, abstention recall 7/7, abstention precision 7/7.
- Provenance verification: 23/23 benchmark cases; live release trace `PASS`.
- MCP SDK 2.0.0 provider: 12 tools, five resource templates, one prompt, stdio and loopback-only Streamable HTTP.
- MCP benchmark: 17/17 FAST and 16/16 PostgreSQL+n8n stdio.
- Exactly ten source-controlled n8n workflows; a waiting approval survived n8n restart and completed after approval.
- Exactly five Metabase dashboards and 36 questions through a dedicated read-only source role.
- Transactional outbox resume event reached `DELIVERED` with immutable human evidence.
- Two fresh-volume Compose starts and a whole-stack persistence restart passed.

These counts describe curated deterministic tests and release checks, not production traffic, model generalization, or remote CI status.
