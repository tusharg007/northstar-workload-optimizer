"""Persistence boundary for governed context identities and versions."""

from __future__ import annotations

from datetime import datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, or_, select

from app.context.exceptions import ContextIntegrityError, ContextNotFoundError
from app.context.hashing import policy_content_hash, term_content_hash
from app.db.base import ensure_utc, utc_now
from app.db.models import (
    BusinessTerm,
    BusinessTermVersion,
    GovernanceOwner,
    PolicyDefinition,
    PolicyRule,
    PolicyVersion,
    TrustSignal,
)
from app.db.session import Database


def stable_id(kind: str, key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"northstar-context:{kind}:{key}"))


def _overlap(
    left_from: datetime,
    left_to: datetime | None,
    right_from: datetime,
    right_to: datetime | None,
) -> bool:
    left_start = ensure_utc(left_from)
    right_start = ensure_utc(right_from)
    left_end = ensure_utc(left_to)
    right_end = ensure_utc(right_to)
    assert left_start is not None and right_start is not None
    return (right_end is None or left_start < right_end) and (
        left_end is None or right_start < left_end
    )


class ContextRepository:
    """Keep governed writes transactional and reads independent of FastAPI."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def owner_state(owner: GovernanceOwner) -> dict:
        return {
            "owner_key": owner.owner_key,
            "display_name": owner.display_name,
            "owner_type": owner.owner_type,
            "domain": owner.domain,
            "contact_reference": owner.contact_reference,
            "active": owner.active,
        }

    def get_owner(self, owner_key: str) -> dict:
        with self.database.session() as session:
            owner = session.scalar(select(GovernanceOwner).where(GovernanceOwner.owner_key == owner_key))
            if owner is None:
                raise ContextNotFoundError("Governance owner not found")
            return self.owner_state(owner)

    def list_policies(self) -> list[dict]:
        with self.database.session() as session:
            rows = session.execute(
                select(PolicyDefinition, GovernanceOwner, func.count(PolicyVersion.policy_version_id))
                .join(GovernanceOwner, GovernanceOwner.owner_id == PolicyDefinition.owner_id)
                .outerjoin(PolicyVersion, PolicyVersion.policy_id == PolicyDefinition.policy_id)
                .group_by(PolicyDefinition.policy_id, GovernanceOwner.owner_id)
                .order_by(PolicyDefinition.policy_key)
            ).all()
            return [self._policy_summary(policy, owner, count) for policy, owner, count in rows]

    def get_policy(self, policy_key: str) -> dict:
        with self.database.session() as session:
            row = session.execute(
                select(PolicyDefinition, GovernanceOwner, func.count(PolicyVersion.policy_version_id))
                .join(GovernanceOwner, GovernanceOwner.owner_id == PolicyDefinition.owner_id)
                .outerjoin(PolicyVersion, PolicyVersion.policy_id == PolicyDefinition.policy_id)
                .where(PolicyDefinition.policy_key == policy_key)
                .group_by(PolicyDefinition.policy_id, GovernanceOwner.owner_id)
            ).one_or_none()
            if row is None:
                raise ContextNotFoundError("Policy not found")
            return self._policy_summary(*row)

    @classmethod
    def _policy_summary(cls, policy: PolicyDefinition, owner: GovernanceOwner, count: int) -> dict:
        return {
            "policy_key": policy.policy_key,
            "policy_name": policy.policy_name,
            "domain": policy.domain,
            "description": policy.description,
            "owner": cls.owner_state(owner),
            "version_count": count,
        }

    def list_terms(self) -> list[dict]:
        with self.database.session() as session:
            rows = session.execute(
                select(BusinessTerm, GovernanceOwner, func.count(BusinessTermVersion.term_version_id))
                .join(GovernanceOwner, GovernanceOwner.owner_id == BusinessTerm.owner_id)
                .outerjoin(BusinessTermVersion, BusinessTermVersion.term_id == BusinessTerm.term_id)
                .group_by(BusinessTerm.term_id, GovernanceOwner.owner_id)
                .order_by(BusinessTerm.term_key)
            ).all()
            return [self._term_summary(term, owner, count) for term, owner, count in rows]

    def get_term(self, term_key: str) -> dict:
        with self.database.session() as session:
            row = session.execute(
                select(BusinessTerm, GovernanceOwner, func.count(BusinessTermVersion.term_version_id))
                .join(GovernanceOwner, GovernanceOwner.owner_id == BusinessTerm.owner_id)
                .outerjoin(BusinessTermVersion, BusinessTermVersion.term_id == BusinessTerm.term_id)
                .where(BusinessTerm.term_key == term_key)
                .group_by(BusinessTerm.term_id, GovernanceOwner.owner_id)
            ).one_or_none()
            if row is None:
                raise ContextNotFoundError("Business term not found")
            return self._term_summary(*row)

    @classmethod
    def _term_summary(cls, term: BusinessTerm, owner: GovernanceOwner, count: int) -> dict:
        return {
            "term_key": term.term_key,
            "canonical_name": term.canonical_name,
            "domain": term.domain,
            "owner": cls.owner_state(owner),
            "version_count": count,
        }

    def policy_versions(self, policy_key: str) -> list[dict]:
        with self.database.session() as session:
            policy = session.scalar(select(PolicyDefinition).where(PolicyDefinition.policy_key == policy_key))
            if policy is None:
                raise ContextNotFoundError("Policy not found")
            versions = session.scalars(
                select(PolicyVersion)
                .where(PolicyVersion.policy_id == policy.policy_id)
                .order_by(PolicyVersion.version_number)
            ).all()
            return [self._policy_version_state(session, version) for version in versions]

    def term_versions(self, term_key: str) -> list[dict]:
        with self.database.session() as session:
            term = session.scalar(select(BusinessTerm).where(BusinessTerm.term_key == term_key))
            if term is None:
                raise ContextNotFoundError("Business term not found")
            versions = session.scalars(
                select(BusinessTermVersion)
                .where(BusinessTermVersion.term_id == term.term_id)
                .order_by(BusinessTermVersion.version_number)
            ).all()
            return [self._term_version_state(version) for version in versions]

    def policy_resolution_rows(self, policy_key: str, as_of: datetime) -> list[dict]:
        point = ensure_utc(as_of)
        assert point is not None
        with self.database.session() as session:
            row = session.execute(
                select(PolicyDefinition, GovernanceOwner)
                .join(GovernanceOwner, GovernanceOwner.owner_id == PolicyDefinition.owner_id)
                .where(PolicyDefinition.policy_key == policy_key)
            ).one_or_none()
            if row is None:
                raise ContextNotFoundError("Policy not found")
            policy, owner = row
            versions = session.scalars(
                select(PolicyVersion).where(
                    PolicyVersion.policy_id == policy.policy_id,
                    PolicyVersion.effective_from <= point,
                    or_(PolicyVersion.effective_to.is_(None), PolicyVersion.effective_to > point),
                ).order_by(PolicyVersion.version_number)
            ).all()
            return [
                {
                    **self._policy_summary(policy, owner, len(versions)),
                    **self._policy_version_state(session, version),
                    "owner_active": owner.active,
                    "signals": self._signals(session, policy_version_id=version.policy_version_id),
                }
                for version in versions
            ]

    def term_resolution_rows(self, term_key: str, as_of: datetime) -> list[dict]:
        point = ensure_utc(as_of)
        assert point is not None
        with self.database.session() as session:
            row = session.execute(
                select(BusinessTerm, GovernanceOwner)
                .join(GovernanceOwner, GovernanceOwner.owner_id == BusinessTerm.owner_id)
                .where(BusinessTerm.term_key == term_key)
            ).one_or_none()
            if row is None:
                raise ContextNotFoundError("Business term not found")
            term, owner = row
            versions = session.scalars(
                select(BusinessTermVersion).where(
                    BusinessTermVersion.term_id == term.term_id,
                    BusinessTermVersion.effective_from <= point,
                    or_(BusinessTermVersion.effective_to.is_(None), BusinessTermVersion.effective_to > point),
                ).order_by(BusinessTermVersion.version_number)
            ).all()
            return [
                {
                    **self._term_summary(term, owner, len(versions)),
                    **self._term_version_state(version),
                    "owner_active": owner.active,
                    "signals": self._signals(session, term_version_id=version.term_version_id),
                }
                for version in versions
            ]

    @staticmethod
    def _rule_state(rule: PolicyRule, term_key: str | None) -> dict:
        return {
            "rule_key": rule.rule_key,
            "rule_name": rule.rule_name,
            "rule_type": rule.rule_type,
            "description": rule.description,
            "parameters": rule.parameters,
            "severity": rule.severity,
            "business_term_key": term_key,
            "source_reference": rule.source_reference,
        }

    def _policy_version_state(self, session, version: PolicyVersion) -> dict:
        rules = session.execute(
            select(PolicyRule, BusinessTerm.term_key)
            .outerjoin(BusinessTerm, BusinessTerm.term_id == PolicyRule.business_term_id)
            .where(PolicyRule.policy_version_id == version.policy_version_id)
            .order_by(PolicyRule.rule_key)
        ).all()
        return {
            "policy_version_id": version.policy_version_id,
            "version_number": version.version_number,
            "status": version.status,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "review_due_at": version.review_due_at,
            "certified_at": version.certified_at,
            "source_reference": version.source_reference,
            "content_hash": version.content_hash,
            "metadata": version.context_metadata,
            "rules": [self._rule_state(rule, term_key) for rule, term_key in rules],
        }

    @staticmethod
    def _term_version_state(version: BusinessTermVersion) -> dict:
        return {
            "term_version_id": version.term_version_id,
            "version_number": version.version_number,
            "definition": version.definition,
            "status": version.status,
            "effective_from": version.effective_from,
            "effective_to": version.effective_to,
            "review_due_at": version.review_due_at,
            "certified_at": version.certified_at,
            "source_reference": version.source_reference,
            "content_hash": version.content_hash,
        }

    @staticmethod
    def _signals(session, *, policy_version_id: str | None = None, term_version_id: str | None = None) -> list[dict]:
        statement = select(TrustSignal)
        if policy_version_id is not None:
            statement = statement.where(TrustSignal.policy_version_id == policy_version_id)
        else:
            statement = statement.where(TrustSignal.business_term_version_id == term_version_id)
        signals = session.scalars(statement.order_by(TrustSignal.signal_type)).all()
        return [
            {
                "signal_type": signal.signal_type,
                "status": signal.status,
                "score": signal.score,
                "observed_at": signal.observed_at,
                "expires_at": signal.expires_at,
                "source": signal.source,
                "details": signal.details,
            }
            for signal in signals
        ]

    def create_owner(self, data: dict) -> dict:
        with self.database.transaction() as session:
            owner = GovernanceOwner(
                owner_id=stable_id("owner", data["owner_key"]),
                owner_key=data["owner_key"], display_name=data["display_name"],
                owner_type=data["owner_type"], domain=data["domain"],
                contact_reference=data.get("contact_reference"),
                active=data.get("active", True), created_at=utc_now(), updated_at=utc_now(),
            )
            session.add(owner)
            session.flush()
            return self.owner_state(owner)

    def create_term(self, data: dict) -> str:
        with self.database.transaction() as session:
            owner = session.scalar(select(GovernanceOwner).where(GovernanceOwner.owner_key == data["owner_key"]))
            if owner is None:
                raise ContextNotFoundError("Governance owner not found")
            term = BusinessTerm(
                term_id=stable_id("term", data["term_key"]), term_key=data["term_key"],
                canonical_name=data["canonical_name"], domain=data["domain"], owner_id=owner.owner_id,
                created_at=utc_now(), updated_at=utc_now(),
            )
            session.add(term)
            session.flush()
            return term.term_id

    def create_policy(self, data: dict) -> str:
        with self.database.transaction() as session:
            owner = session.scalar(select(GovernanceOwner).where(GovernanceOwner.owner_key == data["owner_key"]))
            if owner is None:
                raise ContextNotFoundError("Governance owner not found")
            policy = PolicyDefinition(
                policy_id=stable_id("policy", data["policy_key"]), policy_key=data["policy_key"],
                policy_name=data["policy_name"], domain=data["domain"], description=data["description"],
                owner_id=owner.owner_id, created_at=utc_now(), updated_at=utc_now(),
            )
            session.add(policy)
            session.flush()
            return policy.policy_id

    def create_term_version(self, term_key: str, data: dict) -> str:
        with self.database.transaction() as session:
            term = session.scalar(select(BusinessTerm).where(BusinessTerm.term_key == term_key))
            if term is None:
                raise ContextNotFoundError("Business term not found")
            self._validate_window(data)
            self._ensure_term_no_overlap(session, term.term_id, data)
            version_id = stable_id("term-version", f"{term_key}:{data['version_number']}")
            session.add(BusinessTermVersion(
                term_version_id=version_id, term_id=term.term_id,
                version_number=data["version_number"], definition=data["definition"], status=data["status"],
                effective_from=data["effective_from"], effective_to=data.get("effective_to"),
                review_due_at=data.get("review_due_at"), certified_at=data.get("certified_at"),
                source_reference=data["source_reference"], content_hash=term_content_hash(data), created_at=utc_now(),
            ))
            return version_id

    def create_policy_version(self, policy_key: str, data: dict, rules: list[dict]) -> str:
        with self.database.transaction() as session:
            policy = session.scalar(select(PolicyDefinition).where(PolicyDefinition.policy_key == policy_key))
            if policy is None:
                raise ContextNotFoundError("Policy not found")
            self._validate_window(data)
            self._ensure_policy_no_overlap(session, policy.policy_id, data)
            version_id = stable_id("policy-version", f"{policy_key}:{data['version_number']}")
            version = PolicyVersion(
                policy_version_id=version_id, policy_id=policy.policy_id,
                version_number=data["version_number"], status=data["status"],
                effective_from=data["effective_from"], effective_to=data.get("effective_to"),
                review_due_at=data.get("review_due_at"), certified_at=data.get("certified_at"),
                source_reference=data["source_reference"], content_hash=policy_content_hash(data, rules),
                context_metadata=data.get("metadata", {}), created_at=utc_now(),
            )
            session.add(version)
            session.flush()
            for rule_data in sorted(rules, key=lambda item: item["rule_key"]):
                term_id = None
                if rule_data.get("business_term_key"):
                    term_id = session.scalar(select(BusinessTerm.term_id).where(BusinessTerm.term_key == rule_data["business_term_key"]))
                    if term_id is None:
                        raise ContextNotFoundError("Policy rule business term not found")
                session.add(PolicyRule(
                    rule_id=stable_id("rule", f"{policy_key}:{data['version_number']}:{rule_data['rule_key']}"),
                    policy_version_id=version_id, rule_key=rule_data["rule_key"],
                    rule_name=rule_data["rule_name"], rule_type=rule_data["rule_type"],
                    description=rule_data["description"], parameters=rule_data["parameters"],
                    severity=rule_data["severity"], business_term_id=term_id,
                    source_reference=rule_data.get("source_reference"), created_at=utc_now(),
                ))
            return version_id

    @staticmethod
    def _validate_window(data: dict) -> None:
        start = ensure_utc(data["effective_from"])
        end = ensure_utc(data.get("effective_to"))
        review = ensure_utc(data.get("review_due_at"))
        assert start is not None
        if end is not None and end < start:
            raise ContextIntegrityError("effective_to cannot precede effective_from")
        if review is not None and review < start:
            raise ContextIntegrityError("review_due_at cannot precede effective_from")

    @staticmethod
    def _ensure_policy_no_overlap(session, policy_id: str, data: dict) -> None:
        if data["status"] != "CERTIFIED":
            return
        existing = session.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == policy_id, PolicyVersion.status == "CERTIFIED")).all()
        if any(_overlap(item.effective_from, item.effective_to, data["effective_from"], data.get("effective_to")) for item in existing):
            raise ContextIntegrityError("Certified policy effective windows overlap")

    @staticmethod
    def _ensure_term_no_overlap(session, term_id: str, data: dict) -> None:
        if data["status"] != "CERTIFIED":
            return
        existing = session.scalars(select(BusinessTermVersion).where(BusinessTermVersion.term_id == term_id, BusinessTermVersion.status == "CERTIFIED")).all()
        if any(_overlap(item.effective_from, item.effective_to, data["effective_from"], data.get("effective_to")) for item in existing):
            raise ContextIntegrityError("Certified business-term effective windows overlap")

    def update_policy_version(self, version_id: str, **changes) -> None:
        with self.database.transaction() as session:
            version = session.get(PolicyVersion, version_id)
            if version is None:
                raise ContextNotFoundError("Policy version not found")
            substantive = set(changes) - {"status"}
            if version.certified_at is not None and substantive:
                raise ContextIntegrityError("Certified policy versions are immutable")
            requested_status = changes.get("status")
            if version.certified_at is not None:
                allowed_statuses = {"RETIRED"} if version.status == "CERTIFIED" else {version.status}
                if requested_status is not None and requested_status not in allowed_statuses:
                    raise ContextIntegrityError("Certified policy version has an invalid lifecycle transition")
            for key, value in changes.items():
                setattr(version, "context_metadata" if key == "metadata" else key, value)

    def update_term_version(self, version_id: str, **changes) -> None:
        with self.database.transaction() as session:
            version = session.get(BusinessTermVersion, version_id)
            if version is None:
                raise ContextNotFoundError("Business term version not found")
            substantive = set(changes) - {"status"}
            if version.certified_at is not None and substantive:
                raise ContextIntegrityError("Certified business-term versions are immutable")
            requested_status = changes.get("status")
            if version.certified_at is not None:
                allowed_statuses = {"RETIRED"} if version.status == "CERTIFIED" else {version.status}
                if requested_status is not None and requested_status not in allowed_statuses:
                    raise ContextIntegrityError("Certified business-term version has an invalid lifecycle transition")
            for key, value in changes.items():
                setattr(version, key, value)

    def update_policy_rule(self, rule_id: str, **changes) -> None:
        with self.database.transaction() as session:
            rule = session.get(PolicyRule, rule_id)
            if rule is None:
                raise ContextNotFoundError("Policy rule not found")
            version = session.get(PolicyVersion, rule.policy_version_id)
            assert version is not None
            if version.certified_at is not None:
                raise ContextIntegrityError("Rules of certified policy versions are immutable")
            for key, value in changes.items():
                if key not in {"rule_name", "rule_type", "description", "parameters", "severity", "source_reference"}:
                    raise ContextIntegrityError("Unsupported policy-rule field")
                setattr(rule, key, value)

    def add_trust_signal(self, data: dict) -> str:
        with self.database.transaction() as session:
            target_kind = data["target_kind"]
            target_key = data["target_key"]
            version_number = data["version_number"]
            policy_version_id = None
            term_version_id = None
            if target_kind == "policy":
                policy_version_id = session.scalar(
                    select(PolicyVersion.policy_version_id)
                    .join(PolicyDefinition, PolicyDefinition.policy_id == PolicyVersion.policy_id)
                    .where(PolicyDefinition.policy_key == target_key, PolicyVersion.version_number == version_number)
                )
            elif target_kind == "term":
                term_version_id = session.scalar(
                    select(BusinessTermVersion.term_version_id)
                    .join(BusinessTerm, BusinessTerm.term_id == BusinessTermVersion.term_id)
                    .where(BusinessTerm.term_key == target_key, BusinessTermVersion.version_number == version_number)
                )
            else:
                raise ContextIntegrityError("Trust signal target_kind must be policy or term")
            if policy_version_id is None and term_version_id is None:
                raise ContextNotFoundError("Trust signal target not found")
            signal_id = stable_id("trust", f"{target_kind}:{target_key}:{version_number}:{data['signal_type']}:{data['source']}")
            session.add(TrustSignal(
                trust_signal_id=signal_id, policy_version_id=policy_version_id,
                business_term_version_id=term_version_id, signal_type=data["signal_type"],
                status=data["status"], score=data.get("score"), observed_at=data["observed_at"],
                expires_at=data.get("expires_at"), source=data["source"], details=data.get("details", {}),
                created_at=utc_now(),
            ))
            return signal_id
