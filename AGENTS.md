# AGENTS

Start here when working in this repository.

## Ground Rules

- Prefer the smallest correct change.
- Keep documentation and implementation aligned in the same unit of work.
- Do not treat a task as complete if docs, specs, and code disagree.

## Commit Guidance

- Use Conventional Commits.
- Follow the Conventional Commits 1.0.0 shape: `<type>[optional scope]: <description>`.
- The repo-local `hk` `commit-msg` hook enforces the conventional format and line-length limits configured in
  `package.json`.

### Supported Scopes

- Prefer one of these scopes when a commit is primarily about a single area:
  - `modules`
  - `nix`
  - `scripts`
  - `tests`
  - `docs`
  - `spec`
  - `ci`
  - `tooling`
  - `repo`
- Keep scopes as narrow as possible.
- Prefer separate commits per concern when the work can be split cleanly.
- Use `repo` for rare, truly cross-cutting changes that must land together.
- For cross-cutting commits, use the body to explain why the change spans multiple areas and what parts moved together.

### Subject

- Keep the subject clear first, short second.
- Keep the subject within the enforced `commitlint` limit.

### Body

- For nontrivial changes, include a body.
- Use the body to explain why the change exists and summarize the important parts.
- Keep body lines within the enforced `commitlint` limit.

### Multiline Input

- Prefer `stdin` `heredocs` for multiline command input when the tool supports it, such as `-F -` or `--file -`.
- Example:

  ```text
  git commit -F - <<'EOF
  subject

  multiple line paragraph under 100 characters wide

  - prefer markdown list for concise changes
  ````

- Use process substitution only when the command requires a real filepath.
- Prefer this to reduce quoting and spacing mistakes in commit messages and other structured text.

### Allowed Types

- `build`
- `chore`
- `ci`
- `docs`
- `feat`
- `fix`
- `perf`
- `refactor`
- `revert`
- `style`
- `test`

Reference:

- `https://www.conventionalcommits.org/en/v1.0.0/`

<!-- BEGIN DSTACK WORKFLOW -->
## dstack workflow

### Session start

Run before selecting work:

```bash
bd prime
bd ready --type epic --label workflow:feature --json --limit 0
bd ready --json
```

Select features by canonical `<slug>` or human name through the dstack lifecycle skills. Use the Beads ID returned by
the skill for mutations, but do not expose an opaque hash as the primary workflow command. Inspect selected work with
`bd show <id> --json` and read structured metadata before prose.

### Sources of truth

- **Beads** owns executable work state, dependencies, priorities, claims, findings, and evidence.
- **`docs/src/features/<slug>/design.md`** owns intended feature behavior, boundaries, decisions, validation, and
  documentation impact.
- **Reader-facing pages under `docs/src/`** own current supported behavior.
- **`docs/src/features/<slug>/index.md`** owns delivered-feature reconciliation and audit history.
- **`docs/src/planned-features.md`** is the human roadmap; Beads remains authoritative for live state.
- **Code and tests** provide implementation evidence.

Use Beads instead of Markdown TODO lists for executable work. Use `bd remember` for durable cross-feature knowledge.

### Feature identity

Use an immutable lowercase filesystem-safe slug as each feature identity:

```text
docs/src/features/first-capability/
feat/first-capability
```

Each feature is one Beads epic (a poured molecule uses epic hierarchy with workflow semantics). Store `feature_slug`,
`feature_name`, `design_path`, `implemented_path`, and `base_branch` on that root. Put lifecycle tasks and bounded
implementation tasks beneath the epic. The implementation coordinator remains a task gate, not a second feature or
milestone. Roadmap order and dependencies remain explicit rather than encoded in feature identity.

Start features with a human reference, for example:

```text
/start-feature first-capability
/start-feature "First capability"
```

### Documentation placement

Place documentation by reader intent:

- **Introduction**: purpose, audience, scope, boundaries, and conventions.
- **Architecture**: structure, ownership, interactions, invariants, and durable decisions.
- **Operator's Manual / Usage**: use, deployment, configuration, observability, maintenance, recovery, and
  troubleshooting where applicable.
- **Development Guide**: build, testing, extension, migration, and maintenance.
- **Reference**: exact commands, configuration, interfaces, schemas, fields, states, defaults, limits, terminology, and
  acceptance contracts.
- **Implemented Features**: one standalone delivery and audit record per completed feature.

Create project-specific pages only for durable reader needs. Feature designs name exact pages, not only documentation
sections.

### Workflow skills

Install or refresh dstack skills with:

```bash
npx --yes skills@1.5.16 add RobertDeRose/dstack
npx skills update
```

The workflow commands are:

```text
/setup-project
/update-project
/plan-features
/start-feature
/implement-feature
/close-feature
/audit-project
```

The Skills CLI manages skill files. Copier manages this repository scaffold through `.copier-answers.yml`.

### Beads lifecycle

The project-local formula is `.beads/formulas/dstack-feature.formula.toml`. It defines interactive design, isolated
specification reviews, specification reconciliation, implementation, documentation reconciliation, validation, holistic
close-out reviews, and explicit delivery.

Use dependency types intentionally:

- `blocks`: a real prerequisite that affects readiness;
- `parent-child`: hierarchy only;
- `related`: contextual association;
- `discovered-from`: provenance for work found during execution.

Use issue types intentionally. Feature roots are `epic`; lifecycle gates and ordinary bounded work are `task`; known
defects are `bug`; timeboxed fact-finding with explicit exit criteria is `spike`; durable architecture or product
choices are `decision`; and maintenance is `chore`. Use `feature` for standalone enhancements outside a feature epic.
Introduce `story` only when the repository actually manages a user-story backlog, and `milestone` only as a work-free
aggregate. Labels and metadata, not extra issue types, own workflow phase and review role.

For each implementation task: claim it atomically, load only relevant design and documentation context, implement the
smallest complete scope, update documentation in the same work unit, validate, run an isolated
quality/security/maintainability review, record evidence, commit with the Beads ID, and close only after acceptance
criteria pass. Use focused checks while iterating. Run the full repository suite once after review fixes stabilize and
before commit; rerun it only after a failure or a later broad/shared fix.

### Review orchestration

Initial reviewers always use fresh context. A workflow with two or more review roles first launches exactly one fresh,
read-only context builder. It writes an ephemeral factual packet covering authority, requirements, architecture, changed
files, Beads state, documentation impact, validation evidence, and exact source locations. The packet contains no
findings, recommendations, or verdict and is never committed.

Pass that same packet to each fresh role reviewer. Reviewers reason independently, verify role-critical evidence, and
read extra source only when the packet is insufficient. `/implement-feature` uses one fresh reviewer per task without a
context builder; `/start-feature` uses one context builder plus four reviewers; `/close-feature` uses one context
builder plus two reviewers. Do not add confidence reviewers without a distinct uncovered risk or an explicit user
request.

After a fix, resume only the original reviewers whose domains changed. Do not launch fresh follow-up reviewers unless
the original cannot be resumed or the fix materially changes the review scope. Give a replacement the original packet
when one exists, plus findings, resolutions, and the post-review diff. Refresh the shared packet only after broad
design, architecture, task-graph, or documentation-structure changes.

### Execution efficiency

Do bounded work directly in the controlling session. Launch subagents only when a lifecycle explicitly requires them,
the user asks for delegation, or a distinct independent risk materially benefits from parallel read-only work. Do not
launch a scout, planner, or reviewer merely to save parent context, and never add unrequired confidence reviews.

Reuse existing context packets, review results, and validation evidence while their inputs remain unchanged. After a
fix, resume the affected reviewer instead of starting a replacement. Do not rerun a successful check unless relevant
inputs changed; use one focused check while iterating and one full suite after review fixes stabilize.

Keep verbose output out of the conversation context. Redirect long command output to an ephemeral file, inspect only the
relevant failure excerpt, and report the command, result, and artifact path. Do not poll background work; continue
useful work or use event-driven waiting.

### Commit messages

Every changelog-visible `feat`, `fix`, `perf`, or `refactor` subject must use `<type>(<scope>): <summary>` or
`<type>(<scope>)!: <summary>`. Omitted internal types may be unscoped; release commits use `release: vX.Y.Z`. Choose the
owning subsystem, not a feature number or incidental file name. If `cog.toml` gains a scope allowlist, document the
scope taxonomy in README when present (otherwise the tooling reference) and update this guidance at the same time.

When a body records multiple discrete changes, decisions, or validation results, prefer a Markdown `-` list with one
idea per item. Use prose when sequence, causality, or rationale cannot be adequately expressed as a list; do not force a
body when the subject is sufficient.

For multiline messages, write the message to a temporary file and use `git commit -F <file>`; one argument containing
literal newlines is also valid. A single `-m` is acceptable only for a subject-only commit. Never construct bodies with
multiple `-m` flags or escaped `\n` text. Verify the resulting message before recording its SHA in Beads.

### Worktrees and delivery

Feature branches use `feat/<slug>`. When `wt` is available, treat JSON output from `wt switch --format json` as
authoritative for branch and path.

Only fast-forward merges into `dev` are accepted. Use `git merge --ff-only`; never create a merge commit and never fall
back to one when fast-forwarding fails.

A no-mode `/close-feature` completes close-out and then asks for one explicit action:

```text
create PR
merge
leave ready with no delivery action
```

<!-- END DSTACK WORKFLOW -->
