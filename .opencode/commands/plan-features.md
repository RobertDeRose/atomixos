---
description: Plan and prioritize project features
agent: build
---

Use this command to create, refine, and inspect the project feature roadmap in `docs/src/planned-features.md`.

Use the user's message as the feature-planning input.

## Inputs

- initial project requirements, goals, or problem statement
- existing `docs/src/planned-features.md`, if present
- known constraints
- known non-goals
- target users, operators, or consumers
- optional technology preferences
- optional timeline, risk, compliance, or delivery constraints

## Required Behavior

1. Treat this as project and feature-roadmap planning, not implementation work.
2. Do not create feature folders, feature branches, worktrees, commits, or implementation changes.
3. Use `docs/src/planned-features.md` as the durable planning artifact.
4. If `docs/src/planned-features.md` exists, read it before asking questions or making recommendations.
5. If feature specs exist under `docs/src/features/`, compare them with planned feature statuses and report mismatches.
6. If `docs/src/planned-features.md` does not exist, offer to design the first feature plan from the user's requirements.
7. If planned features exist and any are not `completed` or `deferred`, list the incomplete features and recommend the next feature to start.
8. If all planned features are `completed` or `deferred`, offer to design the next set of planned features.
9. Ask targeted questions one at a time when user input is needed.
10. Challenge weak, risky, overbroad, or internally inconsistent requirements directly and explain the tradeoff.
11. Suggest stronger alternatives when challenging a design direction.
12. Identify feature boundaries and call out when a capability should be split, deferred, or merged.
13. Offer to research best practices, current technologies, open source projects, external tooling, or vendor docs when internal repository context is insufficient.
14. If the user accepts research, use external sources and separate researched facts from recommendations.
15. Keep unresolved decisions explicit instead of quietly choosing defaults.
16. End with `docs/src/planned-features.md` updated or with a clear recommendation for the next `/start-feature` invocation.

## Status Rules

Each planned feature should use one status:

- `planned`: feature is identified but no feature spec exists yet
- `in-spec`: feature spec is being drafted or reviewed
- `in-progress`: implementation has started
- `completed`: feature has passed close-out and docs agree with delivered behavior
- `deferred`: feature is intentionally postponed and should not be recommended next

## Planning Artifact

Create or update only:

- `docs/src/planned-features.md`

The file should be human-readable and useful to agents. Use this shape:

```md
# Planned Features

## Project Overview

## Goals

## Non-Goals

## Global Constraints

## Cross-Cutting Decisions

## Open Questions

## Feature Map

### `<feature-name>`

- Status: planned
- Overview:
- Requirements:
- Constraints:
- Non-goals:
- Success criteria:
- Risks and tradeoffs:
- Dependencies:
- Suggested validation:
- Suggested first workflow command: `/start-feature <feature-name>`
```

## Recommendation Rules

- Recommend the next feature by balancing dependency order, risk reduction, project value, and implementation readiness.
- Prefer features that unblock later work or retire major design uncertainty.
- Do not recommend `deferred` features unless the user explicitly asks to revisit them.
- If multiple features are equally plausible, explain the tradeoff and ask the user to choose.
- If a planned feature has unresolved project-level questions, ask only the questions needed to decide whether it can move to `/start-feature`.

## Brainstorming Rules

- Prefer questions that reduce implementation risk, not broad surveys.
- Ask about users, success criteria, data ownership, operational model, security boundaries, failure modes, rollout strategy, validation, and non-goals when relevant.
- Do not ask every possible question up front.
- If a requirement is too large for one feature, propose a phased breakdown.
- If a technology choice is premature, identify the decision criteria before recommending tools.
- If a requirement conflicts with existing repository direction, say so and cite the relevant docs.

## Challenge Rules

- Challenge requirements that create unclear ownership, hidden operational burden, security risk, excessive coupling, untestable behavior, or scope creep.
- Do not treat the user's first idea as final when a simpler or safer design exists.
- Do not block on perfection; identify the smallest set of decisions needed to update the feature map safely.
- Distinguish hard blockers from choices that can be deferred into an individual feature spec.

## Research Rules

- Offer research before relying on external best practices, vendor behavior, or rapidly changing technology assumptions.
- Research is optional unless the user asks for it.
- Prefer official docs, active open source projects, and current ecosystem evidence.
- Summarize sources by relevance and explain how they affect the project design.
- Do not let research replace repository source-of-truth docs.

## Return

1. planning artifact status: created, updated, unchanged, or missing
2. planned feature status summary
3. incomplete planned features
4. existing feature-spec/status mismatches, if any
5. challenged assumptions and design changes made
6. questions asked and answers received
7. research performed or offered
8. recommended next feature and rationale
9. recommended next workflow command
10. unresolved project-level questions
