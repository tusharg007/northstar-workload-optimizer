"""Deterministic metric computation; no model or subjective judge is used."""

from __future__ import annotations

from collections import defaultdict

from evals.models import CaseResult, Metric


DEFAULT_THRESHOLDS = {
    "decision_outcome_accuracy": 1.0,
    "risk_level_accuracy": 1.0,
    "approval_routing_accuracy": 1.0,
    "risk_signal_accuracy": 1.0,
    "policy_binding_accuracy": 1.0,
    "context_resolution_accuracy": 1.0,
    "abstention_recall": 1.0,
    "abstention_precision": 1.0,
    "unsafe_action_rate": 0.0,
    "provenance_completeness": 1.0,
    "provenance_verification_rate": 1.0,
    "idempotency_correctness": 1.0,
    "transient_recovery_rate": 1.0,
    "dead_letter_correctness": 1.0,
    "replay_recovery_rate": 1.0,
    "logical_duplicate_side_effect_rate": 0.0,
}


def _metric(
    numerator: int,
    denominator: int,
    *,
    threshold: float,
    comparison: str = ">=",
    details=None,
) -> Metric:
    rate = numerator / denominator if denominator else (0.0 if comparison == "<=" else 1.0)
    meets = rate >= threshold if comparison == ">=" else rate <= threshold
    return Metric(
        passed=numerator, denominator=denominator, rate=rate, threshold=threshold,
        comparison=comparison, meets_threshold=meets, details=details or {},
    )


def compute_metrics(
    results: list[CaseResult], thresholds: dict[str, float] | None = None
) -> dict[str, Metric]:
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    buckets: dict[str, list[bool]] = defaultdict(list)
    signal_matrix: dict[str, dict[str, int]] = defaultdict(
        lambda: {"tp": 0, "tn": 0, "fp": 0, "fn": 0}
    )
    abstention = {"tp": 0, "tn": 0, "fp": 0, "fn": 0}

    for result in results:
        by_name: dict[str, bool] = {}
        for item in result.assertions:
            by_name[item.name] = by_name.get(item.name, True) and item.passed
        for name in (
            "decision", "risk_level", "routing", "policy_binding", "context_resolution",
            "provenance_completeness", "provenance_verification", "idempotency",
        ):
            if name in by_name:
                buckets[name].append(by_name[name])

        expected_abstention = result.actual.get("expected_abstained")
        actual_abstention = result.actual.get("abstained")
        if expected_abstention is not None and actual_abstention is not None:
            key = "tp" if expected_abstention and actual_abstention else (
                "tn" if not expected_abstention and not actual_abstention else (
                    "fp" if actual_abstention else "fn"
                )
            )
            abstention[key] += 1

        expected_signals = result.actual.get("expected_signals")
        actual_signals = result.actual.get("triggered_signals")
        if expected_signals is not None and actual_signals is not None:
            expected = set(expected_signals)
            actual = set(actual_signals)
            for signal in set(result.actual.get("risk_catalog", [])):
                key = "tp" if signal in expected and signal in actual else (
                    "tn" if signal not in expected and signal not in actual else (
                        "fp" if signal in actual else "fn"
                    )
                )
                signal_matrix[signal][key] += 1

    labels = {
        "decision": "decision_outcome_accuracy",
        "risk_level": "risk_level_accuracy",
        "routing": "approval_routing_accuracy",
        "policy_binding": "policy_binding_accuracy",
        "context_resolution": "context_resolution_accuracy",
        "provenance_completeness": "provenance_completeness",
        "provenance_verification": "provenance_verification_rate",
        "idempotency": "idempotency_correctness",
    }
    metrics: dict[str, Metric] = {}
    for bucket, label in labels.items():
        values = buckets[bucket]
        metrics[label] = _metric(sum(values), len(values), threshold=limits[label])

    tp, tn, fp, fn = (abstention[key] for key in ("tp", "tn", "fp", "fn"))
    metrics["abstention_recall"] = _metric(
        tp, tp + fn, threshold=limits["abstention_recall"], details={"confusion_matrix": abstention}
    )
    metrics["abstention_precision"] = _metric(
        tp, tp + fp, threshold=limits["abstention_precision"], details={"confusion_matrix": abstention}
    )
    metrics["unsafe_action_rate"] = _metric(
        fn, tp + fn, threshold=limits["unsafe_action_rate"], comparison="<=",
        details={"unsafe_actions": fn, "unsafe_opportunities": tp + fn},
    )

    total_correct = 0
    total = 0
    for signal, matrix in sorted(signal_matrix.items()):
        denominator = sum(matrix.values())
        correct = matrix["tp"] + matrix["tn"]
        total_correct += correct
        total += denominator
        metrics[f"risk_signal.{signal}"] = _metric(
            correct, denominator, threshold=limits["risk_signal_accuracy"], details=matrix
        )
    metrics["risk_signal_accuracy"] = _metric(
        total_correct, total, threshold=limits["risk_signal_accuracy"],
        details={"signals": {key: value for key, value in sorted(signal_matrix.items())}},
    )

    reliability = [item for item in results if item.category.value == "reliability"]
    kinds = {
        "transient_recovery_rate": "RECOVERED",
        "dead_letter_correctness": "DEAD_LETTER",
        "replay_recovery_rate": "REPLAYED_AND_DELIVERED",
    }
    for metric_name, outcome in kinds.items():
        applicable = [item for item in reliability if item.expected.get("reliability_outcome") == outcome]
        correct = sum(item.passed for item in applicable)
        metrics[metric_name] = _metric(correct, len(applicable), threshold=limits[metric_name])
    duplicate_opportunities = len(reliability)
    duplicate_side_effects = sum(
        int(item.actual.get("logical_duplicate_side_effects", 0)) for item in reliability
    )
    metrics["logical_duplicate_side_effect_rate"] = _metric(
        duplicate_side_effects, duplicate_opportunities,
        threshold=limits["logical_duplicate_side_effect_rate"], comparison="<=",
        details={"logical_duplicate_side_effects": duplicate_side_effects,
                 "delivery_opportunities": duplicate_opportunities},
    )

    for category in sorted({item.category.value for item in results}):
        applicable = [item for item in results if item.category.value == category]
        metrics[f"category.{category}"] = _metric(
            sum(item.passed for item in applicable), len(applicable), threshold=1.0
        )
    metrics["case_pass_rate"] = _metric(sum(item.passed for item in results), len(results), threshold=1.0)
    return metrics
