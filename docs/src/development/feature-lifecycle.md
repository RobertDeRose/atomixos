# Feature Lifecycle

A feature moves from design to delivery through a fixed set of steps, tracked in Beads. Each kind of information has
one home:

```text
Beads                                      executable state, dependencies, and delivery history
docs/src/features/<slug>/design.md         intended feature behavior and design
reader-facing pages under docs/src/        current supported behavior
code and tests                             implementation evidence
docs/src/features/<slug>/index.md          delivered capability and deviations from the design
```

The workflow commands come from the `RobertDeRose/dstack` skills, installed with the `skills` CLI, which manages the
agent-specific installation paths and updates.

## Start a session

```bash
bd prime
bd ready --type epic --label workflow:feature --json --limit 0
bd ready --json
```

## Plan

`/plan-features` asks the questions that change the design, decides which documentation pages each feature touches,
writes a design per feature, and creates one Beads epic per feature with lifecycle and implementation child tasks.
Planning settles every decision the tasks need before implementation starts. It recommends the next feature by slug
and human name rather than by Beads ID.

A feature is identified by an immutable lowercase slug, used for both its design and its branch:

```text
docs/src/features/feature-slug/design.md
feat/feature-slug
```

## Review and start

`/start-feature <slug>` resolves the feature through Beads (an exact name or a unique name fragment also works),
activates its worktree, and runs four isolated reviews.

The feature root is an epic. Lifecycle tasks are its direct children, and bounded implementation tasks sit beneath the
implementation coordinator task.

One fresh, read-only context builder gathers a factual evidence packet. Four fresh reviewers share that packet and
independently cover:

1. architecture consistency;
2. simplicity and maintainability;
3. documentation readiness;
4. execution-graph readiness.

The packet contains source locations and facts, but no findings, recommendations, or verdict. Reviewers read more
source when the packet is not enough. After a fix, only the affected reviewers are resumed; a fresh replacement is used
only when the original is unavailable or the scope changed materially, and it receives the original packet plus the
post-review diff. The shared packet is refreshed only after broad design, architecture, task-graph, or
documentation-structure changes.

The command then reconciles clear findings, asks only blocking design questions, commits the reviewed design, and
closes the specification-reconcile gate once implementation can proceed without inventing intent. It records the
feature in repository-local Git configuration, so `/implement-feature` can resume it without a selector.

## Implement

Claim the next ready task beneath the implementation coordinator:

```bash
bd ready --parent <implementation-id> --claim --json
bd show <task-id> --json
```

For each task:

1. Keep code, tests, and affected documentation aligned in the same unit of work.
2. Validate, and get exactly one fresh review; fixes resume that reviewer.
3. Record validation and review evidence in Beads.
4. Commit with the Beads ID in the `Beads:` footer.
5. Close the task only after its acceptance criteria pass.

`/implement-feature` keeps claiming the next ready child until the implementation coordinator closes. It pauses only
when every remaining child is blocked on an explicit user decision.

Use `parent-child` dependencies for hierarchy and `blocks` only for real prerequisites. Record work you discover along
the way with its provenance:

```bash
bd create "Describe discovered work" \
  --type task \
  --deps discovered-from:<current-task-id> \
  --json
```

Add a blocking edge only when the discovered work is required to finish safely.

## Close

`/close-feature` compares the delivered code with the design and the reader-facing pages, writes the feature's
`index.md` record, and runs validation. One fresh context builder supplies a packet to two fresh reviewers, one for
delivery and one for documentation drift, following the same review rules as above.

It then performs one explicit delivery action: create a pull request, merge, or leave the feature ready. With no mode,
it asks which. Merging into `dev` keeps history linear: it fast-forwards with `git merge --ff-only` and never falls
back to a merge commit.

Beads may append rows for the feature to the tracked `.beads/interactions.jsonl` in the base worktree during close-out.
Before merging, the command verifies that this is the only dirty path, that every change is append-only, and that each
row belongs to the feature or to work linked back to it. It commits those rows on the feature branch before restoring
the base copy. Rows written by the closures after the merge get their own interaction-only commit on the base branch.
Any other dirty state blocks the merge.

## Audit

`/audit-project` periodically compares Beads, designs, reader-facing pages, implemented-feature records, code, tests,
and recent commits. Every drift it finds becomes linked Beads work.

## Skill maintenance

After editing a canonical skill, refresh the installed copies:

```bash
npx skills update
```
