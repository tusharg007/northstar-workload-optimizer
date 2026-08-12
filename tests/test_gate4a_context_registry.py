"""Gate 4A governed context, versioning, trust, seed, and API contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError

from app.context.exceptions import ContextConflictError, ContextIntegrityError, SeedConflictError
from app.context.hashing import policy_content_hash, sha256_content, term_content_hash
from app.context.seed import apply_seed, load_seed
from app.db.models import GovernanceOwner, PolicyDefinition, PolicyRule, PolicyVersion, TrustSignal
from app.db.repositories.context import ContextRepository, stable_id
from app.main import create_app

PROJECT_DIR = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_DIR / "context" / "registry.seed.json"
UTC = timezone.utc


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    application = create_app(tmp_path / "context.db")
    apply_seed(application.state.store.database, load_seed(SEED_PATH), write=True)
    return TestClient(application)


def _policy_version(number: int, start: datetime, end: datetime | None, *, review: datetime | None = None, status: str = "CERTIFIED") -> dict:
    return {
        "version_number": number,
        "status": status,
        "effective_from": start,
        "effective_to": end,
        "review_due_at": review or (start + timedelta(days=3650)),
        "certified_at": start if status == "CERTIFIED" else None,
        "source_reference": "tests/test_gate4a_context_registry.py",
        "metadata": {"test": True},
    }


def _rule(key: str = "TEST_RULE") -> dict:
    return {
        "rule_key": key,
        "rule_name": "Test Rule",
        "rule_type": "THRESHOLD",
        "description": "A deterministic test rule.",
        "parameters": {"limit": 10, "nested": {"b": 2, "a": 1}},
        "severity": "WARN",
        "business_term_key": None,
        "source_reference": "tests/test_gate4a_context_registry.py",
    }


def _create_test_policy(client: TestClient, key: str = "TEST_POLICY") -> ContextRepository:
    repository = ContextRepository(client.app.state.store.database)
    try:
        repository.create_policy({
            "policy_key": key,
            "policy_name": "Test Policy",
            "domain": "Expense Management",
            "description": "Disposable test policy.",
            "owner_key": "FINANCE_COMPLIANCE",
        })
    except Exception:
        pass
    return repository


def _add_passing_signals(repository: ContextRepository, key: str, version: int, start: datetime, expiry: datetime) -> None:
    for signal_type in ("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"):
        repository.add_trust_signal({
            "target_kind": "policy", "target_key": key, "version_number": version,
            "signal_type": signal_type, "status": "PASS", "observed_at": start,
            "expires_at": expiry, "source": f"test-{key}-{version}-{signal_type}", "details": {},
        })


def test_seed_preview_write_replay_and_changed_certified_content(client: TestClient) -> None:
    database = client.app.state.store.database
    replay = apply_seed(database, load_seed(SEED_PATH), write=True)
    assert replay == {"created": 0, "unchanged": 31, "conflict": 0, "requires_new_version": 0, "write": True}
    preview = apply_seed(database, load_seed(SEED_PATH), write=False)
    assert preview["created"] == 0 and preview["unchanged"] == 31

    changed = deepcopy(load_seed(SEED_PATH))
    changed["policies"][0]["versions"][0]["rules"][0]["parameters"]["limits"]["Travel"] = 9999
    with pytest.raises(SeedConflictError, match="create a new version"):
        apply_seed(database, changed, write=True)


def test_seed_rejects_changed_certification_and_trust_evidence(client: TestClient) -> None:
    database = client.app.state.store.database
    with database.transaction() as session:
        version = session.get(
            PolicyVersion,
            stable_id("policy-version", "EXPENSE_APPROVAL_ROUTING:1"),
        )
        assert version is not None
        version.status = "DRAFT"
    with pytest.raises(SeedConflictError, match="create a new version"):
        apply_seed(database, load_seed(SEED_PATH), write=True)

    with database.transaction() as session:
        version = session.get(
            PolicyVersion,
            stable_id("policy-version", "EXPENSE_APPROVAL_ROUTING:1"),
        )
        assert version is not None
        version.status = "CERTIFIED"
        signal = session.scalar(
            select(TrustSignal).where(
                TrustSignal.policy_version_id == version.policy_version_id,
                TrustSignal.signal_type == "FRESHNESS",
            )
        )
        assert signal is not None
        signal.details = {"changed": True}
    with pytest.raises(SeedConflictError, match="conflicts with existing evidence"):
        apply_seed(database, load_seed(SEED_PATH), write=True)


def test_hashes_are_canonical_and_change_with_governed_content() -> None:
    assert sha256_content({"b": 2, "a": {"y": 2, "x": 1}}) == sha256_content({"a": {"x": 1, "y": 2}, "b": 2})
    start = datetime(2025, 1, 1, tzinfo=UTC)
    version = _policy_version(1, start, None)
    assert policy_content_hash(version, [_rule("B"), _rule("A")]) == policy_content_hash(version, [_rule("A"), _rule("B")])
    changed = _rule("A")
    changed["parameters"]["limit"] = 11
    assert policy_content_hash(version, [_rule("A")]) != policy_content_hash(version, [changed])
    term = {"version_number": 1, "definition": "One", "effective_from": start, "effective_to": None, "review_due_at": None, "source_reference": "source"}
    assert term_content_hash(term) != term_content_hash({**term, "definition": "Two"})


def test_historical_policy_resolution_and_missing(client: TestClient) -> None:
    repository = _create_test_policy(client, "HISTORICAL_POLICY")
    first = datetime(2020, 1, 1, tzinfo=UTC)
    boundary = datetime(2021, 1, 1, tzinfo=UTC)
    end = datetime(2022, 1, 1, tzinfo=UTC)
    repository.create_policy_version("HISTORICAL_POLICY", _policy_version(1, first, boundary), [_rule("V1")])
    repository.create_policy_version("HISTORICAL_POLICY", _policy_version(2, boundary, end), [_rule("V2")])
    _add_passing_signals(repository, "HISTORICAL_POLICY", 1, first, boundary)
    _add_passing_signals(repository, "HISTORICAL_POLICY", 2, boundary, end)
    service = client.app.state.store.context
    assert service.resolve_policy("HISTORICAL_POLICY", first + timedelta(days=1))["version_number"] == 1
    assert service.resolve_policy("HISTORICAL_POLICY", boundary + timedelta(days=1))["version_number"] == 2
    missing = service.resolve_policy("HISTORICAL_POLICY", first - timedelta(days=1))
    assert missing["trust"]["state"] == "MISSING"
    assert len(repository.policy_versions("HISTORICAL_POLICY")) == 2


def test_certified_policy_term_and_rules_are_immutable(client: TestClient) -> None:
    repository = client.app.state.store.context.repository
    version = repository.policy_versions("EXPENSE_APPROVAL_ROUTING")[0]
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_policy_version(version["policy_version_id"], metadata={"changed": True})
    with client.app.state.store.database.session() as session:
        rule_id = session.scalar(select(PolicyRule.rule_id).where(PolicyRule.policy_version_id == version["policy_version_id"]))
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_policy_rule(rule_id, description="changed")
    term = repository.term_versions("SUPPORTING_RECEIPT")[0]
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_term_version(term["term_version_id"], definition="changed")

    repository.update_policy_version(version["policy_version_id"], status="RETIRED")
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_policy_version(version["policy_version_id"], metadata={"changed": True})
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_policy_rule(rule_id, description="changed after retirement")
    with pytest.raises(ContextIntegrityError, match="lifecycle"):
        repository.update_policy_version(version["policy_version_id"], status="DRAFT")
    repository.update_term_version(term["term_version_id"], status="RETIRED")
    with pytest.raises(ContextIntegrityError, match="immutable"):
        repository.update_term_version(term["term_version_id"], definition="changed after retirement")
    with pytest.raises(ContextIntegrityError, match="lifecycle"):
        repository.update_term_version(term["term_version_id"], status="CERTIFIED")

    replacement = _create_test_policy(client, "REPLACEMENT_POLICY")
    replacement.create_policy_version("REPLACEMENT_POLICY", _policy_version(1, datetime(2020, 1, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC)), [_rule()])
    replacement.create_policy_version("REPLACEMENT_POLICY", _policy_version(2, datetime(2021, 1, 1, tzinfo=UTC), None), [_rule()])
    assert len(replacement.policy_versions("REPLACEMENT_POLICY")) == 2


def test_overlap_prevention_and_defensive_conflict(client: TestClient) -> None:
    repository = _create_test_policy(client, "CONFLICT_POLICY")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    repository.create_policy_version("CONFLICT_POLICY", _policy_version(1, start, None), [_rule("A")])
    with pytest.raises(ContextIntegrityError, match="overlap"):
        repository.create_policy_version("CONFLICT_POLICY", _policy_version(2, start + timedelta(days=1), None), [_rule("B")])

    database = client.app.state.store.database
    with database.transaction() as session:
        policy_id = session.scalar(select(PolicyDefinition.policy_id).where(PolicyDefinition.policy_key == "CONFLICT_POLICY"))
        session.add(PolicyVersion(
            policy_version_id=stable_id("policy-version", "CONFLICT_POLICY:99"), policy_id=policy_id,
            version_number=99, status="CERTIFIED", effective_from=start, effective_to=None,
            review_due_at=start + timedelta(days=3650), certified_at=start,
            source_reference="deliberate defensive fixture", content_hash="f" * 64,
            context_metadata={}, created_at=start,
        ))
    with pytest.raises(ContextConflictError):
        client.app.state.store.context.resolve_policy("CONFLICT_POLICY", start + timedelta(days=2))
    assert client.get("/api/context/policies/CONFLICT_POLICY/resolve", params={"as_of": "2020-01-03T00:00:00Z"}).status_code == 409


def test_stale_expired_signal_inactive_owner_unverified_and_fail_conflict(client: TestClient) -> None:
    repository = _create_test_policy(client, "TRUST_POLICY")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    end = datetime(2030, 1, 1, tzinfo=UTC)
    repository.create_policy_version("TRUST_POLICY", _policy_version(1, start, end, review=datetime(2022, 1, 1, tzinfo=UTC)), [_rule()])
    _add_passing_signals(repository, "TRUST_POLICY", 1, start, end)
    service = client.app.state.store.context
    assert service.resolve_policy("TRUST_POLICY", datetime(2023, 1, 1, tzinfo=UTC))["trust"]["state"] == "STALE"

    repository = _create_test_policy(client, "EXPIRED_POLICY")
    repository.create_policy_version("EXPIRED_POLICY", _policy_version(1, start, end), [_rule()])
    _add_passing_signals(repository, "EXPIRED_POLICY", 1, start, datetime(2021, 1, 1, tzinfo=UTC))
    assert service.resolve_policy("EXPIRED_POLICY", datetime(2022, 1, 1, tzinfo=UTC))["trust"]["state"] == "STALE"

    database = client.app.state.store.database
    with database.transaction() as session:
        session.execute(update(GovernanceOwner).where(GovernanceOwner.owner_key == "FINANCE_COMPLIANCE").values(active=False))
    assert service.resolve_policy("EXPENSE_APPROVAL_ROUTING", datetime(2026, 1, 1, tzinfo=UTC))["trust"]["state"] == "UNVERIFIED"
    with database.transaction() as session:
        session.execute(update(GovernanceOwner).where(GovernanceOwner.owner_key == "FINANCE_COMPLIANCE").values(active=True))
        signal = session.scalar(select(TrustSignal).where(TrustSignal.policy_version_id == stable_id("policy-version", "EXPENSE_APPROVAL_ROUTING:1"), TrustSignal.signal_type == "SOURCE_VERIFICATION"))
        signal.status = "FAIL"
    assert service.resolve_policy("EXPENSE_APPROVAL_ROUTING", datetime(2026, 1, 1, tzinfo=UTC))["trust"]["state"] == "CONFLICTED"


def test_read_only_context_api_and_expense_context_separate_risk(client: TestClient) -> None:
    normal = json.loads((PROJECT_DIR / "demo_payloads" / "normal_expense.json").read_text(encoding="utf-8"))
    suspicious = json.loads((PROJECT_DIR / "demo_payloads" / "suspicious_expense.json").read_text(encoding="utf-8"))
    normal_result = client.post("/api/expenses/process", json=normal).json()
    suspicious_result = client.post("/api/expenses/process", json=suspicious).json()
    assert (normal_result["status"], normal_result["risk_level"], normal_result["approver_role"]) == ("PENDING_APPROVAL", "LOW", "Department Head")
    assert (suspicious_result["status"], suspicious_result["risk_level"], suspicious_result["approver_role"]) == ("ESCALATED", "CRITICAL", "Finance Director + Compliance")

    assert len(client.get("/api/context/policies").json()) == 2
    assert client.get("/api/context/policies/EXPENSE_APPROVAL_ROUTING").json()["owner"]["display_name"] == "Finance Compliance"
    assert len(client.get("/api/context/policies/EXPENSE_APPROVAL_ROUTING/versions").json()) == 1
    assert client.get("/api/context/policies/EXPENSE_APPROVAL_ROUTING/resolve").json()["trust"]["state"] == "TRUSTED"
    assert len(client.get("/api/context/terms").json()) == 3
    assert client.get("/api/context/terms/SUPPORTING_RECEIPT").status_code == 200
    assert client.get("/api/context/terms/SUPPORTING_RECEIPT/resolve").json()["trust"]["state"] == "TRUSTED"
    assert client.get("/api/context/owners/FINANCE_COMPLIANCE").status_code == 200
    assert client.get("/api/context/policies/DOES_NOT_EXIST").status_code == 404
    assert client.post("/api/context/policies", json={}).status_code == 405

    context = client.get("/api/context/expenses/DEMO-SUSPICIOUS-001").json()
    assert context["decision_behavior_changed"] is False
    assert {policy["policy_key"] for policy in context["policies"]} == {"EXPENSE_SUBMISSION_REQUIREMENTS", "EXPENSE_APPROVAL_ROUTING"}
    observed = {signal["signal_key"] for signal in context["risk_signal_definitions"] if signal["observed_flags"]}
    assert {"STATISTICAL_OUTLIER", "WEEKEND_TRANSACTION", "SUSPICIOUS_ROUND_AMOUNT", "MISSING_RECEIPT_HIGH_VALUE", "POTENTIAL_DUPLICATE"}.issubset(observed)
    assert all(signal["category"] == "ALGORITHMIC_RISK_SIGNAL" for signal in context["risk_signal_definitions"])
    assert all(rule["rule_key"] != "STATISTICAL_OUTLIER" for policy in context["policies"] for rule in policy["rules"])


def test_database_window_constraints(client: TestClient) -> None:
    repository = _create_test_policy(client, "WINDOW_POLICY")
    start = datetime(2025, 1, 2, tzinfo=UTC)
    with pytest.raises(ContextIntegrityError, match="effective_to"):
        repository.create_policy_version("WINDOW_POLICY", _policy_version(1, start, start - timedelta(days=1)), [_rule()])
    bad_review = _policy_version(1, start, None, review=start - timedelta(days=1))
    with pytest.raises(ContextIntegrityError, match="review_due_at"):
        repository.create_policy_version("WINDOW_POLICY", bad_review, [_rule()])


def test_schema_constraints_and_version_uniqueness(client: TestClient) -> None:
    database = client.app.state.store.database
    schema = inspect(database.engine)
    assert {
        "governance_owners", "business_terms", "business_term_versions",
        "policy_definitions", "policy_versions", "policy_rules", "trust_signals",
    }.issubset(schema.get_table_names())
    assert {"ix_policy_versions_effective"}.issubset({item["name"] for item in schema.get_indexes("policy_versions")})
    assert {"ix_business_term_versions_effective"}.issubset({item["name"] for item in schema.get_indexes("business_term_versions")})
    assert {"ix_trust_signals_policy", "ix_trust_signals_term"}.issubset({item["name"] for item in schema.get_indexes("trust_signals")})

    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            session.add(TrustSignal(
                trust_signal_id="invalid-target", policy_version_id=None,
                business_term_version_id=None, signal_type="CERTIFICATION", status="PASS",
                observed_at=datetime(2025, 1, 1, tzinfo=UTC), expires_at=None,
                source="test", details={}, created_at=datetime(2025, 1, 1, tzinfo=UTC),
            ))

    existing = client.app.state.store.context.repository.policy_versions("EXPENSE_APPROVAL_ROUTING")[0]
    with pytest.raises(IntegrityError):
        with database.transaction() as session:
            policy_id = session.scalar(select(PolicyDefinition.policy_id).where(PolicyDefinition.policy_key == "EXPENSE_APPROVAL_ROUTING"))
            session.add(PolicyVersion(
                policy_version_id="duplicate-version", policy_id=policy_id,
                version_number=existing["version_number"], status="DRAFT",
                effective_from=datetime(2031, 1, 1, tzinfo=UTC), effective_to=None,
                review_due_at=None, certified_at=None, source_reference="test",
                content_hash="0" * 64, context_metadata={}, created_at=datetime(2031, 1, 1, tzinfo=UTC),
            ))


def test_draft_is_unverified_and_retirement_preserves_history(client: TestClient) -> None:
    repository = _create_test_policy(client, "LIFECYCLE_POLICY")
    start = datetime(2020, 1, 1, tzinfo=UTC)
    draft_id = repository.create_policy_version(
        "LIFECYCLE_POLICY", _policy_version(1, start, datetime(2021, 1, 1, tzinfo=UTC), status="DRAFT"), [_rule()]
    )
    assert client.app.state.store.context.resolve_policy("LIFECYCLE_POLICY", start + timedelta(days=1))["trust"]["state"] == "UNVERIFIED"
    repository.update_policy_version(draft_id, status="RETIRED")
    versions = repository.policy_versions("LIFECYCLE_POLICY")
    assert versions[0]["status"] == "RETIRED"
    assert versions[0]["content_hash"]


def test_historical_business_term_resolution(client: TestClient) -> None:
    repository = client.app.state.store.context.repository
    repository.create_term({
        "term_key": "HISTORICAL_TERM", "canonical_name": "Historical Term",
        "domain": "Expense Management", "owner_key": "FINANCE_COMPLIANCE",
    })
    first = datetime(2020, 1, 1, tzinfo=UTC)
    boundary = datetime(2021, 1, 1, tzinfo=UTC)
    second_end = datetime(2022, 1, 1, tzinfo=UTC)
    for number, definition, start, end in (
        (1, "Definition one", first, boundary),
        (2, "Definition two", boundary, second_end),
    ):
        repository.create_term_version("HISTORICAL_TERM", {
            "version_number": number, "definition": definition, "status": "CERTIFIED",
            "effective_from": start, "effective_to": end, "review_due_at": end,
            "certified_at": start, "source_reference": "test",
        })
        for signal_type in ("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"):
            repository.add_trust_signal({
                "target_kind": "term", "target_key": "HISTORICAL_TERM", "version_number": number,
                "signal_type": signal_type, "status": "PASS", "observed_at": start,
                "expires_at": end, "source": f"term-{number}-{signal_type}", "details": {},
            })
    service = client.app.state.store.context
    assert service.resolve_business_term("HISTORICAL_TERM", first + timedelta(days=1))["definition"] == "Definition one"
    assert service.resolve_business_term("HISTORICAL_TERM", boundary + timedelta(days=1))["definition"] == "Definition two"
    assert service.resolve_business_term("HISTORICAL_TERM", first - timedelta(days=1))["trust"]["state"] == "MISSING"


POSTGRES_URL = os.getenv("NORTHSTAR_TEST_POSTGRES_URL")


@pytest.mark.skipif(not POSTGRES_URL, reason="requires PostgreSQL")
def test_postgres_context_schema_seed_and_resolution() -> None:
    application = create_app(POSTGRES_URL)
    database = application.state.store.database
    with database.transaction() as session:
        from app.db.models import BusinessTerm, BusinessTermVersion
        session.query(TrustSignal).delete()
        session.query(PolicyRule).delete()
        session.query(PolicyVersion).delete()
        session.query(PolicyDefinition).delete()
        session.query(BusinessTermVersion).delete()
        session.query(BusinessTerm).delete()
        session.query(GovernanceOwner).delete()
    result = apply_seed(database, load_seed(SEED_PATH), write=True)
    assert result["created"] == 31
    columns = {column["name"]: str(column["type"]).upper() for column in inspect(database.engine).get_columns("policy_versions")}
    assert columns["metadata"] == "JSONB"
    rule_columns = {column["name"]: str(column["type"]).upper() for column in inspect(database.engine).get_columns("policy_rules")}
    assert rule_columns["parameters"] == "JSONB"
    resolved = application.state.store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING", datetime(2026, 1, 1, tzinfo=UTC))
    assert resolved["version_number"] == 1
    assert resolved["trust"]["state"] == "TRUSTED"
