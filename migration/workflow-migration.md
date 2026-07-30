<!-- rumdl-disable MD013 -->

# Legacy Workflow Migration Report

Generated: `2026-07-30T15:53:44+00:00`

## Inventory

- Features: 16
- Legacy task files: 14
- Parsed task files: 14
- Unparsed task files: 0
- Parsed legacy tasks: 456
- Reconciliation findings: 10
- `completed`: 10
- `deferred`: 1
- `in_progress`: 4
- `planned`: 1

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
- `pre-commit` `exception` — `HK_SKIP_STEPS=docs git commit -m "chore: record workflow migration plan"` — Reused the approved Gate 2-4 docs-step exception after mapping all legacy tasks and recording evidence-backed classifications.

## Feature Mapping

- **Feature:** `rock64-ab-image`
  - Target: `rock64-ab-image`
  - Classification: `in_progress`
  - Roadmap: partially completed
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `first-boot-local-provisioning`
  - Target: `first-boot-local-provisioning`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `durable-journald-logs`
  - Target: `durable-journald-logs`
  - Classification: `in_progress`
  - Roadmap: partially completed
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `provisioning-api-service`
  - Target: `provisioning-api-service`
  - Classification: `in_progress`
  - Roadmap: partially completed
  - Design: —
  - Index: no
  - Findings: 0
- **Feature:** `network-config-extensions`
  - Target: `network-config-extensions`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `activation-options`
  - Target: `activation-options`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `caddy-authcrunch-cockpit-tutorial`
  - Target: `caddy-authcrunch-cockpit-tutorial`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `nixstasis-client`
  - Target: `nixstasis-client`
  - Classification: `completed (override)`
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
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `provisioning-api-live-schema-contract`
  - Target: `provisioning-api-live-schema-contract`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `typed-partial-provisioning-api`
  - Target: `typed-partial-provisioning-api`
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1
- **Feature:** `boot-ui-htmx`
  - Target: `boot-ui-htmx`
  - Classification: `completed (override)`
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
  - Classification: `completed (override)`
  - Roadmap: completed
  - Design: —
  - Index: no
  - Findings: 1

## Reconciliation Findings

### First-boot local provisioning (`first-boot-local-provisioning`)

- `finding:54e5cd13e8ca` — Roadmap says completed/implemented but completion evidence is missing: T999 closed, implemented-feature index.md
- Classification override: `completed` — All 21 mapped implementation tasks are closed, and modules/first-boot.nix, scripts/first-boot.sh, provisioning docs, and first-boot VM checks corroborate delivered behavior; the legacy tracker did not use T999.

### Network config extensions (`network-config-extensions`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed, and the config schema, runtime-boundary documentation, implementation, and network apply/rollback tests corroborate delivery.

### Activation options (`activation-options`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed with VM coverage explicitly deferred, and activation-policy.json implementation, docs, and focused tests corroborate the delivered bounded rollback policy.

### Caddy authcrunch cockpit tutorial (`caddy-authcrunch-cockpit-tutorial`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — All mapped tasks are closed or explicitly skipped, T999 is closed, and the tutorial, example bundle, config validation, and delivered support paths corroborate completion.

### Nixstasis client (`nixstasis-client`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — All 39 legacy tasks including T999 are closed, and modules/nixstasis.nix, its VM test, architecture documentation, and commit 3ca38d6 corroborate delivery.

### Provisioning API privilege separation (`provisioning-api-privilege-separation`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — All 71 legacy tasks including T999 are closed, and the unprivileged service, staged root worker, tests, runtime-boundary docs, and hardening commits corroborate delivery.

### Provisioning API live schema contract (`provisioning-api-live-schema-contract`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed, and live OpenAPI schema assertions, public-route metadata, docs, and commit 395808b corroborate delivery.

### Typed partial provisioning API (`typed-partial-provisioning-api`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed, and authenticated partial endpoints, shared full-state apply behavior, schema tests, VM coverage, docs, and commit 47fa62a corroborate delivery.

### Boot UI htmx (`boot-ui-htmx`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed, and first-boot-only asynchronous UI routes, security tests, documentation, and commit 2c9c2df corroborate delivery.

### Config reapply improvements (`config-reapply-improvements`)

- `finding:5b9be2888efc` — Roadmap says completed/implemented but completion evidence is missing: implemented-feature index.md
- Classification override: `completed` — T000 through T999 are closed with one VM case explicitly deferred, and authenticated atomic promotion, rollback behavior, tests, docs, and follow-up closeouts corroborate delivery.

## Migration Stages

1. Review this report and confirm the feature slug mapping.
2. Use `classify` and `resolve-findings` to record evidence-backed decisions before import.
3. Run `prepare --apply` to rename feature paths and rewrite links.
4. Run `import-beads --apply` to create Beads state.
5. Use `/migrate-workflow` to reconcile designs, delivered records, and status conflicts.
6. Run `finalize --apply` only after no page includes or links to `tasks.md`.
7. Run `verify --beads` and the normal project checks.
