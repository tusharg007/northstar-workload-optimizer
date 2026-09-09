"""Run the non-live Gate 9 release checks using the current Python environment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]


def run(label: str, command: list[str]) -> None:
    print(f"\n== {label} ==", flush=True)
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode:
        raise SystemExit(f"RELEASE CHECK: FAIL at {label} (exit {completed.returncode})")


def main() -> int:
    python = sys.executable
    release_temp = ROOT / ".tmp" / "release-temp"
    release_temp.mkdir(parents=True, exist_ok=True)
    os.environ["TEMP"] = str(release_temp)
    os.environ["TMP"] = str(release_temp)
    # Pytest deletes --basetemp on startup. A unique path avoids stale Windows
    # handles/ACLs and concurrent release runs sharing the same directory.
    pytest_base = ROOT / ".tmp" / f"pytest-release-{uuid4().hex}"
    pytest_base.parent.mkdir(parents=True, exist_ok=True)
    run("dependency lock", [python, "scripts/validate_dependency_lock.py"])
    run("compileall", [python, "-m", "compileall", "-q", "app", "automation", "context", "evals", "mcp_server", "metabase", "scripts", "tests"])
    run("pip check", [python, "-m", "pip", "check"])
    run("n8n workflow validator", [python, "scripts/validate_n8n_workflows.py"])
    run("MCP contract validator", [python, "scripts/validate_mcp_server.py"])
    run("Metabase manifest validator", [python, "-m", "metabase.validate"])
    run("SQLite pytest", [python, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--basetemp={pytest_base}"])
    run("Gate 5 FAST", [python, "-m", "scripts.run_evals", "--profile", "fast"])
    run("MCP FAST", [python, "-m", "scripts.run_mcp_evals", "--profile", "fast"])
    if (ROOT / ".git").exists():
        run("working-tree whitespace", ["git", "diff", "--check"])
        run("staged whitespace", ["git", "diff", "--cached", "--check"])
    else:
        print("\n== whitespace ==\nSKIP: source export has no Git metadata")
    print("\nNORTH STAR LOCAL RELEASE CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
