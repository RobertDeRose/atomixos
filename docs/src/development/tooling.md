# Developer Tooling

[mise](https://mise.jdx.dev/) manages every developer tool, its version, the repository hooks, and the named tasks.
`mise.toml` declares the tools and tasks; `mise.lock` pins the resolved downloads. Install mise, then run:

```bash
mise install --locked
```

That installs the locked tools and, through the `postinstall` hook, the repository-local hk Git hooks. Nothing else
needs a separate install step. The hook runs `hk install --mise` only when hk is on the `PATH`, so a partial install,
such as the pytest job's uv-only install, skips Git hook setup instead of logging a failed hook.

`check` is read-only and runs the hk quality gate (no Nix evaluation). `fix` changes the working tree. The pre-commit
hook runs the hk check/fix steps from `hk.pkl`; the commit-message hook enforces the rules below. Run `cog changelog`
to preview the user-facing changelog.

`mise.toml` requests every tool as `latest` (Node as `lts`, which also runs the Docusaurus docs build); `mise.lock`
pins the exact version and download for each, so installs stay reproducible until the lock changes. To upgrade tools,
run `mise lock`, review the version changes in the lock diff, and commit it. To add a tool,
add it to `mise.toml` as `latest` and run `mise lock`.

## Tasks

| Task                     | Behavior                                                                |
|--------------------------|-------------------------------------------------------------------------|
| `check`                  | Run all hk checks without requesting fixes.                             |
| `fix`                    | Apply deterministic hk fixes to the working tree.                       |
| `docs:install`           | Install the docs site's npm dependencies from `docs/package-lock.json`. |
| `docs:build`             | Build the Docusaurus site into `docs/build`; fails on broken links.     |
| `docs:deployment:enable` | Configure Pages and enable its repository gate through external `gh`.   |
| `docs:serve [port]`      | Serve the docs with hot reload on port 3000 or the supplied port.       |
| `site:build`             | Assemble the product page and the docs build into `_site/atomixos`.     |
| `site:serve [port]`      | Build and serve the site on port 8000; the product page is served live. |

The committed lock targets the `lockfile_platforms` in `mise.toml`: `linux-x64`, `linux-arm64`, and `macos-arm64`.
Intel Macs (`macos-x64`) are not targeted, since hk and nixfmt-rs publish no release for them. Windows is not supported.

The mise environment routes hooks through mise with `HK_MISE=1` and sets `GIT_CONFIG_PARAMETERS="'merge.ff=only'"`, so
Git rejects merges that require a merge commit.

## Files

| File                                | Contract                                                                  |
|-------------------------------------|---------------------------------------------------------------------------|
| `mise.toml`                         | Declares project tools, environment, hooks, and named tasks.              |
| `mise.lock`                         | Project-owned resolved downloads; commit it.                              |
| `hk.pkl`                            | Defines the shared check/fix/pre-commit/commit-msg step map.              |
| `.config/rumdl.toml`                | Configures Markdown linting and deterministic fixes.                      |
| `.editorconfig`                     | Keeps editor output on UTF-8, LF, final newlines, and no trailing spaces. |
| `_typos.toml`                       | Ignores hash-like identifiers while retaining typo checks elsewhere.      |
| `contextlint.config.json`           | Checks documentation links, anchors, and image targets.                   |
| `docs/package.json`                 | Pins the Docusaurus site dependencies; `package-lock.json` locks them.    |
| `cog.toml`                          | Configures Conventional Commits and concise changelogs.                   |
| `.config/cog-changelog.tera`        | Renders plain Markdown changelogs without author noise.                   |
| `scripts/enable-docs-deployment.py` | Configures workflow-built Pages through external `gh`.                    |
| `.github/workflows/hk.yml`          | Runs the hk quality checks on pull requests and manual dispatches.        |
| `.github/workflows/nix.yml`         | Evaluates the flake per platform; runs U-Boot scripts in a sandbox.       |
| `.github/workflows/docs.yml`        | Builds gated docs from the default branch or manual dispatch.             |
| `.github/workflows/pytest.yml`      | Runs provisioning package tests on aarch64 Linux for PRs and dispatches.  |

## GitHub validation

`.github/workflows/hk.yml` runs `mise x -- hk check -a` (formatting, linting, and documentation checks) on pull
requests and manual dispatches. `.github/workflows/nix.yml` independently evaluates the flake with
`flake check --no-build --system <system>` on `aarch64-linux` and `aarch64-darwin` runners. In parallel, its
`uboot-scripts` job builds `checks.aarch64-linux.uboot-scripts`: a U-Boot sandbox binary that executes the compiled
`boot.scr` and the `START_UMS` `PREBOOT`, because U-Boot only parses those scripts at boot time. No workflow builds
images, runs NixOS VM tests, or regenerates the lock. Full build and VM validation stays local through
`./scripts/nix-with-build-config.sh flake check` or individual `nix build` commands, separately from `mise run check`.
The hk and Nix jobs have a 45-minute limit.

`.github/workflows/pytest.yml` runs the provisioning package test suite on the same events. It runs on
`ubuntu-26.04-arm`, matching the device's aarch64 Linux file APIs, which macOS host runs only emulate. It executes
`uv run --python 3.13 --extra dev pytest` through `mise x uv` in `scripts/atomixos_provision`, installing only uv.
The interpreter pin matches the Python series that the pinned nixpkgs `python3` provides on the device. The job has a
15-minute limit.

## Commit messages and changelogs

Changelog-visible `feat`, `fix`, `perf`, and `refactor` commits require a semantic scope. The commit hook also checks
Conventional Commit syntax, a 72-character subject, 100-character body lines, and canonical optional `Beads:` footers.
Internal build, chore, CI, documentation, release, style, and test commits are omitted from `cog changelog`.

To constrain scopes, add a `scopes = ["..."]` allowlist to `cog.toml`, document each stable subsystem in README, and
update `AGENTS.md` so agents apply the same taxonomy. Run `cog check` after changing the allowlist.
