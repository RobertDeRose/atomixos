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

`.github/workflows/hk.yml` runs formatting, linting, and documentation checks on pull requests and manual dispatches.
It uses `mise-action` with tool installation disabled, then runs `mise x -- hk check -a` on `ubuntu-latest`.
Mise provides hk and its tools when executing the command; there is no separate tool-install step or Nix evaluation
in this workflow.

`.github/workflows/nix.yml` independently evaluates Nix on the same events. It installs Nix on `ubuntu-26.04-arm`
(`aarch64-linux`) and `macos-latest` (`aarch64-darwin`). Each runner verifies its Nix platform, then evaluates it with
`flake check --no-build --system <system>`. Evaluating platforms separately reduces peak evaluator memory compared
with checking both platforms in one process. All validation jobs have a 45-minute limit.

PR validation checks flake evaluation without building packages or executing NixOS VM tests. Full build and VM
validation remains available locally through `./scripts/nix-with-build-config.sh flake check` or individual
`nix build` commands, separately from `mise run check`. Darwin VM tests
need a Mac with the Linux builder configured. See [GitHub's runner limitations](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#limitations-for-arm64-macos-runners).

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
