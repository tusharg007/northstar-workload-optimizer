"""Regression checks for current stack readiness contracts."""

import pytest

from scripts.verify_stack import expected_alembic_head, validate_api_health


def test_health_accepts_additive_fields():
    validate_api_health({
        "status": "ok", "service": "northstar", "database": "connected",
        "version": "future-metadata",
    })


@pytest.mark.parametrize("changes", [
    {"status": "error"}, {"service": "other"},
    {"database": "disconnected"}, {"database": None},
])
def test_health_rejects_unhealthy_dependencies(changes):
    health = {"status": "ok", "service": "northstar", "database": "connected"}
    with pytest.raises(RuntimeError, match="unexpected API health"):
        validate_api_health(health | changes)


def test_expected_revision_includes_analytics_migration():
    assert expected_alembic_head() == "b83f04a51468"
