"""Secret-minimized JSON and console reporting for evaluation runs."""

from __future__ import annotations

import json
from pathlib import Path

from evals.models import EvaluationReport


def write_report(report: EvaluationReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def console_summary(report: EvaluationReport) -> str:
    status = "PASS" if report.passed else "FAIL"
    lines = [
        f"Gate 5 {report.profile.value.upper()} evaluation: {status}",
        f"Cases: {report.passed_count}/{report.case_count} passed",
    ]
    for name, metric in sorted(report.metrics.items()):
        marker = "PASS" if metric.meets_threshold else "FAIL"
        lines.append(
            f"  [{marker}] {name}: {metric.passed}/{metric.denominator} ({metric.rate:.3f}; {metric.comparison} {metric.threshold:.3f})"
        )
    if report.baseline_errors:
        lines.append("Baseline errors:")
        lines.extend(f"  - {item}" for item in report.baseline_errors)
    failures = [item for item in report.cases if not item.passed]
    if failures:
        lines.append("Failed cases:")
        for item in failures:
            detail = item.error or "; ".join(
                f"{a.name}: expected={a.expected!r}, actual={a.actual!r}"
                for a in item.assertions if not a.passed
            )
            lines.append(f"  - {item.case_id}: {detail}")
    return "\n".join(lines)
