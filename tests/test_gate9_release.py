"""Static release-contract checks for Gate 9 assets."""

from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_python_and_dependency_lock_contract() -> None:
    assert read(".python-version").strip() == "3.13.9"
    lock = read("requirements.lock")
    assert "northstar-requirements-sha256:" in lock
    assert "--hash=sha256:" in lock
    assert "python-version 3.13.9" in lock
    assert "--universal" in lock


def test_application_image_is_locked_and_non_root() -> None:
    dockerfile = read("infra/docker/Dockerfile.app")
    assert "python:3.13.9-slim-bookworm" in dockerfile
    assert "ghcr.io/astral-sh/uv:0.12.3" in dockerfile
    assert "--require-hashes requirements.lock" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert "COPY observability ./observability" in dockerfile
    assert not re.search(r"COPY\s+\.\s+", dockerfile)


def test_dockerignore_blocks_host_state_and_secrets() -> None:
    ignored = set(read(".dockerignore").splitlines())
    assert {".git", ".venv", ".tmp", ".env", "*.db", "metabase/.runtime", "tests"} <= ignored


def test_compose_release_boundaries() -> None:
    compose = read("docker-compose.yml")
    metabase_dockerfile = read("infra/docker/Dockerfile.metabase")
    for service in (
        "postgres:", "northstar-migrate:", "northstar-seed-context:", "api:",
        "n8n-bootstrap:", "n8n:", "metabase:", "metabase-bootstrap:",
    ):
        assert service in compose
    assert "postgres:16.14" in compose
    assert "n8nio/n8n:2.22.6" in compose
    assert "dockerfile: infra/docker/Dockerfile.metabase" in compose
    assert "sha256:095503d38b0048c1e7b499509d04ffb7b9999167872199a34bb7b73c5913fb9d" in metabase_dockerfile
    assert "sha256:bd846162f7cdf81e8160917bdff6831733db129a1d38c9c9e872db93f90d489f" in metabase_dockerfile
    assert "COPY --from=java-runtime /opt/java/openjdk /opt/java/openjdk" in metabase_dockerfile
    assert '["CMD", "wget", "-qO-", "http://127.0.0.1:3000/api/health"]' in compose
    assert '"java", "-jar", "/app/metabase.jar", "health-check"' not in compose
    assert "DB_TYPE: postgresdb" in compose
    assert "N8N_LISTEN_ADDRESS: 0.0.0.0" in compose
    assert "N8N_RUNNERS_BROKER_PORT: 5680" in compose
    assert "n8n_app" in compose and "metabase_app" in compose
    assert "127.0.0.1:${NORTHSTAR_API_PORT:-8000}:8000" in compose
    assert "service_completed_successfully" in compose and "service_healthy" in compose


def test_workflow_bootstrap_is_bounded_and_uses_service_dns() -> None:
    bootstrap = read("infra/docker/n8n-bootstrap.sh")
    assert "EXPECTED=10" in bootstrap
    assert "http://api:8000" in bootstrap
    assert "http://notification-sink:9010" in bootstrap
    assert bootstrap.count("northstar") >= 11
    assert "*.sh text eol=lf" in read(".gitattributes")


def test_ci_and_documentation_inventory() -> None:
    ci = read(".github/workflows/ci.yml")
    integration = read(".github/workflows/integration.yml")
    assert "permissions:\n  contents: read" in ci
    assert all(f"{job}:" in ci for job in ("static", "sqlite", "postgresql", "docker"))
    assert "workflow_dispatch:" in integration
    assert (ROOT / "AGENTS.md").is_file()
    assert len(list((ROOT / "docs" / "adr").glob("*.md"))) == 8
    for path in (
        "docs/architecture/FINAL_ARCHITECTURE.md",
        "docs/architecture/G9_REPRODUCIBLE_RELEASE.md",
        "docs/SECURITY_BOUNDARIES.md",
        "docs/DEMO_SCRIPT.md",
    ):
        assert (ROOT / path).is_file()


def test_release_check_supports_source_exports_without_git_metadata() -> None:
    release_check = read("scripts/release_check.py")
    assert 'if (ROOT / ".git").exists()' in release_check
    assert "source export has no Git metadata" in release_check
    assert "pytest-release" in release_check
    assert 'os.environ["TEMP"] = str(release_temp)' in release_check
    assert 'os.environ["TMP"] = str(release_temp)' in release_check
    assert "--basetemp=" in release_check
    assert '"--cached", "--check"' in release_check


def test_windows_wrapper_restores_docker_helper_path() -> None:
    script = read("scripts/stack.ps1")
    assert '"Programs\\DockerDesktop\\resources\\bin"' in script
    assert '$env:Path = "$dockerBin;$env:Path"' in script


def test_stack_verifier_bounds_docker_cli_calls() -> None:
    verifier = read("scripts/verify_stack.py")
    assert "sys.path.insert(0, str(ROOT))" in verifier
    assert "timeout=60" in verifier
    assert "except subprocess.TimeoutExpired" in verifier
