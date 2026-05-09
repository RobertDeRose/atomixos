---
description: Run deterministic project alignment analysis and implementation planning
agent: build
---

Use this command to execute the planning half of the structured, stateful
project-alignment pipeline. It takes a repository from drift analysis through
implementation planning, then stops before implementation work begins.

Use the user's message as the pipeline input.

# Command Contract

Follow this command exactly.

## Instruction Precedence

Apply instructions in this order:

1. This command file
2. User answers given during this command run
3. Phase output files produced earlier in this run
4. Current authoritative repository docs under `docs/src/`
5. Current implementation
6. Repository git history
7. General repository workflow guidance

If instructions conflict, follow the higher-priority instruction and record the conflict in `PIPELINE_STATE.md`.

This command does not implement changes, land changes in `dev`, or create pull
requests. Use `/project-alignment-execute` after the user approves Phase 6
execution, then use `/project-alignment-land` after every worktree is merged.

Fresh-run precondition:

- if `PIPELINE_STATE.md` does not exist, the command must begin from a clean checkout of `dev`
- on a fresh run, if the current branch is not `dev`, or if `dev` has staged, unstaged, or untracked changes, stop and emit a blocker report instead of starting Phase 0
- do not analyze a feature branch, backup branch, or dirty `dev` checkout as the source tree for a fresh run

Invocation of this command is explicit user authorization to access repository worktree directories required by this workflow, including newly created Phase 6 worktrees rooted from the Phase 0 repository snapshot.

Do not ask again for permission to access those worktree directories during this command run.

## Evidence Rules

Use evidence in this order:

1. This command file
2. User answers given during this command run
3. Phase output files produced earlier in this run
4. Current authoritative docs under `docs/src/`
5. Current implementation
6. Repository git history

Git history is an adjudication source only. It does not override an explicit current spec statement or an explicit user decision from this run.

## Allowed Chat Output

In chat, output only:

- the required one-line status lines between phases
- the required one-line resume notice
- `Updating: UNKNOWN_RESOLUTION.md`
- Phase 2 questions
- the Phase 6 entry summary
- blocker reports required by this command

## Forbidden Actions

- Do not ask for confirmation outside Phase 2 and Phase 6 entry.
- Do not ask for permission to access workflow-required worktree directories after command invocation.
- Do not modify earlier phase output files except `PIPELINE_STATE.md` and Phase 2 append-only writes to `UNKNOWN_RESOLUTION.md`.
- Do not implement code before Phase 6 approval.
- Do not reinterpret a completed phase once its file exists and `PIPELINE_STATE.md` marks it `COMPLETE`.
- Do not use ambiguous language in any phase output.
- Do not treat git history as a co-equal source of truth with current docs.

Forbidden words in phase outputs:

- `unclear`
- `appears`
- `might`
- `possibly`
- `likely`
- `seems`
- `probably`

## IDs

- `DRIFT-###`
- `DECISION-###`
- `UNKNOWN-###`
- `GAP-###`
- `BLOCKED-###`
- `ISSUE-###`
- `SEC-###`
- `BUG-###`
- `MAINT-###`
- `PERF-###`
- `WORKTREE-###`

IDs increase by 1, must be unique within their file, and keep the lowest surviving ID during deduplication.

## Output Files

Produce exactly one phase file per phase:

- Phase 0: `PIPELINE_STATE.md`
- Phase 1: `SPEC_DRIFT_REPORT.md`
- Phase 2: `UNKNOWN_RESOLUTION.md`
- Phase 3: `SPEC_DRIFT_REPORT_RESOLVED.md`
- Phase 4: `CODE_REVIEW_REPORT.md`
- Phase 5: `IMPLEMENTATION_PLAN.md`

After a phase completes, its output file becomes read-only. The only exceptions are:

- `PIPELINE_STATE.md`, which is updated throughout the run
- `UNKNOWN_RESOLUTION.md`, which is append-only during Phase 2

Cleanup is owned by `/project-alignment-land`. This command does not remove pipeline files.

## Global Completion Rule

A phase is `COMPLETE` only if:

- the required file exists
- the first line matches the required exact heading
- the required sections exist
- all IDs are unique
- all required citations exist
- forbidden ambiguous words do not appear
- `PIPELINE_STATE.md` reflects the phase state accurately

## Resume Rule

Fresh-state rule:

- at the start of every command invocation, re-check the current repository filesystem for `PIPELINE_STATE.md`, `SPEC_DRIFT_REPORT.md`, `UNKNOWN_RESOLUTION.md`, `SPEC_DRIFT_REPORT_RESOLVED.md`, `CODE_REVIEW_REPORT.md`, and `IMPLEMENTATION_PLAN.md`
- treat the live filesystem state as authoritative for resume decisions
- do not infer file existence from prior conversation state, earlier tool output, or earlier runs
- if `PIPELINE_STATE.md` is absent, treat the run as fresh and begin at Phase 0

If `PIPELINE_STATE.md` exists when the command starts:

1. Read it first.
2. Resume from the first phase not marked `COMPLETE`.
3. Do not regenerate completed phase files.
4. Print exactly: `Resuming from Phase N — loading PIPELINE_STATE.md...`

Fresh-run guard:

- if `PIPELINE_STATE.md` is absent, require the current branch to be `dev` and the `dev` worktree to be clean before Phase 0 begins
- if that fresh-run guard fails, stop and emit a blocker report instead of starting the pipeline

Resume behavior:

- If Phases 0 through 5 are `COMPLETE` and Phase 6 is `NOT_STARTED`, reprint the Phase 6 entry summary and wait.
- If Phase 6 is in progress, this command was invoked in error; stop and tell the
  user to run `/project-alignment-execute` instead.
- If every worktree is `MERGED`, this command was invoked in error; stop and tell
  the user to run `/project-alignment-land` instead.
- If any worktree is `BLOCKED`, this command was invoked in error; emit its
  blocker report and tell the user to resume with `/project-alignment-execute`
  after resolving the blocker.

If `PIPELINE_STATE.md` conflicts with the phase files, stop and emit a blocker report.

## Status Line Rule

After each automatic phase output file is written, print exactly:

`✓ Phase N complete — [output filename] written. Starting Phase N+1...`

Exception: after Phase 5, stop and present the Phase 6 entry summary instead.

## Docs vs Code Adjudication

Resolve docs-versus-code disagreements in this order:

1. Current explicit normative docs win.
2. If docs are silent and code is explicit, code defines current behavior.
3. If docs and code both make explicit conflicting claims, inspect git history.
4. If history is conclusive, apply it.
5. If history is not conclusive, classify the item as `DESIGN_DECISION_REQUIRED` for Phase 2.

Conclusive history requires at least one of:

- a commit message with explicit behavior intent
- a PR title or body with explicit behavior intent
- a commit that updates code and docs together for the same behavior
- a commit that updates tests and implementation together for the same behavior

Never use `latest commit wins`. Use `latest explicit intent wins` only when history is conclusive.

When history is used, cite commit SHA, commit subject, and affected paths. Ignore rename-only, formatting-only, and mechanical refactor commits as intent signals.

Use PR metadata only as the lowest-priority history source and only when local repository context is not conclusive. When PR metadata is required, retrieve it with `gh` and cite the PR number, title, and relevant body excerpt. If PR metadata cannot be retrieved, treat that signal as inconclusive.

## Winner Table

Use this table exactly:

- docs explicit, code conflicting and the documented behavior is absent in code -> winner: docs -> result: `Missing Implementation` -> provisional action: `UPDATE_CODE`
- docs explicit, code conflicting and the code implements the behavior with different semantics -> winner: docs -> result: `Behavioral Mismatch` -> provisional action: `UPDATE_CODE`
- docs explicit, code absent -> winner: docs -> result: `Missing Implementation` -> provisional action: `UPDATE_CODE`
- docs silent, code explicit, intentional code history, no authoritative spec page defines behavior -> winner: code -> result: `SPEC_GAP` -> provisional action: `UPDATE_SPEC`
- docs silent, code explicit, intentional code history, authoritative spec matches code but non-authoritative docs do not -> winner: code -> result: `Documentation Drift` -> provisional action: `UPDATE_DOCS`
- docs silent, code explicit, no intent in history -> winner: code -> result: `SPEC_GAP` -> provisional action: `UPDATE_SPEC`
- docs explicit, code explicit, later intentional doc correction -> winner: docs -> result: `Behavioral Mismatch` -> provisional action: `UPDATE_CODE`
- docs explicit, code explicit, later intentional implementation change with tests and no authoritative spec update -> winner: code -> result: `Confirmed Spec Gap` -> provisional action: `UPDATE_SPEC`
- docs explicit, code explicit, later intentional implementation change with tests and authoritative spec still matches code but non-authoritative docs do not -> winner: code -> result: `Documentation Drift` -> provisional action: `UPDATE_DOCS`
- docs explicit, code explicit, history inconclusive -> result: `DESIGN_DECISION_REQUIRED` -> provisional action: `NEEDS_DECISION`
- docs explicit, code implements additional behavior not described in docs -> winner: docs -> result: `Over-Implementation` -> provisional action: `UPDATE_CODE`

## Cross-Phase Mapping

Map winner-table results exactly as follows:

- `Missing Implementation` -> Phase 1 category `Missing Implementation` -> Phase 3 category `Missing Implementation` -> Phase 3 action `UPDATE_CODE`
- `Behavioral Mismatch` -> Phase 1 category `Behavioral Mismatch` -> Phase 3 category `Behavioral Mismatch` -> Phase 3 action `UPDATE_CODE`
- `Over-Implementation` -> Phase 1 category `Over-Implementation` -> Phase 3 category `Over-Implementation` -> Phase 3 action `UPDATE_CODE`
- `SPEC_GAP` -> Phase 1 category `Spec Incomplete` -> Phase 3 category `Confirmed Spec Gap` -> Phase 3 action `UPDATE_SPEC`
- `Confirmed Spec Gap` -> Phase 1 category `Spec Incomplete` -> Phase 3 category `Confirmed Spec Gap` -> Phase 3 action `UPDATE_SPEC`
- `Documentation Drift` -> Phase 1 category `Documentation Drift` -> Phase 3 category `Documentation Drift` -> Phase 3 action `UPDATE_DOCS`
- `DESIGN_DECISION_REQUIRED` -> Phase 1 category `Spec Ambiguity` -> provisional action `NEEDS_DECISION` -> Phase 3 blocked until resolved or explicitly deferred

If an item does not fit this table exactly, stop and emit a blocker report.

## Phase 0 — Repository Snapshot

Input: full repository.

Output file: `PIPELINE_STATE.md`

First line must be exactly:

```text
# Pipeline State
```

Required actions:

1. Record the caller's current `HEAD` SHA and branch as invocation context.
2. Resolve the repository integration branch `dev` and record its current SHA as the pipeline base.
3. Create integration branch `integration/pipeline-run-<short-sha>` from `dev`.
4. Verify the integration branch exists before marking Phase 0 `COMPLETE`.
5. Record the repository root from `git rev-parse --show-toplevel`.
6. Initialize phase states.
7. Initialize an empty worktree registry.

Required structure:

```text
# Pipeline State

## Repository Snapshot
- Invocation HEAD SHA:
- Invocation Branch:
- Pipeline Base Branch: `dev`
- Pipeline Base SHA:
- Integration Branch:
- Repository Root:
- Snapshot Timestamp:

## Phase Status
- Phase 0 — Repository Snapshot: COMPLETE
- Phase 1 — Drift Analysis: NOT_STARTED
- Phase 2 — Unknown Resolution: NOT_STARTED
- Phase 3 — Drift Reconciliation: NOT_STARTED
- Phase 4 — Code Review: NOT_STARTED
- Phase 5 — Implementation Planning: NOT_STARTED
- Phase 6 — Execution: NOT_STARTED

## Worktree Registry
[Each worktree entry must eventually record: Worktree ID | Branch Name | Worktree Path | Status | Source Commit SHA | Integration Commit SHA | Validation Commands | Validation Result | Review Verdict | Integration Ready]
[empty — populated during Phase 6]

## Notes
[Any conditions observed at snapshot time]
```

## Phase 1 — Drift Analysis

Inputs:

- authoritative docs under `docs/src/`
- full codebase
- mdBook docs under `docs/src/`

Output file: `SPEC_DRIFT_REPORT.md`

First line:

```text
# Spec vs Implementation Drift Report
```

Required actions:

1. Inspect all feature `design.md` and `tasks.md` files under `docs/src/features/**/`.
2. Inspect additional source-of-truth files referenced by those docs.
3. Inspect the related implementation and mdBook pages.
4. Validate interfaces, contracts, boundaries, and data flows against the implementation.
5. For docs/code conflicts not resolved by the current tree, inspect git history.
6. Record every drift item with one Phase 1 category and one provisional required action.
7. Record unresolved items as structured unknowns.

Allowed Phase 1 categories:

- `Missing Implementation`
- `Behavioral Mismatch`
- `Over-Implementation`
- `Spec Ambiguity`
- `Spec Incomplete`
- `Documentation Drift`

Required structure:

```text
# Spec vs Implementation Drift Report

## Executive Summary
- Total issues found
- Breakdown by drift category
- High-risk areas

---

## Spec Drift Report

### DRIFT-###
- Category:
- Source of Truth Reference:
- Code Reference:
- Documentation Reference:
- History Reference:
- Provisional Required Action: [UPDATE_CODE | UPDATE_SPEC | UPDATE_DOCS | NEEDS_DECISION]
- Description:
- Evidence:
- Recommended Resolution:
- Justification:

---

## Interface / Contract Issues

## Architectural Boundary Violations

## Data Flow Inconsistencies

## Coverage Gaps
[Specs without implementation | Implementation without spec | Docs without backing code]

## Unresolved Unknowns

### UNKNOWN-###
- DRIFT Reference:
- Category:
- Description:
- Why Unresolved:
- Priority Class: [Security | Contract | Stateful | Other]
- Next Resolution Step:
```

## Phase 2 — Unknown Resolution

Inputs:

- `SPEC_DRIFT_REPORT.md` read-only
- full codebase
- authoritative docs under `docs/src/`
- `UNKNOWN_RESOLUTION.md` if already present

Output file: `UNKNOWN_RESOLUTION.md`

`UNKNOWN_RESOLUTION.md` is append-only after the initial write. Do not edit, rewrite, reorder, or delete earlier entries.

Blocking rule:

- any unresolved `DRIFT-###` whose provisional action is `UPDATE_CODE` must be recorded as `BLOCKED`
- blocked items must be resolved or explicitly deferred before Phase 3 begins

Phase 2A:

1. Resolve each unknown by code tracing, architectural inspection, data-flow analysis, and targeted git-history inspection.
2. Classify each item as exactly one of:
   - `RESOLVED_BY_CODE`
   - `RESOLVED_BY_HISTORY`
   - `SPEC_GAP`
   - `DESIGN_DECISION_REQUIRED`
   - `TRUE_UNKNOWN`
3. Write all Phase 2A results before asking any question.

Phase 2B:

1. Process remaining `DESIGN_DECISION_REQUIRED` and `TRUE_UNKNOWN` items in this order: Security, Contract, Stateful, Other.
2. Print exactly `Updating: UNKNOWN_RESOLUTION.md`.
3. Ask exactly one constrained question.
4. The question must mention the affected `DRIFT-###`.
5. Append the answer and decision to `UNKNOWN_RESOLUTION.md`.
6. Repeat until all such items are resolved or explicitly deferred.

Required structure:

```text
# Unknown Resolution Report

## Initial Snapshot
- Total unknowns:
- Initial unresolved count:
- Snapshot timestamp:

---

## Resolution Log

### UNKNOWN-###
- DRIFT Reference:
- Original Description:
- Priority Class: [Security | Contract | Stateful | Other]
- Classification: [RESOLVED_BY_CODE | RESOLVED_BY_HISTORY | SPEC_GAP | DESIGN_DECISION_REQUIRED | TRUE_UNKNOWN | DEFERRED_BY_USER]
- Resolution or Decision:
- Evidence:
- User Answer: [None | text]
- Impacted Components:
- Phase 3 Blocking Status: [BLOCKED | NOT_BLOCKED]
- Next Step:

---

## Decision Log

### DECISION-###
- DRIFT Reference:
- Question:
- User Answer:
- Final Decision:
- Impacted Components:

---

## Gap Log

### GAP-###
- DRIFT Reference:
- Description:
- Missing Spec Detail:
- Suggested Spec Addition:

---

## Blocker Log

### BLOCKED-###
- DRIFT Reference:
- Reason Blocked:
- Required Before Phase 3: YES
```

Phase 2 is complete only if every `DESIGN_DECISION_REQUIRED` or `TRUE_UNKNOWN` item is resolved, explicitly deferred, or logged as blocked, and no blocking item remains unresolved.

## Phase 3 — Drift Reconciliation

Inputs:

- `SPEC_DRIFT_REPORT.md` read-only
- `UNKNOWN_RESOLUTION.md` read-only

Output file: `SPEC_DRIFT_REPORT_RESOLVED.md`

First line:

```text
# Spec vs Implementation Drift Report (Resolved)
```

Required actions:

1. Reconcile each original `DRIFT-###` using the most specific applicable Phase 2 result.
2. Reclassify each active drift item into exactly one of:
   - `Missing Implementation`
   - `Behavioral Mismatch`
   - `Over-Implementation`
   - `Documentation Drift`
   - `Confirmed Spec Gap`
3. Assign exactly one required action: `UPDATE_CODE`, `UPDATE_SPEC`, or `UPDATE_DOCS`.
4. Assign exactly one resolution source: `CODE_ANALYSIS`, `GIT_HISTORY`, or `USER_DECISION`.
5. Deduplicate by preserving the lowest-numbered `DRIFT-###`.

Hard stop rule:

- if any spec/code disagreement still lacks a user decision, explicit user deferment, or conclusive history result at Phase 3 start, stop and emit a blocker report instead of producing the file

Required structure:

```text
# Spec vs Implementation Drift Report (Resolved)

## Executive Summary
- Total issues (active + invalidated)
- By classification
- By required action
- High-risk areas

---

## Final Drift Report

### DRIFT-###
- Category:
- Source of Truth Reference:
- Code Reference:
- Documentation Reference:
- Description:
- Evidence:
- Resolution Source: [CODE_ANALYSIS | GIT_HISTORY | USER_DECISION — cite COMMIT-SHA, DECISION-###, or UNKNOWN-###]
- Required Action: [UPDATE_CODE | UPDATE_SPEC | UPDATE_DOCS]
- Notes:

---

## Invalidated Issues

### DRIFT-###
- Reason:
- Supporting Evidence:
- Resolution Reference:

---

## Confirmed Spec Gaps

### GAP-###
- Description:
- Required Spec Addition:
- Impacted Areas:

---

## High-Risk Areas
[List areas with active drift or high-severity issues and cite IDs]
```

Every original `DRIFT-###` must appear in either `Final Drift Report` or `Invalidated Issues`.

## Phase 4 — Code Review

Inputs:

- `SPEC_DRIFT_REPORT_RESOLVED.md` as authority
- full codebase
- `docs/src/` as reference only

Output file: `CODE_REVIEW_REPORT.md`

First line:

```text
# Code Review Report
```

Ground truth:

- `UPDATE_CODE` means spec correct, code wrong
- `UPDATE_SPEC` means code correct, spec wrong
- `UPDATE_DOCS` means behavior correct, docs wrong

Do not re-evaluate drift in this phase.

Required structure:

```text
# Code Review Report

## Executive Summary
- Overall system health
- Top risks (maximum 5, ranked by severity)

---

## Critical Issues (Must Fix)

### ISSUE-###
- DRIFT Reference: [DRIFT-### or None]
- Location:
- Problem:
- Impact:
- Recommended Fix:

---

## Security Findings

### SEC-###
- Area:
- Vulnerability:
- Exploit Scenario:
- Risk Level: [Critical | High | Medium | Low]
- Fix:

---

## Correctness Issues

### BUG-###
- Location:
- Scenario:
- Failure Mode:
- Fix:

---

## Maintainability Issues

### MAINT-###
- Area:
- Problem:
- Why It Matters:
- Suggested Improvement:

---

## Performance Issues

### PERF-###
- Area:
- Problem:
- When It Matters:
- Suggested Optimization:
```

## Phase 5 — Implementation Planning

Inputs:

- `CODE_REVIEW_REPORT.md` as authority
- full codebase
- repository structure

Output file: `IMPLEMENTATION_PLAN.md`

First line:

```text
# Implementation Plan
```

Required actions:

1. Group findings by domain, runtime/process boundary, dependency coupling, risk concentration, and file exclusivity.
2. Create one worktree group per execution unit.
3. Branch every worktree from the Phase 0 integration branch.
4. Pre-validate file exclusivity.
5. Define execution order and critical path.
6. Define explicit execution waves so every worktree belongs to exactly one wave.

File exclusivity rules:

- a file may belong to only one parallel worktree
- if two worktrees need the same file, merge them or sequence them
- if ownership cannot be proven, sequence instead of parallelize

Required structure:

```text
# Implementation Plan

## Executive Summary
- Total worktree groups:
- Parallelization level:
- Critical path length:
- Integration branch:

---

## File Exclusivity Validation
- Conflicts found: [Yes / No]
- Resolutions applied:

---

## Worktree Groups

### WORKTREE-###
- Name:
- Branch Name:
- Domain:
- Runtime / Service:
- Related Issue IDs:
- Branch from: [integration branch name]

#### Scope
#### Files Affected
#### Required Changes
#### Acceptance Criteria
#### Risk Level: [Low | Medium | High]
#### Dependencies
#### File Conflict Notes
#### Subagent Instructions

## Execution Plan

### Execution Waves

#### Wave N
- Worktrees: [list of `WORKTREE-###` executed concurrently in this wave]
- Entry Criteria:
- Notes:

### Parallel Worktrees
### Sequential Worktrees
### Critical Path

---

## Merge Strategy
- Integration branch:
- Integration order into integration branch:
- Integration discipline: each worktree is reviewed and validated in its own branch, then its approved commit boundary is cherry-picked onto the current integration branch tip. After all worktrees are integrated, the integration branch is rebased onto `dev` if `dev` has moved, then merged.
- Conflict hotspots:
- Cherry-pick eligible: [Yes / No]
```

At Phase 5 completion, `PIPELINE_STATE.md` must populate the worktree registry with every `WORKTREE-###` at status `NOT_STARTED`.

## Phase 6 Entry — Summary Gate

After writing `IMPLEMENTATION_PLAN.md`, stop and present this exact summary in conversational prose:

```text
## Ready to Execute — Phase 6 Summary

**Pipeline phases complete:** 0 through 5
**Files written:** [list all output files]

**What was found:**
- [N] drift items ([breakdown by category])
- [N] code review findings ([Critical / Security / Bug / Maint / Perf counts])

**Execution plan:**
- [N] worktrees total
- [N] can run in parallel, [N] must run sequentially
- Execution waves: [Wave 1: WORKTREE-###, WORKTREE-###; Wave 2: WORKTREE-###; ...]
- Critical path: [WORKTREE-### → WORKTREE-### → ...] ([N] steps)
- Integration branch: [name]
- Target branch: `dev`
- Default final landing method before initial release: `git merge --ff-only` to `dev`
- PR mode: after initial release, including runs that start after release or
  create the initial release during Phase 6

**Worktrees at a glance:**
- WORKTREE-001 — [name] — [Risk] — [N files] — depends on: [None / ###]
  [1-2 sentence summary of what this worktree changes and why]
- WORKTREE-002 — [name] — [Risk] — [N files] — depends on: [None / ###]
  [1-2 sentence summary of what this worktree changes and why]

**Risks requiring attention:**
- [Any High/Critical findings or worktrees]

To begin execution, run `/project-alignment-execute`.
To cancel or adjust, reply with your changes.
```

Do not proceed beyond Phase 5. After presenting the Phase 6 entry summary,
wait for the user to invoke `/project-alignment-execute` or reply with changes.

## Phase 6 — Execution Handoff

This command stops before Phase 6 implementation work begins.

Next commands:

1. Use `/project-alignment-execute` to begin worktree execution.
2. Use `/project-alignment-land` after `/project-alignment-execute` reports that
   every worktree is `MERGED`.

Success definition for this command:

- Phases 0 through 5 are `COMPLETE`
- `IMPLEMENTATION_PLAN.md` exists and defines the worktree execution plan
- `PIPELINE_STATE.md` has Phase 6 set to `NOT_STARTED`
- the Phase 6 entry summary has been presented to the user
