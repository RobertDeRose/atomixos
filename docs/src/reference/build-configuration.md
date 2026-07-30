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

Artifact embedding, provenance, supported command behavior, and audit procedures are documented as their integration is
delivered.

## Security Boundary

Build configuration must not contain credentials, signing keys, certificates, tokens, or arbitrary Nix expressions.
Source revision, `flake.lock`, verification certificates, and signing credentials remain separately owned build inputs.
Unknown future sections fail until an owning feature defines and documents their schema.
