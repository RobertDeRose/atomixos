# Build Configuration

AtomixOS has a strict, versioned build-stage policy. The committed `build.toml` sets immutable policy, such as watchdog
enforcement and backend, so the same inputs always produce the same images. An ignored, partial `build.dev.toml` lets
maintainers try local changes through the supported `mise` tasks without touching reviewed defaults. The effective
policy is validated before anything builds, embedded with provenance in each system, and copied byte-for-byte beside
disk images and RAUC bundles. The original plan is in the [design record](design.md); Beads tracks the work under
`atomixos-mol-0ws`.

## What changed for users

- **Maintainers** get early, clear failures: invalid syntax, unknown fields, wrong types, unsupported versions, invalid
  or overflowing durations, and out-of-range values all fail during evaluation.
- **Maintainers** can override policy locally. Supported `mise` tasks detect `build.dev.toml` at the repository root,
  print a warning before evaluation, and add `-dev` to image and bundle filenames.
- Direct Git-backed Nix commands, and test or utility tasks, always use the committed policy.

## How it fits in

Build policy is separate from the mutable runtime configuration under `/data`. One evaluator parses, validates, merges,
and renders the canonical policy. A narrow NixOS module maps the effective values to `atomixos.watchdog.enableHardware`,
`backend`, `runtimeWatchdogSec`, and `rebootWatchdogSec`; it adds no way to change policy at runtime.

Canonical TOML, compact JSON provenance, and the policy hash come from shared, immutable Nix store files, so the system,
image, and bundle carry identical audit bytes. Source revision, `flake.lock`, certificates, signing credentials, and
release trust remain separate inputs.

## Running it

1. Create `build.dev.toml` with the values to test.
2. Run a supported `mise` check or build task and confirm the warning and the `-dev` artifact.
3. Inspect the policy sidecars next to the artifact.
4. To promote the values, copy them into `build.toml`, delete `build.dev.toml`, rerun the checks, and rebuild.

`scripts/build.sh` validates policy before touching `.gcroots`, builds replacements under temporary links, and swaps
the retained links only after every build succeeds. A syntax, schema, evaluation, or build failure keeps the previous
retained outputs. Removing a malformed local overlay restores committed-policy behavior.

## Differences from the design

Build retention moved from inline `mise.toml` shell into `scripts/build.sh`, so host and Lima builds share one tested
implementation.

## Not included

- Build-policy sections other than those listed in the reference, and schema-version migration.
- Runtime provisioning fields, secrets, arbitrary Nix expressions, caller-chosen configuration paths, multiple profile
  layers, unmarked local artifacts, and local overrides for direct Nix commands.

## Tests

- `checks.<system>.build-configuration`: strict schema, normalization, provenance, module mapping, and artifact inputs.
- `checks.<system>.build-config-workflow`: override detection, the warning, purity, the supported task list, Lima
  execution, validation ordering, and retained-link replacement.

## Related pages

- [Build Configuration reference](../../reference/build-configuration.md)
- [Building](../../building.md)
- [Testing](../../testing.md)
- [Architecture: Immutable Build Policy](../../architecture.md#immutable-build-policy)
- [Watchdog specification](../../specs/watchdog.md)
- [Flake Outputs](../../reference/flake-outputs.md)
