"""Advisory provider failures must be explicit and context must be authoritative."""

import json
from unittest.mock import Mock

import httpx
import pytest
from fastapi import HTTPException

from app.policy_copilot import AdvisoryGenerationRequest, answer_policy_question, generate_advisory_text


@pytest.fixture
def context():
    ctx = Mock()
    ctx.list_policies.return_value = [{"policy_key": "EXPENSE_APPROVAL_ROUTING"}]
    ctx.resolve_policy.return_value = {
        "policy_key": "EXPENSE_APPROVAL_ROUTING", "policy_name": "Approval Routing",
        "version_number": 2, "trust": {"state": "TRUSTED"},
        "rules": [{"rule_key": "AMOUNT_APPROVAL_TIERS", "parameters": {"maximum_amount": 2000, "role": "Department Head"}}],
    }
    ctx.list_terms.return_value = []
    return ctx


def provider(monkeypatch, handler):
    monkeypatch.setenv("GROQ_API_KEY", "test-only-key")
    client_class = httpx.Client
    monkeypatch.setattr("app.policy_copilot.httpx.Client", lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs))


def test_missing_key_fails_before_provider_or_context(monkeypatch, context):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Who reviews travel?", context)
    assert error.value.status_code == 503
    assert "not configured" in error.value.detail
    context.list_policies.assert_not_called()


@pytest.mark.parametrize("base", ["https://provider.test", "https://provider.test/v1/", "https://provider.test/"])
def test_answer_uses_resolved_rules_and_normalized_url(monkeypatch, context, base):
    def handle(request):
        assert str(request.url) == "https://provider.test/v1/chat/completions"
        request_body = json.loads(request.content)
        assert request_body["model"] == "openai/gpt-oss-20b"
        evidence = json.loads(request_body["messages"][1]["content"])
        assert evidence["policies"][0]["version_number"] == 2
        assert evidence["policies"][0]["rules"][0]["parameters"]["role"] == "Department Head"
        return httpx.Response(200, json={"choices": [{"message": {"content": " Department Head; Approval Routing v2. "}}]})
    provider(monkeypatch, handle)
    monkeypatch.setenv("GROQ_API_BASE", base)
    assert answer_policy_question("Who reviews $640 travel?", context)["answer"] == "Department Head; Approval Routing v2."


def test_generic_advisory_generation_uses_same_groq_adapter(monkeypatch):
    def handle(request):
        body = json.loads(request.content)
        assert body["messages"] == [
            {"role": "system", "content": "Summarize safely."},
            {"role": "user", "content": "Expense evidence"},
        ]
        return httpx.Response(200, json={"choices": [{"message": {"content": "Safe summary"}}]})

    provider(monkeypatch, handle)
    result = generate_advisory_text(
        AdvisoryGenerationRequest(
            system_prompt="Summarize safely.", prompt="Expense evidence", max_tokens=200
        )
    )
    assert result == {"text": "Safe summary"}


@pytest.mark.parametrize("state", ["STALE", "MISSING", "CONFLICTED"])
def test_untrusted_context_never_calls_model(monkeypatch, context, state):
    provider(monkeypatch, lambda request: pytest.fail("Model must not run"))
    context.resolve_policy.return_value["trust"]["state"] = state
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Who reviews travel?", context)
    assert error.value.status_code == 409


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_provider_errors_are_safe(monkeypatch, context, status):
    provider(monkeypatch, lambda request: httpx.Response(status, text="secret provider diagnostics"))
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Who reviews travel?", context)
    assert error.value.status_code == 502
    assert "secret" not in error.value.detail


@pytest.mark.parametrize("body", [{}, {"choices": []}, {"choices": [{"message": {"content": " "}}]}])
def test_empty_model_output_is_not_success(monkeypatch, context, body):
    provider(monkeypatch, lambda request: httpx.Response(200, json=body))
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Who reviews travel?", context)
    assert error.value.status_code == 502


def test_provider_timeout_is_bounded_and_clear(monkeypatch, context):
    def timeout(request):
        raise httpx.ReadTimeout("sensitive diagnostic", request=request)
    provider(monkeypatch, timeout)
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Who reviews travel?", context)
    assert error.value.status_code == 504
    assert "timed out" in error.value.detail


def test_truncated_answer_is_not_presented_as_complete(monkeypatch, context):
    provider(monkeypatch, lambda request: httpx.Response(200, json={
        "choices": [{"finish_reason": "length", "message": {"content": "Half an audit"}}]
    }))
    with pytest.raises(HTTPException) as error:
        answer_policy_question("Summarize the policy", context)
    assert error.value.status_code == 502
    assert "response limit" in error.value.detail
