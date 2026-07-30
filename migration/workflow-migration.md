<!-- rumdl-disable MD013 -->

# Legacy Workflow Migration Report

Generated: `2026-07-30T15:44:04+00:00`

## Inventory

- Features: 16
- Legacy task files: 14
- Parsed task files: 10
- Unparsed task files: 4
- Parsed legacy tasks: 196
- Reconciliation findings: 18
- `deferred`: 1
- `in_progress`: 1
- `needs_review`: 7
- `planned`: 7

## hk Reconciliation

- Baseline status: `evaluable`
- Current status: `evaluable`
- Recorded dispositions: 0
- Blocking inventory issues: 0

## Artifact Lifecycle

- Temporary candidates present: False
- Conditional backup present: False
- Backup disposition: `not_applicable`
- Backup disposition reason: —

## Checkpoint Evidence

- `pre-commit` `exception` — `HK_SKIP_STEPS=docs git commit -m "chore: adopt dstack workflow"` — User approved the bounded docs-step exception while legacy task links and incomplete designs remain migration inputs.

## Feature Mapping

- **Feature:** `caddy-authcrunch-cockpit-tutorial`
  - Target: `caddy-authcrunch-cockpit-tutorial`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 2
- **Feature:** `nixstasis-client`
  - Target: `nixstasis-client`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `rauc-production-keyring-policy`
  - Target: `rauc-production-keyring-policy`
  - Classification: `planned`
  - Roadmap: planned
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `provisioning-api-privilege-separation`
  - Target: `provisioning-api-privilege-separation`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `provisioning-api-live-schema-contract`
  - Target: `provisioning-api-live-schema-contract`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `typed-partial-provisioning-api`
  - Target: `typed-partial-provisioning-api`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `boot-ui-htmx`
  - Target: `boot-ui-htmx`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `watchdog-enforcement`
  - Target: `watchdog-enforcement`
  - Classification: `in_progress`
  - Roadmap: partially completed
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `usb-wifi`
  - Target: `usb-wifi`
  - Classification: `deferred`
  - Roadmap: deferred
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `config-reapply-improvements`
  - Target: `config-reapply-improvements`
  - Classification: `needs_review`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `activation-options`
  - Target: `activation-options`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `durable-journald-logs`
  - Target: `durable-journald-logs`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 2
- **Feature:** `first-boot-local-provisioning`
  - Target: `first-boot-local-provisioning`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 2
- **Feature:** `network-config-extensions`
  - Target: `network-config-extensions`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `provisioning-api-service`
  - Target: `provisioning-api-service`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 2
- **Feature:** `rock64-ab-image`
  - Target: `rock64-ab-image`
  - Classification: `planned`
  - Roadmap: —
  - Design: —
  - Index: no
  - Findings: 2

## Reconciliation Findings

### Caddy authcrunch cockpit tutorial (`caddy-authcrunch-cockpit-tutorial`)

- `finding:6b2eaf2be8db` — Roadmap says completed/implemented but completion evidence is missing: all implementation tasks closed, T999 closed, implemented-feature index.md
- `finding:cdd164a1db6b` — Roadmap dependency tokens do not resolve to known features: 85ec53c

### Nixstasis client (`nixstasis-client`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md

### Provisioning API privilege separation (`provisioning-api-privilege-separation`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md

### Provisioning API live schema contract (`provisioning-api-live-schema-contract`)

- `finding:6b2eaf2be8db` — Roadmap says completed/implemented but completion evidence is missing: all implementation tasks closed, T999 closed, implemented-feature index.md

### Typed partial provisioning API (`typed-partial-provisioning-api`)

- `finding:6b2eaf2be8db` — Roadmap says completed/implemented but completion evidence is missing: all implementation tasks closed, T999 closed, implemented-feature index.md

### Boot UI htmx (`boot-ui-htmx`)

- `finding:6b2eaf2be8db` — Roadmap says completed/implemented but completion evidence is missing: all implementation tasks closed, T999 closed, implemented-feature index.md

### Config reapply improvements (`config-reapply-improvements`)

- `finding:6b2eaf2be8db` — Roadmap says completed/implemented but completion evidence is missing: all implementation tasks closed, T999 closed, implemented-feature index.md

### Activation options (`activation-options`)

- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

### Durable journald logs (`durable-journald-logs`)

- `finding:e4ddc6438542` — Legacy tasks.md exists but no recognizable T### tasks were parsed; extend the parser or resolve this finding after manually mapping the task state
- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

### First boot local provisioning (`first-boot-local-provisioning`)

- `finding:e4ddc6438542` — Legacy tasks.md exists but no recognizable T### tasks were parsed; extend the parser or resolve this finding after manually mapping the task state
- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

### Network config extensions (`network-config-extensions`)

- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

### Provisioning API service (`provisioning-api-service`)

- `finding:e4ddc6438542` — Legacy tasks.md exists but no recognizable T### tasks were parsed; extend the parser or resolve this finding after manually mapping the task state
- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

### Rock64 ab image (`rock64-ab-image`)

- `finding:e4ddc6438542` — Legacy tasks.md exists but no recognizable T### tasks were parsed; extend the parser or resolve this finding after manually mapping the task state
- `finding:fba242b97dad` — Feature is retained from migration state but is not represented in planned-features.md

## Migration Stages

1. Review this report and confirm the feature slug mapping.
2. Use `classify` and `resolve-findings` to record evidence-backed decisions before import.
3. Run `prepare --apply` to rename feature paths and rewrite links.
4. Run `import-beads --apply` to create Beads state.
5. Use `/migrate-workflow` to reconcile designs, delivered records, and status conflicts.
6. Run `finalize --apply` only after no page includes or links to `tasks.md`.
7. Run `verify --beads` and the normal project checks.
