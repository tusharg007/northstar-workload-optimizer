"""Gate 4B policy binding, safety abstention, and immutable provenance."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import delete, func, select, update

from app.context.binding import bind_policies
from app.db.models import (
    ApprovalDecision, ApprovalTask, DecisionHumanEvidence, DecisionPolicyEvidence,
    DecisionProvenance, DecisionRiskEvidence, DecisionRuleEvidence, DecisionTermEvidence,
    DecisionTrustEvidence, Expense, PolicyDefinition, PolicyRule, PolicyVersion,
    TrustSignal, WorkflowRun,
)
from app.db.repositories.context import stable_id
from app.db.repositories.provenance import ProvenanceRepository
from app.main import create_app
from automation.automation_flow import AnomalyDetector, ApprovalRouter, ExpenseSubmission, ExpenseValidator
from automation.policy_manifest import policy_execution_manifest

PROJECT_DIR = Path(__file__).resolve().parents[1]
UTC = timezone.utc


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "gate4b.db"))


def payload(name: str, expense_id: str) -> dict:
    result = json.loads((PROJECT_DIR / "demo_payloads" / name).read_text(encoding="utf-8"))
    result["expense_id"] = expense_id
    return result


def test_policy_binding_match_numeric_canonicalization_missing_extra_and_mismatch(client: TestClient) -> None:
    service = client.app.state.store.context
    policies = [service.resolve_policy(key) for key in policy_execution_manifest()]
    assert bind_policies(policies)["state"] == "MATCHED"
    numeric = deepcopy(policy_execution_manifest())
    numeric["EXPENSE_SUBMISSION_REQUIREMENTS"]["RECEIPT_REQUIRED_THRESHOLD"]["amount_greater_than"] = 75.0
    assert bind_policies(policies, numeric)["state"] == "MATCHED"

    extra = deepcopy(policies)
    extra[0]["rules"].append({"rule_key": "UNRELATED", "parameters": {"x": 1}})
    assert bind_policies(extra)["state"] == "MATCHED"
    missing = deepcopy(policy_execution_manifest())
    missing["EXPENSE_SUBMISSION_REQUIREMENTS"]["NEW_REQUIRED_RULE"] = {"x": 1}
    assert bind_policies(policies, missing)["state"] == "MISSING"
    mismatch = deepcopy(policy_execution_manifest())
    mismatch["EXPENSE_SUBMISSION_REQUIREMENTS"]["RECEIPT_REQUIRED_THRESHOLD"]["amount_greater_than"] = 100
    assert bind_policies(policies, mismatch)["state"] == "MISMATCH"
    untrusted = deepcopy(policies); untrusted[0]["trust"]["state"] = "STALE"
    assert bind_policies(untrusted)["state"] == "UNTRUSTED"


def test_engine_emits_structured_policy_and_risk_evidence() -> None:
    raw = payload("suspicious_expense.json", "STRUCTURED")
    expense, validation = ExpenseValidator().validate(raw)
    assert expense is not None
    assert {item["rule_key"] for item in validation.policy_evaluations} == {
        "CATEGORY_SPENDING_LIMITS", "RECEIPT_REQUIRED_THRESHOLD",
        "DESCRIPTION_REQUIRED_THRESHOLD", "FUTURE_TRANSACTION_DATE_REJECTED",
    }
    anomaly = AnomalyDetector().detect(expense)
    assert len(anomaly.risk_evaluations) == 6
    assert sum(item["triggered"] for item in anomaly.risk_evaluations) == 5
    assert any(not item["triggered"] for item in anomaly.risk_evaluations)
    decision = ApprovalRouter().route(expense, anomaly)
    assert {item["rule_key"] for item in decision.policy_evaluations} == {
        "AMOUNT_APPROVAL_TIERS", "HIGH_RISK_ESCALATION_ROUTE",
        "MEDIUM_RISK_REQUIRES_HUMAN", "REVIEW_REQUIRED_THRESHOLD",
    }


def test_automated_provenance_trace_verify_replay_and_human_evidence(client: TestClient) -> None:
    raw = payload("suspicious_expense.json", "G4B-SUSPICIOUS")
    headers = {"Idempotency-Key": "g4b-suspicious", "X-Correlation-ID": "g4b-correlation"}
    first = client.post("/api/expenses/process", json=raw, headers=headers)
    assert first.status_code == 200
    assert (first.json()["status"], first.json()["risk_level"], first.json()["approver_role"]) == (
        "ESCALATED", "CRITICAL", "Finance Director + Compliance",
    )
    provenance = client.get("/api/provenance/expenses/G4B-SUSPICIOUS").json()
    assert provenance["correlation_id"] == "g4b-correlation"
    assert len(provenance["policies"]) == 2
    assert {item["owner_display_name"] for item in provenance["policies"]} == {"Finance Compliance"}
    assert {item["trust_state"] for item in provenance["policies"]} == {"TRUSTED"}
    assert len(provenance["terms"]) == 3 and len(provenance["rules"]) == 8
    assert len(provenance["risk"]) == 6
    assert sum(item["triggered"] for item in provenance["risk"]) == 5
    assert client.get(f"/api/provenance/decisions/{provenance['provenance_id']}/verify").json()["status"] == "PASS"
    original_hash = provenance["provenance_hash"]

    replay = client.post("/api/expenses/process", json=raw, headers=headers)
    assert replay.status_code == 200
    replayed = client.get("/api/provenance/expenses/G4B-SUSPICIOUS").json()
    assert replayed["provenance_hash"] == original_hash
    with client.app.state.store.database.session() as session:
        assert session.scalar(select(func.count()).select_from(DecisionProvenance)) == 1
        assert session.scalar(select(func.count()).select_from(DecisionRiskEvidence)) == 6

    approved = client.post("/api/expenses/G4B-SUSPICIOUS/decision", json={"decision": "approve", "approver": "Finance Director", "comment": "Reviewed evidence"})
    assert approved.json()["status"] == "APPROVED"
    trace = client.get("/api/provenance/expenses/G4B-SUSPICIOUS/trace").json()
    assert trace["provenance_status"] == "AVAILABLE"
    assert trace["approval_decision"]["decision"] == "approve"
    assert len(trace["human_evidence"]) == 1 and trace["final_status"] == "APPROVED"
    assert trace["context"]["as_of"] == trace["workflow_run"]["started_at"]
    assert client.get(f"/api/provenance/decisions/{provenance['provenance_id']}/verify").json()["status"] == "PASS"


def test_verifier_detects_evidence_tampering(client: TestClient) -> None:
    client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-TAMPER")).raise_for_status()
    provenance = client.get("/api/provenance/expenses/G4B-TAMPER").json()
    database = client.app.state.store.database
    with database.transaction() as session:
        evidence = session.scalar(select(DecisionRiskEvidence).where(DecisionRiskEvidence.provenance_id == provenance["provenance_id"]))
        evidence.observed_value = {"tampered": True}
    verification = client.get(f"/api/provenance/decisions/{provenance['provenance_id']}/verify").json()
    assert verification["status"] == "FAIL"
    assert verification["failures"]


def test_normal_expense_has_non_triggered_risk_evidence(client: TestClient) -> None:
    response = client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-NORMAL"))
    assert (response.json()["status"], response.json()["risk_level"], response.json()["approver_role"]) == (
        "PENDING_APPROVAL", "LOW", "Department Head",
    )
    provenance = client.get("/api/provenance/expenses/G4B-NORMAL").json()
    assert len(provenance["risk"]) == 6
    assert sum(item["triggered"] for item in provenance["risk"]) == 0


def test_policy_drift_abstains_without_financial_state(client: TestClient) -> None:
    database = client.app.state.store.database
    with database.transaction() as session:
        rule = session.scalar(select(PolicyRule).where(PolicyRule.rule_key == "RECEIPT_REQUIRED_THRESHOLD"))
        rule.parameters = {**rule.parameters, "amount_greater_than": 100}
    response = client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-DRIFT"))
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CONTEXT_NOT_AUTHORITATIVE"
    assert response.json()["detail"]["reason_code"] == "POLICY_ENGINE_MISMATCH"
    with database.session() as session:
        assert session.get(Expense, "G4B-DRIFT") is None
        assert session.scalar(select(func.count()).select_from(DecisionProvenance)) == 0


def test_missing_conflicted_and_stale_context_abstain(client: TestClient) -> None:
    database = client.app.state.store.database
    with database.transaction() as session:
        policy = session.scalar(select(PolicyDefinition).where(PolicyDefinition.policy_key == "EXPENSE_APPROVAL_ROUTING"))
        versions = session.scalars(select(PolicyVersion).where(PolicyVersion.policy_id == policy.policy_id)).all()
        for version in versions:
            session.execute(delete(TrustSignal).where(TrustSignal.policy_version_id == version.policy_version_id))
            session.execute(delete(PolicyRule).where(PolicyRule.policy_version_id == version.policy_version_id))
        session.execute(delete(PolicyVersion).where(PolicyVersion.policy_id == policy.policy_id))
        session.execute(delete(PolicyDefinition).where(PolicyDefinition.policy_id == policy.policy_id))
    missing = client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-MISSING"))
    assert missing.status_code == 409 and missing.json()["detail"]["reason_code"] == "POLICY_MISSING"

    conflict_client = TestClient(create_app(client.app.state.store.db_path.parent / "conflict.db"))
    conflict_db = conflict_client.app.state.store.database
    with conflict_db.transaction() as session:
        policy_id = session.scalar(select(PolicyDefinition.policy_id).where(PolicyDefinition.policy_key == "EXPENSE_APPROVAL_ROUTING"))
        session.add(PolicyVersion(
            policy_version_id="conflicting-version", policy_id=policy_id, version_number=99,
            status="CERTIFIED", effective_from=datetime(2025, 1, 1, tzinfo=UTC), effective_to=None,
            review_due_at=datetime(2030, 1, 1, tzinfo=UTC), certified_at=datetime(2025, 1, 1, tzinfo=UTC),
            source_reference="controlled conflict", content_hash="f" * 64, context_metadata={}, created_at=datetime.now(UTC),
        ))
    conflict = conflict_client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-CONFLICT"))
    assert conflict.status_code == 409 and conflict.json()["detail"]["reason_code"] == "POLICY_CONFLICT"

    stale_client = TestClient(create_app(client.app.state.store.db_path.parent / "stale.db"))
    with stale_client.app.state.store.database.transaction() as session:
        session.execute(update(PolicyVersion).where(PolicyVersion.policy_version_id == stable_id("policy-version", "EXPENSE_APPROVAL_ROUTING:1")).values(review_due_at=datetime(2025, 1, 2, tzinfo=UTC)))
    stale = stale_client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-STALE"))
    assert stale.status_code == 409 and stale.json()["detail"]["reason_code"] == "POLICY_UNTRUSTED"


def test_historical_snapshot_and_trust_evidence_do_not_change(client: TestClient) -> None:
    client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-HISTORY")).raise_for_status()
    before = client.get("/api/provenance/expenses/G4B-HISTORY").json()
    policy_before = next(item for item in before["policies"] if item["policy_key"] == "EXPENSE_APPROVAL_ROUTING")
    trust_before = deepcopy(before["trust"])
    database = client.app.state.store.database
    with database.transaction() as session:
        signal = session.scalar(select(TrustSignal).where(TrustSignal.signal_type == "FRESHNESS"))
        signal.status = "WARN"
    after = client.get("/api/provenance/expenses/G4B-HISTORY").json()
    policy_after = next(item for item in after["policies"] if item["policy_key"] == "EXPENSE_APPROVAL_ROUTING")
    assert policy_after["version_number"] == policy_before["version_number"] == 1
    assert policy_after["content_hash"] == policy_before["content_hash"]
    assert after["trust"] == trust_before


def test_historical_trace_remains_v1_after_current_policy_v2(client: TestClient) -> None:
    client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-VERSION-HISTORY")).raise_for_status()
    before = client.get("/api/provenance/expenses/G4B-VERSION-HISTORY").json()
    old = next(item for item in before["policies"] if item["policy_key"] == "EXPENSE_APPROVAL_ROUTING")
    repository = client.app.state.store.context.repository
    resolved = client.app.state.store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING")
    repository.update_policy_version(resolved["policy_version_id"], status="RETIRED")
    start = datetime(2027, 1, 1, tzinfo=UTC)
    repository.create_policy_version("EXPENSE_APPROVAL_ROUTING", {
        "version_number": 2, "status": "CERTIFIED", "effective_from": start,
        "effective_to": None, "review_due_at": datetime(2030, 1, 1, tzinfo=UTC),
        "certified_at": start, "source_reference": "Gate 4B historical test",
        "metadata": {"test": "v2"},
    }, resolved["rules"])
    for signal_type in ("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"):
        repository.add_trust_signal({
            "target_kind": "policy", "target_key": "EXPENSE_APPROVAL_ROUTING", "version_number": 2,
            "signal_type": signal_type, "status": "PASS", "observed_at": start,
            "expires_at": datetime(2030, 1, 1, tzinfo=UTC), "source": f"g4b-v2-{signal_type}", "details": {},
        })
    current = client.app.state.store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING", start + timedelta(days=1))
    assert current["version_number"] == 2
    after = client.get("/api/provenance/expenses/G4B-VERSION-HISTORY").json()
    historical = next(item for item in after["policies"] if item["policy_key"] == "EXPENSE_APPROVAL_ROUTING")
    assert historical["version_number"] == 1
    assert historical["content_hash"] == old["content_hash"]


def test_processing_and_human_evidence_failures_roll_back(client: TestClient, monkeypatch) -> None:
    database = client.app.state.store.database
    monkeypatch.setattr(ProvenanceRepository, "persist_automated", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced provenance failure")))
    with pytest.raises(RuntimeError, match="forced provenance failure"):
        client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-ROLLBACK"))
    with database.session() as session:
        for model in (Expense, WorkflowRun, ApprovalTask, DecisionProvenance):
            assert session.scalar(select(func.count()).select_from(model)) == 0

    monkeypatch.undo()
    client.post("/api/expenses/process", json=payload("normal_expense.json", "G4B-HUMAN-ROLLBACK")).raise_for_status()
    monkeypatch.setattr(ProvenanceRepository, "add_human_evidence", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("forced human evidence failure")))
    with pytest.raises(RuntimeError, match="forced human evidence failure"):
        client.post("/api/expenses/G4B-HUMAN-ROLLBACK/decision", json={"decision": "approve", "approver": "Head", "comment": "test"})
    with database.session() as session:
        assert session.scalar(select(func.count()).select_from(ApprovalDecision)) == 0
        assert session.scalar(select(func.count()).select_from(DecisionHumanEvidence)) == 0
        assert session.scalar(select(Expense).where(Expense.expense_id == "G4B-HUMAN-ROLLBACK")).status == "PENDING_APPROVAL"


def test_legacy_trace_is_explicitly_unavailable(tmp_path: Path) -> None:
    application = create_app(tmp_path / "legacy.db")
    raw = payload("normal_expense.json", "G4B-LEGACY")
    application.state.store.repository.process_expense(raw, lambda _: {
        "expense_id": "G4B-LEGACY", "status": "PENDING_APPROVAL", "validation": {},
        "anomaly": {"risk_level": "LOW", "flags": []},
        "decision": {"approver_role": "Department Head", "approver_level": 2},
    })
    response = TestClient(application).get("/api/provenance/expenses/G4B-LEGACY/trace")
    assert response.status_code == 200
    assert response.json()["provenance_status"] == "LEGACY_UNAVAILABLE"
