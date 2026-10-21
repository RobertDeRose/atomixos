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
    if "can_admins_bypass" in current:
        body["can_admins_bypass"] = current["can_admins_bypass"]
    message = "Pages environment query returned unexpected protection rules"
    try:
        for rule in current.get("protection_rules", []):
            kind = rule.get("type") if isinstance(rule, dict) else None
            if not isinstance(kind, str) or not kind:
                raise EnablementError(message)
            if kind == "wait_timer":
                if type(rule["wait_timer"]) is not int:
                    raise EnablementError(message)
                body["wait_timer"] = rule["wait_timer"]
            elif kind == "required_reviewers":
                prevent_self_review, reviewers = rule.get("prevent_self_review", False), rule["reviewers"]
                if not isinstance(prevent_self_review, bool) or not isinstance(reviewers, list):
                    raise EnablementError(message)
                body["prevent_self_review"] = prevent_self_review
                body["reviewers"] = []
                for reviewer in reviewers:
                    reviewer_type, identifier = reviewer["type"], reviewer["reviewer"]["id"]
                    if reviewer_type not in {"User", "Team"} or type(identifier) is not int:
                        raise EnablementError(message)
                    body["reviewers"].append({"type": reviewer_type, "id": identifier})
    except (AttributeError, KeyError, TypeError) as error:
        raise EnablementError(message) from error
    return body


def parse_build_type(output: str) -> str:
    """Return the Pages site's build type."""
    try:
        site = json.loads(output)
    except json.JSONDecodeError as error:
        message = "Pages query returned invalid JSON"
        raise EnablementError(message) from error
    if not isinstance(site, dict) or not isinstance(site.get("build_type"), str):
        message = "Pages query returned an unexpected build type"
        raise EnablementError(message)
    return site["build_type"]


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
    if not isinstance(current.get("can_admins_bypass", False), bool):
        message = "Pages environment query returned an unexpected administrator bypass setting"
        raise EnablementError(message)
    return current


def query_optional(executable: str, endpoint: str, operation: str) -> str | None:
    """Return a gh api GET response, or None when the resource does not exist."""
    result = run_gh(executable, ["api", endpoint])
    if result.returncode == 0:
        return result.stdout
    if http_status(result) == "404":
        return None
    message = f"{operation} failed: {failure_detail(result)}"
    raise EnablementError(message)


def put_environment(executable: str, environment: str, body: dict, operation: str) -> None:
    """Create or update the environment with the given settings."""
    gh(executable, ["api", "--method", "PUT", environment, "--input", "-"], operation, json.dumps(body))


def allow_publish_branch(executable: str, environment: str, policies: str, current: dict) -> list[list[str]]:
    """Ensure the publish policy exists, restoring the prior mode if setup fails."""
    update = environment_update(current)
    changed = current.get("deployment_branch_policy") != CUSTOM_BRANCH_POLICY
    # The policy endpoints require selected-branch mode, so this PUT must come first. A failed PUT changed
    # nothing, so it needs no rollback.
    if changed:
        put_environment(executable, environment, update, "Pages environment update")
    try:
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
        if not current:
            # Restoring a new environment's default mode would allow every branch; selected-branch mode with no
            # policies blocks every deployment until a rerun allows main.
            message = f"{error}; new environment allows no deployment branches until setup is rerun"
            raise EnablementError(message) from error
        previous = current.get("deployment_branch_policy")
        update["deployment_branch_policy"] = previous
        try:
            put_environment(executable, environment, update, "Pages environment rollback")
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
    site = query_optional(executable, endpoint, "Pages query")
    if site is None:
        gh(executable, ["api", "--method", "POST", endpoint, "-f", "build_type=workflow"], "Pages creation")
    elif parse_build_type(site) != "workflow":
        gh(executable, ["api", "--method", "PUT", endpoint, "-f", "build_type=workflow"], "Pages update")

    # GitHub creates github-pages allowing only the default branch (dev); the site publishes from main.
    environment = f"repos/{repository}/environments/{PAGES_ENVIRONMENT}"
    queried = query_optional(executable, environment, "Pages environment query")
    # The environment PUT creates a missing environment.
    current_environment = {} if queried is None else parse_environment(queried)
    policies = f"{environment}/deployment-branch-policies"
    rows = allow_publish_branch(executable, environment, policies, current_environment)
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
