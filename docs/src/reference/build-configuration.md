# Build Configuration

AtomixOS build policy uses a strict versioned TOML schema. The evaluator recursively merges the parsed base and local
overlay, then passes the result through one typed Nix module. That module owns field types, ranges, and cross-field
assertions; canonical artifacts and consumer values are derived only from its evaluated policy. Build configuration is
non-secret input fixed into artifacts; it is separate from mutable runtime provisioning in `config.toml`.

Built-in LAN fallback values are not build policy. They live in `defaults/lan.json`; see
[LAN Range](../provisioning/lan-range.md).

## Version 1 Schema

The committed `build.toml` document is complete:

```toml
version = 1

[watchdog]
enable_hardware = false
backend = "external"
runtime_timeout = "30s"
reboot_timeout = "10min"

[provisioning]
bootstrap_transport = "network"

[nixstasis]
enable = false
api_url = ""
frp_server_addr = ""
frp_server_port = 7000
```

| Field                              | Type    | Required in `build.toml` | Default    | Validation                          |
|------------------------------------|---------|--------------------------|------------|-------------------------------------|
| `version`                          | Integer | Yes                      | `1`        | Must equal `1`                      |
| `watchdog.enable_hardware`         | Boolean | Yes                      | `false`    | `true` or `false`                   |
| `watchdog.backend`                 | String  | Yes                      | `external` | `internal` or `external`            |
| `watchdog.runtime_timeout`         | String  | Yes                      | `30s`      | Inclusive range: 10 seconds–5 min   |
| `watchdog.reboot_timeout`          | String  | Yes                      | `10min`    | Inclusive range: 1 minute–10 min    |
| `provisioning.bootstrap_transport` | String  | Yes                      | `network`  | `network` or `nixstasis`            |
| `nixstasis.enable`                 | Boolean | Yes                      | `false`    | `true` or `false`                   |
| `nixstasis.api_url`                | String  | Yes                      | `""`       | Non-empty when Nixstasis is enabled |
| `nixstasis.frp_server_addr`        | String  | Yes                      | `""`       | Non-empty when Nixstasis is enabled |
| `nixstasis.frp_server_port`        | Integer | Yes                      | `7000`     | Inclusive range: 1–65535            |

Duration strings contain a positive integer followed immediately by one of `ms`, `s`, `min`, or `h`. Signs, zero,
decimals, compound spans, whitespace, unitless numbers, values that overflow conversion, and values outside the field's
converted range are invalid.

These ranges constrain accepted policy; they do not guarantee that a physical watchdog supports every accepted value.
systemd may program the nearest timeout the driver supports, so check the value it reports on the target hardware.

## Local Overlay Schema

`build.dev.toml` is ignored by Git and may contain only fields being tested. It merges recursively over `build.toml`; an
omitted field inherits the committed value. For example:

```toml
[watchdog]
enable_hardware = true
backend = "internal"
runtime_timeout = "45s"
```

The overlay may omit `version`. If present, `version` must equal `1`. It cannot remove a committed field or introduce an
unknown field. The effective document must still be complete after merging. A fleet overlay can opt into the reviewed
transport and provide the public Nixstasis endpoints:

```toml
[provisioning]
bootstrap_transport = "nixstasis"

[nixstasis]
enable = true
api_url = "https://nixstasis.example.invalid"
frp_server_addr = "frps.example.invalid"
frp_server_port = 7000
```

## Provisioning Transport and Nixstasis

`provisioning.bootstrap_transport` is an explicit policy. Selecting `nixstasis` requires
`nixstasis.enable = true`; enabling Nixstasis while retaining `network` is valid and does
not change the provisioning listener:

- `network` keeps the existing network bootstrap exposure and is the committed default.
- `nixstasis` selects the fleet loopback transport; the runtime listener and firewall behavior are owned by the fleet
  implementation.
- A fleet policy without the Nixstasis client enabled fails closed during evaluation.

The evaluator maps the typed effective policy to NixOS options without runtime TOML parsing or repeating build-policy
assertions in downstream adapter modules:

- `provisioning.bootstrap_transport` → `atomixos.provisioning.bootstrapTransport`.
- `nixstasis.enable` → `atomixos.nixstasis.enable`.
- `nixstasis.api_url` → `atomixos.nixstasis.apiUrl`.
- `nixstasis.frp_server_addr` and `nixstasis.frp_server_port` → the corresponding
  `atomixos.nixstasis.frp.*` options.

When `nixstasis.enable` is `true`, both `api_url` and `frp_server_addr` must be non-empty. These values are public
routing configuration only; runtime tokens, FRP credentials, signing keys, and other secrets are not valid build-policy
fields.

## Watchdog Backend Selection

`watchdog.enable_hardware` is the master switch. `watchdog.backend` remains required even when enforcement is disabled;
it selects the hardware path that will be used when enforcement is enabled. Neither setting is read from runtime
`config.toml`.

Use an ignored `build.dev.toml` for a local test build, or put the same values in committed `build.toml` for a promoted
build. The timeout fields may be omitted from a local overlay and inherit the committed values.

### Internal Rock64 Watchdog

The onboard RK3328 DesignWare watchdog uses the corrected TOP interval table and is exposed as
`/dev/watchdog-internal`:

```toml
[watchdog]
enable_hardware = true
backend = "internal"
```

### External SOM Watchdog

The external example path on Rock64 uses the TI UCC2946 through the PCA/TCA9536-compatible four-bit I2C GPIO expander
at bus 1, address `0x41`. GPIO0 is held low to enable the watchdog and GPIO1 toggles `WDI`; the kernel `gpio-pca953x`
and `gpio-wdt` drivers expose it as `/dev/watchdog-external`:

```toml
[watchdog]
enable_hardware = true
backend = "external"
```

Systemd remains the sole owner of either device. The legacy userspace `i2cset` kicker is not used.

### Radxa CM3 Watchdog

The CM3 IO Board has no external watchdog. CM3 builds always use the internal RK3566 watchdog (`fe600000`), exposed as
`/dev/watchdog-internal`; selecting `backend = "external"` with enforcement enabled logs a build warning and still uses
the internal device.

### Disable Watchdog Enforcement

Keep a valid backend value but set the master switch to `false`:

```toml
[watchdog]
enable_hardware = false
backend = "internal"
```

With enforcement disabled, systemd does not set `WatchdogDevice`, `RuntimeWatchdogSec`, or `RebootWatchdogSec`. The
external always-running device-tree node is also omitted, so the external hardware is not armed accidentally. The
backend choice has no runtime effect until enforcement is enabled.

## Strict Validation

Both documents reject:

- unknown top-level sections or fields in any supported table;
- wrong TOML value types;
- unsupported versions;
- a transport other than `network` or `nixstasis`;
- a Nixstasis port outside 1–65535;
- malformed or out-of-range durations;
- an incomplete committed document.

After the overlay is merged, an enabled Nixstasis policy also rejects an empty `api_url` or `frp_server_addr`.

A TOML syntax error reports the input filename and preserves the native parser's line and column context. A schema error
reports the input filename and canonical field path. Validation completes during Nix evaluation, before an artifact
derivation builds.

## Canonical Effective Form

The evaluator renders effective values in a deterministic order with lowercase booleans, one blank line before each
section, and one final newline:

```toml
version = 1

[watchdog]
enable_hardware = false
backend = "external"
runtime_timeout = "30s"
reboot_timeout = "10min"

[provisioning]
bootstrap_transport = "network"

[nixstasis]
enable = false
api_url = ""
frp_server_addr = ""
frp_server_port = 7000
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

| `mise` task                 | Applies local overlay | Contract                                                     |
|-----------------------------|-----------------------|--------------------------------------------------------------|
| `check`                     | No                    | Formatting, linting, and documentation only                  |
| `build [--board <board>]`   | Yes                   | Build and retain configured artifacts for one board          |
| `build:squashfs`            | Yes                   | Build immutable configured system policy (`--board`)         |
| `build:rauc-bundle`         | Yes                   | Build configured update and audit sidecars (`--board`)       |
| `build:boot-script`         | Yes                   | Reference the configured closure and squashfs ID (`--board`) |
| `vm:bundle-test`            | Yes                   | Build an interactive configured-system test                  |
| `e2e`, `e2e:*`, `e2e:debug` | No                    | Fixtures own explicit isolated configuration                 |
| `serial:*`, `_lima`, `gc`   | No                    | Commands do not construct configured AtomixOS outputs        |

Use `./scripts/nix-with-build-config.sh flake check` to evaluate and test effective policy, including a local overlay.
`mise run check` does not invoke Nix or apply build policy.

Direct `nix build .#...` and `nix flake check` remain pure and committed-policy-only. External `nixpkgs` helper builds
also remain outside this contract. When `mise run build --board <board>` exports a local-override image with
`-o <path>`, the destination filename must include `-dev`; an unmarked destination is rejected before evaluation or
retained-link mutation.

## Failure and Retention Contract

Effective policy is evaluated before a configured command creates or replaces an output link. The full retained build
runs an explicit preflight before creating `.gcroots`, builds all replacements under temporary `.new` links, and only
after every build succeeds points the selected board's `.gcroots/<board>/current`, `previous`, and `toplevel` links at the
new store paths. Each final link is written by `nix build <store-path> -o <link>`, which replaces it atomically and
registers it as a Nix GC root; a renamed link would leave Nix tracking the old path. ROCK64 and CM3 roots are independent.

A syntax, schema, evaluation, or later build failure preserves the board's previous `current`, `previous`, and `toplevel`
roots. Temporary links are removed on exit. Correct the document—or remove `build.dev.toml` to return to
committed policy—and rerun the same command.

Before publishing, the outgoing build is rooted under `previous.new`. If publishing itself is interrupted, the build stops
with an error and keeps every `.new` link, each a GC root, so neither build can be collected; rerunning the build
finishes publishing. A `current` link whose store path no longer exists is replaced without becoming `previous`.

## Security Boundary

Build configuration must not contain credentials, signing keys, certificates, tokens, or arbitrary Nix expressions.
Source revision, `flake.lock`, verification certificates, and signing credentials remain separately owned build inputs.
Unknown sections fail validation.
