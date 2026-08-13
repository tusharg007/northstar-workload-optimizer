"""Create/reconcile the local demo principal used by Metabase."""

from __future__ import annotations

import argparse
import os

import psycopg
from psycopg import sql

DEFAULT_ROLE = "northstar_metabase_ro"


def reconcile_role(admin_dsn: str, role: str, password: str) -> None:
    if not password:
        raise ValueError("NORTHSTAR_METABASE_DB_PASSWORD must be non-empty")
    psycopg_dsn = admin_dsn.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(psycopg_dsn, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
        ).fetchone()
        ident = sql.Identifier(role)
        if not exists:
            connection.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    ident, sql.Literal(password)
                )
            )
        else:
            connection.execute(
                sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
                    ident, sql.Literal(password)
                )
            )
        connection.execute(sql.SQL("ALTER ROLE {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(ident))
        connection.execute(sql.SQL("REVOKE ALL ON SCHEMA public FROM {}").format(ident))
        connection.execute(sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(ident))
        connection.execute(sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {}").format(ident))
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA observability TO {}").format(ident))
        connection.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA observability TO {}").format(ident))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admin-dsn", default=os.getenv("NORTHSTAR_DATABASE_URL"))
    parser.add_argument("--role", default=os.getenv("NORTHSTAR_METABASE_DB_USER", DEFAULT_ROLE))
    args = parser.parse_args()
    password = os.getenv("NORTHSTAR_METABASE_DB_PASSWORD", "")
    if not args.admin_dsn:
        parser.error("--admin-dsn or NORTHSTAR_DATABASE_URL is required")
    reconcile_role(args.admin_dsn, args.role, password)
    print(f"PASS: reconciled read-only role {args.role!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
