# Feature lifecycle

## Responsibilities

```text
Beads                                            executable state and dependencies
docs/src/features/<slug>/design.md         intended feature behavior and design
reader-facing docs under docs/src/               current supported behavior
code and tests                                   implementation evidence
docs/src/features/<slug>/index.md          delivered reconciliation and audit record
```

Workflow commands are installed from `RobertDeRose/dstack` with the `skills` CLI. The CLI manages the agent-specific
installation paths and updates; Copier manages this repository scaffold.

## Start a session

```bash
bd prime
bd ready --type epic --label workflow:feature --json --limit 0
bd ready --json
```

## Plan

`/plan-features` asks design-changing questions, defines the documentation architecture, creates slug-named feature
designs, pours one Beads epic/molecule per feature, and decomposes lifecycle and implementation into bounded child
tasks. Native planning resolves every decision needed by those tasks before implementation; unresolved decision gaps may
remain only on imported migration work with explicit reconciliation blockers. It recommends the next feature by
canonical slug and human name rather than by an opaque Beads hash.

A new feature uses:

```text
docs/src/features/feature-slug/design.md
feat/feature-slug
```

## Review and start

`/start-feature <slug>` resolves the human feature reference through Beads, activates the worktree, and runs four
isolated reviews. An exact feature name or a unique name fragment also resolves; the Beads ID remains internal
mutation/audit evidence.

The feature root is an epic. Lifecycle tasks are direct children, and bounded implementation tasks sit beneath the
implementation coordinator task. A milestone is not used as the feature container.

One fresh, read-only context builder gathers a factual evidence packet once. Four fresh reviewers share that packet and
independently cover:

1. architecture consistency;
2. simplicity and maintainability;
3. documentation readiness;
4. execution-graph readiness.

The packet contains factual source locations but no findings, recommendations, or verdict. Reviewers read extra source
when it is insufficient. Do not add confidence reviewers without a distinct uncovered risk or user request. Fix
verification resumes only affected reviewers; fresh replacements are used only when an original is unavailable or the
scope materially changes, and receive the original evidence and post-review diff. Refresh a shared packet only after
broad design, architecture, task-graph, or documentation-structure changes.

It reconciles clear findings, asks only blocking design questions, commits the reviewed design, and closes
`spec-reconcile` only when implementation can proceed without inventing intent. A successful start records the canonical
feature in repository-local Git configuration so `/implement-feature` can resume it from the base worktree when no
selector is supplied.

## Implement

Claim the next ready task beneath the implementation coordinator:

```bash
bd ready --parent <implementation-id> --claim --json
bd show <task-id> --json
```

Use `parent-child` for hierarchy and `blocks` only for real prerequisites. Keep code, tests, and affected documentation
aligned in the same work unit. Record validation and review evidence, include the Beads ID in the commit message, and
close the task only after its acceptance criteria pass. Each task gets exactly one fresh reviewer; fixes resume that
reviewer. A fresh replacement is allowed only when the original is unavailable or scope materially changes.
`/implement-feature` then claims the next ready child and continues until the implementation coordinator closes. It
pauses only when every remaining child is blocked on explicit user decisions; native planned work should never reach
that state.

Discovered work should retain provenance:

```bash
bd create "Describe discovered work" \
  --type task \
  --deps discovered-from:<current-task-id> \
  --json
```

Add a blocking edge only when the discovery is required for safe completion.

## Close

`/close-feature` compares delivered code with the design and reader-facing docs, creates a standalone
implemented-feature record, and runs validation. One fresh context builder supplies a factual packet to two fresh
holistic reviewers for delivery and drift. They follow the neutrality, extra-source, refresh, confidence-review, and
replacement rules above; fixes resume only the affected reviewer. The workflow then performs an explicit `pr`, `merge`,
or `ready` action. With no mode, it asks which action to take. Merge mode uses `git merge --ff-only` unless the target
repository's `AGENTS.md` explicitly permits merge commits; it never falls back to a merge commit after a failed
fast-forward. Native Beads can append selected-feature rows to the tracked `.beads/interactions.jsonl` in the base
worktree during close-out. Merge mode verifies that this is the only dirty path and that every change is append-only and
belongs to the selected feature molecule or separately identified work with a `discovered-from` or `parent-child` path
back to it, commits those rows on the feature branch, and restores the base copy only after committed preservation.
Delivery and root closures happen after the merge; their interaction rows receive a separate interaction-only commit on
the base branch. Malformed, rewritten, foreign, or mixed dirty state remains blocking.

## Audit

`/audit-project` periodically compares Beads, designs, current docs, implemented-feature records, code, tests, and
recent commits. Drift becomes linked Beads work rather than an untracked note.

## Skill maintenance

After editing a canonical skill:

```bash
npx skills update
```
