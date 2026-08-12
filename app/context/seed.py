"""Idempotent source-controlled loading for governed context."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path

from sqlalchemy import select

from app.context.exceptions import SeedConflictError
from app.context.hashing import policy_content_hash, term_content_hash
from app.db.models import (
    BusinessTerm,
    BusinessTermVersion,
    GovernanceOwner,
    PolicyDefinition,
    PolicyVersion,
    TrustSignal,
)
from app.db.repositories.context import ContextRepository, stable_id
from app.db.session import Database


def parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def load_seed(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _version_data(raw: dict) -> dict:
    return {
        **raw,
        "effective_from": parse_timestamp(raw["effective_from"]),
        "effective_to": parse_timestamp(raw.get("effective_to")),
        "review_due_at": parse_timestamp(raw.get("review_due_at")),
        "certified_at": parse_timestamp(raw.get("certified_at")),
    }


def apply_seed(database: Database, seed: dict, *, write: bool = False) -> dict:
    repository = ContextRepository(database)
    report = {"created": 0, "unchanged": 0, "conflict": 0, "requires_new_version": 0, "write": write}

    with database.session() as session:
        owner_keys = set(session.scalars(select(GovernanceOwner.owner_key)).all())
        term_keys = set(session.scalars(select(BusinessTerm.term_key)).all())
        policy_keys = set(session.scalars(select(PolicyDefinition.policy_key)).all())

    for owner in seed["owners"]:
        if owner["owner_key"] in owner_keys:
            existing = repository.get_owner(owner["owner_key"])
            expected = {key: owner.get(key) for key in existing}
            if existing != expected:
                report["conflict"] += 1
                raise SeedConflictError(f"Owner {owner['owner_key']} conflicts with existing identity")
            report["unchanged"] += 1
        else:
            report["created"] += 1
            if write:
                repository.create_owner(owner)

    for term in seed["business_terms"]:
        if term["term_key"] not in term_keys:
            report["created"] += 1
            if write:
                repository.create_term(term)
        else:
            existing_term = repository.get_term(term["term_key"])
            if (
                existing_term["canonical_name"] != term["canonical_name"]
                or existing_term["domain"] != term["domain"]
                or existing_term["owner"]["owner_key"] != term["owner_key"]
            ):
                report["conflict"] += 1
                raise SeedConflictError(f"Term {term['term_key']} conflicts with existing identity")
            report["unchanged"] += 1
        for raw_version in term["versions"]:
            version = _version_data(raw_version)
            expected_hash = term_content_hash(version)
            with database.session() as session:
                existing = session.scalar(
                    select(BusinessTermVersion)
                    .join(BusinessTerm, BusinessTerm.term_id == BusinessTermVersion.term_id)
                    .where(BusinessTerm.term_key == term["term_key"], BusinessTermVersion.version_number == version["version_number"])
                )
            if existing is None:
                report["created"] += 1
                if write:
                    repository.create_term_version(term["term_key"], version)
            elif (
                existing.content_hash != expected_hash
                or existing.status != version["status"]
                or existing.certified_at != version.get("certified_at")
            ):
                report["requires_new_version"] += 1
                report["conflict"] += 1
                raise SeedConflictError(f"Certified term {term['term_key']} v{version['version_number']} differs; create a new version")
            else:
                report["unchanged"] += 1

    for policy in seed["policies"]:
        if policy["policy_key"] not in policy_keys:
            report["created"] += 1
            if write:
                repository.create_policy(policy)
        else:
            existing_policy = repository.get_policy(policy["policy_key"])
            if (
                existing_policy["policy_name"] != policy["policy_name"]
                or existing_policy["domain"] != policy["domain"]
                or existing_policy["description"] != policy["description"]
                or existing_policy["owner"]["owner_key"] != policy["owner_key"]
            ):
                report["conflict"] += 1
                raise SeedConflictError(f"Policy {policy['policy_key']} conflicts with existing identity")
            report["unchanged"] += 1
        for raw_version in policy["versions"]:
            rules = raw_version["rules"]
            version = _version_data({key: value for key, value in raw_version.items() if key != "rules"})
            expected_hash = policy_content_hash(version, rules)
            with database.session() as session:
                existing = session.scalar(
                    select(PolicyVersion)
                    .join(PolicyDefinition, PolicyDefinition.policy_id == PolicyVersion.policy_id)
                    .where(PolicyDefinition.policy_key == policy["policy_key"], PolicyVersion.version_number == version["version_number"])
                )
            if existing is None:
                report["created"] += 1
                if write:
                    repository.create_policy_version(policy["policy_key"], version, rules)
            elif (
                existing.content_hash != expected_hash
                or existing.status != version["status"]
                or existing.certified_at != version.get("certified_at")
            ):
                report["requires_new_version"] += 1
                report["conflict"] += 1
                raise SeedConflictError(f"Certified policy {policy['policy_key']} v{version['version_number']} differs; create a new version")
            else:
                report["unchanged"] += 1

    defaults = seed["trust_signal_defaults"]
    for target in seed["trust_signals"]:
        for signal_type in defaults["signals"]:
            signal_id = stable_id("trust", f"{target['target_kind']}:{target['target_key']}:{target['version_number']}:{signal_type}:{defaults['source']}")
            with database.session() as session:
                existing = session.get(TrustSignal, signal_id)
            if existing is not None:
                expected_observed = parse_timestamp(defaults["observed_at"])
                expected_expires = parse_timestamp(defaults.get("expires_at"))
                if (
                    existing.status != "PASS"
                    or existing.score is not None
                    or existing.observed_at != expected_observed
                    or existing.expires_at != expected_expires
                    or existing.source != defaults["source"]
                    or existing.details != defaults.get("details", {})
                ):
                    report["conflict"] += 1
                    raise SeedConflictError(
                        f"Trust signal {target['target_key']} v{target['version_number']} "
                        f"{signal_type} conflicts with existing evidence"
                    )
                report["unchanged"] += 1
                continue
            report["created"] += 1
            if write:
                repository.add_trust_signal({
                    **target,
                    "signal_type": signal_type,
                    "status": "PASS",
                    "observed_at": parse_timestamp(defaults["observed_at"]),
                    "expires_at": parse_timestamp(defaults.get("expires_at")),
                    "source": defaults["source"],
                    "details": defaults.get("details", {}),
                })
    return report
