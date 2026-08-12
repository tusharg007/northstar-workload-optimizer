"""Safely migrate the legacy runtime SQLite table into the Gate 1 schema."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.db.repositories.workflows import WorkflowRepository
from app.db.session import Database

DEFAULT_SOURCE = PROJECT_DIR / "data" / "northstar_runtime.db"
DEFAULT_TARGET_URL = "sqlite:///data/northstar_runtime_g1.db"
LEGACY_TABLE = "runtime_expenses"
REQUIRED_COLUMNS = {
    "expense_id",
    "input_payload",
    "result",
    "status",
    "risk_level",
    "approver_role",
    "decision",
    "decided_by",
    "decision_comment",
    "decided_at",
    "created_at",
    "updated_at",
}


def read_legacy_rows(source: Path) -> list[dict]:
    """Read and validate the source in SQLite read-only mode."""
    source = source.resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Legacy SQLite source does not exist: {source}")
    uri = source.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (LEGACY_TABLE,),
        ).fetchone()
        if table is None:
            raise ValueError(f"Source is missing required table: {LEGACY_TABLE}")
        columns = {
            row[1]
            for row in connection.execute(f"PRAGMA table_info({LEGACY_TABLE})")
        }
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                "Legacy runtime schema is missing columns: "
                + ", ".join(sorted(missing))
            )
        connection.row_factory = sqlite3.Row
        raw_rows = connection.execute(
            f"SELECT * FROM {LEGACY_TABLE} ORDER BY created_at"
        ).fetchall()

    rows: list[dict] = []
    for raw in raw_rows:
        row = dict(raw)
        try:
            row["input_payload"] = json.loads(row["input_payload"])
            row["result"] = json.loads(row["result"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Legacy expense {row.get('expense_id')} contains invalid JSON"
            ) from exc
        rows.append(row)
    return rows


def _sqlite_target_path(target_url: str) -> Path | None:
    url = make_url(target_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return None
    return Path(url.database).resolve()


def migrate(
    source: Path = DEFAULT_SOURCE,
    target_url: str | None = None,
    *,
    write: bool = False,
) -> dict[str, int | bool]:
    """Validate/dry-run by default, or atomically import with explicit write."""
    rows = read_legacy_rows(source)
    selected_target = target_url or os.getenv(
        "NORTHSTAR_DATABASE_URL", DEFAULT_TARGET_URL
    )
    print(f"Legacy source: {source.resolve()}")
    print(f"Legacy records: {len(rows)}")
    print(f"Target: {selected_target}")
    if not write:
        print("DRY RUN: target database was not opened or changed")
        return {"records": len(rows), "imported": 0, "skipped": 0, "write": False}

    target_path = _sqlite_target_path(selected_target)
    if target_path is not None and target_path == source.resolve():
        raise ValueError(
            "Refusing to write into the legacy source database; choose a separate target"
        )

    database = Database(
        selected_target,
        create_schema=make_url(selected_target).get_backend_name() == "sqlite",
    )
    try:
        outcome = WorkflowRepository(database).import_legacy_rows(rows)
    finally:
        database.dispose()
    print(f"Imported: {outcome.imported}")
    print(f"Skipped existing: {outcome.skipped}")
    return {
        "records": len(rows),
        "imported": outcome.imported,
        "skipped": outcome.skipped,
        "write": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target-url", default=None)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Perform the import. Without this flag the command is read-only.",
    )
    args = parser.parse_args()
    try:
        migrate(args.source, args.target_url, write=args.write)
        return 0
    except (FileNotFoundError, ValueError, sqlite3.Error, SQLAlchemyError) as exc:
        print(f"MIGRATION FAILED: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
