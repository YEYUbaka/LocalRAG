"""CI policy tests: the quality-gates workflow must exist and be least-privilege."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "quality-gates.yml"


def test_workflow_exists():
    assert WORKFLOW_PATH.exists(), "quality-gates.yml workflow must exist"


def test_workflow_least_privilege_permissions():
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    perms = data.get("permissions", {})
    assert perms.get("contents") == "read", "top-level permissions must be contents: read"
    assert "pull_request_target" not in str(data), "pull_request_target is forbidden"


def test_workflow_has_five_required_jobs():
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    jobs = data.get("jobs", {})
    required = {"backend", "frontend", "contracts", "migrations", "security"}
    assert required <= set(jobs), f"missing jobs: {required - set(jobs)}"


def test_workflow_runs_contract_check():
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    text = str(data)
    assert "export_contracts.py" in text and "--check" in text


def test_workflow_runs_secret_scanner():
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert "check_secrets.py" in str(data)


def test_workflow_triggers_on_integration_branch():
    data = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    text = str(data)
    assert "integration/knowledge-quality" in text
