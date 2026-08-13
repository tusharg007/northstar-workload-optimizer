"""Gate 5 tests validate the evaluator itself, not only the product."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

from evals.loader import cases_for_profile, load_dataset, validate_baseline
from evals.metrics import compute_metrics
from evals.models import (
    AssertionResult, CaseResult, Category, EvaluationCase, EvaluationReport, ExpectedOutcome,
    Metric, Profile,
)
from evals.runner import run_case
from evals.reporting import write_report
from automation.policy_manifest import DECISION_ENGINE_VERSION, RISK_ENGINE_VERSION
from app.provenance.hashing import risk_catalog_hash
from app.provenance.service import load_risk_catalog
from scripts import run_evals as eval_cli


def test_v1_dataset_is_strict_complete_and_bounded() -> None:
    manifest, cases = load_dataset()
    assert manifest.dataset_version == "1.0.0"
    assert 24 <= len(cases) <= 40
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.category for case in cases} == set(Category)
    assert len(cases_for_profile(cases, Profile.FAST)) == len(cases)
    assert len(cases_for_profile(cases, Profile.POSTGRES)) == len(cases)
    assert 4 <= len(cases_for_profile(cases, Profile.LIVE)) < len(cases)


def test_dataset_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({
            "case_id": "bad_case", "category": "decision", "description": "long enough",
            "profiles": ["fast"], "payload": {}, "expected": {}, "sql": "DROP TABLE expenses",
        })


def test_dataset_rejects_unknown_scenario() -> None:
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({
            "case_id": "bad_scenario", "category": "decision", "description": "long enough",
            "profiles": ["fast"], "scenario": "arbitrary_sql", "payload": {}, "expected": {},
        })


def test_dataset_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        EvaluationCase.model_validate({
            "case_id": "bad_category", "category": "imaginary", "description": "long enough",
            "profiles": ["fast"], "scenario": "default", "payload": {}, "expected": {},
        })


def test_loader_rejects_duplicate_case_ids(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "v1"
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["case_files"] = ["duplicates.json"]
    manifest["expected_case_count"] = 24
    manifest["minimum_cases"] = 24
    case = {
        "case_id": "duplicate", "category": "decision", "description": "duplicate fixture",
        "profiles": ["fast"], "scenario": "default", "payload": {}, "expected": {},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (tmp_path / "duplicates.json").write_text(json.dumps([case] * 24), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate case IDs"):
        load_dataset(tmp_path)


def test_payload_is_required_for_mutating_scenarios() -> None:
    with pytest.raises(ValidationError, match="requires a payload"):
        EvaluationCase.model_validate({
            "case_id": "missing_payload", "category": "decision", "description": "long enough",
            "profiles": ["fast"], "scenario": "default", "expected": {},
        })


def test_baseline_detects_no_drift() -> None:
    manifest, cases = load_dataset()
    for profile in Profile:
        assert validate_baseline(manifest, cases, profile) == []


def test_baseline_detects_missing_case(tmp_path: Path) -> None:
    manifest, cases = load_dataset()
    baseline = {
        "dataset_version": manifest.dataset_version, "case_count": len(cases) - 1,
        "category_counts": {}, "case_ids": [], "profile_case_counts": {},
        "profile_case_ids": {}, "decision_engine_version": "wrong",
        "risk_engine_version": "wrong", "risk_catalog_hash": "wrong", "policy_manifest": {},
    }
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    errors = validate_baseline(manifest, cases, Profile.FAST, path)
    assert any("case_count" in item for item in errors)
    assert any("decision_engine_version" in item for item in errors)


@pytest.mark.parametrize("field,value,match", [
    ("expected_decision_engine_version", "wrong", "decision engine drift"),
    ("expected_risk_catalog_hash", "0" * 64, "risk catalog drift"),
])
def test_loader_rejects_engine_or_catalog_drift(tmp_path: Path, field: str, value: str, match: str) -> None:
    source = Path(__file__).resolve().parents[1] / "evals" / "datasets" / "v1" / "manifest.json"
    manifest = json.loads(source.read_text(encoding="utf-8"))
    manifest[field] = value
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_dataset(tmp_path)


def test_metrics_include_denominators_and_abstention_confusion_matrix() -> None:
    result = CaseResult(
        case_id="metric", category=Category.CONTEXT_SAFETY, profile=Profile.FAST,
        passed=True, duration_ms=1,
        assertions=[AssertionResult(name="context_resolution", passed=True)],
        actual={"expected_abstained": True, "abstained": True},
    )
    metrics = compute_metrics([result])
    assert metrics["abstention_recall"].denominator == 1
    assert metrics["abstention_precision"].details["confusion_matrix"]["tp"] == 1
    assert metrics["unsafe_action_rate"].details["unsafe_actions"] == 0


def test_metrics_fail_for_unsafe_action() -> None:
    result = CaseResult(
        case_id="unsafe", category=Category.CONTEXT_SAFETY, profile=Profile.FAST,
        passed=False, duration_ms=1,
        assertions=[AssertionResult(name="context_resolution", passed=False)],
        actual={"expected_abstained": True, "abstained": False},
    )
    metrics = compute_metrics([result])
    assert metrics["abstention_recall"].meets_threshold is False
    assert metrics["unsafe_action_rate"].meets_threshold is False
    assert metrics["unsafe_action_rate"].details["unsafe_actions"] == 1


def test_risk_signal_matrix_has_exact_counts() -> None:
    result = CaseResult(
        case_id="signals", category=Category.RISK, profile=Profile.FAST, passed=True,
        duration_ms=1, assertions=[], expected={},
        actual={"expected_abstained": False, "abstained": False,
                "expected_signals": ["A"], "triggered_signals": ["A"],
                "risk_catalog": ["A", "B"]},
    )
    metrics = compute_metrics([result])
    assert metrics["risk_signal.A"].details == {"tp": 1, "tn": 0, "fp": 0, "fn": 0}
    assert metrics["risk_signal.B"].details == {"tp": 0, "tn": 1, "fp": 0, "fn": 0}
    assert metrics["risk_signal_accuracy"].denominator == 2


def test_threshold_pass_and_fail() -> None:
    good = CaseResult(case_id="good", category=Category.DECISION, profile=Profile.FAST,
                      passed=True, duration_ms=1,
                      assertions=[AssertionResult(name="decision", passed=True)],
                      actual={"expected_abstained": False, "abstained": False})
    bad = good.model_copy(deep=True)
    bad.assertions[0].passed = False
    assert compute_metrics([good])["decision_outcome_accuracy"].meets_threshold is True
    assert compute_metrics([bad])["decision_outcome_accuracy"].meets_threshold is False


def test_report_json_serialization(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    report = EvaluationReport(
        run_id="run", dataset_version="1.0.0", profile=Profile.FAST,
        decision_engine_version=DECISION_ENGINE_VERSION,
        risk_engine_version=RISK_ENGINE_VERSION,
        risk_catalog_hash=risk_catalog_hash(load_risk_catalog()),
        started_at=now, finished_at=now, duration_ms=0, passed=True,
        case_count=0, passed_count=0, failed_count=0, metrics={}, cases=[],
        category_summaries={}, environment={"python": "test"},
    )
    path = tmp_path / "report.json"
    write_report(report, path)
    assert json.loads(path.read_text(encoding="utf-8"))["run_id"] == "run"


def test_cli_returns_nonzero_for_unknown_required_case(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["run_evals.py", "--profile", "fast", "--case-id", "missing-case"])
    assert eval_cli.main() == 2


def _case(case_id: str) -> EvaluationCase:
    _, cases = load_dataset()
    return next(case for case in cases if case.case_id == case_id)


def test_wrong_expectation_negative_control_fails() -> None:
    case = _case("decision_department_above_500").model_copy(deep=True)
    case.expected.approver_role = "Wrong Approver"
    result = run_case(case, Profile.FAST)
    assert result.passed is False
    assert any(item.name == "routing" and not item.passed for item in result.assertions)


def test_policy_drift_negative_control_abstains() -> None:
    result = run_case(_case("context_policy_drift_negative_control"), Profile.FAST)
    assert result.passed is True
    assert result.actual["abstained"] is True
    assert result.actual["reason_code"] == "POLICY_ENGINE_MISMATCH"


def test_provenance_corruption_fails_then_restores() -> None:
    result = run_case(_case("provenance_corruption_detected"), Profile.FAST)
    assert result.passed is True
    assert result.actual["provenance_verified"] is False
    assert result.actual["provenance_restored"] is True


@pytest.mark.parametrize("case_id", [
    "risk_no_signals", "risk_all_signals_critical", "idempotency_exact_replay",
    "reliability_transient_resume_recovers", "reliability_dead_letter_replay",
])
def test_representative_fast_cases(case_id: str) -> None:
    result = run_case(_case(case_id), Profile.FAST)
    assert result.passed, result.model_dump(mode="json")
