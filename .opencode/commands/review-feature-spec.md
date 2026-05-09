---
description: Review a feature spec against the repo docs
agent: build
---

Use this command after a feature has an intended design but before implementation proceeds too far.

Use the user's message as the feature review input.

## Inputs

- feature `design.md`
- feature `tasks.md`
- optional additional user content
- optional temporary `OPEN_QUESTIONS.md` in `docs/src/features/<feature-name>/`

## Required Behavior

1. Read the feature `design.md` and `tasks.md`.
2. Read affected docs under `docs/src/` before making a readiness decision.
3. If the invocation includes additional user content or a temporary `OPEN_QUESTIONS.md`, treat that material as review input.
4. Compare the intended feature behavior against current repository docs and current codebase direction.
5. Identify conflicts, stale documentation, assumptions, risks, non-goals, breaking changes, missing affected-doc updates, missing dependency or parallelization information, weak validation criteria, and missing reconciliation bookends.
6. Update the feature spec directly when the needed fixes are clear, local, and do not require a policy decision from the user.
7. Separate what was resolved directly from what still requires user input.
8. When real design ambiguity remains, ask targeted questions one at a time and resolve them interactively before returning the final readiness decision.
9. Make recommendations based on current repository direction first, current docs context second, and external guidance third.
10. Offer to do external research for best practices or external tooling docs when internal repo evidence is not sufficient.
11. When the review reaches an implementation-ready state, the reviewed spec must be committed on the feature branch.
12. If unresolved questions remain, do not return `ready to implement`.

## Commit Rules

- If the spec has not been committed yet, create the reviewed-spec commit when the review reaches a ready state.
- If the spec was committed as a draft and the reviewed-spec result is ready, amend that draft-spec commit only when all of the following are true:
  - the draft commit was created by this workflow
  - the draft commit has not been pushed or shared
  - the draft commit boundary still matches the reviewed-spec boundary cleanly
- If any of those conditions are not true, create a new reviewed-spec commit instead of amending.
- If the spec was previously committed not as a draft and the review changes the spec, create a new commit for those review changes.
- If the review does not reach a ready state, do not create a ready-spec commit.

## Temporary Question File Rules

- `OPEN_QUESTIONS.md` is a temporary workflow artifact only.
- Do not commit `OPEN_QUESTIONS.md`.
- Remove it after its contents are resolved or no longer needed.
- If passing questions inline is simpler, do that instead of creating the file.

## Execution Rules

- Do not invent missing design intent.
- Ask questions one at a time when user input is required.
- Make it explicit which findings were resolved directly, which remain open, and why.
- If `OPEN_QUESTIONS.md` was used, remove it before returning a ready state.
- If the feature is not ready, say exactly what must change before implementation should proceed.

## Return

1. findings ordered by severity with file references
2. list of affected docs/pages
3. issues resolved directly during review
4. targeted questions asked and user answers received, if any
5. remaining open questions and assumptions
6. recommended updates to `design.md`
7. recommended updates to `tasks.md`
8. repo-direction recommendation with supporting rationale
9. optional external-research offer when applicable
10. changes applied directly to the feature spec, if any
11. commit action taken for the reviewed spec, if any
12. explicit readiness decision: `ready to implement`, `ready after spec fixes`, or `blocked by unresolved design conflict`
