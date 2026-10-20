"""Check Pages setup convergence and failures without changing GitHub settings."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def pages(monkeypatch):
    script = Path(__file__).resolve().parents[1] / "scripts" / "enable-docs-deployment.py"
    spec = importlib.util.spec_from_file_location("enable_docs_deployment", script)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    state = SimpleNamespace(
        exists=True,
        policies=[],
        enabled=False,
        fail=None,
        next_id=100,
        environment=None,
        rules=[],
        environment_exists=True,
        branch_policy=None,
        puts=0,
    )
    endpoint = "repos/example/project/pages"
    policies = "repos/example/project/environments/github-pages/deployment-branch-policies"

    def run_gh(executable, args, stdin=None):
        def result(stdout="", error=""):
            return subprocess.CompletedProcess(args, bool(error), stdout=stdout, stderr=error)

        if args[:2] == ["repo", "view"]:
            return result("example/project\n")
        if args[:2] == ["auth", "status"]:
            return result()
        if args[:2] == ["variable", "set"]:
            state.enabled = True
            return result()
        target = next(arg for arg in args if arg.startswith("repos/"))
        method = args[args.index("--method") + 1] if "--method" in args else "GET"
        if target == endpoint:
            if method == "GET":
                return result("https://example.github.io/project/\n") if state.exists else result(error="(HTTP 404)")
            if not state.exists:
                state.policies = [{"id": 1, "type": "branch", "name": "dev"}]
            state.exists = True
            return result()
        if target.endswith("/environments/github-pages") and method == "GET":
            if state.fail == "environment query":
                return result(error="environment query refused")
            if not state.environment_exists:
                return result(error="gh: Not Found (HTTP 404)")
            environment = {"protection_rules": state.rules, "deployment_branch_policy": state.branch_policy}
            return result(json.dumps(environment))
        if target.endswith("/environments/github-pages") and method == "PUT":
            if state.fail == "environment":
                return result(error="environment update refused")
            state.environment = json.loads(stdin)
            state.environment_exists = True
            state.branch_policy = state.environment["deployment_branch_policy"]
            state.puts += 1
            return result()
        if target == policies and method == "GET":
            if state.fail == "query":
                return result(error="policy query refused")
            return result("\n".join(f"{p['id']}\t{p['type']}\t{p['name']}" for p in state.policies))
        if target.startswith(policies + "/") and method == "DELETE":
            if state.fail == "remove":
                return result(error="policy deletion refused")
            policy_id = int(target.rsplit("/", 1)[1])
            state.policies = [p for p in state.policies if p["id"] != policy_id]
            return result()
        if target == policies and method == "POST":
            if state.fail == "create":
                return result(error="policy creation refused")
            values = dict(arg.split("=", 1) for arg in args if "=" in arg)
            state.policies.append({"id": state.next_id, "type": values["type"], "name": values["name"]})
            state.next_id += 1
            return result()
        pytest.fail(f"Unexpected GitHub request: {args}")

    monkeypatch.setattr(module.shutil, "which", lambda _name: "/fake/gh")
    monkeypatch.setattr(module, "run_gh", run_gh)
    return module, state


@pytest.mark.parametrize(
    ("exists", "initial"),
    [
        (False, []),
        (True, [(1, "branch", "dev")]),
        (True, [(7, "branch", "main")]),
        (True, [(7, "branch", "main"), (1, "branch", "dev"), (2, "tag", "main"), (3, "branch", "*")]),
    ],
)
def test_setup_allows_only_main_and_rerun_preserves_policy(pages, exists, initial):
    module, state = pages
    state.exists = exists
    state.policies = [{"id": policy_id, "type": policy_type, "name": name} for policy_id, policy_type, name in initial]
    assert module.enable() == "https://example.github.io/project/"
    assert state.enabled
    assert [(p["type"], p["name"]) for p in state.policies] == [("branch", "main")]
    assert state.environment == {
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}
    }
    if any(p[2] == "main" and p[1] == "branch" for p in initial):
        assert state.policies[0]["id"] == 7
    first_policy = state.policies[0].copy()
    module.enable()
    assert state.policies == [first_policy]


@pytest.mark.parametrize("failure", ["environment query", "environment", "query", "remove", "create"])
def test_policy_failure_does_not_enable_publication(pages, failure):
    module, state = pages
    state.policies = [{"id": 1, "type": "branch", "name": "dev"}]
    state.fail = failure
    with pytest.raises(module.EnablementError, match="Pages"):
        module.enable()
    assert not state.enabled


def test_environment_update_keeps_other_protection_rules(pages):
    module, state = pages
    state.rules = [
        {"id": 1, "type": "wait_timer", "wait_timer": 30},
        {
            "id": 2,
            "type": "required_reviewers",
            "prevent_self_review": True,
            "reviewers": [{"type": "User", "reviewer": {"id": 42, "login": "octocat"}}],
        },
        {"id": 3, "type": "branch_policy"},
    ]
    module.enable()
    assert state.environment == {
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True},
        "wait_timer": 30,
        "prevent_self_review": True,
        "reviewers": [{"type": "User", "id": 42}],
    }


def test_setup_creates_a_missing_environment(pages):
    module, state = pages
    state.environment_exists = False
    assert module.enable() == "https://example.github.io/project/"
    assert state.environment == {
        "deployment_branch_policy": {"protected_branches": False, "custom_branch_policies": True}
    }
    assert [(p["type"], p["name"]) for p in state.policies] == [("branch", "main")]


def test_rerun_leaves_a_converged_environment_untouched(pages):
    module, state = pages
    module.enable()
    module.enable()
    assert state.puts == 1
