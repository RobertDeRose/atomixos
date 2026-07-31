# Design — Build Configuration

## Metadata

- Beads feature root: `atomixos-mol-0ws`
- Feature slug: `build-configuration`
- Design path: `docs/src/features/build-configuration/design.md`
- Implemented record: `docs/src/features/build-configuration/index.md`
- Base branch: `dev`
- Status: ready for delivery

## Feature Summary

Introduce a strict build-stage `build.toml` contract for settings that are fixed into AtomixOS artifacts. The first
consumer is watchdog policy. A committed complete configuration defines normal and release builds; an ignored partial
`build.dev.toml` overlay makes local customization easy to test without changing committed policy.

## User Intent

The user selected a separate reusable build-stage configuration capability instead of extending runtime provisioning
`config.toml`. The committed file is `build.toml`. An ignored `build.dev.toml` is a local staging overlay for testing
customizations before copying accepted values into `build.toml`.

Supported `mise` build and check tasks will apply the local overlay automatically when it exists. They must make this
conspicuous before evaluation with:

```text
WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.
```

Local-override artifacts must also remain distinguishable after the terminal warning is gone.

## Goals

1. Define and validate a versioned, fail-closed build configuration schema.
2. Preserve a committed, reproducible default policy while supporting an ignored partial local overlay.
3. Map effective watchdog policy into existing `atomixos.watchdog.*` NixOS options.
4. Embed the normalized effective policy and non-secret provenance into immutable system and artifact outputs.
5. Keep supported `mise` build and check workflows convenient and explicit about local overrides.
6. Leave a small, section-oriented contract that future features can extend without a generic key/value mechanism.

## Non-Goals

- Moving runtime provisioning concerns from `config.toml` into build configuration.
- Supporting secrets, credentials, signing keys, or arbitrary Nix expressions in either TOML file.
- Adding build settings beyond the watchdog section in the first delivery.
- Supporting multiple named profiles, cascading override files, environment-variable field overrides, or command-line
  field overrides.
- Making ignored local files visible to ordinary Git-backed `nix build .#...` or `nix flake check` commands.
- Mutating a built system's policy at runtime.

## User-Facing Behavior

The intended behavior is that the repository will contain a complete committed `build.toml`. A normal supported build
will use it. When a
repository-root `build.dev.toml` exists, the explicitly enumerated `mise` tasks will merge its known fields over the
committed configuration, print the warning before Nix evaluation, and identify resulting artifacts as local-override
outputs.

Deleting `build.dev.toml` will restore committed-policy behavior. Direct Git-backed Nix commands will intentionally
ignore the untracked file and use committed policy only.

The initial complete configuration is:

```toml
version = 1

[watchdog]
enable_hardware = false
runtime_timeout = "30s"
reboot_timeout = "10min"
```

A valid local overlay may be partial:

```toml
[watchdog]
enable_hardware = true
runtime_timeout = "45s"
```

## Requirements

### Functional Requirements

- `build.toml` must be committed, versioned, complete, and the sole authority for schema-owned build policy in normal
  and release builds. It is not a complete release description: source revision, `flake.lock`, production verification
  certificates, and external signing credentials remain separately owned inputs.
- `build.dev.toml` must be ignored by Git and may contain only fields being overridden.
- The overlay merges recursively over the committed document; omitted fields inherit committed values.
- An optional overlay `version` must equal `1`. The committed document must contain `version = 1`.
- The version-1 schema permits only `version` and `[watchdog]`, with exactly these watchdog fields:
  - `enable_hardware`: Boolean.
  - `runtime_timeout`: positive integer followed by `ms`, `s`, `min`, or `h`.
  - `reboot_timeout`: positive integer followed by `ms`, `s`, `min`, or `h`.
- Zero, signs, decimals, compound spans, whitespace variants, unitless values, and other systemd duration syntax are
  invalid.
- Duration conversion must be overflow-safe. `runtime_timeout` must resolve to 10 seconds through 5 minutes inclusive;
  `reboot_timeout` must resolve to 1 minute through 10 minutes inclusive.
- These ranges are policy limits, not proof of hardware capability. Systemd may program the nearest timeout supported
  by a device; physical Watchdog Enforcement acceptance must record the actual programmed timeout and reject a policy
  whose observed behavior is outside its intended timing.
- Unknown sections or fields, wrong types, unsupported versions, and incomplete committed documents must fail during
  evaluation before any artifact derivation builds.
- Effective watchdog fields map to existing NixOS options:
  - `enable_hardware` → `atomixos.watchdog.enableHardware`.
  - `runtime_timeout` → `atomixos.watchdog.runtimeWatchdogSec`.
  - `reboot_timeout` → `atomixos.watchdog.rebootWatchdogSec`.
- The normalized effective policy must be available read-only at `/etc/atomixos/build.toml`. Its canonical UTF-8 bytes
  use this exact order and layout, lowercase TOML booleans, one blank line before `[watchdog]`, and one final newline:

  ```toml
  version = 1

  [watchdog]
  enable_hardware = false
  runtime_timeout = "30s"
  reboot_timeout = "10min"
  ```

  Effective values replace only the rendered values; key and section order never changes.
- Machine-readable non-secret provenance must be available read-only at `/etc/atomixos/build-metadata.json`. Its exact
  UTF-8 representation is one compact JSON object plus a final newline:
  `{"local_override":<boolean>,"policy_sha256":"<64 lowercase hexadecimal characters>"}`. The hash is SHA-256 over
  the exact canonical TOML bytes.
- Image and RAUC bundle output directories must contain `build.toml` and `build-metadata.json` sidecars byte-for-byte
  identical to the immutable `/etc/atomixos` files.
- Local-override image and bundle filenames must include `-dev` and their metadata must mark
  `local_override = true`.
- The configuration-aware task matrix is authoritative:

  | `mise` task                 | Applies local overlay | Reason                                              |
  |-----------------------------|-----------------------|-----------------------------------------------------|
  | `check`, `nix:check`        | Yes                   | Evaluate and test the effective configuration       |
  | `build`                     | Yes                   | Build configuration-bearing system/artifact outputs |
  | `build:squashfs`            | Yes                   | Contains immutable system policy                    |
  | `build:rauc-bundle`         | Yes                   | Contains the configured squashfs and audit sidecars |
  | `build:boot-script`         | Yes                   | References the configured closure and squashfs ID   |
  | `vm:bundle-test`            | Yes                   | Provides an interactive configured-system test      |
  | `e2e`, `e2e:*`, `e2e:debug` | No                    | Test fixtures own explicit isolated configuration   |
  | `serial:*`, `_lima`, `gc`   | No                    | Do not construct AtomixOS configured outputs        |

- Each included Nix evaluation must print the exact warning before evaluation when the local overlay exists. A
  multi-evaluation task such as `build` may print it before each evaluation rather than hide later override use.
- Direct `nix build .#...`, `nix flake check`, external `nixpkgs` helper builds, and excluded `mise` tasks remain pure
  committed-policy workflows and do not inspect ignored files.

### Quality Requirements

- The same source revision plus the same effective configuration must produce the same derivation inputs and normalized
  policy content.
- Committed-policy evaluation remains pure. Local override evaluation may use a narrowly bounded impure file read, but
  the file contents and effective policy must become derivation inputs and immutable provenance.
- TOML syntax errors must identify the input filename and preserve native parser line/column context. Schema errors must
  identify the input filename and canonical field path without exposing unrelated environment data.
- The implementation must use one parser/validator/renderer for checks and builds.
- Warning and development identity behavior must be testable without building a full disk image.
- Build configuration must never accept secret-bearing fields.

### Compatibility and Migration Requirements

- The committed version-1 defaults preserve current watchdog behavior: hardware enforcement remains disabled, with
  stored `30s` and `10min` timeout defaults.
- Existing direct Nix commands continue to work and use committed policy.
- Existing `mise` commands keep their names; only configuration-aware task internals change.
- No runtime `config.toml`, provisioning schema, API, or persisted `/data` state changes.

## Existing Context

`flake.nix` currently constructs Rock64 and QEMU NixOS configurations directly and derives squashfs, image, boot script,
and RAUC bundle outputs from the Rock64 configuration. `mise.toml` invokes those flake outputs through multiple build
and check tasks. `modules/watchdog.nix` already owns the target NixOS options and defaults.

Runtime `config.toml` is owned by first-boot and re-apply provisioning under `/data`; it is intentionally mutable and is
not an immutable image-policy interface. Watchdog specification reconciliation explicitly rejected extending that
runtime contract for hardware watchdog policy.

Ignored files are absent from Git-backed flake sources. Therefore automatic local overlay handling belongs to supported
`mise` wrappers, while ordinary direct Nix commands remain committed-policy-only.

## Proposed Design

### Strict Configuration Evaluator

Add one Nix evaluator that accepts a committed base path and optional local overlay bytes. It parses with
`builtins.fromTOML`, preserving native syntax diagnostics with filename context, then validates allowed keys, versions,
types, completeness, duration grammar, and converted bounds. It recursively merges only known fields and returns:

- typed effective values;
- deterministic normalized TOML;
- a SHA-256 hash of normalized TOML;
- `localOverride`, which controls provenance and development naming.

Validation occurs while flake outputs evaluate, before build derivations execute. Tests call the same evaluator with
fixture documents, including expected failures.

### NixOS and Artifact Integration

A narrow NixOS module receives the validated effective value and maps the watchdog section to the existing watchdog
options. The module writes normalized policy and JSON provenance into the immutable `/etc/atomixos` closure. It does not
parse TOML itself and does not expose runtime mutation options.

The Rock64 squashfs, disk image, and RAUC bundle derive from the same effective configuration. Image and bundle builders
copy the same generated policy and metadata beside their primary artifacts. `localOverride` adds `-dev` to image and
bundle filenames without changing RAUC compatibility or slot layout.

### Local Override Wrapper

Use `scripts/nix-with-build-config.sh <nix-subcommand> [arguments...]` for every included task invocation:

1. Resolve the repository root from the wrapper's own location; reject a caller-supplied configuration path.
2. If repository-root `build.dev.toml` is absent, execute `nix <subcommand> ...` unchanged.
3. If it exists, print the exact warning to standard error before evaluation, set
   `ATOMIXOS_BUILD_DEV_CONFIG` to that exact canonical repository-root path, and execute
   `nix <subcommand> --impure ...`.
4. `flake.nix` reads that environment variable only during impure evaluation, reads the fixed file bytes, and passes
   those bytes to the shared evaluator. The resulting effective values, normalized bytes, and hash become derivation
   inputs. The wrapper accepts no option or environment override for another path.
5. Lima-prefixed tasks invoke the wrapper inside the VM at the repository's same mounted path, so detection and path
   ownership remain identical.

The wrapper does not parse TOML, merge values, or construct metadata. This avoids a second schema implementation. The
`ATOMIXOS_BUILD_DEV_CONFIG` transport is an internal supported-wrapper contract, not a public field-override interface.

### Trust and Security Boundaries

- Committed `build.toml` is reviewed source policy.
- Ignored `build.dev.toml` is unreviewed local input and always produces visibly marked local-override artifacts.
- Build configuration is non-secret. Signing keys and credentials retain their existing ownership and paths.
- Runtime provisioning cannot read, replace, or apply build policy.
- Unknown future sections fail until their owning feature extends the schema and documentation.
- `localOverride` solely owns this feature's warning, `-dev` suffix, and provenance bit. The suffix means only that local
  build-policy overrides were applied; it does not describe the separate `DEVELOPMENT` mode, RAUC signing trust, or
  release readiness.

### Failure and Recovery

Invalid committed or local configuration stops a shared validation preflight before any output link or `.gcroots`
mutation. Syntax errors report filename plus native line/column context; schema errors report filename plus field path.
Configuration-aware builds create temporary result/GC links and atomically replace retained links only after all
required builds succeed, so a later build failure also preserves prior retained outputs. Nix store outputs are
immutable. Fixing the document and rerunning is sufficient recovery. Deleting `build.dev.toml` restores committed
behavior. A local-override artifact cannot silently lose its `-dev` and provenance markers.

## Architecture Consistency

### Existing Patterns Reused

- Existing `atomixos.watchdog.*` module options remain the policy application surface.
- Nix evaluation and module assertions remain the build-time validation boundary.
- Existing `mise` tasks remain the supported developer command surface.
- Immutable `/etc` files and derivation sidecars provide audit evidence without mutable state.

### Invariants Preserved

- Runtime provisioning `config.toml` owns mutable operator/application configuration only.
- Hardware watchdog enforcement remains disabled in committed policy until physical validation supports a deliberate
  change.
- Build outputs remain content-addressed and current direct Nix commands remain pure.
- No secrets enter build configuration or immutable audit files.
- QEMU evidence does not become physical watchdog evidence.

### New Decisions Introduced

- `build.toml` is the committed complete contract for schema-owned immutable build policy.
- `build.dev.toml` is one ignored partial overlay, automatically used only by supported `mise` workflows.
- Local overrides produce a warning, `-dev` filenames, and immutable provenance; this identity is independent of other
  development or signing modes.
- Version 1 initially contains only watchdog policy and uses a restricted duration grammar.

### Architecture Documentation Changes

`docs/src/architecture.md` will identify immutable build policy as separate from runtime provisioning and describe where
the effective policy is fixed and audited.

## Operational Considerations

Maintainers edit `build.dev.toml` to trial image policy, run an included `mise` task, inspect the warning and sidecars,
and test the `-dev` artifact. They verify the sidecar hash against the exact normalized TOML bytes and compare sidecars
byte-for-byte with `/etc/atomixos` on a running system. Once accepted, they copy the intended fields into `build.toml`,
remove the local overlay, and rerun checks/builds to produce committed-policy artifacts.

Release automation and reviewers should use a clean checkout or direct Nix commands. The absence of `-dev`, a
`local_override = false` provenance value, and the embedded effective hash identify committed build-policy output only;
release signing and verification trust require their separately owned evidence.

## Documentation Impact

| Documentation concern      | Exact page                                                                        | Create or update       | Planned change                                                                                                                         | Owning Beads task                    |
|----------------------------|-----------------------------------------------------------------------------------|------------------------|----------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------|
| Introduction               | Not applicable                                                                    | —                      | The feature does not change product purpose or audience                                                                                | —                                    |
| Architecture               | `docs/src/architecture.md`                                                        | Update                 | Separate immutable build policy from runtime provisioning and identify audit outputs                                                   | `atomixos-mol-off.2`                 |
| Usage / Operations         | `docs/src/building.md`                                                            | Update                 | Explain warning, promotion, diagnosis/recovery, hash verification, and byte comparison                                                 | `atomixos-mol-off.3`                 |
| Development                | `docs/src/testing.md`                                                             | Update                 | Explain effective-overlay checks and focused validation                                                                                | `atomixos-mol-off.3`                 |
| Reference                  | `docs/src/reference/build-configuration.md`                                       | Create/extend          | `.1`: schema/merge/diagnostics; `.2`: canonical audit format; `.3`: normative preflight/failure, task matrix, and direct-Nix contracts | `atomixos-mol-off.1`–`.3`            |
| Reference                  | `docs/src/specs/watchdog.md`                                                      | Update                 | Map build fields to watchdog options and retain defaults                                                                               | `atomixos-mol-off.2`                 |
| Reference                  | `docs/src/reference/flake-outputs.md`                                             | Update                 | Document configuration-aware outputs and direct-Nix boundary                                                                           | `atomixos-mol-off.3`                 |
| Reference                  | `docs/src/reference/project-structure.md`                                         | Update                 | Register build policy, evaluator, wrapper, and tests                                                                                   | `atomixos-mol-off.3`                 |
| Navigation                 | `docs/src/SUMMARY.md`                                                             | Update                 | Planning registers design; `.1` registers reference; close-out registers record                                                        | planning / `.1` / `atomixos-mol-bf2` |
| Roadmap                    | `docs/src/planned-features.md`                                                    | Update                 | Record dependency, scope, and active design                                                                                            | planning / close-out                 |
| Implemented Feature Record | `docs/src/features/build-configuration/index.md` and `docs/src/features/index.md` | Create/update at close | Preserve delivery/audit history and index it in both implemented-feature navigation pages                                              | `atomixos-mol-bf2`                   |

## Validation Strategy

- Add an evaluation check named `build-configuration` for both host check namespaces.
- Test committed completeness, overlay omission of `version`, rejection of a present non-`1` overlay version, valid
  partial merge, converted timeout bounds/overflow, deterministic normalization, provenance, defaults, custom values,
  and each fail-closed validation class.
- Extend watchdog module evaluation to prove effective build policy maps to existing options without runtime state.
- Evaluate immutable `/etc` policy and metadata contents.
- Inspect lightweight image/bundle derivation metadata or outputs for matching sidecars and development naming without
  requiring every test to build a complete image.
- Add command-level tests with a fake `nix` executable to prove the exact task matrix, wrapper delegation, warning order,
  automatic detection, Lima path behavior, pure-default behavior, and arguments used for build/check commands.
- Verify syntax diagnostics include filename and native location context; schema diagnostics include filename and field.
- Verify Linux and Darwin `build-configuration` checks, exact canonical bytes, lowercase hexadecimal hash, byte-identical
  closure/image/bundle copies, development names, preflight-before-mutation ordering, and atomic GC-root replacement.
- Run `uv run scripts/check-docs.py`, mdBook, repository hooks, focused Nix checks, and the repository-standard suite.
- Preserve any environment limitation or unrelated baseline failure as explicit Beads evidence rather than weakening
  feature checks.

## Implementation Decomposition

1. `atomixos-mol-off.1` defines, validates, merges, normalizes, and documents version-1 schema and diagnostics.
2. `atomixos-mol-off.2` applies effective watchdog policy, canonical bytes, metadata, and byte-identical audit copies.
3. `atomixos-mol-off.3` wires the exact task matrix, automatic local overrides, warning, local-override identity,
   validation preflight, and atomic retained-link updates into supported `mise` workflows.

Each task begins with failing tests and updates its assigned reader documentation in the same commit.

## Dependencies and Parallelism

The schema task blocks policy integration. Integration blocks workflow wiring because the wrapper must target a stable
configuration input and artifact identity. The tasks are intentionally sequential and not parallel-safe because they
share flake/build integration. Every implementation task is blocked by specification reconciliation.

Build Configuration delivery (`atomixos-mol-t08`) blocks physical Watchdog Enforcement tasks `atomixos-aua.7.4`,
`atomixos-aua.7.11`, and `atomixos-aua.7.30`; Beads already records those edges. Their ordered dependents remain blocked
through the physical validation chain.

## Rollout and Migration

Land a committed default `build.toml` that preserves existing behavior. No data migration is required. Existing direct
Nix commands remain valid. Maintainers opt into local testing only by creating ignored `build.dev.toml`; deleting it is
the rollback. Future schema versions require an explicit design and migration policy.

## Risks and Tradeoffs

- Automatic local overlay use is convenient but could be overlooked; the pre-evaluation warning, `-dev` filenames, and
  immutable provenance mitigate that risk.
- Local override evaluation is narrowly impure because Git flakes cannot see ignored files. The fixed-path wrapper,
  exact transport, canonical hashing, and embedding preserve artifact auditability, while committed builds remain pure.
- A strict schema requires deliberate extension work but prevents typo-driven or silently ignored build policy.
- String durations are readable but need a restricted grammar and converted policy bounds. Hardware may support only
  discrete values, so physical evidence must record the actual programmed timeout.

## Rejected Alternatives

- **Runtime `config.toml` watchdog settings:** rejected because mutable provisioning must not own immutable hardware
  policy.
- **Automatic unmarked local override:** rejected because artifacts could be mistaken for committed-policy builds.
- **Explicit `--dev` requirement:** rejected in favor of automatic local experimentation with conspicuous warnings.
- **Committed shared `build.dev.toml`:** rejected; the user wants an ignored per-developer staging overlay.
- **Full systemd duration syntax:** rejected for predictable cross-platform validation.
- **Generic arbitrary sections or Nix fragments:** rejected as unvalidated complexity and a trust-boundary violation.
- **Multiple profile files or environment field overrides:** rejected as unnecessary for the first consumer.

## Open Questions

None required for implementation.

## Deferred Decisions

- Additional top-level sections are deferred to the feature that owns each new immutable policy concern.
- A future schema version and migration mechanism are deferred until version 1 cannot represent a required compatible
  extension.

## Planning Record

### Questions Asked and Answers

- Use committed defaults plus an override: yes; `build.toml` is committed and `build.dev.toml` supplies overrides.
- Commit the development file: no; it is ignored and per-developer.
- Select the override explicitly: no; supported local workflows apply it automatically and warn conspicuously.
- Initial schema: approved as version 1 with the three watchdog fields.
- Overlay behavior: approved as partial recursive merge with fail-closed strict validation.
- Duration grammar: restricted positive integer plus `ms`, `s`, `min`, or `h`; runtime is bounded to 10 seconds–5
  minutes and reboot to 1–10 minutes, with physical hardware capability verified separately.
- Automatic override scope: supported `mise` workflows; direct Git-backed Nix commands use committed policy.
- Embed effective policy and sidecars: approved.
- Mark local-override artifacts: approved with `-dev` and immutable provenance.
- Apply the same behavior to `mise run check`: approved with the same warning.

### Assumptions

- The repository remains the implementation owner.
- Initial configuration contains no secret-bearing values.
- Existing watchdog NixOS options remain the application surface.

### Design Changes During Planning

- Replaced an explicit `--dev` recommendation with automatic local overlay discovery plus layered safety signals.
- Limited version 1 to the concrete watchdog consumer instead of a speculative general schema.

### Source Material

- User decisions made while starting `build-configuration`.
- `docs/src/features/watchdog-enforcement/design.md` and its build-policy dependency.
- `flake.nix`, `mise.toml`, `modules/watchdog.nix`, `nix/image.nix`, and `nix/rauc-bundle.nix`.
- `docs/src/building.md`, `docs/src/architecture.md`, and current reference pages.
