# Gate 9: reproducible release foundation

## 1. Release goals

Gate 9 turns the verified Gate 7 system into a clean-checkout release: locked Python dependencies, one non-root application image, automatically bootstrapped Compose services, CI, local verification, and accurate engineering documentation. It adds no domain or voice features.

## 2. Compose architecture

`docker-compose.yml` defines PostgreSQL, migration/context/role one-shots, API, demo notification sink, n8n bootstrap/runtime, and Metabase bootstrap/runtime. The Python services reuse `northstar-app:g9`; n8n is exactly 2.22.6 and Metabase retains the verified 0.63.2.7 application image and JAR pinned by digest. `northstar-metabase:g9` replaces that image's published zero-length JDK tree with the Temurin 21 tree from the pinned official 0.61.2.x image; both inputs remain immutable digest pins.

## 3. Database separation

One PostgreSQL 16.14 server holds `northstar`, `n8n_app`, and `metabase_app`. Their owners are `northstar_app`, `northstar_n8n`, and `northstar_metabase`. The bootstrap admin is not used by normal runtime services. `northstar_metabase_ro` is separately reconciled for source reads.

## 4. Bootstrap ordering

PostgreSQL health gates Alembic. Migration success gates deterministic context seeding and read-only-role reconciliation. Context success gates API and workflow import. API/n8n/Metabase health and completed bootstraps gate the release verifier. Failures remain visible as failed one-shot containers.

## 5. Dependency locking

`requirements.txt` remains the human-maintained direct specification. `requirements.lock` contains the universal uv resolution, platform markers, and artifact hashes for Python 3.13.9. `scripts/validate_dependency_lock.py` binds it to the SHA-256 of canonical LF dependency text, so Windows and Linux checkouts validate identically.

Intentional update:

```powershell
.\.venv\Scripts\uv.exe pip compile requirements.txt --output-file requirements.lock --generate-hashes --python-version 3.13.9
.\.venv\Scripts\python.exe scripts\validate_dependency_lock.py --stamp
```

Install with `uv pip sync --require-hashes requirements.lock` into a fresh environment.

## 6. n8n persistence

n8n uses `n8n_app` through the actual 2.22.6 `DB_POSTGRESDB_*` settings. A named profile volume retains the instance configuration; workflow/execution/Wait truth resides in PostgreSQL. The internal task broker uses port 5680, separate from the HTTP service on 5679. Bootstrap transforms only runtime copies from host loopback API/sink URLs to Compose service DNS, preserving portable source JSON and stable IDs.

## 7. Metabase persistence

Metabase application state uses `metabase_app`. The idempotent bootstrap reconciles one logical collection, 36 questions, and five dashboards. North Star data is queried only through the read-only source principal and approved observability views.

## 8. Docker networking

All containers join `northstar_private`. API, n8n, Metabase, and the debugging PostgreSQL mapping bind only to `127.0.0.1`. The notification sink is internal. No service treats container loopback as another service.

## 9. Configuration and secrets

`.env.example` inventories every required credential and safe operational default. `.env` is ignored. Values are disposable examples, not production secrets. n8n and Metabase encryption keys are required explicitly.

## 10. CI design

`ci.yml` has static, SQLite, PostgreSQL 16.14, and Docker structural jobs. `integration.yml` is manual because the full n8n/Metabase stack is heavier; it performs Compose smoke, MCP stdio, and live Metabase validation with disposable credentials and least repository permissions.

## 11. Local release checks

`python scripts/release_check.py` calls existing compile, dependency, validator, pytest, Gate 5 FAST, MCP FAST, and whitespace checks. `scripts/verify_stack.py` fails closed on service health, inventory, governed context, suspicious-expense/approval, Wait completion, delivered resume outbox, human evidence, and provenance verification.

## 12. Clean-checkout verification

The release candidate must be reconstructed from candidate source-controlled files, installed into a fresh virtual environment, and started with fresh project-scoped Compose volumes. Existing `.venv`, local databases, n8n profiles, Metabase application state, reports, and unrelated Docker resources are excluded.

## 13. Restart verification

Restart n8n while an approval is waiting, approve it, and require completion. Restart API and the full stack without deleting volumes, then require previous state, provenance, workflows, and dashboards to remain.

## 14. Fresh-volume verification

Only the selected Compose project's resources are removed with `docker compose -p <project> down --volumes`. A second zero-state start must recreate databases, reach Alembic `20260813_0006`, seed context, import ten workflows, bootstrap 36/5 Metabase objects, and pass smoke without manual repair.

## 15. Known limitations

This is a loopback demo release, not an internet deployment. Production auth/RBAC, TLS, secret management, backups, HA, ingress/network policy, remote MCP auth, and real notification providers remain open. Delivery is at least once.

## 16. Release evidence

The final recovery verification produced these exact results:

- SQLite: 122 passed, 13 skipped.
- PostgreSQL: 134 passed, 1 skipped.
- Gate 5 FAST and PostgreSQL: 37/37 each.
- MCP FAST: 17/17; MCP PostgreSQL+n8n stdio: 16/16.
- n8n bootstrap and restart inventory: exactly 13 workflows.
- Metabase bootstrap and restart inventory: exactly 36 questions and five dashboards.
- Alembic: `20260813_0006`; both zero-volume starts and the whole-stack persistence restart passed.
- An approval execution remained `WAITING` across an n8n-only restart, then reached `APPROVED` and `COMPLETED` with immutable human evidence, a `DELIVERED` resume outbox, and provenance `PASS`.
