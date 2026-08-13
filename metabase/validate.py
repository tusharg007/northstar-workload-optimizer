"""Static validation for the source-controlled Metabase manifest."""

from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "manifest.json"
EXPECTED_DASHBOARDS = {
    "North Star | Operations Overview",
    "North Star | Approval & SLA",
    "North Star | Reliability & Recovery",
    "North Star | Governed Context Health",
    "North Star | Decision Trace & Risk",
}
SUPPORTED_DISPLAYS = {"scalar", "bar", "line", "row", "table"}
MUTATION = re.compile(r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|TRUNCATE|DROP|ALTER|CREATE|GRANT|REVOKE|CALL|COPY)\b", re.I)
SECRET = re.compile(r"(session[_-]?token|api[_-]?key|authorization\s*:|password\s*[=:]\s*[^$<{])", re.I)


def _unique(items: list[dict], field: str, label: str, errors: list[str]) -> None:
    values = [item.get(field) for item in items]
    if None in values or len(values) != len(set(values)):
        errors.append(f"{label} {field}s must be present and unique")


def validate() -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest is unreadable: {exc}"]
    questions = manifest.get("questions", [])
    dashboards = manifest.get("dashboards", [])
    _unique(questions, "key", "question", errors)
    _unique(dashboards, "key", "dashboard", errors)
    question_keys = {item.get("key") for item in questions}
    referenced: set[str] = set()
    declared_sql: set[Path] = set()
    for question in questions:
        display = question.get("display")
        if display not in SUPPORTED_DISPLAYS:
            errors.append(f"{question.get('key')}: unsupported display {display!r}")
        settings = question.get("visualization_settings", {})
        if not isinstance(settings, dict):
            errors.append(f"{question.get('key')}: visualization_settings must be an object")
        sql_file = ROOT / str(question.get("sql_file", ""))
        declared_sql.add(sql_file.resolve())
        if not sql_file.is_file():
            errors.append(f"{question.get('key')}: missing SQL file {sql_file}")
            continue
        sql_text = sql_file.read_text(encoding="utf-8")
        if MUTATION.search(sql_text):
            errors.append(f"{question.get('key')}: SQL contains a mutation/DDL keyword")
        if not re.match(r"^\s*(SELECT|WITH)\b", sql_text, re.I):
            errors.append(f"{question.get('key')}: SQL must begin with SELECT or WITH")
        if re.search(r"\bSELECT\s+\*", sql_text, re.I):
            errors.append(f"{question.get('key')}: SELECT * is prohibited")
    actual_sql = {item.resolve() for item in (ROOT / "sql").glob("*.sql")}
    for unused in sorted(actual_sql - declared_sql):
        errors.append(f"unused SQL file: {unused.name}")
    names = {item.get("name") for item in dashboards}
    if len(dashboards) != 5 or names != EXPECTED_DASHBOARDS:
        errors.append("manifest must define exactly the five required dashboards")
    for dashboard in dashboards:
        cards = dashboard.get("cards", [])
        seen_cards: set[str] = set()
        occupied: set[tuple[int, int]] = set()
        for card in cards:
            key = card.get("question")
            referenced.add(key)
            if key not in question_keys:
                errors.append(f"{dashboard.get('key')}: unresolved question {key!r}")
            if key in seen_cards:
                errors.append(f"{dashboard.get('key')}: duplicate card {key!r}")
            seen_cards.add(key)
            row, col = card.get("row"), card.get("col")
            width, height = card.get("width"), card.get("height")
            if not all(isinstance(value, int) and value >= 0 for value in (row, col, width, height)) or width == 0 or height == 0 or col + width > 24:
                errors.append(f"{dashboard.get('key')}/{key}: invalid layout")
                continue
            cells = {(r, c) for r in range(row, row + height) for c in range(col, col + width)}
            if occupied & cells:
                errors.append(f"{dashboard.get('key')}/{key}: layout overlaps another card")
            occupied |= cells
    if referenced != question_keys:
        errors.append(f"unreferenced questions: {sorted(question_keys - referenced)}")
    tracked_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in [MANIFEST, *sorted((ROOT / "sql").glob("*.sql"))]
    )
    if SECRET.search(tracked_text):
        errors.append("committed Metabase content appears to contain a credential")
    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("FAIL: Metabase manifest validation")
        for error in errors:
            print(f"- {error}")
        return 1
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"PASS: {len(manifest['questions'])} questions, {len(manifest['dashboards'])} dashboards, read-only SQL and non-overlapping layouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
