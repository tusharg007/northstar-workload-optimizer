#!/bin/sh
set -eu

: "${NORTHSTAR_APP_DB_USER:?NORTHSTAR_APP_DB_USER is required}"
: "${NORTHSTAR_APP_DB_PASSWORD:?NORTHSTAR_APP_DB_PASSWORD is required}"
: "${N8N_DB_USER:?N8N_DB_USER is required}"
: "${N8N_DB_PASSWORD:?N8N_DB_PASSWORD is required}"
: "${METABASE_APP_DB_USER:?METABASE_APP_DB_USER is required}"
: "${METABASE_APP_DB_PASSWORD:?METABASE_APP_DB_PASSWORD is required}"

export PGUSER="$POSTGRES_USER"
export PGPASSWORD="$POSTGRES_PASSWORD"

psql --dbname postgres \
  --set=app_user="$NORTHSTAR_APP_DB_USER" \
  --set=app_password="$NORTHSTAR_APP_DB_PASSWORD" \
  --set=n8n_user="$N8N_DB_USER" \
  --set=n8n_password="$N8N_DB_PASSWORD" \
  --set=metabase_user="$METABASE_APP_DB_USER" \
  --set=metabase_password="$METABASE_APP_DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'n8n_user', :'n8n_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'n8n_user') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'metabase_user', :'metabase_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'metabase_user') \gexec

SELECT format('CREATE DATABASE northstar OWNER %I', :'app_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'northstar') \gexec
SELECT format('CREATE DATABASE n8n_app OWNER %I', :'n8n_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'n8n_app') \gexec
SELECT format('CREATE DATABASE metabase_app OWNER %I', :'metabase_user')
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'metabase_app') \gexec
SQL
