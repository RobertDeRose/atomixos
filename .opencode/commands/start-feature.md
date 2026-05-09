---
description: Start a new feature with the repo workflow
agent: build
---

Use this command when beginning a new feature specification and implementation flow.

Use the user's message as the feature input.

## Inputs

- feature name
- feature goal
- optional affected docs
- optional constraints
- optional non-goals
- optional project plan in `docs/src/planned-features.md`

## Required Behavior

1. If `docs/src/planned-features.md` exists, read it before asking feature-design questions.
2. If the requested feature appears in `docs/src/planned-features.md`, use that feature brief as the starting source of intent.
3. If the requested feature is not in the project plan, ask whether to proceed as an unplanned feature or update the project plan first.
4. If no project plan exists and the user does not provide enough input to identify the feature name or intended goal, run a targeted one-feature Q&A before creating the feature spec.
5. Do not guess major design intent when the request is ambiguous.
6. Confirm the feature name is suitable for `docs/src/features/<feature-name>/` and `feat/<feature-name>`.
7. Determine the current branch and worktree context before running `wt`.
8. Use `dev` as the default base branch unless the user explicitly requests another base.
9. Create or switch to the feature worktree from the intended base branch without changing the caller's current worktree branch unnecessarily.
10. Verify that the active worktree is now on `feat/<feature-name>` before creating any feature-spec files.
11. If `wt` does not land in the intended feature worktree, stop and say so before writing files.
12. Do not create `design.md` or `tasks.md` in the current working tree and then copy them into the feature worktree.
13. Create or update only these files in the active feature worktree:
  - `docs/src/features/<feature-name>/design.md`
  - `docs/src/features/<feature-name>/tasks.md`
14. Ensure `tasks.md` begins with `T000` and includes `T999`.
15. Draft the initial feature structure so implementation can proceed without guessing the intended design.
16. At the end of the command, offer exactly two next actions:
  - start `/review-feature-spec` immediately
  - create a draft-spec commit now

## Project Plan Rules

- `docs/src/planned-features.md` is project-level context, not a substitute for feature specs.
- Use planned feature entries to seed `design.md` with project intent, requirements, constraints, non-goals, success criteria, risks, dependencies, and suggested validation.
- Keep the generated feature spec narrower and more concrete than the project plan.
- If the plan contains unresolved questions for the selected feature, ask only the questions needed to make that feature spec safe to draft.
- If no plan exists, ask a smaller version of `/plan-features` questions focused only on the requested feature.

## Worktree Rules

- The feature branch must use `feat/<feature-name>`.
- The feature must live in its own `wt` worktree.
- If the feature worktree does not exist, run `wt switch --create --yes --format json feat/<feature-name> --base <intended-base-branch>`.
- If the feature worktree already exists, run `wt switch --format json feat/<feature-name>`.
- Only avoid running `wt` if the user explicitly asks for planning without execution.
- Do not create the feature worktree from an arbitrary currently checked out branch.
- Do not switch the caller's current worktree back to the default branch just to create the feature worktree if `wt` can branch from the intended base directly.
- Treat stdout from `wt switch --format json` as the authoritative source for the resulting branch and worktree path; ignore the human-readable stderr status lines.
- If the active worktree path or branch still does not match the intended feature worktree after running `wt`, stop instead of writing files in the wrong location.

## Commit Rules

- `/start-feature` does not create a required commit automatically.
- If the user chooses the draft-spec commit path, create one draft-spec commit in the feature worktree.
- If the user chooses to start `/review-feature-spec`, leave the spec changes in the feature worktree for that workflow.

## Return

1. proposed feature name
2. base branch used for worktree creation
3. `wt` command run
4. resulting branch name
5. resulting worktree path
6. project plan source used, if any
7. list of docs/pages likely affected
8. draft `design.md` outline
9. draft `tasks.md` outline including `T000`, implementation tasks, and `T999`
10. next-action choices offered
