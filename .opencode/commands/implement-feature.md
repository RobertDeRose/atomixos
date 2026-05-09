---
description: Implement the next actionable work for a feature
agent: build
---

Use this command to execute a feature from its spec after the feature has been created and reviewed.

Use the user's message as the implementation input.

## Required Behavior

1. Ensure work is happening in the correct feature worktree on branch `feat/<feature-name>` before making changes.
2. If the feature worktree does not exist, run `wt switch --create --yes --format json feat/<feature-name> --base dev` unless the reviewed feature spec explicitly established a different base branch.
3. If the feature worktree already exists, run `wt switch --format json feat/<feature-name>`.
4. Verify that the active worktree is now on `feat/<feature-name>` before making changes.
5. If the feature spec exists only as untracked files in another worktree, stop and tell the user those files must be moved, copied, or committed before implementation can continue safely in the feature worktree.
6. Read the feature `design.md` and `tasks.md` before making code changes.
7. Verify the reviewed feature spec is committed on the feature branch before implementation starts.
8. If the reviewed spec is not committed, do not start coding. Route back through `/review-feature-spec` first and require the reviewed spec commit.
9. Ensure `T000` is complete before implementation proceeds.
10. Select the next actionable task based on task status and dependencies.
11. Implement tasks in dependency order while respecting explicit parallelism information.
12. Update task status in `tasks.md` when that can be done confidently from the implemented state.
13. Run relevant validation for the implemented tasks.
14. Run a second-agent review pass focused on quality, security, and maintainability before reporting the implementation step complete.

## Ambiguity Handling

- Do not guess missing design intent.
- If ambiguity remains after reading the reviewed spec and related docs, do not start coding.
- Route that ambiguity into `/review-feature-spec` instead.
- Pass the questions inline when possible.
- If needed, create a temporary `docs/src/features/<feature-name>/OPEN_QUESTIONS.md`, do not commit it, and remove it after it is no longer needed.

## Execution Rules

- Prefer the smallest correct implementation that satisfies the feature spec.
- Keep docs and implementation aligned in the same unit of work.
- Respect task boundaries when they map cleanly to isolated commits.
- If the user did not specify a task, pick the next actionable one from `tasks.md`.
- Do not implement from the wrong worktree just because the current shell happens to be elsewhere.
- Do not silently strand untracked feature files in another worktree.
- If `wt` does not land in the intended feature worktree, stop before making code changes.
- Treat stdout from `wt switch --format json` as the authoritative source for the resulting branch and worktree path; ignore the human-readable stderr status lines.
- The review pass must use a second agent via the `task` tool with `subagent_type: general`.
- The review pass must focus on quality risks, security issues, and maintainability concerns in the implemented task scope.
- If the review pass finds actionable problems, address them before declaring the task implementation complete.

## Commit Rules

- Invocation of this command is explicit user authorization to create the workflow-required commits for the feature.
- The reviewed feature spec must already be committed before implementation work begins.
- Commit completed task boundaries when practical and when the task maps cleanly to an isolated change.
- Do not ask again for commit confirmation unless the user explicitly asks for a dry run, asks to review before committing, or says not to commit.
- Do not create extra commits outside the feature workflow.

## Completion Guardrails

- Before reporting implementation complete, verify the feature branch is ahead of its base branch when implementation work was performed.
- Before reporting implementation complete, verify intended feature changes are not left uncommitted in the feature worktree.
- If intended feature changes remain uncommitted, create the appropriate workflow commit before declaring the feature ready for review.

## Return

1. feature being implemented
2. `wt` command run and resulting worktree path
3. task or tasks selected
4. reviewed-spec commit verification result
5. changes made
6. validation run
7. second-agent review findings and fixes applied
8. updated task status summary
9. blockers or open questions, if any
