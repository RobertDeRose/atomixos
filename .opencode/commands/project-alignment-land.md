---
description: Land a completed project-alignment integration branch
agent: build
---

Use this command after `/project-alignment-execute` reports that every planned
worktree is `MERGED`.

This command owns final landing and pre-release cleanup. In post-initial-release
PR mode, it creates the PR and preserves pipeline files until the PR has actually
merged.

# Command Contract

Follow this command exactly.

## Inputs

Required files:

- `PIPELINE_STATE.md`
- `IMPLEMENTATION_PLAN.md`

If either file is missing, stop and emit a blocker report.

## Instruction Precedence

Apply instructions in this order:

1. This command file
2. User answers given during this command run
3. `PIPELINE_STATE.md`
4. `IMPLEMENTATION_PLAN.md`
5. Current authoritative repository docs under `docs/src/`
6. Current implementation
7. Repository git history
8. General repository workflow guidance

If instructions conflict, follow the higher-priority instruction and record the
conflict in `PIPELINE_STATE.md` unless the next successful step is cleanup.

## Allowed Chat Output

In chat, output only:

- one-line start or resume notices
- blocker reports required by this command
- release detection summary
- final PR approval request when PR mode is used
- final completion summary

## Forbidden Actions

- Do not implement code.
- Do not create commits except for rebase conflict resolution during landing,
  pipeline file cleanup after successful pre-release landing, or a release-mode
  PR flow when explicitly required by the user.
- Do not create a merge commit when landing the integration branch in `dev`.
- Do not use `--no-ff`.
- Do not use a regular merge for final landing.
- Do not open a PR unless the repository is post-initial-release.
- Do not perform a final bookkeeping-only update to `PIPELINE_STATE.md` when the
  next successful step is deleting it.
- Do not remove pipeline files on blocker exit, validation failure, merge
  failure, open PR state, or any incomplete run state.

## Resume Rule

On each invocation, read `PIPELINE_STATE.md` and determine the current landing
state:

- If a release-mode PR URL is recorded, resume PR tracking (see below).
- If the integration branch has been rebased but not yet merged or PR-created,
  resume from the rebase result: validate, then continue with ff-merge or PR
  creation as appropriate.
- If no landing work has started, begin from Required State checks.

## Required State

Before landing:

1. Read `PIPELINE_STATE.md`.
2. Read `IMPLEMENTATION_PLAN.md`.
3. If `PIPELINE_STATE.md` records a release-mode PR URL from a prior run,
   handle that PR before requiring the integration branch to still exist.

If `PIPELINE_STATE.md` records a release-mode PR URL:

- query the PR state with `gh pr view <url> --json state,merged,url`
- if the PR is open, report the URL and wait; do not create another PR
- if the PR is merged, clean up pipeline files and report completion
- if the PR is closed without merge, stop and wait for user instruction to
  either abandon pipeline state or create a replacement PR
- if the user chooses to abandon, remove `SPEC_DRIFT_REPORT.md`,
  `UNKNOWN_RESOLUTION.md`, `SPEC_DRIFT_REPORT_RESOLVED.md`,
  `CODE_REVIEW_REPORT.md`, `IMPLEMENTATION_PLAN.md`, and `PIPELINE_STATE.md`,
  then report abandonment

If there is no recorded release-mode PR URL:

1. Verify every planned worktree is marked `MERGED` in `PIPELINE_STATE.md`.
2. Verify every merged worktree has source and integration commit SHAs recorded.
3. Verify the integration branch exists.
4. Verify the final target branch is `dev`.
5. Verify Phase 6 is `COMPLETE` in `PIPELINE_STATE.md` before landing.

If any check fails, stop and emit a blocker report.

Before release-state detection, fetch current remote branch and tag data:

- run `git fetch origin dev --tags`
- use the fetched refs when determining whether the repository is
  post-initial-release

## Release State Detection

Determine whether the repository is already after its initial release and whether
a release occurred during this pipeline run.

Post-initial-release evidence includes any release tag, release commit, or
release metadata reachable from the current repository history, whether it was
created before or during the pipeline run.

Pipeline-run release evidence includes:

- a release tag created after the Phase 0 base SHA
- a release commit after the Phase 0 base SHA
- release artifacts or release metadata committed after the Phase 0 base SHA

If the repository is post-initial-release, use release-mode PR flow. If no
initial release exists, use direct fast-forward landing. Pipeline-run release
evidence is additional context for the PR body; it is not the only condition for
PR mode.

Report:

```text
### RELEASE STATE DETECTION
- Phase 0 Base SHA:
- Integration Branch:
- Post-Initial-Release: [Yes | No]
- Release Occurred: [Yes | No]
- Evidence:
- Landing Mode: [`git merge --ff-only` | PR]
```

## Default Non-Release Landing

If the repository is not post-initial-release:

1. Check whether `dev` has diverged from the integration branch base.
2. If `dev` has moved, rebase the integration branch onto current `dev`, resolve
   conflicts automatically when the resolution follows from approved integration
   state, validate the result with `hk check -a`, and stop with a landing
   blocker report if validation fails.
3. Run `hk check -a` on the integration branch even when no rebase was required.
4. Check out `dev`.
5. Verify `dev` is clean except pipeline output files scheduled for cleanup.
6. Run `git merge --ff-only <integration-branch>`.
7. If fast-forward is not possible, stop and emit a landing blocker report; do
   not regress Phase 6 state, do not use `--no-ff`, do not create a merge
   commit, and do not use a regular merge.
8. Clean up pipeline files.

## Release-Mode PR Flow

If the repository is post-initial-release:

1. Check whether `dev` has diverged from the integration branch base.
2. If `dev` has moved, rebase the integration branch onto current `dev`, resolve
   conflicts automatically when the resolution follows from approved integration
   state, validate the result with `hk check -a`, and stop with a landing
   blocker report if validation fails.
3. Run `hk check -a` on the integration branch even when no rebase was required.
4. Draft a final PR title and body.
5. Present this exact request and wait for explicit user approval:

```text
### FINAL PR REQUEST: integration -> dev

- Proposed PR Title:
- Proposed PR Body:
- Integration branch:
- Target branch: `dev`
- All worktrees merged: [list]
- Post-initial-release evidence:
- Pipeline-run release evidence:
- `dev` diverged since pipeline start: [Yes / No]
- Rebase required: [Yes / No]
- Conflict summary (if applicable):

---

### REQUIRED ACTION
Awaiting USER APPROVAL of the PR title and body before creating the PR.
DO NOT create the PR without explicit confirmation.
```

6. After user approval, write the approved PR body to a temporary body file.
7. Push the integration branch with `git push -u origin <integration-branch>`.
8. Create the PR non-interactively with
   `gh pr create --base dev --head <integration-branch> --title <approved-title> --body-file <approved-body-file>`.
9. Record the PR URL in `PIPELINE_STATE.md` so later runs can check whether it
   is open, merged, or closed.
10. Remove the temporary body file after PR creation succeeds.
11. Report the PR URL in chat.
12. Keep pipeline files in place until the PR is merged.

## Cleanup

After successful pre-release direct landing, remove exactly these pipeline files
if present and commit the removal on `dev`:

- `SPEC_DRIFT_REPORT.md`
- `UNKNOWN_RESOLUTION.md`
- `SPEC_DRIFT_REPORT_RESOLVED.md`
- `CODE_REVIEW_REPORT.md`
- `IMPLEMENTATION_PLAN.md`
- `PIPELINE_STATE.md`

Use `git rm` for tracked files and filesystem deletion for untracked files, then
commit using `git commit -F <message-file>` with a conventional `chore:` subject.
If no tracked files were removed, skip the commit.

Do not update `PIPELINE_STATE.md` immediately before deleting it.

In post-initial-release PR mode, do not remove pipeline files when the PR is
created. Cleanup happens only after the PR has merged or after the user explicitly
asks to abandon the resumable pipeline state.

## Failure Handling

On missing state, incomplete worktree integration, unresolved rebase conflict,
validation failure, non-fast-forward final merge, merge failure, PR creation
failure, or any unexpected file conflict that cannot be resolved from approved
pipeline state, stop, keep all pipeline files, record the failure in
`PIPELINE_STATE.md`, and wait for user instruction.

## Success Definition

- if the repository is not post-initial-release, `dev` has been fast-forwarded to
  the integration branch with `git merge --ff-only`, and `hk check -a` passed
- if the repository is post-initial-release, the final PR into `dev` has been
  explicitly approved for title and body, created automatically, and its URL is
  reported in chat, with pipeline files preserved for PR follow-up until merge
- for pre-release direct landing, all pipeline files listed in the cleanup
  section have been removed
