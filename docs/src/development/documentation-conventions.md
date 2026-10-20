# Documentation Conventions

How this site is organized and how to write for it. Read this before adding or changing a page.

## What gets published

The site describes what AtomixOS does today. Plans, work in progress, and delivery history live in Beads and never
appear on a published page.

- **Feature designs stay unpublished until delivery.** A directory under `docs/src/features/<slug>/` is left off the
  site until it has an `index.md`. That lets a design be written and reviewed before the work ships; adding `index.md`
  at delivery publishes the design and the delivery record together. `docs/site/features.ts` enforces this, and
  [Feature Lifecycle](feature-lifecycle.md) covers the full process.
- **Templates are never published.** Underscore-prefixed paths, such as `docs/src/features/_template/`, are excluded.
- **The roadmap stays in the repository.** `docs/src/planned-features.md` is the human-readable roadmap. It is kept
  in the repository but excluded from the site in `docs/docusaurus.config.ts`; Beads stays authoritative for live
  state.

## Where things go

Put each page where a reader would look for it:

| If the reader is asking…                                           | Section              |
|--------------------------------------------------------------------|----------------------|
| What is AtomixOS, who is it for, and what does it support?         | Introduction         |
| How is it put together, and why that way?                          | Architecture         |
| How do I flash, provision, configure, or recover a device?         | Operations           |
| How do I build, test, change, or document it?                      | Development          |
| What exactly is this setting, output, module, script, or limit?    | Reference            |
| What did a delivered feature add, and how did it differ from plan? | Implemented Features |

Keep each fact in one place and link to it from everywhere else, so pages never disagree. Add a new page only when it
answers a question readers will keep asking.

When a feature ships, its design names the exact pages it changes. Those pages must make sense on their own: nobody
should have to read a feature design to understand how AtomixOS works.

## Add a page

1. Create the page under `docs/src/`, in the directory that matches its section. Start it with a single `#` heading.
2. Register it in `docs/sidebars.ts` with `doc('<id>', '<label>')` inside the right category. The ID is the path under
   `docs/src` without the extension, for example `doc('operations/ntp-settings', 'NTP Settings')`. Implemented
   features are listed automatically from their `index.md` records.
3. Link to other pages with relative paths to their source files, such as `[Building](../building.md)` or
   `[Flake Outputs](../reference/flake-outputs.md)`; add `#anchor` to target a heading. Docusaurus turns them into
   site routes.
4. Preview with `mise run docs:serve`, then run `mise run docs:build`. The build fails on any broken link, anchor, or
   image, and `mise run check` runs the same build whenever documentation changes.

## Page format

- **`.md` pages are CommonMark.** Write plain Markdown; MDX syntax such as imports and JSX does not apply.
- **`.mdx` pages are MDX.** Use MDX only when a page needs components or JSX, as the introduction page
  (`docs/src/README.mdx`) does.
- **Diagrams** use fenced `mermaid` code blocks. Readers can expand and zoom them on the site.
- **Code blocks** name their language (`sh`, `toml`, `nix`, `json`, `text`, and so on) for syntax highlighting.
- **Source code** is cited by file path and symbol name, never by line number, because line numbers drift.

## Keep pages durable

Pages hold information that stays true until the behavior changes: behavior, contracts, architecture, decisions, and
how to operate or extend the system. Never record transient state on a page:

- pull request numbers or links;
- commit SHAs or branch names;
- review-pass notes, delivery or merge status;
- results of a particular validation or test run.

Beads and Git history own that state. When you edit a page that contains it, remove it rather than updating it.

## When docs and code disagree

If the docs, the code, the tests, or Beads disagree, open a Beads issue for it. Work out which side is wrong, fix that
side, keep the reasoning in the issue, and close it once everything matches again.

## Writing style

Write the way you would explain the system to a colleague who is new to it:

- **Start with what the reader can do.** Open a page or section with its purpose, not a description of the page.
- **Use plain words.** Explain any unavoidable term the first time it appears.
- **Say why.** When a rule would surprise someone, give the reason in a sentence.
- **Keep sentences short.** One idea per sentence.
- **Talk to the reader.** In guides and procedures, use "you" and number the steps.
- **Be exact where it matters.** Put commands, paths, settings, defaults, and limits in code formatting, tables, or code
  blocks.
- **Link instead of repeating.** Point to the page that covers a topic rather than restating it.
