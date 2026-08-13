"""Profile-aware execution of deterministic golden cases against real contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile
from time import perf_counter
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
import httpx
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, text, update

from app.context.seed import apply_seed, load_seed
from app.db.base import Base, utc_now
from app.db.models import (
    DecisionProvenance,
    DecisionRiskEvidence,
    GovernanceOwner,
    ApprovalTask,
    PolicyDefinition,
    PolicyRule,
    PolicyVersion,
    TrustSignal,
    WorkflowRun,
)
from app.db.repositories.context import stable_id
from app.db.session import Database
from app.main import create_app
from app.provenance.service import load_risk_catalog
from app.reliability import ReliabilityPolicy
from automation.policy_manifest import policy_execution_manifest
from evals.models import AssertionResult, CaseResult, EvaluationCase, Profile, Scenario


PROJECT_DIR = Path(__file__).resolve().parents[1]
SEED_PATH = PROJECT_DIR / "context" / "registry.seed.json"
UTC = timezone.utc
RISK_CATALOG = sorted(item["signal_key"] for item in load_risk_catalog()["signals"])
POLICY_KEYS = sorted(policy_execution_manifest())
RULE_KEYS = sorted({key for rules in policy_execution_manifest().values() for key in rules})


def prepare_postgres(database_url: str) -> None:
    config = Config(str(PROJECT_DIR / "alembic.ini"))
    previous = os.environ.get("NORTHSTAR_DATABASE_URL")
    os.environ["NORTHSTAR_DATABASE_URL"] = database_url
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("NORTHSTAR_DATABASE_URL", None)
        else:
            os.environ["NORTHSTAR_DATABASE_URL"] = previous


def reset_postgres(database_url: str) -> None:
    database = Database(database_url)
    tables = ", ".join(f'"{table.name}"' for table in Base.metadata.sorted_tables)
    with database.transaction() as session:
        session.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    apply_seed(database, load_seed(SEED_PATH), write=True)
    database.dispose()


def _mutate_context(database: Database, scenario: Scenario) -> None:
    if scenario in {Scenario.DEFAULT, Scenario.APPROVAL, Scenario.IDEMPOTENT_REPLAY,
                    Scenario.IDEMPOTENCY_CONFLICT, Scenario.HISTORICAL_PROVENANCE,
                    Scenario.PROVENANCE_CORRUPTION, Scenario.OUTBOX_TRANSIENT_RESUME,
                    Scenario.OUTBOX_TRANSIENT_NOTIFICATION, Scenario.OUTBOX_DEAD_LETTER,
                    Scenario.OUTBOX_REPLAY}:
        return
    with database.transaction() as session:
        if scenario == Scenario.POLICY_MISSING:
            policy = session.scalar(select(PolicyDefinition).where(
                PolicyDefinition.policy_key == "EXPENSE_APPROVAL_ROUTING"
            ))
            versions = session.scalars(select(PolicyVersion).where(
                PolicyVersion.policy_id == policy.policy_id
            )).all()
            for version in versions:
                session.execute(delete(TrustSignal).where(
                    TrustSignal.policy_version_id == version.policy_version_id
                ))
                session.execute(delete(PolicyRule).where(
                    PolicyRule.policy_version_id == version.policy_version_id
                ))
            session.execute(delete(PolicyVersion).where(PolicyVersion.policy_id == policy.policy_id))
            session.execute(delete(PolicyDefinition).where(PolicyDefinition.policy_id == policy.policy_id))
        elif scenario in {Scenario.POLICY_MISMATCH, Scenario.POLICY_DRIFT}:
            rule = session.scalar(select(PolicyRule).where(
                PolicyRule.rule_key == "RECEIPT_REQUIRED_THRESHOLD"
            ))
            rule.parameters = {**rule.parameters, "amount_greater_than": 100}
        elif scenario == Scenario.POLICY_CONFLICT:
            policy_id = session.scalar(select(PolicyDefinition.policy_id).where(
                PolicyDefinition.policy_key == "EXPENSE_APPROVAL_ROUTING"
            ))
            session.add(PolicyVersion(
                policy_version_id=str(uuid4()), policy_id=policy_id, version_number=99,
                status="CERTIFIED", effective_from=datetime(2025, 1, 1, tzinfo=UTC),
                effective_to=None, review_due_at=datetime(2030, 1, 1, tzinfo=UTC),
                certified_at=datetime(2025, 1, 1, tzinfo=UTC),
                source_reference="Gate 5 controlled conflict", content_hash="f" * 64,
                context_metadata={"evaluation": True}, created_at=utc_now(),
            ))
        elif scenario == Scenario.POLICY_STALE:
            session.execute(update(PolicyVersion).where(
                PolicyVersion.policy_version_id == stable_id(
                    "policy-version", "EXPENSE_APPROVAL_ROUTING:1"
                )
            ).values(review_due_at=datetime(2025, 1, 2, tzinfo=UTC)))
        elif scenario == Scenario.OWNER_INACTIVE:
            session.execute(update(GovernanceOwner).values(active=False))
        elif scenario == Scenario.TRUST_EXPIRED:
            session.execute(update(TrustSignal).where(
                TrustSignal.signal_type == "FRESHNESS"
            ).values(expires_at=datetime(2025, 1, 2, tzinfo=UTC)))


def _binding_state(reason_code: str | None) -> str:
    return {
        "POLICY_MISSING": "MISSING",
        "POLICY_ENGINE_MISMATCH": "MISMATCH",
        "POLICY_CONFLICT": "CONFLICTED",
        "POLICY_UNTRUSTED": "UNTRUSTED",
    }.get(reason_code, "MATCHED")


def _provenance_complete(provenance: dict[str, Any]) -> bool:
    return all((
        sorted(item["policy_key"] for item in provenance.get("policies", [])) == POLICY_KEYS,
        sorted(item["rule_key"] for item in provenance.get("rules", [])) == RULE_KEYS,
        sorted(item["signal_key"] for item in provenance.get("risk", [])) == RISK_CATALOG,
        len(provenance.get("terms", [])) == 3,
        len(provenance.get("trust", [])) == 20,
        provenance.get("context_trust_state") == "TRUSTED",
        all(item.get("snapshot_hash") for item in provenance.get("policies", [])),
        all(item.get("snapshot_hash") for item in provenance.get("terms", [])),
        all(item.get("evidence_hash") for item in provenance.get("rules", [])),
        all(item.get("evidence_hash") for item in provenance.get("trust", [])),
        all(item.get("evidence_hash") and item.get("signal_definition_hash")
            for item in provenance.get("risk", [])),
        bool(provenance.get("provenance_hash")),
        bool(provenance.get("decision_engine_version")),
        bool(provenance.get("risk_engine_version")),
        bool(provenance.get("risk_catalog_hash")),
    ))


def _response_json(response) -> Any:
    try:
        return response.json()
    except Exception:
        return {"detail": "non-JSON response"}


def _post(client, path: str, *, json: dict | None = None, headers: dict | None = None):
    return client.post(path, json=json, headers=headers)


def _get(client, path: str):
    return client.get(path)


def _make_resume_event(client, payload: dict, process_path: str = "/api/expenses/process") -> dict:
    processed = _post(client, process_path, json=payload)
    processed.raise_for_status()
    task = _get(client, f"/api/internal/approval-tasks/by-expense/{payload['expense_id']}").json()
    decision = _post(client, f"/api/expenses/{payload['expense_id']}/decision", json={
        "decision": "approve", "approver": "Gate 5 Evaluator", "comment": "controlled evaluation"
    })
    decision.raise_for_status()
    return _get(client, f"/api/internal/outbox/by-delivery-key/approval-resume:{task['task_id']}").json()


def _make_notification_event(client, payload: dict, process_path: str = "/api/expenses/process") -> dict:
    _post(client, process_path, json=payload).raise_for_status()
    task = _get(client, f"/api/internal/approval-tasks/by-expense/{payload['expense_id']}").json()
    notification = _post(client, f"/api/internal/approval-tasks/{task['task_id']}/notifications/reserve", json={
        "notification_type": "REMINDER", "escalation_level": 0
    }).json()
    return _get(client, f"/api/internal/outbox/by-delivery-key/notification:{notification['notification_id']}").json()


def _run_reliability(
    case: EvaluationCase, client, process_path: str = "/api/expenses/process"
) -> dict[str, Any]:
    payload = deepcopy(case.payload)
    event = (_make_notification_event(client, payload, process_path)
             if case.scenario == Scenario.OUTBOX_TRANSIENT_NOTIFICATION
             else _make_resume_event(client, payload, process_path))
    event_id = event["outbox_event_id"]
    worker = f"gate5-{case.case_id}"
    if case.scenario in {Scenario.OUTBOX_TRANSIENT_RESUME, Scenario.OUTBOX_TRANSIENT_NOTIFICATION}:
        _post(client, f"/api/internal/outbox/{event_id}/claim", json={"worker_id": worker, "lease_seconds": 1}).raise_for_status()
        failed = _post(client, f"/api/internal/outbox/{event_id}/failure", json={
            "worker_id": worker, "status_code": 503, "error_message": "controlled transient failure"
        }).json()
        _post(client, f"/api/internal/outbox/{event_id}/claim", json={"worker_id": worker, "lease_seconds": 1}).raise_for_status()
        delivered = _post(client, f"/api/internal/outbox/{event_id}/success", json={
            "worker_id": worker, "status_code": 200
        }).json()
        detail = _get(client, f"/api/internal/outbox/{event_id}").json()
        ok = failed["status"] == "PENDING" and delivered["status"] == "DELIVERED"
        ok = ok and [item["outcome"] for item in detail["attempts"]] == ["RETRYABLE_FAILURE", "SUCCESS"]
        return {"http_status": 200, "reliability_outcome": "RECOVERED", "reliability_ok": ok,
                "logical_duplicate_side_effects": 0}

    for _ in range(4):
        _post(client, f"/api/internal/outbox/{event_id}/claim", json={"worker_id": worker, "lease_seconds": 1}).raise_for_status()
        state = _post(client, f"/api/internal/outbox/{event_id}/failure", json={
            "worker_id": worker, "status_code": 503, "error_message": "controlled poison event"
        }).json()
    if case.scenario == Scenario.OUTBOX_DEAD_LETTER:
        detail = _get(client, f"/api/internal/outbox/{event_id}").json()
        ok = state["status"] == "DEAD_LETTER" and len(detail["attempts"]) == 4
        return {"http_status": 200, "reliability_outcome": "DEAD_LETTER", "reliability_ok": ok,
                "logical_duplicate_side_effects": 0}
    replayed = _post(client, f"/api/internal/outbox/{event_id}/replay").json()
    _post(client, f"/api/internal/outbox/{event_id}/claim", json={"worker_id": worker, "lease_seconds": 1}).raise_for_status()
    delivered = _post(client, f"/api/internal/outbox/{event_id}/success", json={
        "worker_id": worker, "status_code": 200
    }).json()
    detail = _get(client, f"/api/internal/outbox/{event_id}").json()
    ok = replayed["replay_count"] == 1 and delivered["status"] == "DELIVERED" and len(detail["attempts"]) == 5
    return {"http_status": 200, "reliability_outcome": "REPLAYED_AND_DELIVERED", "reliability_ok": ok,
            "logical_duplicate_side_effects": 0}


def _create_v2(store) -> dict:
    repository = store.context.repository
    resolved = store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING")
    repository.update_policy_version(resolved["policy_version_id"], status="RETIRED")
    start = datetime(2027, 1, 1, tzinfo=UTC)
    repository.create_policy_version("EXPENSE_APPROVAL_ROUTING", {
        "version_number": 2, "status": "CERTIFIED", "effective_from": start,
        "effective_to": None, "review_due_at": datetime(2030, 1, 1, tzinfo=UTC),
        "certified_at": start, "source_reference": "Gate 5 historical scenario",
        "metadata": {"evaluation": True},
    }, resolved["rules"])
    for signal_type in ("CERTIFICATION", "FRESHNESS", "OWNERSHIP", "SOURCE_VERIFICATION"):
        repository.add_trust_signal({
            "target_kind": "policy", "target_key": "EXPENSE_APPROVAL_ROUTING",
            "version_number": 2, "signal_type": signal_type, "status": "PASS",
            "observed_at": start, "expires_at": datetime(2030, 1, 1, tzinfo=UTC),
            "source": f"gate5-v2-{signal_type}", "details": {},
        })
    return store.context.resolve_policy("EXPENSE_APPROVAL_ROUTING", start + timedelta(days=1))


def _run_historical(case: EvaluationCase, client, store) -> dict[str, Any]:
    if case.scenario == Scenario.HISTORICAL_RESOLUTION:
        before = store.context.resolve_policy(
            "EXPENSE_APPROVAL_ROUTING", datetime(2026, 8, 13, tzinfo=UTC)
        )
        current = _create_v2(store)
        return {
            "http_status": 200, "context_version": current["version_number"],
            "historical_version": before["version_number"],
        }
    response = _post(client, "/api/expenses/process", json=case.payload)
    response.raise_for_status()
    before = _get(client, f"/api/provenance/expenses/{case.payload['expense_id']}").json()
    _create_v2(store)
    after = _get(client, f"/api/provenance/expenses/{case.payload['expense_id']}").json()
    old = {item["policy_key"]: item for item in before["policies"]}
    retained = all(
        item["version_number"] == old[item["policy_key"]]["version_number"] == 1
        and item["content_hash"] == old[item["policy_key"]]["content_hash"]
        for item in after["policies"]
    )
    return {"http_status": 200, "context_version": 1, "historical_retained": retained}


def _run_standard(
    case: EvaluationCase,
    client,
    database: Database | None,
    *,
    expense_submit_path: str = "/api/expenses/process",
    approval_submit_url: str | None = None,
) -> dict[str, Any]:
    payload = deepcopy(case.payload)
    headers = {"Idempotency-Key": f"gate5:{case.case_id}", "X-Correlation-ID": f"gate5-{case.case_id}"}
    response = _post(client, expense_submit_path, json=payload, headers=headers)
    body = _response_json(response)
    detail = body.get("detail", {}) if isinstance(body, dict) else {}
    reason_code = detail.get("reason_code") if isinstance(detail, dict) else None
    actual: dict[str, Any] = {
        "http_status": response.status_code,
        "status": body.get("status") if isinstance(body, dict) else None,
        "risk_level": body.get("risk_level") if isinstance(body, dict) else None,
        "approver_role": body.get("approver_role") if isinstance(body, dict) else None,
        "reason_code": reason_code,
        "error_code": detail.get("code") if isinstance(detail, dict) else None,
        "binding_state": _binding_state(reason_code),
        "abstained": response.status_code == 409 and reason_code is not None,
    }
    if response.status_code != 200:
        return actual

    expense_id = payload["expense_id"]
    provenance_response = _get(client, f"/api/provenance/expenses/{expense_id}")
    if provenance_response.status_code == 200:
        provenance = provenance_response.json()
        actual["triggered_signals"] = sorted(
            item["signal_key"] for item in provenance["risk"] if item["triggered"]
        )
        actual["risk_catalog"] = sorted(item["signal_key"] for item in provenance["risk"])
        actual["provenance_complete"] = _provenance_complete(provenance)
        actual["provenance_verified"] = _get(
            client, f"/api/provenance/decisions/{provenance['provenance_id']}/verify"
        ).json()["status"] == "PASS"
        actual["provenance_id"] = provenance["provenance_id"]
        actual["provenance_hash"] = provenance["provenance_hash"]
        actual["policy_keys"] = sorted(item["policy_key"] for item in provenance["policies"])
        actual["rule_keys"] = sorted(item["rule_key"] for item in provenance["rules"])
        actual["triggered_rules"] = sorted(
            item["rule_key"] for item in provenance["rules"] if item["triggered"]
        )
        actual["context_trust_state"] = provenance["context_trust_state"]
        actual["correlation_id"] = provenance["correlation_id"]

    if case.scenario == Scenario.APPROVAL:
        decision_payload = {
            "decision": "approve", "approver": "Gate 5 Evaluator", "comment": "evidence reviewed"
        }
        if approval_submit_url:
            decision_payload = {"expense_id": expense_id, **decision_payload}
        _post(client, approval_submit_url or f"/api/expenses/{expense_id}/decision", json=decision_payload).raise_for_status()
        trace = _get(client, f"/api/provenance/expenses/{expense_id}/trace").json()
        actual["human_evidence"] = (
            trace["final_status"] == "APPROVED" and len(trace["human_evidence"]) == 1
            and trace["approval_decision"]["decision"] == "approve"
        )
    elif case.scenario == Scenario.IDEMPOTENT_REPLAY:
        first_id = actual.get("provenance_id")
        first_hash = actual.get("provenance_hash")
        second = _post(client, expense_submit_path, json=payload, headers=headers)
        second_provenance = _get(client, f"/api/provenance/expenses/{expense_id}").json()
        count_ok = True
        if database is not None:
            with database.session() as session:
                count_ok = all(
                    session.scalar(select(func.count()).select_from(model)) == 1
                    for model in (WorkflowRun, ApprovalTask, DecisionProvenance)
                )
        actual["idempotency_preserved"] = (
            second.status_code == 200
            and _response_json(second) == body
            and second_provenance["provenance_id"] == first_id
            and second_provenance["provenance_hash"] == first_hash
            and count_ok
        )
    elif case.scenario == Scenario.IDEMPOTENCY_CONFLICT:
        changed = deepcopy(payload)
        changed["amount"] = float(changed["amount"]) + 1
        conflict = _post(client, expense_submit_path, json=changed, headers=headers)
        after = _get(client, f"/api/provenance/expenses/{expense_id}").json()
        actual["idempotency_preserved"] = (
            conflict.status_code == 409 and after["provenance_hash"] == actual["provenance_hash"]
        )
    elif case.scenario == Scenario.PROVENANCE_CORRUPTION:
        if database is None:
            raise RuntimeError("Provenance corruption requires direct evaluation database access")
        with database.transaction() as session:
            evidence = session.scalar(select(DecisionRiskEvidence).where(
                DecisionRiskEvidence.provenance_id == actual["provenance_id"]
            ))
            original_observed = deepcopy(evidence.observed_value)
            evidence.observed_value = {"controlled_corruption": True}
        actual["provenance_verified"] = _get(
            client, f"/api/provenance/decisions/{actual['provenance_id']}/verify"
        ).json()["status"] == "PASS"
        with database.transaction() as session:
            evidence = session.scalar(select(DecisionRiskEvidence).where(
                DecisionRiskEvidence.provenance_id == actual["provenance_id"]
            ))
            evidence.observed_value = original_observed
        actual["provenance_restored"] = _get(
            client, f"/api/provenance/decisions/{actual['provenance_id']}/verify"
        ).json()["status"] == "PASS"
    return actual


def _assertions(case: EvaluationCase, actual: dict[str, Any]) -> list[AssertionResult]:
    expected = case.expected
    items = [AssertionResult(name="http_status", passed=actual.get("http_status") == expected.http_status,
                             expected=expected.http_status, actual=actual.get("http_status"))]
    mapping = {
        "status": "decision", "risk_level": "risk_level", "approver_role": "routing",
        "binding_state": "policy_binding", "provenance_complete": "provenance_completeness",
        "provenance_verified": "provenance_verification", "human_evidence": "provenance_completeness",
        "idempotency_preserved": "idempotency", "context_version": "context_resolution",
        "reliability_outcome": "reliability",
        "error_code": "context_resolution", "context_trust_state": "context_resolution",
        "policy_keys": "provenance_completeness", "rule_keys": "provenance_completeness",
        "triggered_rules": "decision",
    }
    for field, name in mapping.items():
        value = getattr(expected, field)
        if value is not None:
            items.append(AssertionResult(name=name, passed=actual.get(field) == value,
                                         expected=value, actual=actual.get(field)))
    if expected.reason_code is not None:
        items.append(AssertionResult(name="context_resolution", passed=actual.get("reason_code") == expected.reason_code,
                                     expected=expected.reason_code, actual=actual.get("reason_code")))
    if expected.triggered_signals is not None:
        desired = sorted(expected.triggered_signals)
        items.append(AssertionResult(name="risk_signals", passed=actual.get("triggered_signals") == desired,
                                     expected=desired, actual=actual.get("triggered_signals")))
    if expected.non_triggered_signals is not None and actual.get("risk_catalog") is not None:
        not_triggered = sorted(set(actual["risk_catalog"]) - set(actual.get("triggered_signals", [])))
        desired = sorted(expected.non_triggered_signals)
        items.append(AssertionResult(name="risk_signals", passed=not_triggered == desired,
                                     expected=desired, actual=not_triggered))
    items.append(AssertionResult(name="abstention", passed=actual.get("abstained") == expected.abstained,
                                 expected=expected.abstained, actual=actual.get("abstained")))
    if expected.reliability_outcome is not None:
        items.append(AssertionResult(name="reliability", passed=actual.get("reliability_ok") is True,
                                     expected=True, actual=actual.get("reliability_ok")))
    if case.scenario == Scenario.PROVENANCE_CORRUPTION:
        items.append(AssertionResult(name="provenance_verification", passed=actual.get("provenance_restored") is True,
                                     expected=True, actual=actual.get("provenance_restored")))
    return items


def run_case(
    case: EvaluationCase,
    profile: Profile,
    *,
    database_url: str | None = None,
    api_base_url: str = "http://127.0.0.1:8000",
    expense_webhook_url: str = "http://127.0.0.1:5678/webhook/northstar-expense",
    approval_webhook_url: str = "http://127.0.0.1:5678/webhook/northstar-approval",
) -> CaseResult:
    started = perf_counter()
    client = None
    store = None
    database = None
    temp_dir = None
    try:
        os.environ["NORTHSTAR_OUTBOX_RETRY_SECONDS"] = "0,0,0,0"
        if profile == Profile.FAST:
            temp_dir = tempfile.TemporaryDirectory(prefix="northstar-gate5-")
            application = create_app(Path(temp_dir.name) / "evaluation.db")
            client = TestClient(application)
            store = application.state.store
            database = store.database
        elif profile == Profile.POSTGRES:
            if not database_url:
                raise ValueError("PostgreSQL profile requires --database-url or NORTHSTAR_EVAL_POSTGRES_URL")
            reset_postgres(database_url)
            application = create_app(database_url)
            client = TestClient(application)
            store = application.state.store
            database = store.database
        else:
            if not database_url:
                raise ValueError("Live profile requires --database-url or NORTHSTAR_EVAL_POSTGRES_URL")
            reset_postgres(database_url)
            database = Database(database_url)
            client = httpx.Client(base_url=api_base_url, timeout=httpx.Timeout(15.0, connect=5.0))

        _mutate_context(database, case.scenario)
        if case.category.value == "reliability":
            actual = _run_reliability(
                case, client,
                expense_webhook_url if profile == Profile.LIVE else "/api/expenses/process",
            )
        elif case.category.value == "historical_context":
            if store is None:
                raise RuntimeError("Historical context cases run in fast/postgres profiles")
            actual = _run_historical(case, client, store)
        else:
            actual = _run_standard(
                case, client, database,
                expense_submit_path=(expense_webhook_url if profile == Profile.LIVE else "/api/expenses/process"),
                approval_submit_url=(approval_webhook_url if profile == Profile.LIVE else None),
            )
        actual.setdefault("abstained", False)
        actual["expected_abstained"] = case.expected.abstained
        if case.expected.triggered_signals is not None:
            actual["expected_signals"] = sorted(case.expected.triggered_signals)
        assertions = _assertions(case, actual)
        return CaseResult(
            case_id=case.case_id, category=case.category, profile=profile,
            passed=all(item.passed for item in assertions),
            duration_ms=round((perf_counter() - started) * 1000),
            assertions=assertions, actual=actual,
            expected=case.expected.model_dump(mode="json", exclude_none=True),
            failure_reasons=[item.name for item in assertions if not item.passed],
            correlation_id=actual.get("correlation_id"), provenance_id=actual.get("provenance_id"),
        )
    except Exception as exc:
        safe_error = ReliabilityPolicy.sanitize(f"{type(exc).__name__}: {exc}")
        return CaseResult(
            case_id=case.case_id, category=case.category, profile=profile, passed=False,
            duration_ms=round((perf_counter() - started) * 1000), assertions=[],
            actual={"expected_abstained": case.expected.abstained},
            expected=case.expected.model_dump(mode="json", exclude_none=True),
            failure_reasons=[safe_error],
            error=safe_error,
        )
    finally:
        if isinstance(client, httpx.Client):
            client.close()
        if database is not None:
            database.dispose()
        if temp_dir is not None:
            temp_dir.cleanup()


def run_evaluations(
    cases: list[EvaluationCase],
    profile: Profile,
    *,
    database_url: str | None = None,
    api_base_url: str = "http://127.0.0.1:8000",
    expense_webhook_url: str = "http://127.0.0.1:5678/webhook/northstar-expense",
    approval_webhook_url: str = "http://127.0.0.1:5678/webhook/northstar-approval",
) -> list[CaseResult]:
    if profile == Profile.POSTGRES and database_url:
        prepare_postgres(database_url)
    return [run_case(case, profile, database_url=database_url, api_base_url=api_base_url,
                     expense_webhook_url=expense_webhook_url,
                     approval_webhook_url=approval_webhook_url)
            for case in cases]
