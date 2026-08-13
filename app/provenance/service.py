"""Assemble decision-relevant reference and snapshot evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from app.db.base import utc_now
from app.provenance.hashing import (
    evidence_hash,
    provenance_hash,
    risk_catalog_hash,
    signal_definition_hash,
)
from automation.policy_manifest import DECISION_ENGINE_VERSION, RISK_ENGINE_VERSION

PROJECT_DIR = Path(__file__).resolve().parents[2]
RISK_CATALOG_PATH = PROJECT_DIR / "context" / "risk_signals.json"


def load_risk_catalog() -> dict:
    return json.loads(RISK_CATALOG_PATH.read_text(encoding="utf-8"))


def _hashed(data: dict, field: str) -> dict:
    return {**data, field: evidence_hash(data)}


def build_automated_provenance(
    *, expense_id: str, payload_hash: str, workflow_run_id: str, correlation_id: str,
    context_as_of, policies: list[dict], terms: list[dict], result: dict,
) -> dict:
    now = utc_now()
    policy_rows = []
    rule_by_key = {item["rule_key"]: item for item in result.get("policy_evaluations", [])}
    relevant_term_keys: set[str] = set()
    rule_rows = []
    trust_rows = []
    for policy in policies:
        snapshot = {
            "policy_id": policy["policy_id"], "policy_version_id": policy["policy_version_id"],
            "policy_key": policy["policy_key"], "policy_name": policy["policy_name"],
            "version_number": policy["version_number"], "content_hash": policy["content_hash"],
            "owner_key": policy["owner"]["owner_key"], "owner_display_name": policy["owner"]["display_name"],
            "status": policy["status"], "effective_from": policy["effective_from"],
            "effective_to": policy["effective_to"], "trust_state": policy["trust"]["state"],
        }
        policy_rows.append(_hashed(snapshot, "snapshot_hash"))
        for signal in policy["trust"]["signals"]:
            trust = {
                "trust_signal_id": signal["trust_signal_id"], "target_type": "POLICY",
                "target_key": policy["policy_key"], "signal_type": signal["signal_type"],
                "signal_status": signal["status"], "observed_at": signal["observed_at"],
                "expires_at": signal["expires_at"], "source": signal["source"], "details": signal["details"],
            }
            trust_rows.append(_hashed(trust, "evidence_hash"))
        for rule in policy["rules"]:
            evaluation = rule_by_key.get(rule["rule_key"])
            if evaluation is None:
                continue
            if rule.get("business_term_key"):
                relevant_term_keys.add(rule["business_term_key"])
            evidence = {
                "policy_version_id": policy["policy_version_id"], "policy_rule_id": rule["policy_rule_id"],
                "rule_key": rule["rule_key"], "rule_name": rule["rule_name"], "rule_type": rule["rule_type"],
                "severity": rule["severity"], "parameters": rule["parameters"],
                "evaluation_status": evaluation["evaluation_status"], "triggered": evaluation["triggered"],
                "observed_value": evaluation.get("observed_value"),
                "evaluation_details": evaluation.get("evaluation_details", {}),
            }
            rule_rows.append(_hashed(evidence, "evidence_hash"))

    term_rows = []
    for term in terms:
        if term["term_key"] not in relevant_term_keys:
            continue
        snapshot = {
            "business_term_id": term["business_term_id"], "business_term_version_id": term["term_version_id"],
            "term_key": term["term_key"], "canonical_name": term["canonical_name"],
            "definition": term["definition"], "version_number": term["version_number"],
            "content_hash": term["content_hash"], "owner_key": term["owner"]["owner_key"],
            "trust_state": term["trust"]["state"],
        }
        term_rows.append(_hashed(snapshot, "snapshot_hash"))
        for signal in term["trust"]["signals"]:
            trust = {
                "trust_signal_id": signal["trust_signal_id"], "target_type": "BUSINESS_TERM",
                "target_key": term["term_key"], "signal_type": signal["signal_type"],
                "signal_status": signal["status"], "observed_at": signal["observed_at"],
                "expires_at": signal["expires_at"], "source": signal["source"], "details": signal["details"],
            }
            trust_rows.append(_hashed(trust, "evidence_hash"))

    catalog = load_risk_catalog()
    catalog_hash = risk_catalog_hash(catalog)
    definitions = {item["signal_key"]: item for item in catalog["signals"]}
    risk_rows = []
    for evaluation in result.get("risk_evaluations", []):
        definition = definitions[evaluation["signal_key"]]
        evidence = {
            "signal_key": definition["signal_key"], "canonical_name": definition["canonical_name"],
            "engine_component": definition["engine_component"], "triggered": evaluation["triggered"],
            "observed_value": evaluation.get("observed_value"),
            "threshold_or_reference": evaluation.get("threshold_or_reference"),
            "details": evaluation.get("details", {}),
            "signal_definition_hash": signal_definition_hash(definition), "risk_catalog_hash": catalog_hash,
        }
        risk_rows.append(_hashed(evidence, "evidence_hash"))

    anomaly = result.get("anomaly") or {}
    decision = result.get("decision") or {}
    header = {
        "expense_id": expense_id, "source_payload_hash": payload_hash, "workflow_run_id": workflow_run_id,
        "correlation_id": correlation_id, "context_as_of": context_as_of,
        "context_resolved_at": now, "automated_status": result["status"],
        "risk_level": anomaly.get("risk_level"), "approver_role": decision.get("approver_role"),
        "automated_reason": decision.get("reason"), "context_trust_state": "TRUSTED",
        "decision_engine_version": DECISION_ENGINE_VERSION, "risk_engine_version": RISK_ENGINE_VERSION,
        "risk_catalog_hash": catalog_hash, "build_revision": os.getenv("NORTHSTAR_BUILD_REVISION") or None,
    }
    evidence = {"policies": policy_rows, "terms": term_rows, "rules": rule_rows, "trust": trust_rows, "risk": risk_rows}
    header["provenance_hash"] = provenance_hash(header, evidence)
    return {"header": header, **evidence}
