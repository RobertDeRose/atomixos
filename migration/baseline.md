# Legacy workflow baseline

Generated: `2026-07-30T13:58:27+00:00`

## Documentation

- Status: `passed`
- Command: `1 named partition(s)`
- Note: See validation_partitions for command ownership and evidence.

## Tests

- Status: `failed`
- Command: `nix flake check --max-jobs 1`
- Note: Explicit baseline test command.

## Hk

- Status: `evaluable`
- Command: `pkl eval hk.pkl`
- Note: Pkl evaluation passed.

## Resolution

- Write eligible: `true`
- Unresolved: none
- Resolution flags: documentation=supplied; tests=supplied
- Uncovered candidates: none
- Residual limitations: .: Python test files exist but pyproject.toml is missing

## Validation partitions

<!-- rumdl-disable MD013 -->

- `root-book-build` (documentation): status=`passed`; argv=`mdbook build docs`; cwd=`.`; provenance=`docs/book.toml`
  - Return code: `0`; output truncated: `false`
  - stdout:
    (empty)
  - stderr:
    INFO Book building has started
    Warning: The mdbook-mermaid preprocessor was built against version 0.5.0 of mdbook, but we're being called from version 0.5.2
    INFO Running the html backend
    INFO HTML book written to `/Users/DeRoseR/workspace/personal/atomixos/docs/../book`

## Capability inventory

- Layout: `single-package`
- Config roots: `.`
- Documentation evidence: `.opencode/commands/close-feature.md`, `.opencode/commands/implement-feature.md`, `.opencode/commands/plan-features.md`, `.opencode/commands/project-alignment-execute.md`, `.opencode/commands/project-alignment-land.md`, `.opencode/commands/project-alignment-review.md`, `.opencode/commands/review-feature-spec.md`, `.opencode/commands/start-feature.md`, `AGENTS.md`, `HARDWARE-TEST-PLAN.md`, `README.md`, `certs/README.md`, `config_bundle.md`, `docs/book.toml`, `docs/src/SUMMARY.md`, `docs/src/architecture.md`, `docs/src/architecture/authentication.md`, `docs/src/architecture/network-topology.md`, `docs/src/architecture/overwatch-enrollment.md`, `docs/src/architecture/partition-layout.md`, `docs/src/architecture/update-rollback.md`, `docs/src/building.md`, `docs/src/code-reference.md`, `docs/src/code-reference/derivations.md`, `docs/src/code-reference/modules.md`, `docs/src/code-reference/scripts.md`, `docs/src/data-flow.md`, `docs/src/design-decisions.md`, `docs/src/features.md`, `docs/src/features/activation-options/design.md`, `docs/src/features/activation-options/tasks.md`, `docs/src/features/boot-ui-htmx/design.md`, `docs/src/features/boot-ui-htmx/tasks.md`, `docs/src/features/caddy-authcrunch-cockpit-tutorial/design.md`, `docs/src/features/caddy-authcrunch-cockpit-tutorial/tasks.md`, `docs/src/features/config-reapply-improvements/design.md`, `docs/src/features/config-reapply-improvements/tasks.md`, `docs/src/features/durable-journald-logs/design.md`, `docs/src/features/durable-journald-logs/tasks.md`, `docs/src/features/first-boot-local-provisioning/design.md`, `docs/src/features/first-boot-local-provisioning/tasks.md`, `docs/src/features/network-config-extensions/design.md`, `docs/src/features/network-config-extensions/tasks.md`, `docs/src/features/nixstasis-client/design.md`, `docs/src/features/nixstasis-client/tasks.md`, `docs/src/features/provisioning-api-live-schema-contract/design.md`, `docs/src/features/provisioning-api-live-schema-contract/tasks.md`, `docs/src/features/provisioning-api-privilege-separation/design.md`, `docs/src/features/provisioning-api-privilege-separation/tasks.md`, `docs/src/features/provisioning-api-service/design.md`, `docs/src/features/provisioning-api-service/tasks.md`, `docs/src/features/rock64-ab-image/design.md`, `docs/src/features/rock64-ab-image/tasks.md`, `docs/src/features/typed-partial-provisioning-api/design.md`, `docs/src/features/typed-partial-provisioning-api/tasks.md`, `docs/src/features/watchdog-enforcement/design.md`, `docs/src/features/watchdog-enforcement/tasks.md`, `docs/src/hardware-testing.md`, `docs/src/introduction.md`, `docs/src/operations/ntp-settings.md`, `docs/src/planned-features.md`, `docs/src/provisioning.md`, `docs/src/provisioning/flash-image.md`, `docs/src/provisioning/lan-range.md`, `docs/src/reference/flake-outputs.md`, `docs/src/reference/project-structure.md`, `docs/src/reference/tasks.md`, `docs/src/runtime-boundaries.md`, `docs/src/specs/boot-rollback.md`, `docs/src/specs/lan-gateway.md`, `docs/src/specs/nix-flake-config.md`, `docs/src/specs/partition-layout.md`, `docs/src/specs/rauc-integration.md`, `docs/src/specs/update-confirmation.md`, `docs/src/specs/watchdog.md`, `docs/src/testing.md`, `docs/src/tutorials/oidc-device-management.md`, `docs/src/unknowns.md`, `oop_all_logging.md`
- Test evidence: `scripts/atomixos_provision/tests/test_activation.py`, `scripts/atomixos_provision/tests/test_app.py`, `scripts/atomixos_provision/tests/test_auth.py`, `scripts/atomixos_provision/tests/test_bundle.py`, `scripts/atomixos_provision/tests/test_config.py`, `scripts/atomixos_provision/tests/test_config_builder.py`, `scripts/atomixos_provision/tests/test_config_service.py`, `scripts/atomixos_provision/tests/test_deps.py`, `scripts/atomixos_provision/tests/test_exceptions.py`, `scripts/atomixos_provision/tests/test_jobs.py`, `scripts/atomixos_provision/tests/test_partial_config.py`, `scripts/atomixos_provision/tests/test_provision.py`, `scripts/atomixos_provision/tests/test_quadlet.py`, `scripts/atomixos_provision/tests/test_quadlet_sync.py`, `scripts/atomixos_provision/tests/test_schemas.py`, `scripts/atomixos_provision/tests/test_server.py`, `scripts/atomixos_provision/tests/test_settings.py`, `scripts/atomixos_provision/tests/test_staging.py`, `tests/test_lan_gateway_apply.py`
- CI workflows: `.github/workflows/docs.yml`, `.github/workflows/hk.yml`
- Ambiguities: .: Python test files exist but pyproject.toml is missing

### Packages

- `.`
  - Manifests: `package.json`
  - Test evidence: `scripts/atomixos_provision/tests/test_activation.py`, `scripts/atomixos_provision/tests/test_app.py`, `scripts/atomixos_provision/tests/test_auth.py`, `scripts/atomixos_provision/tests/test_bundle.py`, `scripts/atomixos_provision/tests/test_config.py`, `scripts/atomixos_provision/tests/test_config_builder.py`, `scripts/atomixos_provision/tests/test_config_service.py`, `scripts/atomixos_provision/tests/test_deps.py`, `scripts/atomixos_provision/tests/test_exceptions.py`, `scripts/atomixos_provision/tests/test_jobs.py`, `scripts/atomixos_provision/tests/test_partial_config.py`, `scripts/atomixos_provision/tests/test_provision.py`, `scripts/atomixos_provision/tests/test_quadlet.py`, `scripts/atomixos_provision/tests/test_quadlet_sync.py`, `scripts/atomixos_provision/tests/test_schemas.py`, `scripts/atomixos_provision/tests/test_server.py`, `scripts/atomixos_provision/tests/test_settings.py`, `scripts/atomixos_provision/tests/test_staging.py`, `tests/test_lan_gateway_apply.py`

<!-- rumdl-enable MD013 -->

### Proposed commands

- `root-book-build` (documentation): argv=`mdbook build docs`; cwd=`.`; provenance=`docs/book.toml`
- `root-mise-check` (tests): argv=`mise run check`; cwd=`.`; provenance=`mise.toml`

### CI command evidence

- `.github/workflows/docs.yml:36`: `mdbook build docs` (ci-evidence-only)
- `.github/workflows/hk.yml:33`: `mise plugin install nix https://github.com/jbadeau/mise-nix.git
mise install
hk check -a` (ci-evidence-only)
