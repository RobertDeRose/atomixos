# Releasing

Use the **Release** GitHub Actions workflow to publish an official AtomixOS release:

```sh
gh workflow run release.yml --ref dev
```

Development lands on `dev`. The official release branch, `main`, advances only through this workflow, by
fast-forward to the exact commit selected when the run starts. An annotated `vX.Y.Z` tag identifies that same commit.
The workflow creates no merge or version-bump commit and never rewrites an existing release tag. Development can
continue while a release runs; newer work stays off the release branch until another release selects it.

## Plan, validate, and approve

The workflow accepts dispatches from the development branch only and serializes release runs. GitHub keeps at most
one release run pending behind the active one: a new dispatch cancels a run that is still pending, so the newest
dispatch replaces it. A run that has started, including one waiting for approval, is never cancelled this way.

1. **Plan** verifies that the official release branch is an ancestor of the selected commit, if that branch exists,
   and refuses a commit that already carries a version tag. Cocogitto computes the next version from Conventional
   Commits since the latest version tag, using `cog bump --auto --dry-run`, and generates notes with
   `cog changelog`. Before `v1.0.0`, any breaking change (a `!` after the type or a `BREAKING CHANGE:` footer)
   bumps the minor version instead, because Cocogitto alone treats only `feat!` that way. The run summary shows
   the version, source commit, and notes before approval. No version file is changed.
2. **Validate** calls the existing repository-check, Nix, and Python-test workflows with the selected commit's full
   SHA. They run the same checks as pull requests, including the U-Boot sandbox and release-promotion regression
   tests. These are not the full NixOS VM or physical-hardware suites; see [Testing](../testing.md).
3. **Build** produces the ROCK64 and CM3 board packages on native aarch64 Linux runners. Both builds must succeed.
4. **Approve and publish** waits for the configured reviewers of the `release` environment. After approval, it
   atomically fast-forwards the official branch and creates the annotated tag. On the first release it creates the
   official branch at the selected commit. It uploads both boards' assets to a draft GitHub release and publishes
   the release only after every upload succeeds.

The workflow never advances development or merges release-only changes back into it. Immediately after promotion,
both branches point to the selected commit if development has not advanced during the run. Otherwise the release
branch remains an ancestor of development, so the next release can fast-forward again.

## Release assets and versions

Each release contains `atomixos-<board>-vX.Y.Z.tar.xz` and its `.sha256` checksum for each supported board. Extract
the archive to get the flashable image, signed RAUC bundle, U-Boot, U-Boot environment tools, and boot script. These
are the same artifacts exposed by the [board package](../reference/flake-outputs.md). Archive creation follows the
Nix output links so extraction does not require the original builder's Nix store. The U-Boot environment tools stay
dynamically linked against Nix store libraries, so run them on the device or a Nix host. Image and update outputs include
`build.toml` and `build-metadata.json` audit sidecars.

The release version identifies the source tag and archive. Inside the archive, image filenames retain their NixOS
release-series naming and RAUC manifests retain `system.nixos.version`. The release workflow does not substitute
the AtomixOS tag into runtime OS versions. It uses the committed build configuration, without local overrides.

Bundles use the development signing keys currently wired into the flake. Publication does not make those keys
production credentials. Production devices require separate signing credentials and a matching trusted keyring;
see [RAUC Integration](../specs/rauc-integration.md).

Before `v1.0.0`, releases may break interfaces, configuration, and on-disk state. Affected devices are reprovisioned,
not migrated in place.

## Repository setup

Configure these GitHub settings before the first release:

- Create a `release` environment with required reviewers and allow deployments from `dev` only. Approval is a GitHub
  environment setting; naming the environment in the workflow alone does not configure reviewers.
- Add a dedicated write-enabled deploy key. Store its private half as `RELEASE_DEPLOY_KEY` in that environment,
  rather than as a repository-wide secret. Publication refuses to run without that key.
- Protect `main` with a ruleset that restricts creation and updates, blocks deletion and force pushes, and requires
  linear history. Allow the release deploy key to bypass the creation and update restrictions. Do not require a
  merge commit or a release PR for this branch.
- Protect `v*` tags against creation, updates, and deletion, with the same deploy-key bypass.
- Keep the development branch as the default branch, so manual dispatch can discover the release workflow before
  the first release. Continue reviewing development changes through the normal PR checks.

The deploy key only updates Git references. The workflow's `GITHUB_TOKEN` creates the GitHub release and uploads
assets. Build and validation jobs have read-only repository access and receive no release key. The workflow calls
validation directly, so it does not depend on tag-triggered workflows. Existing documentation deployment remains
independent; see [GitHub Pages Deployment](github-pages.md).

Do not push to the official branch or create version tags by hand. To rotate the release key, remove its old public
half from the repository, register a new write-enabled deploy key, and replace the environment secret. Remove any
local private-key files after storing the secret.

## Recovery

A failure before approval changes no remote branch, tag, or GitHub release. If the branch diverges before approval,
publication fails rather than creating a merge commit or forcing a push. The branch and tag are pushed atomically:
if either reference update is rejected, neither changes.

An upload or GitHub API failure after promotion can leave the branch and tag in place with a draft or absent GitHub
release. Rerun the failed jobs from the **same run** to retain the planned version and validated source. The workflow
accepts an existing tag only when it is annotated and points to that exact commit, preserves its original tag object,
and reuses a draft release. Lightweight tags are rejected without changing the remote references. Uploads replace
incomplete draft assets. A published release's assets are left unchanged on a rerun.

Do not rerun all jobs to repair an upload failure: Plan refuses a commit that already carries a version tag. If
another release has already advanced the official branch, a rerun of an older run leaves the branch and its tag in
place, completes its GitHub release, and does not mark it as the latest release.
Resolve divergent history or conflicting tags explicitly; never delete a published tag or force the branch as a
recovery shortcut.
