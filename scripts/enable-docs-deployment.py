#!/usr/bin/env python3
"""Enable this repository's generated GitHub Pages deployment."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from collections.abc import Sequence


PAGES_ENVIRONMENT = "github-pages"
PUBLISH_BRANCH = "main"


class EnablementError(RuntimeError):
    """An expected GitHub CLI operation failed."""


class MissingGhError(EnablementError):
    """GitHub CLI is unavailable."""


def run_gh(executable: str, args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    """Run the resolved gh executable without a shell."""
    return subprocess.run([executable, *args], check=False, capture_output=True, text=True)


def gh(executable: str, args: Sequence[str], operation: str) -> subprocess.CompletedProcess[str]:
    """Run gh and retain output for explicit error handling."""
    result = run_gh(executable, args)
    if result.returncode:
        detail = result.stderr.strip() or result.stdout.strip() or f"gh exited {result.returncode}"
        message = f"{operation} failed: {detail}"
        raise EnablementError(message)
    return result


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
    elif (status := re.search(r"\(HTTP (\d{3})\)\s*$", current.stderr)) and status.group(1) == "404":
        gh(executable, ["api", "--method", "POST", endpoint, "-f", "build_type=workflow"], "Pages creation")
    else:
        detail = current.stderr.strip() or current.stdout.strip() or f"gh exited {current.returncode}"
        message = f"Pages query failed: {detail}"
        raise EnablementError(message)

    # GitHub creates github-pages allowing only the default branch (dev); the site publishes from main.
    environment = f"repos/{repository}/environments/{PAGES_ENVIRONMENT}"
    gh(
        executable,
        [
            "api",
            "--method",
            "PUT",
            environment,
            "-F",
            "deployment_branch_policy[protected_branches]=false",
            "-F",
            "deployment_branch_policy[custom_branch_policies]=true",
        ],
        "Pages environment update",
    )
    policies = f"{environment}/deployment-branch-policies"
    existing = gh(
        executable,
        ["api", "--paginate", policies, "--jq", '.branch_policies[] | [.id, .type // "branch", .name] | @tsv'],
        "Pages environment policy query",
    ).stdout.splitlines()
    rows = [line.split("\t") for line in existing if line]
    # Allow main before removing anything, so a failure never leaves the environment with no deployable branch.
    if not any(policy_type == "branch" and name == PUBLISH_BRANCH for _, policy_type, name in rows):
        gh(
            executable,
            ["api", "--method", "POST", policies, "-f", f"name={PUBLISH_BRANCH}", "-f", "type=branch"],
            "Pages policy creation",
        )
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
        print("Manual recovery:", file=sys.stderr)
        print("  gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow", file=sys.stderr)
        print("  # Use POST instead of PUT when Pages does not exist.", file=sys.stderr)
        environment = f"repos/OWNER/REPO/environments/{PAGES_ENVIRONMENT}"
        print(
            f"  gh api --method PUT {environment}"
            " -F 'deployment_branch_policy[protected_branches]=false'"
            " -F 'deployment_branch_policy[custom_branch_policies]=true'",
            file=sys.stderr,
        )
        print(
            f"  gh api --method POST {environment}/deployment-branch-policies -f name={PUBLISH_BRANCH} -f type=branch",
            file=sys.stderr,
        )
        print(
            f"  # Then delete every other policy listed by: gh api {environment}/deployment-branch-policies",
            file=sys.stderr,
        )
        print(
            f"  gh api --method DELETE {environment}/deployment-branch-policies/POLICY_ID",
            file=sys.stderr,
        )
        print(
            "  gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO",
            file=sys.stderr,
        )
        return 1

    print(f"GitHub Pages deployment enabled: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
