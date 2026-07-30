# GitHub Pages deployment

Documentation deployment is generated but disabled by default. Local documentation commands and pull-request validation
do not require GitHub Pages.

## Enable deployment

Install GitHub CLI separately, authenticate an identity with repository administration access, and run from a clone
whose GitHub repository can be resolved:

```bash
gh auth login
mise run docs:deployment:enable
```

The task checks `gh`, authentication, and repository resolution. It creates or updates Pages with the GitHub Actions
build type, then sets `DOCS_DEPLOYMENT_ENABLED=true` as the last mutation and prints the Pages URL. Repeating the task
updates the same configuration safely.

Deployment requires both Pages `build_type=workflow` and the repository variable to be exactly `true`. The workflow runs
only for pushes to the configured default branch and explicit manual dispatches; pull requests never deploy.

## Recovery

A failed task names the failed GitHub operation and does not report success. Install `gh` from <https://cli.github.com/>
if necessary. Complete the same state manually:

```bash
gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow
gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO
gh api repos/OWNER/REPO/pages --jq .html_url
```

Use POST instead of PUT when the repository does not have an existing Pages site.

If URL lookup fails after the variable is set, the repository may already be enabled; verify both settings before
rerunning or dispatching the Documentation workflow.
