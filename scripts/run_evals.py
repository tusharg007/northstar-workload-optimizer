"""CLI entry point for the Gate 5 deterministic evaluation harness."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import sys

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from evals.loader import cases_for_profile, load_baseline, load_dataset, validate_baseline
from evals.metrics import compute_metrics
from evals.models import EvaluationReport, Profile
from evals.reporting import console_summary, write_report
from evals.runner import run_evaluations
from app.provenance.hashing import risk_catalog_hash
from app.provenance.service import load_risk_catalog
from automation.policy_manifest import DECISION_ENGINE_VERSION, RISK_ENGINE_VERSION
from uuid import uuid4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic Northstar safety evaluations")
    parser.add_argument("--profile", choices=[item.value for item in Profile], default="fast")
    parser.add_argument("--database-url", default=os.getenv("NORTHSTAR_EVAL_POSTGRES_URL"))
    parser.add_argument("--api-base-url", default=os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--expense-webhook-url", default=os.getenv("N8N_EXPENSE_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/northstar-expense"))
    parser.add_argument("--approval-webhook-url", default=os.getenv("N8N_APPROVAL_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/northstar-approval"))
    parser.add_argument("--case-id", action="append", help="Run only the named case (repeatable)")
    parser.add_argument("--report", type=Path, help="Report path (default: evals/reports/<profile>.json)")
    parser.add_argument("--skip-baseline", action="store_true", help="Diagnostic only: skip baseline comparison")
    parser.add_argument("--compare-baseline", action="store_true", help="Explicitly compare the source-controlled baseline (also the default for full runs)")
    parser.add_argument("--negative-control", choices=["wrong-expectation"],
                        help="Test-only derived control; never changes the authored golden dataset")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    profile = Profile(args.profile)
    manifest, all_cases = load_dataset()
    selected = cases_for_profile(all_cases, profile)
    if args.case_id:
        requested = set(args.case_id)
        selected = [case for case in selected if case.case_id in requested]
        missing = requested - {case.case_id for case in selected}
        if missing:
            print(f"Unknown or unavailable case IDs for {profile.value}: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2
    if args.negative_control == "wrong-expectation":
        selected = [case.model_copy(deep=True) for case in selected]
        target = next((case for case in selected if case.expected.approver_role), None)
        if target is None:
            print("Wrong-expectation control needs a case with an expected approver", file=sys.stderr)
            return 2
        target.expected.approver_role = "INTENTIONALLY WRONG APPROVER"
    baseline = load_baseline()
    baseline_errors = [] if args.skip_baseline or args.case_id or args.negative_control else validate_baseline(
        manifest, all_cases, profile
    )
    started = datetime.now(timezone.utc)
    results = run_evaluations(
        selected, profile, database_url=args.database_url, api_base_url=args.api_base_url,
        expense_webhook_url=args.expense_webhook_url,
        approval_webhook_url=args.approval_webhook_url,
    )
    metrics = compute_metrics(results, baseline["metric_thresholds"])
    finished = datetime.now(timezone.utc)
    passed = not baseline_errors and all(case.passed for case in results) and all(
        metric.meets_threshold for metric in metrics.values()
    )
    report = EvaluationReport(
        run_id=str(uuid4()),
        dataset_version=manifest.dataset_version, profile=profile,
        decision_engine_version=DECISION_ENGINE_VERSION,
        risk_engine_version=RISK_ENGINE_VERSION,
        risk_catalog_hash=risk_catalog_hash(load_risk_catalog()),
        started_at=started, finished_at=finished, passed=passed,
        duration_ms=round((finished - started).total_seconds() * 1000),
        case_count=len(results), passed_count=sum(case.passed for case in results),
        failed_count=sum(not case.passed for case in results), metrics=metrics,
        cases=results, baseline_errors=baseline_errors,
        category_summaries={category: {
            "passed": sum(item.passed for item in results if item.category.value == category),
            "total": sum(1 for item in results if item.category.value == category),
        } for category in sorted({item.category.value for item in results})},
        environment={
            "python": platform.python_version(),
            "platform": platform.system(),
            "api_base_url": args.api_base_url if profile == Profile.LIVE else "in-process",
        },
    )
    report_path = args.report or PROJECT_DIR / "evals" / "reports" / f"{report.run_id}.json"
    write_report(report, report_path)
    print(console_summary(report))
    print(f"Report: {report_path}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
