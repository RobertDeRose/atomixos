#!/usr/bin/env python3
"""Enable this repository's generated GitHub Pages deployment."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from collections.abc import Sequence


PAGES_ENVIRONMENT = "github-pages"
PUBLISH_BRANCH = "main"
CUSTOM_BRANCH_POLICY = {"protected_branches": False, "custom_branch_policies": True}


class EnablementError(RuntimeError):
    """An expected GitHub CLI operation failed."""


class MissingGhError(EnablementError):
    """GitHub CLI is unavailable."""


def run_gh(executable: str, args: Sequence[str], stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run the resolved gh executable without a shell."""
    return subprocess.run([executable, *args], check=False, capture_output=True, input=stdin, text=True)


def gh(
    executable: str, args: Sequence[str], operation: str, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    """Run gh and retain output for explicit error handling."""
    result = run_gh(executable, args, stdin)
    if result.returncode:
        message = f"{operation} failed: {failure_detail(result)}"
        raise EnablementError(message)
    return result


def http_status(result: subprocess.CompletedProcess[str]) -> str | None:
    """Return the HTTP status gh api reports at the end of stderr, if any."""
    status = re.search(r"\(HTTP (\d{3})\)\s*$", result.stderr)
    return status.group(1) if status else None


def failure_detail(result: subprocess.CompletedProcess[str]) -> str:
    """Describe a failed gh invocation from its output."""
    return result.stderr.strip() or result.stdout.strip() or f"gh exited {result.returncode}"


def environment_update(current: dict) -> dict:
    """Restrict deployments to custom branch policies while keeping the other protection rules.

    The environment PUT may reset protection rules it omits, so it resends the current ones.
    """
    body: dict = {"deployment_branch_policy": dict(CUSTOM_BRANCH_POLICY)}
    message = "Pages environment query returned unexpected protection rules"
    try:
        for rule in current.get("protection_rules", []):
            if not isinstance(rule, dict) or not isinstance(rule.get("type"), str) or not rule["type"]:
                raise EnablementError(message)
            if rule.get("type") == "wait_timer":
                if type(rule["wait_timer"]) is not int:
                    raise EnablementError(message)
                body["wait_timer"] = rule["wait_timer"]
            elif rule.get("type") == "required_reviewers":
                body["prevent_self_review"] = rule.get("prevent_self_review", False)
                reviewers = rule["reviewers"]
                if not isinstance(body["prevent_self_review"], bool) or not isinstance(reviewers, list):
                    raise EnablementError(message)
                body["reviewers"] = []
                for reviewer in reviewers:
                    kind, identifier = reviewer["type"], reviewer["reviewer"]["id"]
                    if kind not in {"User", "Team"} or type(identifier) is not int:
                        raise EnablementError(message)
                    body["reviewers"].append({"type": kind, "id": identifier})
    except (AttributeError, KeyError, TypeError) as error:
        raise EnablementError(message) from error
    return body


def parse_environment(output: str) -> dict:
    """Validate the environment settings needed before changing its deployment mode."""
    try:
        current = json.loads(output)
    except json.JSONDecodeError as error:
        message = "Pages environment query returned invalid JSON"
        raise EnablementError(message) from error
    if not isinstance(current, dict) or not {"deployment_branch_policy", "protection_rules"} <= current.keys():
        message = "Pages environment query returned an unexpected response shape"
        raise EnablementError(message)
    policy = current["deployment_branch_policy"]
    if policy is not None and (
        not isinstance(policy, dict) or any(not isinstance(policy.get(key), bool) for key in CUSTOM_BRANCH_POLICY)
    ):
        message = "Pages environment query returned an unexpected deployment branch policy"
        raise EnablementError(message)
    if not isinstance(current["protection_rules"], list):
        message = "Pages environment query returned unexpected protection rules"
        raise EnablementError(message)
    return current


def allow_publish_branch(executable: str, environment: str, current: dict) -> list[list[str]]:
    """Ensure the publish policy exists, restoring the prior mode if setup fails."""
    update = environment_update(current)
    changed = current.get("deployment_branch_policy") != CUSTOM_BRANCH_POLICY
    policies = f"{environment}/deployment-branch-policies"
    try:
        # The policy endpoints require selected-branch mode, so this PUT must come first.
        if changed:
            gh(
                executable,
                ["api", "--method", "PUT", environment, "--input", "-"],
                "Pages environment update",
                json.dumps(update),
            )
        existing = gh(
            executable,
            ["api", "--paginate", policies, "--jq", '.branch_policies[] | [.id, .type // "branch", .name] | @tsv'],
            "Pages environment policy query",
        ).stdout.splitlines()
        rows = [line.split("\t") for line in existing if line]
        if any(len(row) != 3 or not row[0].isdigit() or row[1] not in {"branch", "tag"} or not row[2] for row in rows):
            message = "Pages environment policy query returned unexpected policy data"
            raise EnablementError(message)
        if not any(policy_type == "branch" and name == PUBLISH_BRANCH for _, policy_type, name in rows):
            gh(
                executable,
                ["api", "--method", "POST", policies, "-f", f"name={PUBLISH_BRANCH}", "-f", "type=branch"],
                "Pages policy creation",
            )
    except EnablementError as error:
        if not changed:
            raise
        previous = current.get("deployment_branch_policy")
        update["deployment_branch_policy"] = previous
        try:
            gh(
                executable,
                ["api", "--method", "PUT", environment, "--input", "-"],
                "Pages environment rollback",
                json.dumps(update),
            )
        except EnablementError as rollback_error:
            message = f"{error}; {rollback_error}; previous deployment branch policy: {json.dumps(previous)}"
            raise EnablementError(message) from rollback_error
        message = f"{error}; previous deployment branch settings restored"
        raise EnablementError(message) from error
    return rows


def enable() -> str:
    """Configure workflow-built Pages from main, enable the workflow gate, and return its URL."""
    executable = shutil.which("gh")
    if executable is None:
        message = "GitHub CLI (gh) is not installed or is not on PATH"
        raise MissingGhError(message)

    gh(executable, ["auth", "status"], "GitHub authentication check")
    repository = gh(
        executable,
        ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        "GitHub repository resolution",
    ).stdout.strip()
    if not repository:
        message = "GitHub repository resolution returned no owner/name"
        raise EnablementError(message)

    endpoint = f"repos/{repository}/pages"
    current = run_gh(executable, ["api", endpoint])
    if current.returncode == 0:
        gh(executable, ["api", "--method", "PUT", endpoint, "-f", "build_type=workflow"], "Pages update")
    elif http_status(current) == "404":
        gh(executable, ["api", "--method", "POST", endpoint, "-f", "build_type=workflow"], "Pages creation")
    else:
        message = f"Pages query failed: {failure_detail(current)}"
        raise EnablementError(message)

    # GitHub creates github-pages allowing only the default branch (dev); the site publishes from main.
    environment = f"repos/{repository}/environments/{PAGES_ENVIRONMENT}"
    queried = run_gh(executable, ["api", environment])
    if queried.returncode == 0:
        current_environment = parse_environment(queried.stdout)
    elif http_status(queried) == "404":
        # The PUT below creates a missing environment.
        current_environment = {}
    else:
        message = f"Pages environment query failed: {failure_detail(queried)}"
        raise EnablementError(message)
    rows = allow_publish_branch(executable, environment, current_environment)
    policies = f"{environment}/deployment-branch-policies"
    # Main is now allowed; a failed removal must not undo that or roll back the environment.
    for policy_id, policy_type, name in rows:
        if policy_type != "branch" or name != PUBLISH_BRANCH:
            gh(executable, ["api", "--method", "DELETE", f"{policies}/{policy_id}"], "Pages policy removal")

    gh(
        executable,
        ["variable", "set", "DOCS_DEPLOYMENT_ENABLED", "--body", "true", "--repo", repository],
        "deployment variable update",
    )
    url = gh(executable, ["api", endpoint, "--jq", ".html_url"], "Pages URL query").stdout.strip()
    if not url:
        message = "Pages URL query returned no html_url"
        raise EnablementError(message)
    return url


def main() -> int:
    try:
        url = enable()
    except EnablementError as error:
        print(f"error: {error}", file=sys.stderr)
        if isinstance(error, MissingGhError):
            print("Install GitHub CLI: https://cli.github.com/", file=sys.stderr)
        policies = f"repos/OWNER/REPO/environments/{PAGES_ENVIRONMENT}/deployment-branch-policies"
        recovery = (
            "Manual recovery:",
            "  gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow",
            "  # Use POST instead of PUT when Pages does not exist.",
            f"  # In Settings > Environments > {PAGES_ENVIRONMENT}, choose Selected branches and tags,",
            "  # keeping any required reviewers and wait timer. Then add main by API:",
            f"  gh api --method POST {policies} -f name={PUBLISH_BRANCH} -f type=branch",
            f"  # Then delete every other policy listed by: gh api {policies}",
            f"  gh api --method DELETE {policies}/POLICY_ID",
            "  gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO",
        )
        print("\n".join(recovery), file=sys.stderr)
        return 1

    print(f"GitHub Pages deployment enabled: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
