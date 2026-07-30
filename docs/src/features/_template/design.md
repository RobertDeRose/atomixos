# Design — {{ feature_name }}

## Metadata

- Beads feature root: `{{ beads_root_id }}`
- Feature slug: `{{ feature_slug }}`
- Design path: `docs/src/features/{{ feature_slug }}/design.md`
- Implemented record: `docs/src/features/{{ feature_slug }}/index.md`
- Base branch: `{{ base_branch }}`
- Status: draft

## Feature Summary

## User Intent

Preserve concrete user wording, examples, expectations, constraints, and rejected directions that should shape
implementation.

## Goals

## Non-Goals

## User-Facing Behavior

## Requirements

### Functional Requirements

### Quality Requirements

### Compatibility and Migration Requirements

## Existing Context

Describe the current implementation, relevant documentation, related completed features, constraints, and established
patterns this design builds upon.

## Proposed Design

Explain the smallest complete design. Cover only the concerns that apply, such as boundaries, ownership, components,
data or state, control flow, interfaces, configuration, security, failure behavior, recovery, and observability.

## Architecture Consistency

### Existing Patterns Reused

### Invariants Preserved

### New Decisions Introduced

### Architecture Documentation Changes

## Operational Considerations

Describe usage, deployment, configuration, observability, maintenance, recovery, or support implications where
applicable.

## Documentation Impact

Name exact pages, not only sections. Mark whether each page exists or must be created. Every new durable page must be
registered in `docs/src/SUMMARY.md`.

| Documentation concern      | Exact page                                      | Create or update                   | Planned change                      | Owning Beads task |
|----------------------------|-------------------------------------------------|------------------------------------|-------------------------------------|-------------------|
| Introduction               |                                                 |                                    |                                     |                   |
| Architecture               |                                                 |                                    |                                     |                   |
| Usage / Operations         |                                                 |                                    |                                     |                   |
| Development                |                                                 |                                    |                                     |                   |
| Reference                  |                                                 |                                    |                                     |                   |
| Navigation                 | `docs/src/SUMMARY.md`                           | Update if pages are added or moved |                                     |                   |
| Implemented Feature Record | `docs/src/features/{{ feature_slug }}/index.md` | Create during close-out            | Preserve delivery and audit history |                   |

Remove non-applicable rows or mark them `Not applicable` with a brief reason.

## Validation Strategy

List commands, test layers, manual checks, migration checks, failure-injection checks, and acceptance evidence.

## Implementation Decomposition

Summarize the intended slices. Beads is authoritative for executable tasks, dependencies, ownership, status, and
evidence.

## Dependencies and Parallelism

## Rollout and Migration

## Risks and Tradeoffs

## Rejected Alternatives

## Open Questions

## Deferred Decisions

## Planning Record

### Questions Asked and Answers

### Assumptions

### Design Changes During Planning

### Source Material
