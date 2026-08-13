"""Cross-platform, fail-closed verification for the running Gate 9 stack."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
EXPECTED_WORKFLOWS = 10
EXPECTED_QUESTIONS = 36
EXPECTED_DASHBOARDS = 5
EXPECTED_ALEMBIC_HEAD = "20260813_0006"


def load_dotenv() -> None:
    """Load simple KEY=VALUE pairs without adding a runtime dependency."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def wait_json(client: httpx.Client, url: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    last = "no response"
    while time.monotonic() < deadline:
        try:
            response = client.get(url)
            if response.is_success:
                value = response.json()
                if isinstance(value, dict):
                    return value
            last = f"HTTP {response.status_code}"
        except (httpx.HTTPError, ValueError) as exc:
            last = str(exc)
        time.sleep(1)
    raise RuntimeError(f"{url} not ready within {timeout:g}s ({last})")


def docker_executable() -> str:
    found = shutil.which("docker")
    if found:
        return found
    fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "DockerDesktop" / "resources" / "bin" / "docker.exe"
    if fallback.is_file():
        return str(fallback)
    raise RuntimeError("Docker CLI not found on PATH or at the Docker Desktop fallback path")


def workflow_count(project: str) -> int:
    command = [docker_executable(), "compose", "-p", project, "exec", "-T", "n8n", "n8n", "list:workflow", "--onlyId"]
    try:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False, timeout=60)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("n8n workflow listing exceeded 60 seconds") from exc
    require(result.returncode == 0, f"n8n workflow listing failed: {(result.stderr or result.stdout).strip()}")
    return len([line for line in result.stdout.splitlines() if line.strip().startswith("northstar")])


def metabase_inventory(base_url: str, email: str, password: str) -> tuple[int, int]:
    from metabase.bootstrap import MARKER, _items, _logical_key
    from metabase.client import MetabaseClient

    client = MetabaseClient(base_url, timeout=20)
    try:
        client.login(email, password)
        questions = [item for item in _items(client.get("/api/card?f=all")) if _logical_key(item)]
        dashboards = [item for item in _items(client.get("/api/dashboard")) if _logical_key(item)]
        require(all(MARKER in str(item.get("description")) for item in questions + dashboards), "Metabase inventory contains an unmarked North Star item")
        return len(questions), len(dashboards)
    finally:
        client.close()


def wait_metabase_inventory(base_url: str, email: str, password: str, timeout: float) -> tuple[int, int]:
    deadline = time.monotonic() + timeout
    last: tuple[int, int] | str = "not authenticated"
    while time.monotonic() < deadline:
        try:
            last = metabase_inventory(base_url, email, password)
            if last == (EXPECTED_QUESTIONS, EXPECTED_DASHBOARDS):
                return last
        except Exception as exc:
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1)
    raise RuntimeError(f"Metabase bootstrap did not reach 36 questions/5 dashboards; last={last}")


def database_contract() -> str:
    import psycopg

    connection = psycopg.connect(
        host="127.0.0.1",
        port=int(os.getenv("NORTHSTAR_POSTGRES_PORT", "55432")),
        dbname="postgres",
        user=os.getenv("NORTHSTAR_POSTGRES_ADMIN_USER", "northstar_admin"),
        password=os.getenv("NORTHSTAR_POSTGRES_ADMIN_PASSWORD", ""),
        connect_timeout=5,
    )
    try:
        databases = {row[0]: row[1] for row in connection.execute(
            "SELECT d.datname, r.rolname FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba WHERE d.datname IN ('northstar','n8n_app','metabase_app')"
        )}
        require(databases == {
            "northstar": os.getenv("NORTHSTAR_APP_DB_USER", "northstar_app"),
            "n8n_app": os.getenv("N8N_DB_USER", "northstar_n8n"),
            "metabase_app": os.getenv("METABASE_APP_DB_USER", "northstar_metabase"),
        }, f"database ownership separation is wrong: {databases}")
    finally:
        connection.close()
    northstar = psycopg.connect(
        host="127.0.0.1",
        port=int(os.getenv("NORTHSTAR_POSTGRES_PORT", "55432")),
        dbname="northstar",
        user=os.getenv("NORTHSTAR_APP_DB_USER", "northstar_app"),
        password=os.getenv("NORTHSTAR_APP_DB_PASSWORD", ""),
        connect_timeout=5,
    )
    try:
        revision = northstar.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        require(revision == EXPECTED_ALEMBIC_HEAD, f"expected Alembic {EXPECTED_ALEMBIC_HEAD}, found {revision}")
        return revision
    finally:
        northstar.close()


def poll_task(client: httpx.Client, api: str, expense_id: str, expected: str, timeout: float = 45) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"{api}/api/internal/approval-tasks/by-expense/{expense_id}")
        if response.status_code == 200:
            last = response.json()
            if last.get("orchestration_status") == expected:
                return last
        time.sleep(0.25)
    raise RuntimeError(f"approval task did not reach {expected}; last state={last}")


def smoke(client: httpx.Client, api: str, n8n: str) -> str:
    payload = json.loads((ROOT / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    expense_id = "G9-STACK-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    payload["expense_id"] = expense_id
    response = client.post(f"{n8n}/webhook/northstar-expense", json=payload, headers={"X-Correlation-ID": expense_id.lower()})
    response.raise_for_status()
    submitted = response.json()
    require(
        (submitted.get("status"), submitted.get("risk_level"), submitted.get("approver_role"))
        == ("ESCALATED", "CRITICAL", "Finance Director + Compliance"),
        f"unexpected suspicious-expense result: {submitted}",
    )
    task = poll_task(client, api, expense_id, "WAITING")
    time.sleep(0.5)
    response = client.post(f"{n8n}/webhook/northstar-approval", json={
        "expense_id": expense_id,
        "decision": "approve",
        "approver": "Gate 9 Verifier",
        "comment": "Deterministic release verification",
    })
    response.raise_for_status()
    require(response.json().get("status") == "APPROVED", f"approval did not succeed: {response.text}")
    poll_task(client, api, expense_id, "COMPLETED")
    outbox = client.get(f"{api}/api/internal/outbox/by-delivery-key/approval-resume:{task['task_id']}")
    outbox.raise_for_status()
    require(outbox.json().get("status") == "DELIVERED", f"resume outbox not delivered: {outbox.text}")
    trace = client.get(f"{api}/api/provenance/expenses/{expense_id}/trace")
    trace.raise_for_status()
    trace_body = trace.json()
    provenance_id = trace_body.get("provenance_id")
    require(trace_body.get("final_status") == "APPROVED" and trace_body.get("approval_decision"), "trace lacks final approval human evidence")
    verification = client.get(f"{api}/api/provenance/decisions/{provenance_id}/verify")
    verification.raise_for_status()
    require(verification.json().get("status") == "PASS", "provenance hash verification failed")
    return expense_id


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("COMPOSE_PROJECT_NAME", "northstar-g9"))
    parser.add_argument("--wait-seconds", type=float, default=360)
    parser.add_argument("--no-smoke", action="store_true")
    args = parser.parse_args()
    api = os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    n8n = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5679").rstrip("/")
    metabase = os.getenv("METABASE_URL", "http://127.0.0.1:3000").rstrip("/")
    email = os.getenv("METABASE_ADMIN_EMAIL", "admin@northstar.local")
    password = os.getenv("METABASE_ADMIN_PASSWORD", "")
    try:
        require(password != "", "METABASE_ADMIN_PASSWORD is required for inventory verification")
        with httpx.Client(timeout=20) as client:
            health = wait_json(client, f"{api}/health", args.wait_seconds)
            require(health == {"status": "ok", "service": "northstar"}, f"unexpected API health: {health}")
            print("PASS: API health", flush=True)
            readiness = wait_json(client, f"{n8n}/healthz/readiness", args.wait_seconds)
            require(readiness.get("status") == "ok", f"unexpected n8n readiness: {readiness}")
            print("PASS: n8n readiness", flush=True)
            metabase_health = wait_json(client, f"{metabase}/api/health", args.wait_seconds)
            require(metabase_health.get("status") == "ok", f"unexpected Metabase health: {metabase_health}")
            print("PASS: Metabase health", flush=True)
            policies = client.get(f"{api}/api/context/policies")
            policies.raise_for_status()
            require(len(policies.json()) > 0, "governed context registry is empty")
            print("PASS: governed context", flush=True)
            workflows = workflow_count(args.project)
            require(workflows == EXPECTED_WORKFLOWS, f"expected 10 workflows, found {workflows}")
            print("PASS: 10 n8n workflows", flush=True)
            questions, dashboards = wait_metabase_inventory(metabase, email, password, args.wait_seconds)
            print("PASS: 36 Metabase questions / 5 dashboards", flush=True)
            revision = database_contract()
            print(f"PASS: PostgreSQL ownership / Alembic {revision}", flush=True)
            expense_id = None if args.no_smoke else smoke(client, api, n8n)
            if expense_id:
                print(f"PASS: suspicious-expense smoke {expense_id}", flush=True)
        print(json.dumps({
            "status": "PASS", "api": "PostgreSQL-backed", "workflow_count": workflows,
            "question_count": questions, "dashboard_count": dashboards,
            "alembic_revision": revision, "expense_id": expense_id, "smoke": not args.no_smoke,
        }, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"NORTH STAR STACK VERIFICATION: FAIL: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
