"""Strict loading and baseline validation for the versioned golden dataset."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from app.provenance.hashing import risk_catalog_hash
from app.provenance.service import load_risk_catalog
from automation.policy_manifest import (
    DECISION_ENGINE_VERSION,
    RISK_ENGINE_VERSION,
    policy_execution_manifest,
)
from evals.models import DatasetManifest, EvaluationCase, Profile


DATASET_ROOT = Path(__file__).resolve().parent / "datasets" / "v1"
BASELINE_PATH = Path(__file__).resolve().parent / "baselines" / "v1.json"


def load_baseline(path: Path = BASELINE_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_dataset(root: Path = DATASET_ROOT) -> tuple[DatasetManifest, list[EvaluationCase]]:
    manifest = DatasetManifest.model_validate_json((root / "manifest.json").read_text(encoding="utf-8"))
    catalog_hash = risk_catalog_hash(load_risk_catalog())
    drift = {
        "decision engine": (manifest.expected_decision_engine_version, DECISION_ENGINE_VERSION),
        "risk engine": (manifest.expected_risk_engine_version, RISK_ENGINE_VERSION),
        "risk catalog": (manifest.expected_risk_catalog_hash, catalog_hash),
    }
    for name, (expected, actual) in drift.items():
        if expected != actual:
            raise ValueError(f"Dataset {name} drift: expected {expected}, actual {actual}")
    cases: list[EvaluationCase] = []
    for name in manifest.case_files:
        raw = json.loads((root / name).read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"Dataset file {name} must contain a JSON array")
        cases.extend(EvaluationCase.model_validate(item) for item in raw)
    ids = [case.case_id for case in cases]
    duplicates = sorted(key for key, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError(f"Duplicate case IDs: {', '.join(duplicates)}")
    if not manifest.minimum_cases <= len(cases) <= manifest.maximum_cases:
        raise ValueError(
            f"Dataset has {len(cases)} cases; expected {manifest.minimum_cases}..{manifest.maximum_cases}"
        )
    if len(cases) != manifest.expected_case_count:
        raise ValueError(
            f"Dataset has {len(cases)} cases; manifest records {manifest.expected_case_count}"
        )
    missing = manifest.required_categories - {case.category for case in cases}
    if missing:
        raise ValueError(f"Dataset missing categories: {', '.join(sorted(missing))}")
    return manifest, cases


def cases_for_profile(cases: list[EvaluationCase], profile: Profile) -> list[EvaluationCase]:
    return [case for case in cases if profile in case.profiles]


def validate_baseline(
    manifest: DatasetManifest,
    cases: list[EvaluationCase],
    profile: Profile,
    baseline_path: Path = BASELINE_PATH,
) -> list[str]:
    baseline = load_baseline(baseline_path)
    errors: list[str] = []
    selected = cases_for_profile(cases, profile)
    categories = Counter(case.category.value for case in cases)
    expected_ids = sorted(case.case_id for case in cases)
    checks = {
        "dataset_version": (baseline.get("dataset_version"), manifest.dataset_version),
        "case_count": (baseline.get("case_count"), len(cases)),
        "category_counts": (baseline.get("category_counts"), dict(sorted(categories.items()))),
        "case_ids": (baseline.get("case_ids"), expected_ids),
        f"profile_case_counts.{profile.value}": (
            baseline.get("profile_case_counts", {}).get(profile.value), len(selected)
        ),
        f"profile_case_ids.{profile.value}": (
            baseline.get("profile_case_ids", {}).get(profile.value),
            sorted(case.case_id for case in selected),
        ),
        "decision_engine_version": (
            baseline.get("decision_engine_version"), DECISION_ENGINE_VERSION
        ),
        "risk_engine_version": (
            baseline.get("risk_engine_version"), RISK_ENGINE_VERSION
        ),
        "risk_catalog_hash": (
            baseline.get("risk_catalog_hash"), risk_catalog_hash(load_risk_catalog())
        ),
        "policy_manifest": (
            baseline.get("policy_manifest"), policy_execution_manifest()
        ),
        "metric_threshold_names": (
            sorted(baseline.get("metric_thresholds", {})), sorted(manifest.metric_names)
        ),
    }
    for name, (stored, actual) in checks.items():
        if stored != actual:
            errors.append(f"Baseline mismatch for {name}: stored={stored!r}, actual={actual!r}")
    return errors
