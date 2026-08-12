"""Canonical SHA-256 hashes for governed context content."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from typing import Any


def _canonical_value(value: Any) -> Any:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return normalized.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def sha256_content(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def term_content_hash(version: dict) -> str:
    governed = {
        "version_number": version["version_number"],
        "definition": version["definition"],
        "effective_from": version["effective_from"],
        "effective_to": version.get("effective_to"),
        "review_due_at": version.get("review_due_at"),
        "source_reference": version["source_reference"],
    }
    return sha256_content(governed)


def policy_content_hash(version: dict, rules: list[dict]) -> str:
    governed_rules = [
        {
            "rule_key": rule["rule_key"],
            "rule_name": rule["rule_name"],
            "rule_type": rule["rule_type"],
            "description": rule["description"],
            "parameters": rule["parameters"],
            "severity": rule["severity"],
            "business_term_key": rule.get("business_term_key"),
            "source_reference": rule.get("source_reference"),
        }
        for rule in sorted(rules, key=lambda item: item["rule_key"])
    ]
    governed = {
        "version_number": version["version_number"],
        "effective_from": version["effective_from"],
        "effective_to": version.get("effective_to"),
        "review_due_at": version.get("review_due_at"),
        "source_reference": version["source_reference"],
        "metadata": version.get("metadata", {}),
        "rules": governed_rules,
    }
    return sha256_content(governed)
