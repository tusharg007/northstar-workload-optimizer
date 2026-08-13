"""Canonical hashes for catalogs, evidence snapshots, and decisions."""

from __future__ import annotations

from app.context.hashing import sha256_content


def evidence_hash(data: dict) -> str:
    return sha256_content(data)


def risk_catalog_hash(catalog: dict) -> str:
    return sha256_content(catalog)


def signal_definition_hash(definition: dict) -> str:
    return sha256_content(definition)


def provenance_hash_payload(header: dict, evidence: dict[str, list[dict]]) -> dict:
    return {
        "source_payload_hash": header["source_payload_hash"],
        "workflow_run_id": header["workflow_run_id"],
        "correlation_id": header["correlation_id"],
        "context_as_of": header["context_as_of"],
        "automated_status": header["automated_status"],
        "risk_level": header.get("risk_level"),
        "approver_role": header.get("approver_role"),
        "automated_reason": header.get("automated_reason"),
        "context_trust_state": header["context_trust_state"],
        "decision_engine_version": header["decision_engine_version"],
        "risk_engine_version": header["risk_engine_version"],
        "risk_catalog_hash": header["risk_catalog_hash"],
        "build_revision": header.get("build_revision"),
        "policy_evidence_hashes": sorted(item["snapshot_hash"] for item in evidence["policies"]),
        "term_evidence_hashes": sorted(item["snapshot_hash"] for item in evidence["terms"]),
        "rule_evidence_hashes": sorted(item["evidence_hash"] for item in evidence["rules"]),
        "trust_evidence_hashes": sorted(item["evidence_hash"] for item in evidence["trust"]),
        "risk_evidence_hashes": sorted(item["evidence_hash"] for item in evidence["risk"]),
    }


def provenance_hash(header: dict, evidence: dict[str, list[dict]]) -> str:
    return sha256_content(provenance_hash_payload(header, evidence))
