# Developer tooling

The repository uses mise to provide project tools and named tasks. Install mise, then run:

```bash
mise install --locked
```

Use the same commands locally and in automation:

```bash
mise run check
mise run fix
mise run docs:check
mise run docs:build
mise run docs:deployment:enable
mise run docs:serve
```

Use `/update-project` for the recorded template channel, or `/update-project --stable` / `--unstable` to change it. The
update always records the exact resolved template commit.

`check` is read-only and delegates to the hk quality gate. `fix` changes the working tree. Contextlint checks links,
anchors, and image targets across README and `docs/**/*.md`. The pre-commit hook may fix files while safely stashing
unrelated unstaged work. The commit-message hook enforces Conventional Commits, required scopes for changelog-visible
changes, 72/100-character line limits, and canonical optional `Beads:` footers. Run `cog changelog` to preview
the concise user-facing changelog. The hk policy uses native built-in steps whenever their behavior matches;
hk's file locking coordinates independent steps. No dependency chain serializes unrelated checks. Go projects retain two
output-sensitive edges: `gofumpt` follows `goimports`, then fix-only module tidy observes the final imports.

Mise installs the pinned `commitlint` CLI directly from `mise.toml` and `mise.lock`; the repository has no separate npm
install step or root Node package manifest.

No recognized language profile is active; only the universal tooling baseline runs.

## GitHub validation

`.github/workflows/hk.yml` is the single quality workflow for every push and pull request. It installs Nix and the
committed tool lock on `ubuntu-26.04-arm` (`aarch64-linux`) and `macos-latest` (`aarch64-darwin`). Both jobs verify the
Nix platform and run the shared formatting, linting, and documentation checks. Linux runs `hk check -a`, including
evaluation of all flake systems and building the native Linux checks and VM tests. Builds are serialized, with a
180-minute job limit.

Hosted macOS runs `hk check -a --skip-step nix` followed by evaluation of all flake systems with `--no-build`; its
job limit is 45 minutes. GitHub's ARM64 macOS runners do not support nested virtualization, so they cannot run this
repository's Linux builder or Darwin VM tests. Full Darwin checks remain a local validation step on a Mac with the
Linux builder configured. See [GitHub's runner limitations](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners).

CI does not regenerate the lock. Dependency-update branches and fork PRs are not excluded from the pull-request gate.
The provisioning package test suite remains separate.

## Hooks and recovery

Setup installs repository-local hk hooks when the destination is a Git repository. To restore tooling after an offline
or degraded setup, run:

```bash
python3 scripts/setup-tooling.py --json
```

The command gives lock, install, and hook stages one temporary `MISE_CONFIG_DIR`, removes inherited global config
overrides, and deletes the temporary directory on exit. It preserves the scaffold on failure, reports the failed stage,
and uses the same command above for recovery. A repository created without Git can install hooks after Git
initialization with:

```bash
python3 scripts/setup-tooling.py --json
```
