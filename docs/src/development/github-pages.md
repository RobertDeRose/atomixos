# GitHub Pages Deployment

GitHub Pages serves two things from one site:

- the product page, a static page in `product/`, at <https://robertderose.github.io/atomixos/>;
- the documentation, a Docusaurus build of `docs/`, at <https://robertderose.github.io/atomixos/docs/>.

Publishing is off until you enable it; building and previewing locally never needs GitHub Pages.

## Build and preview locally

`mise run site:build` builds the docs, then assembles the site in `_site/atomixos/`: the files from `product/` at the
root, the docs build under `docs/`, the docs' `404.html` at the root, and the three web fonts the product page uses,
copied from the docs' npm packages into `fonts/`. The product page loads its logo from the docs build
(`docs/img/atomixos-logo.svg`), so the two always share one logo.

`mise run site:serve [port]` builds the same tree and serves it at `http://localhost:8000/atomixos/` by default. Use
`mise run docs:serve` instead while writing docs; it reloads on every change but serves only the docs.

The product page and the docs share the `theme` key in `localStorage`, so a light or dark choice on one carries to
the other.

## How the site is published

`.github/workflows/docs.yml` runs on every push to `dev` and on manual dispatch. Both of its jobs run only when the
repository variable `DOCS_DEPLOYMENT_ENABLED` is exactly `true`:

1. **build** checks out the repository, installs the locked tools with mise, runs `mise run site:build`, and uploads
   `_site/atomixos` as the Pages artifact. It has `contents: read` only.
2. **deploy** publishes that artifact to the `github-pages` environment. Only this job has `pages: write` and
   `id-token: write`.

Pull requests never deploy. They still build the site through the `docs` step of `mise run check`, which fails on any
broken link, anchor, or image.

## Enable deployment

You need the GitHub CLI, signed in as an identity with administration access to the repository. Run from a clone
whose GitHub repository `gh` can resolve:

```bash
gh auth login
mise run docs:deployment:enable
```

The task (`scripts/enable-docs-deployment.py`):

1. checks that `gh` is installed, signed in, and can resolve the repository;
2. creates the Pages site, or updates the existing one, with the GitHub Actions (`workflow`) build type;
3. sets `DOCS_DEPLOYMENT_ENABLED=true` as its last change;
4. prints the Pages URL.

Running it again is safe; it converges on the same configuration.

## Recovery

If the task fails, it names the GitHub operation that failed and prints the manual commands. Install `gh` from
<https://cli.github.com/> if needed, then complete the same state by hand:

```bash
gh api --method PUT repos/OWNER/REPO/pages -f build_type=workflow
gh variable set DOCS_DEPLOYMENT_ENABLED --body true --repo OWNER/REPO
gh api repos/OWNER/REPO/pages --jq .html_url
```

Use `POST` instead of `PUT` when the repository has no Pages site yet.

If only the final URL lookup failed, deployment may already be enabled. Check both the Pages build type and the
variable before rerunning the task or dispatching the Documentation workflow.
