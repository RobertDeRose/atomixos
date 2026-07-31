# Build Configuration

## Delivery Summary

- Beads feature root: `atomixos-mol-0ws`
- Status: delivered locally
- Pull request: not created
- Delivery: fast-forwarded into local `dev` at `d6046e4f564a4c6cc046b721197b5d048cd57d2c`
- Design record: [design.md](design.md)
- Implementation commits: `1e9874ec88dda42c3d364143072cdeb826d52147`,
  `de794fe423bea98280d3150eae0bc7b20113c627`, and `42608e796311dddaedcd6a3bdfba495184d4a970`

## Delivered Capability

AtomixOS now has a strict, versioned build-stage policy contract. Committed `build.toml` supplies reproducible immutable
watchdog policy, while an ignored partial `build.dev.toml` lets maintainers test local changes through supported `mise`
commands without changing reviewed defaults.

The effective policy is validated before artifacts build, mapped to existing watchdog options, embedded with provenance
in configured systems, and copied byte-for-byte beside disk-image and RAUC bundle artifacts.

## User-Facing Behavior

Version 1 accepts only complete committed watchdog policy and known partial local overrides. Invalid syntax, unknown
fields, wrong types, unsupported versions, invalid durations, overflow, and policy values outside documented ranges
fail closed during evaluation.

Supported configuration-bearing `mise` commands automatically detect repository-root `build.dev.toml`, print the exact
override warning before affected evaluations, and mark image and bundle filenames with `-dev`. Direct Git-backed Nix
commands and excluded test or utility tasks continue to use committed policy only.

## Design Integration

Build policy remains separate from mutable runtime provisioning under `/data`. The evaluator is the single parser,
validator, merger, and canonical renderer. A narrow NixOS module maps effective values to
`atomixos.watchdog.enableHardware`, `runtimeWatchdogSec`, and `rebootWatchdogSec`; it does not create a runtime mutation
surface.

Canonical TOML, compact JSON provenance, and the policy hash come from shared immutable Nix store files. The system,
image, and bundle therefore use identical audit bytes. Source revision, `flake.lock`, certificates, signing credentials,
and release trust remain separately owned inputs.

## Operational Impact

Maintainers can create `build.dev.toml`, run an included `mise` check or build command, inspect the warning and `-dev`
artifact, and verify its sidecars. Promotion consists of copying accepted values to committed `build.toml`, removing the
local overlay, rerunning checks, and rebuilding.

The retained-artifact build validates policy before touching `.gcroots`, builds replacements under temporary links, and
replaces retained links only after every required build succeeds. Syntax, schema, evaluation, or later build failures
preserve the prior retained outputs; removing a malformed local overlay restores committed-policy behavior.

## Reference and Contracts

- [Build Configuration](../../reference/build-configuration.md)
- [Building](../../building.md)
- [Testing](../../testing.md)
- [Architecture — Immutable Build Policy](../../architecture.md#immutable-build-policy)
- [Watchdog Specification](../../specs/watchdog.md)
- [Flake Outputs](../../reference/flake-outputs.md)
- [Project Structure](../../reference/project-structure.md)

## Validation Evidence

- `checks.aarch64-darwin.build-configuration` and `checks.aarch64-linux.build-configuration` cover strict schema,
  normalization, provenance, module mapping, and artifact inputs.
- `checks.aarch64-darwin.build-config-workflow` and `checks.aarch64-linux.build-config-workflow` cover fixed-path
  override handling, warning and purity behavior, the task matrix, Lima execution, validation ordering, and retained-link
  replacement.
- Real wrapper evaluation demonstrated `localOverride = true`; the same direct Git-backed Nix evaluation remained
  `false`.
- `uv run scripts/check-docs.py` and `mise exec -- hk check -a` passed for the implementation worktree.
- The repository-wide `mise run check` reached the pre-existing `first-boot-provision` rollback-fixture failure tracked
  as `atomixos-1az`; the build-configuration checks passed independently.

## Design Reconciliation

### Delivered as Designed

The complete committed schema, recursive strict overlay, bounded duration grammar, watchdog mapping, canonical immutable
policy, compact provenance, byte-identical sidecars, `-dev` identity, exact supported-task matrix, fixed-path wrapper,
narrow impurity, Lima behavior, direct-Nix boundary, and atomic retained-link workflow were delivered.

### Intentional Changes

No product-policy changes were required during implementation. Build retention logic moved from inline `mise.toml` shell
to `scripts/build.sh` so host and Lima execution share one testable implementation.

### Deferred Work

Future build-policy sections and schema-version migration remain deferred until an owning feature needs them. Physical
Watchdog Enforcement must still verify systemd's actual programmed timeout and complete Rock64 reboot, rollback, and
soak evidence before committed policy enables hardware enforcement.

### Rejected or Removed Scope

Runtime provisioning fields, secrets, arbitrary Nix expressions, caller-selected configuration paths, multiple profile
layers, unmarked local artifacts, and automatic local overrides for direct Nix commands remain intentionally excluded.

## Documentation Updated

- `docs/src/architecture.md`
- `docs/src/building.md`
- `docs/src/testing.md`
- `docs/src/reference/build-configuration.md`
- `docs/src/specs/watchdog.md`
- `docs/src/reference/flake-outputs.md`
- `docs/src/reference/project-structure.md`
- `docs/src/planned-features.md`
- `docs/src/features/watchdog-enforcement/design.md`
- `docs/src/SUMMARY.md`
- `docs/src/features/index.md`

## Audit Trail

Specification reconciliation completed in `231c7e8f94d0facc9abbd83c6a882f1a64396824`. Implementation tasks
`atomixos-mol-off.1`, `atomixos-mol-off.2`, and `atomixos-mol-off.3` delivered the schema, immutable policy integration,
and supported workflow in the three implementation commits listed above. Each task used test-first evidence, focused
validation, aligned reader documentation, and an independent implementation review. The feature was fast-forwarded
into local `dev` at `d6046e4f564a4c6cc046b721197b5d048cd57d2c`; no pull request or remote branch push occurred. Beads
preserves detailed findings, resolutions, validation limitations, and commit evidence under the feature root.
