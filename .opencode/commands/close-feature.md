---
description: Reconcile a completed feature before PR
agent: build
---

Use this command when implementation is complete and the feature must be reconciled with the docs before merge.

Use the user's message as the feature close-out input.

## Supported Modes

- `/close-feature`
  - run close-out only
- `/close-feature merge`
  - run close-out first
  - if the result is `ready for PR`, run `wt merge --no-squash --no-rebase`
  - then run `wt remove feat/<feature-name>`
- `/close-feature pr`
  - run close-out first
  - if the result is `ready for PR`, create a GitHub pull request with `gh pr create`

## Required Behavior

1. Ensure work is happening in the correct feature worktree on branch `feat/<feature-name>`.
2. If the active worktree is not the intended feature worktree, switch to it before close-out work begins.
3. Verify that the active worktree is now on `feat/<feature-name>` before proceeding.
4. Review delivered implementation changes and the feature spec.
5. Confirm `T999` covers final reconciliation work.
6. Compare delivered behavior with:
   - feature `design.md`
   - feature `tasks.md`
   - affected system docs under `docs/src/`
7. Identify any remaining mismatches between implementation and docs.
8. Update straightforward documentation or feature-spec mismatches directly when the intended final behavior is clear from the implementation.
9. Run a second-agent reconciliation review focused on correctness, docs alignment, security-sensitive regressions, and maintainability risks in the delivered scope.
10. Run default validation with `hk check -a` when implementation changed, plus any feature-specific validation that the feature docs or task list require.
11. Confirm the feature is ready for pull request review into `dev`.
12. If mode is `merge` or `pr`, perform that action only after the close-out result is otherwise `ready for PR`.

## Execution Rules

- Inspect the delivered implementation before deciding that docs are correct.
- If `wt` does not land in the intended feature worktree, stop before close-out work begins.
- Do not silently ignore unresolved mismatches between code and docs.
- If the feature is not ready for PR, say exactly what remains open.
- If intended feature changes remain uncommitted and the final behavior is clear, create the final reconciliation commit before returning `ready for PR`.
- If intended feature changes remain uncommitted but the correct commit boundary is not clear, return a non-ready decision and say exactly what must be committed before PR review.
- Treat extra user input after `/close-feature` as an optional action mode. Supported modes are `merge` and `pr` only.

## Review Rules

- The second-agent review must use the `task` tool with `subagent_type: general`.
- The review must focus on final docs/implementation reconciliation, quality risks, security issues, and maintainability concerns.
- If the review finds actionable problems, address them before returning `ready for PR`.

## Validation Rules

- Default to `hk check -a` when implementation changed.
- Also run any narrower or additional feature-relevant validation required by the feature spec, task list, or affected docs.
- If validation remains incomplete, state exactly what remains and why.

## Action Rules

- With no action mode, do not merge or open a PR.
- For `merge` mode:
  - use `wt merge --no-squash --no-rebase`
  - only remove the feature worktree after the merge succeeds
  - then run `wt remove feat/<feature-name>`
- For `pr` mode:
  - use `gh pr create`
  - set the title to `feat: <feature-name in lowercase>`
  - use the close-out output's concise PR summary bullets as the PR body
  - return the PR URL
- If close-out does not reach `ready for PR`, do not run `wt merge`, `wt remove`, or `gh pr create`.

## Return

1. unresolved mismatches with file references
2. docs that were updated or still need updates
3. validation performed and remaining gaps
4. second-agent reconciliation review findings and fixes applied
5. changes applied directly during close-out, if any
6. readiness decision: `ready for PR`, `ready after docs reconciliation`, or `blocked by implementation/docs mismatch`
7. concise PR summary bullets if the feature is ready
8. action taken for `merge` or `pr` mode, if any
9. PR URL for `pr` mode, if created
