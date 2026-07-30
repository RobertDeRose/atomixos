# Documentation conventions

## Source responsibilities

- Beads stores workflow state, dependencies, priorities, claims, findings, and execution evidence.
- Feature `design.md` files store intended feature behavior and design decisions.
- Reader-facing pages under `docs/src/` describe current supported behavior.
- Implemented-feature `index.md` files preserve feature-specific delivery and audit history.
- `planned-features.md` provides a human roadmap; Beads is authoritative for live execution state.
- Code and tests provide implementation evidence.

## Page placement

Choose a page by the question the reader is asking:

| Reader question                                                                               | Documentation concern |
|-----------------------------------------------------------------------------------------------|-----------------------|
| What is this project, who is it for, and what does it currently promise?                      | Introduction          |
| Why is it structured this way, and what boundaries or invariants apply?                       | Architecture          |
| How do I use, deploy, configure, observe, operate, or recover it?                             | Operator's Manual     |
| How do I build, test, change, migrate, or extend it?                                          | Development Guide     |
| What is the exact command, configuration key, interface, field, schema, default, or contract? | Reference             |
| What did one delivered feature change, and how was it verified?                               | Implemented Features  |

Create a focused page only after the project has concrete facts that answer a durable reader question. Do not create an
empty page merely to fill a category. Keep navigation, feature designs, and validation rules aligned when pages change.

## Concerns for this infrastructure project

Add focused pages when the infrastructure project has concrete environment, deployment, operations, recovery, inventory,
configuration, security, development, or architecture facts to document.

## Feature documentation

A feature design must name exact existing pages to update and exact new pages to create. Section names alone are not
sufficient. User-facing documentation must stand on its own; readers should not need the internal feature design to
understand supported behavior.

## Status language

- **Planned**: intended but not delivered.
- **Implemented**: present in code but not necessarily validated or fully documented.
- **Supported**: implemented, validated, documented, and part of the current contract.
- **Deprecated**: still present but scheduled for replacement or removal.
- **Removed**: no longer available.

## Drift handling

When design, implementation, tests, Beads, or published docs disagree:

1. record the mismatch in Beads;
2. determine whether the divergence was intentional;
3. correct the implementation or update the appropriate authoritative artifact;
4. preserve the rationale and validation evidence;
5. close the drift issue only after the sources agree.

## Writing style

State current behavior directly. Separate planned behavior from delivered behavior. Prefer exact commands, paths,
defaults, failure cases, and validation evidence where precision matters.
