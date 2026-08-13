"""HTTP-only adapter from MCP to existing North Star application boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
import os
from typing import Any
from uuid import uuid4

import httpx

from mcp_server.errors import NorthStarMCPError, invalid

UTC = timezone.utc
DEFAULT_TIMEOUT_SECONDS = 10.0
MAX_LIMIT = 100


def _parse_time(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        point = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise invalid("as_of must be an ISO-8601 timestamp") from exc
    if point.tzinfo is None:
        raise invalid("as_of must include a timezone offset")
    return point.astimezone(UTC)


def _bounded(limit: int) -> int:
    if not 1 <= limit <= MAX_LIMIT:
        raise invalid(f"limit must be between 1 and {MAX_LIMIT}")
    return limit


def _owner(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "owner_key": value.get("owner_key"),
        "display_name": value.get("display_name"),
        "domain": value.get("domain"),
        "active": value.get("active"),
    }


def _trust(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": value.get("state"),
        "reasons": list(value.get("reasons") or []),
        "signals": [
            {
                "signal_type": item.get("signal_type"),
                "status": item.get("status"),
                "score": item.get("score"),
                "observed_at": item.get("observed_at"),
                "expires_at": item.get("expires_at"),
            }
            for item in value.get("signals") or []
        ],
    }


def _rule(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "rule_key": value.get("rule_key"),
        "rule_name": value.get("rule_name"),
        "rule_type": value.get("rule_type"),
        "description": value.get("description"),
        "parameters": value.get("parameters") or {},
        "severity": value.get("severity"),
        "business_term_key": value.get("business_term_key"),
    }


def _state(value: dict[str, Any]) -> dict[str, Any]:
    """Minimize the historical public expense payload for MCP clients."""
    return {
        key: value.get(key)
        for key in (
            "expense_id", "status", "risk_level", "approver_role", "decision",
            "decided_at", "created_at", "updated_at", "anomaly_flags", "message",
            "correlation_id",
        )
        if value.get(key) is not None
    }


class NorthStarAdapter:
    """Normalize transport errors and expose only minimized application results."""

    def __init__(self) -> None:
        self.api_base_url = os.getenv("NORTHSTAR_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
        self.expense_webhook_url = os.getenv(
            "N8N_EXPENSE_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/northstar-expense"
        )
        self.approval_webhook_url = os.getenv(
            "N8N_APPROVAL_WEBHOOK_URL", "http://127.0.0.1:5678/webhook/northstar-approval"
        )
        self.timeout = float(os.getenv("NORTHSTAR_MCP_HTTP_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        try:
            response = httpx.request(method, url, timeout=self.timeout, **kwargs)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            raise NorthStarMCPError("UPSTREAM_UNAVAILABLE", "North Star service is unavailable") from exc
        except httpx.HTTPError as exc:
            raise NorthStarMCPError("UPSTREAM_UNAVAILABLE", "North Star request failed safely") from exc
        if response.is_success:
            try:
                body = response.json()
            except ValueError as exc:
                raise NorthStarMCPError("UPSTREAM_UNAVAILABLE", "North Star returned an invalid response") from exc
            correlation = response.headers.get("X-Correlation-ID")
            if correlation and isinstance(body, dict) and "correlation_id" not in body:
                body = {**body, "correlation_id": correlation}
            return body
        detail: Any
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        correlation = response.headers.get("X-Correlation-ID")
        if response.status_code == 404:
            raise NorthStarMCPError("NOT_FOUND", str(detail or "North Star record was not found"))
        if response.status_code == 422:
            raise NorthStarMCPError("INVALID_INPUT", "North Star rejected invalid input")
        if response.status_code == 409 and isinstance(detail, dict) and detail.get("code") == "CONTEXT_NOT_AUTHORITATIVE":
            raise NorthStarMCPError(
                "CONTEXT_NOT_AUTHORITATIVE", str(detail.get("reason") or "Governed context is not authoritative"),
                str(detail.get("reason_code") or "UNKNOWN"), str(detail.get("correlation_id") or correlation or "") or None,
            )
        if response.status_code == 409:
            raise NorthStarMCPError("CONFLICT", str(detail or "North Star rejected a conflicting operation"), correlation_id=correlation)
        raise NorthStarMCPError("UPSTREAM_UNAVAILABLE", f"North Star returned HTTP {response.status_code}")

    def submit_expense(self, payload: dict[str, Any]) -> dict[str, Any]:
        correlation = f"mcp-{uuid4()}"
        value = self.request("POST", self.expense_webhook_url, json=payload, headers={"X-Correlation-ID": correlation})
        return _state({**value, "correlation_id": value.get("correlation_id", correlation)})

    def approve_expense(self, expense_id: str, approver: str, comment: str) -> dict[str, Any]:
        value = self.request("POST", self.approval_webhook_url, json={
            "expense_id": expense_id, "decision": "approve", "approver": approver, "comment": comment,
        })
        return _state(value)

    def expense_status(self, expense_id: str) -> dict[str, Any]:
        return _state(self.request("GET", f"{self.api_base_url}/api/expenses/{expense_id}"))

    def pending_approvals(self, limit: int = 20) -> dict[str, Any]:
        size = _bounded(limit)
        values = self.request("GET", f"{self.api_base_url}/api/expenses")
        items = [_state(item) for item in values if item.get("status") in {"PENDING_APPROVAL", "ESCALATED"}][:size]
        return {"count": len(items), "limit": size, "items": items}

    def explain_risk(self, expense_id: str) -> dict[str, Any]:
        value = self.request("GET", f"{self.api_base_url}/api/expenses/{expense_id}/explanation")
        return {key: value.get(key) for key in (
            "expense_id", "status", "risk_level", "anomaly_flags", "routing_decision",
            "approver", "reason", "provenance_id", "provenance_hash", "evidence_verified",
        )}

    def _resolved_policy(self, policy_key: str, as_of: str | None) -> dict[str, Any]:
        params = {"as_of": _parse_time(as_of).isoformat()} if as_of else None
        return self.request("GET", f"{self.api_base_url}/api/context/policies/{policy_key}/resolve", params=params)

    def policy_version(self, policy_key: str, version: int | None = None, as_of: str | None = None) -> dict[str, Any]:
        if version is not None and version < 1:
            raise invalid("version must be at least 1")
        resolved = self._resolved_policy(policy_key, as_of)
        if version is not None and resolved.get("version_number") != version:
            versions = self.request("GET", f"{self.api_base_url}/api/context/policies/{policy_key}/versions")
            selected = next((item for item in versions if item.get("version_number") == version), None)
            if selected is None:
                raise NorthStarMCPError("NOT_FOUND", "Policy version was not found")
            if as_of:
                raise NorthStarMCPError("CONFLICT", "Requested version is not applicable at as_of")
            resolved = self._resolved_policy(policy_key, selected["effective_from"])
        return {
            "policy_key": resolved.get("policy_key"), "policy_name": resolved.get("policy_name"),
            "domain": resolved.get("domain"), "description": resolved.get("description"),
            "owner": _owner(resolved.get("owner") or {}), "as_of": resolved.get("as_of"),
            "version_number": resolved.get("version_number"), "status": resolved.get("status"),
            "effective_from": resolved.get("effective_from"), "effective_to": resolved.get("effective_to"),
            "review_due_at": resolved.get("review_due_at"), "certified_at": resolved.get("certified_at"),
            "content_hash": resolved.get("content_hash"), "trust": _trust(resolved.get("trust") or {}),
            "rules": [_rule(item) for item in resolved.get("rules") or []],
        }

    def business_term(self, term_key: str, version: int | None = None, as_of: str | None = None) -> dict[str, Any]:
        if version is not None and version < 1:
            raise invalid("version must be at least 1")
        params = {"as_of": _parse_time(as_of).isoformat()} if as_of else None
        resolved = self.request("GET", f"{self.api_base_url}/api/context/terms/{term_key}/resolve", params=params)
        if version is not None and resolved.get("version_number") != version:
            versions = self.request("GET", f"{self.api_base_url}/api/context/terms/{term_key}/versions")
            selected = next((item for item in versions if item.get("version_number") == version), None)
            if selected is None:
                raise NorthStarMCPError("NOT_FOUND", "Business term version was not found")
            if as_of:
                raise NorthStarMCPError("CONFLICT", "Requested version is not applicable at as_of")
            resolved = self.request("GET", f"{self.api_base_url}/api/context/terms/{term_key}/resolve", params={"as_of": selected["effective_from"]})
        return {
            "term_key": resolved.get("term_key"), "canonical_name": resolved.get("canonical_name"),
            "domain": resolved.get("domain"), "definition": resolved.get("definition"),
            "owner": _owner(resolved.get("owner") or {}), "as_of": resolved.get("as_of"),
            "version_number": resolved.get("version_number"), "status": resolved.get("status"),
            "effective_from": resolved.get("effective_from"), "effective_to": resolved.get("effective_to"),
            "review_due_at": resolved.get("review_due_at"), "certified_at": resolved.get("certified_at"),
            "content_hash": resolved.get("content_hash"), "trust": _trust(resolved.get("trust") or {}),
        }

    def search_policy_context(self, query: str, as_of: str | None = None, domain: str | None = None, trust_state: str | None = None, limit: int = 20) -> dict[str, Any]:
        text = query.strip()
        if not text:
            raise invalid("query must not be empty")
        size = _bounded(limit)
        if trust_state and trust_state not in {"TRUSTED", "STALE", "UNVERIFIED", "CONFLICTED", "MISSING"}:
            raise invalid("trust_state is not recognized")
        candidates: list[tuple[int, str, dict[str, Any]]] = []
        needle = text.casefold()
        for kind, path, key_field, name_field in (
            ("policy", "policies", "policy_key", "policy_name"),
            ("business_term", "terms", "term_key", "canonical_name"),
        ):
            for item in self.request("GET", f"{self.api_base_url}/api/context/{path}"):
                if domain and str(item.get("domain", "")).casefold() != domain.casefold():
                    continue
                key, name = str(item.get(key_field, "")), str(item.get(name_field, ""))
                haystack = f"{key} {name} {item.get('description', '')}".casefold()
                if needle not in haystack and not all(token in haystack for token in needle.split()):
                    continue
                rank = 0 if needle == key.casefold() else 1 if needle == name.casefold() else 2 if key.casefold().startswith(needle) else 3
                resolved = self.policy_version(key, as_of=as_of) if kind == "policy" else self.business_term(key, as_of=as_of)
                state = resolved["trust"]["state"]
                if trust_state and state != trust_state:
                    continue
                candidates.append((rank, key, {"kind": kind, "key": key, "name": name, "domain": item.get("domain"), "version_number": resolved.get("version_number"), "trust_state": state}))
        results = [item for _, _, item in sorted(candidates, key=lambda row: (row[0], row[1]))[:size]]
        return {"query": text, "as_of": _parse_time(as_of).isoformat() if as_of else None, "limit": size, "count": len(results), "results": results}

    def expense_context(self, expense_id: str) -> dict[str, Any]:
        value = self.request("GET", f"{self.api_base_url}/api/context/expenses/{expense_id}")
        policies = [self.policy_version(item["policy_key"], as_of=value.get("as_of")) for item in value.get("policies") or []]
        terms = [self.business_term(item["term_key"], as_of=value.get("as_of")) for item in value.get("business_terms") or []]
        signals = [{
            "signal_key": item.get("signal_key"), "canonical_name": item.get("canonical_name"),
            "engine_component": item.get("engine_component"), "deterministic": item.get("deterministic"),
            "category": item.get("category"), "observed_flags": item.get("observed_flags") or [],
        } for item in value.get("risk_signal_definitions") or []]
        return {
            "expense_id": expense_id, "as_of": value.get("as_of"),
            "governed_policy_context": {"policies": policies, "business_terms": terms, "trust_summary": value.get("trust_summary") or {}},
            "algorithmic_risk_signal_context": {"signals": signals},
            "decision_behavior_changed": False,
        }

    def decision_trace(self, expense_id: str | None = None, provenance_id: str | None = None) -> dict[str, Any]:
        if bool(expense_id) == bool(provenance_id):
            raise invalid("provide exactly one of expense_id or provenance_id")
        if provenance_id:
            record = self.request("GET", f"{self.api_base_url}/api/provenance/decisions/{provenance_id}")
            expense_id = record["expense_id"]
        assert expense_id
        raw = self.request("GET", f"{self.api_base_url}/api/provenance/expenses/{expense_id}/trace")
        if raw.get("provenance_status") != "AVAILABLE":
            raise NorthStarMCPError("PROVENANCE_UNAVAILABLE", "Decision provenance is unavailable for this expense")
        verification = self.request("GET", f"{self.api_base_url}/api/provenance/decisions/{raw['provenance_id']}/verify")
        workflow = raw.get("workflow_run") or {}
        task = raw.get("approval_task") or {}
        decision = raw.get("approval_decision") or {}
        return {
            "expense_id": expense_id, "correlation_id": workflow.get("correlation_id"),
            "workflow_run": {key: workflow.get(key) for key in ("id", "status", "started_at", "completed_at")},
            "context": raw.get("context"),
            "policies": [{key: item.get(key) for key in ("policy_key", "policy_name", "version_number", "content_hash", "owner_key", "status", "effective_from", "effective_to", "trust_state")} for item in raw.get("policies") or []],
            "business_terms": [{key: item.get(key) for key in ("term_key", "canonical_name", "definition", "version_number", "content_hash", "owner_key", "trust_state")} for item in raw.get("business_terms") or []],
            "policy_rule_evaluations": [{key: item.get(key) for key in ("rule_key", "rule_name", "rule_type", "severity", "evaluation_status", "triggered")} for item in raw.get("rule_evaluations") or []],
            "risk_signal_evaluations": [{key: item.get(key) for key in ("signal_key", "canonical_name", "engine_component", "triggered")} for item in (raw.get("risk_engine") or {}).get("signals") or []],
            "automated_outcome": raw.get("automated_outcome"),
            "approval_task": {key: task.get(key) for key in ("task_id", "approver_role", "approval_level", "status", "created_at", "due_at", "orchestration_status") if key in task},
            "human_decision": {"decision": decision.get("decision"), "decided_at": decision.get("decided_at")} if decision else None,
            "final_status": raw.get("final_status"), "provenance_id": raw.get("provenance_id"),
            "provenance_hash": raw.get("provenance_hash"), "verification": verification,
        }

    def expense_lineage(self, expense_id: str) -> dict[str, Any]:
        return self.request("GET", f"{self.api_base_url}/api/expenses/{expense_id}/lineage")

    def verify_provenance(self, expense_id: str | None = None, provenance_id: str | None = None) -> dict[str, Any]:
        if bool(expense_id) == bool(provenance_id):
            raise invalid("provide exactly one of expense_id or provenance_id")
        if expense_id:
            record = self.request("GET", f"{self.api_base_url}/api/provenance/expenses/{expense_id}")
            provenance_id = record["provenance_id"]
        else:
            record = self.request("GET", f"{self.api_base_url}/api/provenance/decisions/{provenance_id}")
        result = self.request("GET", f"{self.api_base_url}/api/provenance/decisions/{provenance_id}/verify")
        return {
            "verification_passed": result.get("status") == "PASS", "provenance_id": provenance_id,
            "stored_hash": result.get("stored_hash"), "recomputed_hash": result.get("recomputed_hash"),
            "engine_versions": {"decision": record.get("decision_engine_version"), "risk": record.get("risk_engine_version"), "risk_catalog_hash": record.get("risk_catalog_hash")},
            "evidence_category_counts": {key: len(record.get(key) or []) for key in ("policies", "terms", "rules", "trust", "risk", "human_decisions")},
            "failures": result.get("failures") or [],
        }


adapter = NorthStarAdapter()
