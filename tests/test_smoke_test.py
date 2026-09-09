"""Contract checks for clear end-to-end smoke-test failures."""

from __future__ import annotations

from unittest.mock import Mock

from scripts import smoke_test


def test_smoke_test_fails_clearly_when_n8n_is_unavailable(
    monkeypatch, capsys
) -> None:
    health = Mock()
    health.json.return_value = {"status": "ok", "service": "northstar", "database": "connected"}

    def fake_request(client, method, url, **kwargs):
        if url.endswith("/health"):
            return health
        raise RuntimeError(f"Cannot connect to {url}. Is the service running?")

    monkeypatch.setattr(smoke_test, "request", fake_request)
    assert smoke_test.main() == 1
    error = capsys.readouterr().err
    assert "NORTH STAR END-TO-END DEMO: FAIL" in error
    assert "northstar-expense" in error
    assert "Is the service running?" in error
