"""Preview or write the source-controlled governed context registry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from app.context.exceptions import SeedConflictError  # noqa: E402
from app.context.seed import apply_seed, load_seed  # noqa: E402
from app.db.session import Database  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the North Star Governed Context Registry")
    parser.add_argument("--seed", default=str(PROJECT_DIR / "context" / "registry.seed.json"))
    parser.add_argument("--write", action="store_true", help="Persist changes; default is preview only")
    args = parser.parse_args(argv)
    database = Database()
    try:
        result = apply_seed(database, load_seed(args.seed), write=args.write)
    except SeedConflictError as exc:
        print(json.dumps({"status": "CONFLICT", "error": str(exc)}, indent=2))
        return 1
    finally:
        database.dispose()
    print(json.dumps({"status": "OK", **result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
