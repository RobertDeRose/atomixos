# Build Configuration

AtomixOS build policy uses a strict versioned TOML schema. Build configuration is non-secret input fixed into artifacts;
it is separate from mutable runtime provisioning in `config.toml`.

## Version 1 Schema

The committed `build.toml` document is complete:

```toml
version = 1

[watchdog]
enable_hardware = false
runtime_timeout = "30s"
reboot_timeout = "10min"
```

| Field                      | Type    | Required in `build.toml` | Default | Validation                        |
|----------------------------|---------|--------------------------|---------|-----------------------------------|
| `version`                  | Integer | Yes                      | `1`     | Must equal `1`                    |
| `watchdog.enable_hardware` | Boolean | Yes                      | `false` | `true` or `false`                 |
| `watchdog.runtime_timeout` | String  | Yes                      | `30s`   | Inclusive range: 10 seconds–5 min |
| `watchdog.reboot_timeout`  | String  | Yes                      | `10min` | Inclusive range: 1 minute–10 min  |

Duration strings contain a positive integer followed immediately by one of `ms`, `s`, `min`, or `h`. Signs, zero,
decimals, compound spans, whitespace, unitless numbers, values that overflow conversion, and values outside the field's
converted range are invalid.

These ranges constrain accepted policy; they do not prove that a physical watchdog supports every accepted value.
Hardware validation must record the timeout systemd actually programs and verify that observed behavior satisfies the
intended timing.

## Local Overlay Schema

`build.dev.toml` is ignored by Git and may contain only fields being tested. It merges recursively over `build.toml`; an
omitted field inherits the committed value. For example:

```toml
[watchdog]
enable_hardware = true
runtime_timeout = "45s"
```

The overlay may omit `version`. If present, `version` must equal `1`. It cannot remove a committed field or introduce an
unknown field. The effective document must still be complete after merging.

## Strict Validation

Both documents reject:

- unknown top-level sections or watchdog fields;
- wrong TOML value types;
- unsupported versions;
- malformed or out-of-range durations;
- an incomplete committed document.

A TOML syntax error reports the input filename and preserves the native parser's line and column context. A schema error
reports the input filename and canonical field path. Validation completes during Nix evaluation, before an artifact
derivation builds.

## Canonical Effective Form

The evaluator renders effective values in a deterministic order with lowercase booleans, one blank line before the
watchdog section, and one final newline:

```toml
version = 1

[watchdog]
enable_hardware = false
runtime_timeout = "30s"
reboot_timeout = "10min"
```

## Immutable Policy and Provenance

Configured systems expose the canonical bytes at `/etc/atomixos/build.toml`. The adjacent
`/etc/atomixos/build-metadata.json` is one compact JSON object plus a final newline:

```json
{"local_override":false,"policy_sha256":"<64 lowercase hexadecimal characters>"}
```

`policy_sha256` is SHA-256 over the exact canonical TOML bytes, including the final newline. Image and RAUC bundle
output directories contain `build.toml` and `build-metadata.json` copied from the same immutable Nix store files, so the
sidecars and running-system files are byte-identical.

When a local override is effective, `local_override` is `true` and image and bundle filenames include `-dev`. This
marker means only that local build-policy overrides were applied. It does not describe the separate NixOS development
mode, signing certificate trust, or release readiness. Without a local override, the suffix is absent and
`local_override` is `false`.

## Supported Command Contract

`scripts/nix-with-build-config.sh` resolves only repository-root `build.dev.toml`. It removes any caller-provided
`ATOMIXOS_BUILD_DEV_CONFIG`; when the file exists, it sets that internal transport to the canonical repository path,
prints the warning, and appends `--impure` to the Nix command. The wrapper does not accept another configuration path or
parse policy itself. Lima tasks invoke the same wrapper inside the repository mounted at the same path.

| `mise` task                 | Applies local overlay | Contract                                              |
|-----------------------------|-----------------------|-------------------------------------------------------|
| `check`, `nix:check`        | Yes                   | Evaluate and test effective policy                    |
| `build`                     | Yes                   | Build and retain configured artifacts                 |
| `build:squashfs`            | Yes                   | Build immutable configured system policy              |
| `build:rauc-bundle`         | Yes                   | Build configured update and audit sidecars            |
| `build:boot-script`         | Yes                   | Reference the configured closure and squashfs ID      |
| `vm:bundle-test`            | Yes                   | Build an interactive configured-system test           |
| `e2e`, `e2e:*`, `e2e:debug` | No                    | Fixtures own explicit isolated configuration          |
| `serial:*`, `_lima`, `gc`   | No                    | Commands do not construct configured AtomixOS outputs |

Direct `nix build .#...` and `nix flake check` remain pure and committed-policy-only. External `nixpkgs` helper builds
also remain outside this contract.

## Failure and Retention Contract

Effective policy is evaluated before a configured command creates or replaces an output link. The full retained build
runs an explicit preflight before creating `.gcroots`, builds all replacements under temporary `.new` links, and renames
them over retained links only after every build succeeds. Renames use platform-specific no-dereference behavior so a
symlink to a Nix store directory is replaced rather than treated as a destination directory.

A syntax, schema, evaluation, or later build failure preserves all previous retained kernel, system, bootloader, image,
and bundle roots. Temporary links are removed on exit. Correct the document—or remove `build.dev.toml` to return to
committed policy—and rerun the same command.

## Security Boundary

Build configuration must not contain credentials, signing keys, certificates, tokens, or arbitrary Nix expressions.
Source revision, `flake.lock`, verification certificates, and signing credentials remain separately owned build inputs.
Unknown future sections fail until an owning feature defines and documents their schema.
