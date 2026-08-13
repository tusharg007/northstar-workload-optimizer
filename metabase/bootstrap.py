"""Idempotently reconcile the North Star collection, questions, and dashboards."""

from __future__ import annotations

import json
import os
from pathlib import Path
import time

from metabase.client import MetabaseAPIError, MetabaseClient

ROOT = Path(__file__).resolve().parent
MARKER = "northstar.logical-key:"


def _required(name: str) -> str:
    value = os.getenv(name, "")
    if not value:
        raise RuntimeError(f"Required environment variable {name} is not set")
    return value


def _items(body: object) -> list[dict]:
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and isinstance(body.get("data"), list):
        return body["data"]
    raise MetabaseAPIError(f"Expected list response, got {type(body).__name__}")


def _description(key: str, text: str = "") -> str:
    prefix = f"[{MARKER}{key}]"
    return f"{prefix} {text}".strip()


def _logical_key(item: dict) -> str | None:
    description = str(item.get("description") or "")
    start = description.find(f"[{MARKER}")
    if start < 0:
        return None
    start += len(MARKER) + 1
    end = description.find("]", start)
    return description[start:end] if end > start else None


def wait_ready(client: MetabaseClient, timeout: float = 180.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.ready():
            return
        time.sleep(1)
    raise RuntimeError(f"Metabase did not become ready within {timeout:.0f}s")


def authenticate(client: MetabaseClient, email: str, password: str) -> None:
    properties = client.setup_properties()
    setup_token = properties.get("setup-token")
    if setup_token:
        client.initial_setup({
            "token": setup_token,
            "user": {"first_name": "North", "last_name": "Star", "email": email, "password": password, "site_name": "North Star"},
            "prefs": {"site_name": "North Star", "site_locale": "en", "allow_tracking": False},
            "database": None,
        })
    client.login(email, password)


def ensure_database(client: MetabaseClient) -> int:
    name = os.getenv("NORTHSTAR_METABASE_SOURCE_NAME", "North Star Observability")
    existing = next((item for item in _items(client.get("/api/database")) if item.get("name") == name and not item.get("is_sample")), None)
    details = {
        "host": os.getenv("NORTHSTAR_METABASE_DB_HOST", "host.docker.internal"),
        "port": int(os.getenv("NORTHSTAR_METABASE_DB_PORT", "5432")),
        "dbname": os.getenv("NORTHSTAR_METABASE_DB_NAME", "northstar"),
        "user": os.getenv("NORTHSTAR_METABASE_DB_USER", "northstar_metabase_ro"),
        "password": _required("NORTHSTAR_METABASE_DB_PASSWORD"),
        "ssl": False,
        "tunnel-enabled": False,
        "advanced-options": False,
    }
    payload = {"engine": "postgres", "name": name, "details": details, "is_full_sync": True, "is_on_demand": False, "schedules": {}}
    if existing:
        client.put(f"/api/database/{existing['id']}", payload)
        return int(existing["id"])
    return int(client.post("/api/database", payload)["id"])


def ensure_collection(client: MetabaseClient, manifest: dict) -> int:
    spec = manifest["collection"]
    existing = next((item for item in _items(client.get("/api/collection")) if _logical_key(item) == spec["key"]), None)
    payload = {"name": spec["name"], "description": _description(spec["key"], spec.get("description", "")), "color": "#509EE3", "parent_id": None}
    if existing:
        client.put(f"/api/collection/{existing['id']}", payload)
        return int(existing["id"])
    return int(client.post("/api/collection", payload)["id"])


def ensure_questions(client: MetabaseClient, manifest: dict, database_id: int, collection_id: int) -> dict[str, int]:
    existing = {_logical_key(item): item for item in _items(client.get("/api/card?f=all")) if _logical_key(item)}
    ids: dict[str, int] = {}
    for spec in manifest["questions"]:
        query = (ROOT / spec["sql_file"]).read_text(encoding="utf-8").strip()
        payload = {
            "name": spec["name"], "description": _description(spec["key"], spec.get("description", "")),
            "collection_id": collection_id, "display": spec["display"], "visualization_settings": {},
            "dataset_query": {"database": database_id, "type": "native", "native": {"query": query, "template-tags": {}}},
        }
        current = existing.get(spec["key"])
        result = client.put(f"/api/card/{current['id']}", payload) if current else client.post("/api/card", payload)
        ids[spec["key"]] = int(result.get("id", current["id"] if current else 0))
    return ids


def ensure_dashboards(client: MetabaseClient, manifest: dict, collection_id: int, question_ids: dict[str, int]) -> dict[str, int]:
    existing = {_logical_key(item): item for item in _items(client.get("/api/dashboard")) if _logical_key(item)}
    ids: dict[str, int] = {}
    for spec in manifest["dashboards"]:
        payload = {"name": spec["name"], "description": _description(spec["key"], spec.get("description", "")), "collection_id": collection_id, "parameters": []}
        current = existing.get(spec["key"])
        result = client.put(f"/api/dashboard/{current['id']}", payload) if current else client.post("/api/dashboard", payload)
        dashboard_id = int(result.get("id", current["id"] if current else 0))
        full = client.get(f"/api/dashboard/{dashboard_id}")
        attached = {int(item["card_id"]): item for item in full.get("dashcards", []) if item.get("card_id") is not None}
        layout = []
        for index, position in enumerate(spec["cards"], start=1):
            card_id = question_ids[position["question"]]
            dashcard = attached.get(card_id)
            layout.append({
                "id": int(dashcard["id"]) if dashcard else -index,
                "card_id": card_id,
                "row": position["row"], "col": position["col"],
                "size_x": position["width"], "size_y": position["height"],
                "parameter_mappings": [], "visualization_settings": {},
                "series": [],
            })
        client.put(f"/api/dashboard/{dashboard_id}/cards", {"cards": layout, "tabs": []})
        ids[spec["key"]] = dashboard_id
    return ids


def main() -> int:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    client = MetabaseClient(os.getenv("METABASE_URL", "http://localhost:3000"), timeout=float(os.getenv("METABASE_HTTP_TIMEOUT_SECONDS", "20")))
    try:
        wait_ready(client, float(os.getenv("METABASE_READY_TIMEOUT_SECONDS", "180")))
        authenticate(client, os.getenv("METABASE_ADMIN_EMAIL", "admin@northstar.local"), _required("METABASE_ADMIN_PASSWORD"))
        database_id = ensure_database(client)
        collection_id = ensure_collection(client, manifest)
        questions = ensure_questions(client, manifest, database_id, collection_id)
        dashboards = ensure_dashboards(client, manifest, collection_id, questions)
        print(json.dumps({"status":"PASS","database_id":database_id,"collection_id":collection_id,"question_count":len(questions),"dashboard_count":len(dashboards),"dashboard_card_count":sum(len(item["cards"]) for item in manifest["dashboards"])}, sort_keys=True))
        return 0
    except (MetabaseAPIError, RuntimeError, ValueError) as exc:
        print(f"FAIL: Metabase bootstrap: {exc}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
