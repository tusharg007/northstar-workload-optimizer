# Security boundaries

## Implemented

- Compose application services do not share the PostgreSQL superuser. North Star, n8n, and Metabase use separate databases and login roles.
- The application image runs as UID/GID `10001`, installs from a hash-locked dependency set, and excludes host virtual environments, Git metadata, environment files, local databases, runtime profiles, logs, and generated reports.
- Metabase connects to North Star only as `northstar_metabase_ro`, with `USAGE` on `observability` and `SELECT` on approved views; base-table access and writes are revoked.
- MCP outputs are minimized. MCP has no direct database access, write tools use normal n8n pathways, and Streamable HTTP rejects non-loopback bindings.
- Policy-dependent decisions require authoritative, versioned governed context and safely abstain when trust or engine binding fails.
- Approval decisions, context evidence, provenance hashes, workflow state, and delivery attempts are transactional and auditable.
- Exposed Compose ports bind to `127.0.0.1`; containers communicate over a dedicated bridge network.
- No real credentials, tokens, or `.env` file are source-controlled.

## Not implemented

- Production authentication or end-user identity binding.
- RBAC and tenant isolation.
- OAuth or another remote authentication scheme for MCP HTTP.
- A production secret manager or automated secret rotation.
- TLS termination, production firewall/network policy, or an ingress gateway.
- Database backup/restore automation, high availability, or disaster recovery.
- Production notification providers; the bundled sink is test/demo infrastructure.

Do not expose this demo stack to an untrusted network. Replace disposable credentials, add an authenticated ingress, and complete the controls above before any production deployment.
