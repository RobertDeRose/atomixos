# Feature: nixstasis-client

## Source

Seeded from `docs/src/planned-features.md` entry `nixstasis-client`, refined by
review against the existing client implementation at
`/Users/DeRoseR/workspace/personal/nixstasis/packages/client`, and aligned with
`docs/src/architecture/overwatch-enrollment.md`.

## Overview

Include the existing Nixstasis Go client in the AtomixOS squashfs as part of the
base operating system closure. AtomixOS should consume the Nixstasis client as a
flake input/package, install its binary and runtime assets into the immutable
image, and provide AtomixOS-specific NixOS module wiring for configuration,
identity persistence, registration, polling, and FRP tunnel operation.

This feature is an integration feature, not a rewrite of the Nixstasis client or
protocol. The client remains the source of truth for the Nixstasis API contract:
registration uses `POST /api/v1/devices/register`, polling uses
`POST /api/v1/devices/{id}/heartbeat`, and heartbeat responses can provide the
`remote_access_token` used for FRP remote access.

## Goals

1. Add Nix flake packaging to the Nixstasis repository and consume that flake
   package from AtomixOS.
2. Install the existing `nixstasis` client binary into the squashfs closure.
3. Install required client runtime assets, including `frpc` and `frpc.toml`, in
   paths compatible with the client defaults or explicit environment overrides.
4. Render `/etc/nixstasis/config.yaml` from AtomixOS NixOS options.
5. Persist the Nixstasis identity file on `/data`, while presenting the path the
   client expects through `NIXSTASIS_IDENTITY_PATH` or a stable bind/symlink.
6. Run registration and polling under systemd without blocking local boot, LAN
   gateway service, or local SSH recovery.
7. Preserve AtomixOS key-only SSH and zero-default-credential guarantees.
8. Validate the integration with a NixOS VM test using the Nixstasis mock API.

## Non-Goals

- Reimplementing the Nixstasis client in AtomixOS.
- Defining a new AtomixOS-specific Nixstasis HTTP protocol.
- Implementing Nixstasis server-side inventory, approval, or fleet orchestration.
- Hosting a web management UI on the device.
- Making provisioned containers responsible for remote management availability.
- Extending `config.toml` for Nixstasis configuration in the first iteration.

## Constraints

- The client must live in the immutable rootfs/squashfs closure so it survives
  container-layer failures.
- Mutable identity and runtime state must live on `/data` or another persistent
  path that survives RAUC slot switches.
- The AtomixOS integration should not patch the Nixstasis API behavior unless an
  upstream client change is required and reviewed separately.
- The system must tolerate WAN or Nixstasis outages without failing boot.
- SSH must remain key-only. Nixstasis-managed authorized keys must be explicit,
  bounded to the configured path, and compatible with existing SSH policy.
- The integration must fit the existing embedded image size and avoid duplicating
  large runtime assets unnecessarily.

## Existing Nixstasis Client Behavior

The current client package provides:

- `nixstasis register`
- `nixstasis poll`
- `nixstasis frp-session`
- config loading from `/etc/nixstasis/config.yaml`, with `NIXSTASIS_CONFIG_FILE`
  override
- identity loading from `/etc/nixstasis/id`, with `NIXSTASIS_IDENTITY_PATH`
  override
- bundled FRP defaults at `/usr/libexec/nixstasis/frpc` and
  `/usr/share/nixstasis/frpc.toml`, with `NIXSTASIS_FRPC_BINARY_PATH` and
  `NIXSTASIS_FRPC_CONFIG_PATH` overrides
- runtime authorized key management defaulting to
  `/var/lib/nixstasis/.ssh/authorized_keys`
- registration endpoint `POST /api/v1/devices/register`
- heartbeat endpoint `POST /api/v1/devices/{id}/heartbeat`
- FRP auth token sourced from heartbeat `remote_access_token` and passed to the
  transient FRP service as a systemd credential

AtomixOS should integrate these behaviors instead of restating or replacing the
protocol.

## Architecture

### Flake Integration

Add Nix flake packaging to the Nixstasis repository first, then add that repo as
an AtomixOS flake input. AtomixOS should not create a long-lived local package
adapter for this feature; the reusable client package belongs with the Nixstasis
client source.

The AtomixOS package should install at least:

- `nixstasis` executable
- `frpc` executable for the target architecture
- `frpc.toml` template
- example/default config material needed for rendered config validation

### AtomixOS Module Surface

Add an AtomixOS NixOS module, expected as `modules/nixstasis.nix`, with options
similar to:

- `atomixos.nixstasis.enable`
- `atomixos.nixstasis.package`
- `atomixos.nixstasis.apiUrl`
- `atomixos.nixstasis.pollInterval`
- `atomixos.nixstasis.frp.serverAddr`
- `atomixos.nixstasis.frp.serverPort`
- `atomixos.nixstasis.frp.httpLocalAddr`
- `atomixos.nixstasis.frp.sshLocalPort`
- `atomixos.nixstasis.runtime.sshUser`
- `atomixos.nixstasis.runtime.execCommands`

The first implementation should keep these as image-build-time options. A later
feature can decide whether provisioning `config.toml` should render Nixstasis
client settings.

### Persistent State

Persist the device identity below `/data`, for example:

- `/data/nixstasis/id`
- `/data/nixstasis/.ssh/authorized_keys`

Configure the client with environment variables rather than patching its defaults:

- `NIXSTASIS_IDENTITY_PATH=/data/nixstasis/id`
- `NIXSTASIS_CONFIG_FILE=/etc/nixstasis/config.yaml`
- `NIXSTASIS_FRPC_BINARY_PATH=<store path or installed libexec path>`
- `NIXSTASIS_FRPC_CONFIG_PATH=<store path or installed share path>`

The module should create `/data/nixstasis` with restrictive permissions before
registration or polling starts. The identity file remains the Nixstasis client's
JSON credential file and may contain both UUID and runtime token.

### Systemd Units

Do not directly import the upstream Debian/RPM unit files without review. Recreate
AtomixOS-native systemd units so paths, persistence, ordering, hardening, and
restart policy match the appliance.

Expected units:

- `nixstasis-registration.service`: runs `nixstasis register` while identity is
  absent or incomplete
- `nixstasis-poll.service`: runs `nixstasis poll` after registration state exists

Both units should order after network availability but should not be required by
`multi-user.target` in a way that blocks boot. Restart/backoff should tolerate
WAN or server outages.

### SSH Access Boundary

The client can manage only its configured authorized-keys file. AtomixOS must make
that path meaningful to OpenSSH without weakening existing admin key behavior.

The first implementation should prefer adding the Nixstasis authorized-keys file
as an additional `services.openssh.authorizedKeysFiles` entry rather than merging
Nixstasis keys into `/data/config/ssh-authorized-keys/%u`. This keeps Nixstasis
remote access state separate from provisioned operator admin state. The first
implementation exposes that file only inside an OpenSSH `Match User admin` block
by default so Nixstasis-managed keys do not authenticate every local account.

Any command execution exposed through Nixstasis scripts remains deny-by-default
through `runtime.exec_commands`; only explicitly configured commands should be
  available in the rendered client config. Identity repair for a corrupt
  `/data/nixstasis/id` file is manual in this iteration; delete the file and
  restart registration to re-enroll.

### FRP Remote Access

Use the Nixstasis client's existing FRP manager. The heartbeat response supplies
`remote_access_token`; the client passes that token to a transient FRP unit as a
systemd credential. AtomixOS should ensure `systemd-run`, `systemctl`, and the
configured `frpc` binary are available in the unit environment.

FRP local endpoints should default to local SSH and, if enabled, local HTTPS only.
The module must not open new WAN firewall ports for FRP; remote access is outbound
from the device to the configured Nixstasis/FRP server.

## Documentation Impact

- `docs/src/architecture/overwatch-enrollment.md`: update from future-tense model
  to the included client behavior.
- `docs/src/runtime-boundaries.md`: document Nixstasis as immutable platform code
  with mutable state under `/data/nixstasis`.
- `docs/src/testing.md`: document the Nixstasis mock-API VM validation.
- `docs/src/planned-features.md`: mark this feature complete after closeout.
- `docs/src/SUMMARY.md`: add the feature spec to the feature list if that is the
  current convention for new specs.

## Validation

- Nix evaluation/build proves the Nixstasis client package is included in the
  AtomixOS closure for the target architecture.
- Unit or VM assertions verify rendered `/etc/nixstasis/config.yaml` contains the
  configured API URL, poll interval, FRP settings, authorized-keys path, and
  explicit command allowlist.
- NixOS VM test starts a mock Nixstasis API compatible with the existing client
  endpoints.
- VM test verifies registration creates persistent identity under `/data`.
- VM test verifies polling sends heartbeat data after registration.
- VM test verifies a mock `remote_access_token` triggers the FRP launch boundary:
  the client attempts to start the transient FRP unit and passes the token through
  the intended credential path. Full end-to-end FRP server/tunnel validation is
  deferred.
- VM test verifies server unavailability does not block boot or local SSH/LAN
  recovery.

## Success Criteria

1. AtomixOS images can include the Nixstasis client from the Nixstasis flake/package.
2. The client binary and FRP assets are present in the squashfs closure when enabled.
3. Registration against the mock API persists identity under `/data`.
4. Polling reuses persisted identity and reaches the mock heartbeat endpoint.
5. Nixstasis-managed SSH access is isolated from provisioned operator keys.
6. WAN/Nixstasis outages do not block boot or local recovery.

## Risks And Tradeoffs

- The Nixstasis repository currently has no flake packaging, so this feature spans
  the Nixstasis repo and AtomixOS integration.
- Bundling FRP increases closure size and should be measured.
- The client's default paths are FHS-like; AtomixOS must use environment overrides
  or Nix-native paths carefully.
- Adding a second authorized-keys source can confuse operational recovery if not
  documented clearly.
- Full FRP tunnel validation may need a heavier integration environment than the
  initial VM test.

## Resolved Review Decisions

- The existing Nixstasis client and API contract are authoritative. AtomixOS will
  not define a local placeholder protocol.
- The feature is about including and wiring the client into the OS squashfs as a
  flake/package dependency.
- Nix flake packaging should be added to the Nixstasis repository rather than
  hidden behind an AtomixOS-side temporary adapter.
- Nixstasis configuration remains a NixOS/image option for this feature; extending
  `config.toml` is deferred.
- First-pass AtomixOS VM validation covers the FRP launch boundary, not a real
  end-to-end FRP tunnel.

## Open Questions

None for initial implementation.
