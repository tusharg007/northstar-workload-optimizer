"""Fail when requirements.lock was not generated from the current requirements.txt."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
LOCK = ROOT / "requirements.lock"
MARKER = "# northstar-requirements-sha256: "


def source_hash() -> str:
    # Git and Windows working trees may use different line endings. Dependency
    # meaning does not change, so bind the lock to canonical LF text.
    canonical = REQUIREMENTS.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stamp", action="store_true", help="Update the lock source-hash marker after regenerating it")
    args = parser.parse_args()
    if not LOCK.is_file():
        raise SystemExit("FAIL: requirements.lock is missing")
    text = LOCK.read_text(encoding="utf-8")
    expected = source_hash()
    if args.stamp:
        if MARKER in text:
            text = re.sub(r"^# northstar-requirements-sha256: [0-9a-f]+$", MARKER + expected, text, count=1, flags=re.MULTILINE)
        else:
            lines = text.splitlines()
            lines.insert(2, MARKER + expected)
            text = "\n".join(lines) + "\n"
        LOCK.write_text(text, encoding="utf-8", newline="\n")
        print(f"PASS: stamped requirements.lock with {expected}")
        return 0
    marker = next((line.removeprefix(MARKER) for line in text.splitlines() if line.startswith(MARKER)), None)
    if marker != expected:
        raise SystemExit(
            "FAIL: requirements.lock is stale. Regenerate with the documented uv command, "
            "then run scripts/validate_dependency_lock.py --stamp"
        )
    if "--hash=sha256:" not in text:
        raise SystemExit("FAIL: requirements.lock does not contain package hashes")
    print(f"PASS: requirements.lock matches requirements.txt ({expected})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
