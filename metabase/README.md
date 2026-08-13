# North Star Metabase bootstrap

Gate 6 targets Metabase Open Source **v0.63.2.7** (`30c5762`). The official
release line is `metabase/metabase:v0.63.2.x` with image digest
`sha256:095503d38b0048c1e7b499509d04ffb7b9999167872199a34bb7b73c5913fb9d`.
The verified OSS JAR SHA-256 is
`dc719b2dce60e0fae8d351dc0d44a59f0da696245f10bfb2882aa20c0506c858`.

On the verified Docker Desktop 29.6.2 Windows host, the official image's large
layers were repeatedly materialized corrupt after an initial disk-full ingest.
The Gate 6 compose file therefore runs the hash-verified official JAR on pinned
Temurin Java 21. This does not modify the Metabase application artifact.

Prepare and statically validate:

```powershell
.\.venv\Scripts\python.exe -m metabase.prepare_artifact
.\.venv\Scripts\python.exe metabase\validate.py
```

Set disposable credentials, start PostgreSQL, migrate North Star, create the
read-only principal, and start Metabase:

```powershell
$env:NORTHSTAR_POSTGRES_ADMIN_PASSWORD="choose-a-local-admin-password"
$env:NORTHSTAR_METABASE_DB_PASSWORD="choose-a-distinct-readonly-password"
$env:METABASE_ADMIN_PASSWORD="choose-a-local-metabase-password"
$env:NORTHSTAR_DATABASE_URL="postgresql+psycopg://northstar:$env:NORTHSTAR_POSTGRES_ADMIN_PASSWORD@localhost:55432/northstar"

docker compose -p northstar-g6 -f infra\metabase\docker-compose.metabase.yml up -d postgres
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\seed_context_registry.py --write
.\.venv\Scripts\python.exe scripts\create_metabase_readonly_role.py
.\.venv\Scripts\python.exe -m scripts.seed_observability_demo
docker compose -p northstar-g6 -f infra\metabase\docker-compose.metabase.yml up -d metabase
```

Bootstrap and verify all live cards:

```powershell
$env:METABASE_URL="http://localhost:3000"
$env:NORTHSTAR_METABASE_DB_HOST="postgres"
.\.venv\Scripts\python.exe -m metabase.bootstrap
.\.venv\Scripts\python.exe -m metabase.live_validate
```

The bootstrap may be run repeatedly. Repository logical keys in descriptions,
not Metabase numeric IDs, are authoritative. An upgrade requires revalidating
the centralized API contracts in `client.py` and `bootstrap.py`.

Metabase owns the separate `metabase_app` database. Its North Star data-source
credentials are `northstar_metabase_ro`, which can select only approved
`observability` views and cannot select or mutate base tables.
