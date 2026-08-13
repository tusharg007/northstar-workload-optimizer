"""Bind governed policy metadata to deterministic engine configuration."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from automation.policy_manifest import policy_execution_manifest


def _semantic(value: Any) -> Any:
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float, Decimal)):
        number = Decimal(str(value))
        return int(number) if number == number.to_integral_value() else number.normalize().to_eng_string()
    if isinstance(value, dict):
        return {key: _semantic(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_semantic(item) for item in value]
    return value


def bind_policies(resolved_policies: list[dict], manifest: dict | None = None) -> dict:
    """Return a deterministic safety result for every required policy."""
    required = manifest or policy_execution_manifest()
    by_key = {policy["policy_key"]: policy for policy in resolved_policies}
    results = []
    overall = "MATCHED"
    priority = {"MATCHED": 0, "MISSING": 1, "UNTRUSTED": 2, "MISMATCH": 3, "CONFLICTED": 4}
    for policy_key, engine_rules in required.items():
        policy = by_key.get(policy_key)
        if policy is None or policy.get("trust", {}).get("state") == "MISSING":
            state, details = "MISSING", ["REQUIRED_POLICY_MISSING"]
        elif policy.get("trust", {}).get("state") == "CONFLICTED":
            state, details = "CONFLICTED", ["POLICY_CONTEXT_CONFLICTED"]
        elif policy.get("trust", {}).get("state") != "TRUSTED":
            state, details = "UNTRUSTED", [f"POLICY_TRUST_{policy.get('trust', {}).get('state', 'UNKNOWN')}"]
        else:
            governed = {rule["rule_key"]: rule["parameters"] for rule in policy.get("rules", [])}
            missing = sorted(set(engine_rules) - set(governed))
            mismatched = sorted(
                key for key in set(engine_rules) & set(governed)
                if _semantic(engine_rules[key]) != _semantic(governed[key])
            )
            state = "MISSING" if missing else "MISMATCH" if mismatched else "MATCHED"
            details = [*(f"MISSING_RULE:{key}" for key in missing), *(f"PARAMETER_MISMATCH:{key}" for key in mismatched)]
        results.append({"policy_key": policy_key, "state": state, "details": details})
        if priority[state] > priority[overall]:
            overall = state
    return {"state": overall, "policies": results}


def safety_reason(binding_state: str) -> tuple[str, str]:
    mapping = {
        "MISSING": ("POLICY_MISSING", "Required governed policy context is missing."),
        "CONFLICTED": ("POLICY_CONFLICT", "Required governed policy context is conflicted."),
        "UNTRUSTED": ("POLICY_UNTRUSTED", "Required governed policy context is not trusted and current."),
        "MISMATCH": ("POLICY_ENGINE_MISMATCH", "Governed policy parameters do not match the deterministic engine."),
    }
    return mapping[binding_state]
