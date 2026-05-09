---
description: Execute planned project-alignment worktrees and integrate them
agent: build
---

Use this command after `/project-alignment-review` has completed Phases 0
through 5 and the user is ready to begin worktree execution.

This command owns only Phase 6 worktree execution. It does not land the
integration branch in `dev`, create a pull request, or clean up pipeline files.
Use `/project-alignment-land` after every worktree is `MERGED`.

# Command Contract

Follow this command exactly.

## Inputs

Required files:

- `PIPELINE_STATE.md`
- `SPEC_DRIFT_REPORT_RESOLVED.md`
- `IMPLEMENTATION_PLAN.md`

Optional context files (read if present for conflict resolution reference):

- `SPEC_DRIFT_REPORT.md`
- `UNKNOWN_RESOLUTION.md`
- `CODE_REVIEW_REPORT.md`

If any required file is missing, stop and emit a blocker report.

## Instruction Precedence

Apply instructions in this order:

1. This command file
2. User answers given during this command run
3. `IMPLEMENTATION_PLAN.md`
4. `SPEC_DRIFT_REPORT_RESOLVED.md`
5. `PIPELINE_STATE.md`
6. Current authoritative repository docs under `docs/src/`
7. Current implementation
8. Repository git history
9. General repository workflow guidance

If instructions conflict, follow the higher-priority instruction and record the
conflict in `PIPELINE_STATE.md`.

## Allowed Chat Output

In chat, output only:

- one-line resume or start notices
- blocker reports required by this command
- worktree completion reports
- worktree review reports
- worktree integration reports
- the final execution-complete handoff to `/project-alignment-land`

## Forbidden Actions

- Do not redesign, reinterpret, or reprioritize `IMPLEMENTATION_PLAN.md`.
- Do not expand scope for cleanup or obvious follow-ups.
- Do not edit files outside the planned worktree file list unless required by
  validation and directly related to the worktree scope.
- Do not stop for review findings that are actionable inside planned scope; fix
  them and repeat review until approval.
- Do not stop for expected cherry-pick conflicts when the correct resolution is
  derivable from the approved worktree state and current integration branch;
  resolve them and continue.
- Do not merge a worktree branch into the integration branch.
- Do not land the integration branch in `dev`.
- Do not create a pull request.
- Do not clean up pipeline files.

## Cancellation

If the user explicitly requests cancellation mid-execution:

1. Record the current worktree states in `PIPELINE_STATE.md`.
2. Mark any `IN_PROGRESS` worktrees as `CANCELLED` in `PIPELINE_STATE.md`.
3. Stop and report which worktrees completed, which were cancelled, and which
   were not started.
4. Do not remove pipeline files; the user may resume or abandon later.

## Commit Message Rules

All commits created by this command must use a message file and `git commit -F`.
Do not build commit messages with repeated `-m` arguments.

Commit message body rules:

- use Conventional Commits subject format
- prefer list-first bodies for all nontrivial changes
- use prose only after the list when it adds useful reason or context
- do not insert blank lines between list items in the body
- keep body lines within the repository commitlint limit
- create the message file inside an approved temporary location or the active
  worktree, commit with `git commit -F <message-file>`, then remove the message
  file after the commit succeeds

Preferred nontrivial shape:

```text
fix(scope): concise behavioral change

- first concrete change
- second concrete change
- validation or contract note when relevant

Short prose paragraph only when it explains why the list is not enough.
```

## Resume Rule

1. Read `PIPELINE_STATE.md` first.
2. Read `IMPLEMENTATION_PLAN.md` second.
3. If Phase 6 is `NOT_STARTED`, mark Phase 6 `IN_PROGRESS` before starting
   worktree execution.
4. Resume from the first execution wave with a worktree not marked `MERGED` or
   `CANCELLED`. Skip `CANCELLED` worktrees.
5. If any worktree is `BLOCKED`, emit its blocker report and wait.
6. If every worktree is `MERGED` and Phase 6 is not `COMPLETE`, run final
   integration branch validation, mark Phase 6 `COMPLETE`, and tell the user to
   run `/project-alignment-land`.
7. If every worktree is `MERGED` and Phase 6 is `COMPLETE`, stop and tell the user to run
   `/project-alignment-land`.

If `PIPELINE_STATE.md` conflicts with `IMPLEMENTATION_PLAN.md`, stop and emit a
blocker report.

## Phase 6 — Worktree Execution

Execution rules:

- mark Phase 6 `IN_PROGRESS` in `PIPELINE_STATE.md` before any worktree starts
- execute all worktrees in the same parallel wave concurrently when the plan
  marks them parallel-eligible and file exclusivity allows it
- do not serialize independent worktrees within the same planned parallel wave
  without a recorded blocker or user instruction
- parallel execution applies to implementation, validation, and review only;
  cherry-picks into the shared integration branch must be serialized in the
  integration order from `IMPLEMENTATION_PLAN.md`
- complete each planned execution wave before starting a later wave that depends
  on it
- use concurrent tool calls for initialization, validation, and review work
  inside a parallel wave whenever those operations are independent
- run every `wt` command from the Phase 0 repository root
- before any `wt` command, run `git rev-parse --show-toplevel` and require it to
  equal the Phase 0 repository root
- verify the integration branch exists before Phase 6 initialize or resume uses
  it
- use the local `wt` CLI exactly as documented by `wt switch --help`; do not
  improvise alternate worktree-creation flows
- use `wt switch --format json` so worktree path and branch data come from
  machine-readable output rather than human-readable terminal text; parse stdout
  only and ignore the human-readable stderr status lines
- create or switch the worktree first and then record the actual `wt` path in
  `PIPELINE_STATE.md` before implementation begins
- after initialization, use the recorded actual `wt` path as the authoritative
  path for the rest of the run
- every worktree starts from the current integration branch tip
- default validation command is `hk check -a`
- if narrower validation is used, list the exact commands in the plan
- produce one approved commit boundary per worktree unless the plan explicitly
  says otherwise
- review-fix commits are allowed while iterating, but before integration they
  must be folded into the approved worktree commit boundary using
  `git reset --soft <original-commit>^` followed by `git commit -F <message-file>`
  so cherry-picking one SHA includes the complete worktree result
- do not reference ephemeral pipeline identifiers (drift IDs, worktree IDs,
  review finding IDs, or any tag that only exists in temporary pipeline files)
  in commit messages; record traceability in `PIPELINE_STATE.md` only
- the only allowed worktree-to-integration command is
  `git cherry-pick <worktree-commit-sha>`
- never merge a worktree branch into the integration branch during this pipeline
- if `git cherry-pick <worktree-commit-sha>` conflicts, resolve the conflict
  automatically when the correct resolution can be derived from the approved
  worktree diff, current integration branch, implementation plan, and validation
  requirements
- only stop for a cherry-pick conflict when the resolution would require a new
  design decision, out-of-scope edits, destructive git operations, or changing
  user-authored unrelated work

## Per Execution Wave

1. Identify the next wave whose entry criteria are satisfied.
2. Start every parallel-eligible worktree in that wave concurrently.
3. Allow parallel worktrees to advance through implementation, validation, and
   review concurrently.
4. After reviews approve, cherry-pick approved worktree commit boundaries into
   the integration branch one at a time in the plan's integration order.
5. Do not start a later wave until the current wave is fully advanced or stopped
   by a blocker.

## Per Worktree

1. Initialize
   - set workdir to the Phase 0 repository root
   - run `git rev-parse --show-toplevel`
   - require that result to equal the Phase 0 repository root
   - verify the integration branch exists before any `wt` call
   - if the worktree does not exist, run `wt switch --create --yes --format json <Branch Name> --base <Integration Branch>` from the repository root using the current `wt` configuration
   - if the worktree already exists, run `wt switch --format json <Branch Name>` from the repository root
   - capture the actual worktree path and branch from stdout only from the JSON output that `wt switch` returned
   - record that actual path in `PIPELINE_STATE.md`
   - use the actual recorded path as the authoritative path for the rest of the run
   - for a new or `NOT_STARTED` worktree with no source commit recorded, verify
     `HEAD` matches the current integration tip
   - for a resumed `IN_PROGRESS`, `PENDING_REVIEW`, or `APPROVED` worktree with
     a source commit recorded, verify `HEAD` matches the recorded source commit
     exactly; if `HEAD` does not match, stop and emit a blocker report indicating
     the worktree branch has diverged from the recorded state
   - mark `IN_PROGRESS`
2. Implement
   - make only scoped changes in planned files
   - commit in the worktree using `git commit -F <message-file>`
3. Validate
   - run `hk check -a` or the narrower planned command set
   - require all listed validation commands to succeed
   - require no out-of-scope files changed unless validation required directly
     related lint or formatting fixes
4. Completion report

```text
### WORKTREE COMPLETE REPORT
- Worktree ID:
- Source Commit SHA:
- Summary of Changes:
- Files Modified:
- Diff Summary:
- Validation Results:
- Risks Introduced (if any):
```

- mark `PENDING_REVIEW`
- record in `PIPELINE_STATE.md`: Worktree ID, Source Commit SHA,

     Integration Commit SHA [None until cherry-pick], Validation Commands,
     Validation Result

5. Review agent pass
   - invoke a second agent with the `task` tool using `subagent_type: general`
   - provide only: the relevant `WORKTREE-###` plan section,
     `SPEC_DRIFT_REPORT_RESOLVED.md`, the current worktree diff, and the
     integration-branch diff relative to the worktree base
   - require exactly this report and nothing else:

```text
### WORKTREE REVIEW REPORT
- Worktree ID:
- Correctness vs SPEC_DRIFT_REPORT_RESOLVED.md:
- Security Assessment:
- Consistency with Implementation Plan:
- New drift vs integration branch: [Yes / No — detail if Yes]
- Issues Found (if any):
- Approval Recommendation: [APPROVE | REQUIRES CHANGES | REJECT]
```

   - if the review returns `APPROVE`, mark `APPROVED`
   - if the review returns `REQUIRES CHANGES` and every finding is actionable
     inside the planned worktree scope, implement the fixes, validate, commit a
     follow-up using `git commit -F`, and repeat the review agent pass until it
     returns `APPROVE`
   - if the review returns `REJECT`, or a required review fix is outside planned
     scope or requires a new design decision, mark `BLOCKED`
   - if review-fix commits were created, fold them into one approved worktree
     commit boundary before integration using `git reset --soft <original-commit>^`
     followed by `git commit -F <message-file>`, then re-run validation and record the
     final approved source commit SHA in `PIPELINE_STATE.md`
   - record in `PIPELINE_STATE.md`: Worktree ID, Review Verdict, Integration

     Ready [YES | NO]

6. Post-review integration
   - verify the approved source commit SHA is still the intended complete
     worktree commit boundary
   - verify the approved source commit contains the original implementation and
     all review-fix changes for that worktree
   - cherry-pick the approved worktree commit into the integration branch with
     `git cherry-pick <worktree-commit-sha>`
   - run only one integration-branch cherry-pick at a time; wait for any active
     cherry-pick, conflict resolution, and integration validation to finish
     before starting the next worktree cherry-pick
   - if the cherry-pick conflicts, resolve it automatically when the resolution
     follows from the approved worktree state and current integration branch
   - after resolving a conflict, continue the cherry-pick, validate the
     integration branch, and record the conflict summary in `PIPELINE_STATE.md`
   - if the cherry-pick fails for a reason that cannot be resolved safely, stop,
     mark the worktree `BLOCKED`, record the failing command and result in
     `PIPELINE_STATE.md`, and wait for user instruction
   - mark `MERGED`
   - record in `PIPELINE_STATE.md`: Worktree ID, Integration Commit SHA, Status
     `MERGED`
   - record the new integration branch tip SHA as the Integration Commit SHA for
     that worktree
7. Integration report — emit after each successful cherry-pick integration

```text
### INTEGRATION REPORT: WORKTREE-###
- Worktree ID:
- Review Agent Verdict:
- Integration method: Cherry-pick
- Source Commit SHA:
- Integration Commit SHA:
- Conflict Resolution: [None / summary]
- Integration Validation Results:
```

## Failure Handling

On scope ambiguity, path mismatch, validation failure, worktree creation failure,
review rejection, unresolved cherry-pick conflict, cherry-pick failure, or any
unexpected file conflict that cannot be resolved from approved pipeline state,
stop the affected worktree, mark it `BLOCKED`, record the failing command and
result in `PIPELINE_STATE.md`, and wait for user instruction.

## Success Definition

- every worktree in `IMPLEMENTATION_PLAN.md` is `MERGED`
- every merged worktree has source and integration commit SHAs recorded in
  `PIPELINE_STATE.md`
- every recorded source commit SHA is a complete approved worktree commit
  boundary containing implementation and review fixes
- final integration branch validation has passed
- Phase 6 is marked `COMPLETE` in `PIPELINE_STATE.md`
- chat output says: `✓ Phase 6 execution complete — run /project-alignment-land`
