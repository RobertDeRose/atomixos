# Config Reapply Improvements

## Summary

Harden the existing `config.toml` re-apply path and formalize the configuration contract. The feature keeps first-time
provisioning local and unblocked, but requires authenticated, validated, atomic replacement for already-provisioned
devices. It also moves OS/device settings into explicit top-level sections and nests all container-related Quadlet config
under `[containers]`.

## Project Plan Source

This feature is seeded from `docs/src/planned-features.md` entry `config-reapply-improvements`, plus the feature request
to restructure `config.toml` around `[users]`, `[network]`, and `[containers]`, and to introduce an official schema.

## Goals

- Reject unauthenticated `POST /api/config` requests on already-provisioned devices.
- Validate `config.toml` against an official schema before any persistent state is replaced.
- Replace `/data/config` atomically enough that crashes do not leave partially imported state.
- Roll back to the previous config when service activation fails after re-apply.
- Reserve top-level `config.toml` sections for OS/device configuration.
- Move all container, network, volume, and build Quadlet configuration under `[containers]`.
- Introduce structured top-level `[users]` and `[network]` sections.
- Manage local users declared under `[users.<name>]`.
- Preserve the fresh-flash provisioning path from `/boot`, USB, and the bootstrap UI.

## Non-Goals

- Full `/data` wipe or factory reset behavior.
- Partial config updates; re-apply remains a full replacement operation.
- Changing the A/B update model or RAUC slot confirmation semantics beyond checking re-applied services.
- Adding remote fleet management or Nixstasis integration.
- Making `config.toml` a general-purpose Linux distribution configuration format.

## Current Behavior

`scripts/first-boot-provision.py` owns config parsing, import, bootstrap UI, and `POST /api/config`. The current format
uses top-level `[admin]`, `[firewall]`, `[health]`, optional `[lan]`, optional `[os_upgrade]`, and top-level Quadlet tables
such as `[container.<name>]`, `[network.<name>]`, `[volume.<name>]`, and `[build.<name>]`.

The existing import path writes derived state under `/data/config`, including:

- `config.toml`
- `admin-signers`
- `ssh-authorized-keys/admin`
- `firewall-inbound.json`
- `lan-settings.json`
- `os-upgrade.json`
- `quadlet/`
- `quadlet-runtime.json`

The base image currently sets `users.mutableUsers = false` and declares only fixed service users such as `appsvc`.
OpenSSH already reads authorized keys from `/data/config/ssh-authorized-keys/%u`, but arbitrary config-declared
users do not exist unless a runtime apply step materializes them.

The planned feature states that basic re-apply already works by accepting a POST, overwriting `/data/config`, and running
Quadlet sync. This feature narrows that behavior into a safer state-machine.

## Config Contract

### Top-Level Sections

Top-level sections are reserved for OS/device configuration:

- `[users]`
- `[network]`
- `[health]`
- `[os_upgrade]`
- `[containers]`

The prior top-level `[admin]`, `[firewall]`, `[lan]`, `[container]`, `[network]` as Quadlet networks, `[volume]`, and
`[build]` tables are rejected by the new schema. AtomixOS is still unreleased and in design/testing, so this feature does
not need a compatibility or migration path for earlier test configs. Existing examples and docs must be updated in the
same unit of work.

### Users

`[users]` contains named local users. The implementation must manage declared users, including creating or updating local
accounts and their SSH authorized keys from the config.

Example:

```toml
[users]

[users.admin]
isAdmin = true
ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQCt5v7m8X9Zl5n"

[users.guest]
isAdmin = false
ssh_key = ""
```

Rules:

- `isAdmin` defaults to `false`.
- `ssh_key` defaults to an empty string.
- At least one admin user with a non-empty SSH public key is required before first boot can complete.
- Empty SSH keys are ignored, not written as authorized key lines.
- Admin users are members of `wheel`; non-admin users are not.
- Removed users from a re-applied config are disabled or locked rather than silently retaining access.
- Usernames must be validated against a narrow safe pattern and must not collide with reserved system users.
- The existing password-locked, key-only SSH model remains mandatory for all managed users.

Because the root filesystem is an immutable squashfs with an ephemeral overlay, managed users must be derived from
persisted config on every boot or re-apply. The import path should write normalized user state under `/data/config`, and
a dedicated runtime apply step should materialize those users and groups before SSH access is expected. The apply step
must preserve fixed system users such as `root` and `appsvc`; operator accounts, including an optional `admin` username,
come from `[users.<name>]` config.

### Network

`[network]` contains device networking, DNS, dnsmasq, and firewall configuration.

The implemented schema covers the LAN gateway and firewall controls this feature wires into runtime services:

- dnsmasq enablement and dnsmasq LAN configuration.
- upstream NTP servers for chrony, defaulting to Cloudflare NTP.
- Firewall rules equivalent to the current provisioned firewall model.

DNS servers, DNS search domains, arbitrary interface configuration, and default gateway configuration are deferred until
runtime support is implemented.

The default network behavior remains the current LAN gateway design:

- `eth0` is WAN.
- `eth1` is LAN.
- dnsmasq is enabled by default.
- LAN gateway defaults to `172.20.30.1/24`.
- DHCP serves the existing `172.20.30.10` through `172.20.30.254` range unless overridden.
- DHCP option 3, 6, and 42 point at the gateway IP.
- DNS remains gateway-local by default.
- NTP is served to LAN clients by chrony.
- IP forwarding remains disabled.

### Containers

`[containers]` is the only top-level section for operator-provisioned Quadlet config. It contains nested sections for
container units and supporting units.

The canonical structure should be:

```toml
[containers.container.example]
privileged = false

[containers.container.example.Container]
Image = "docker.io/library/nginx:latest"

[containers.network.app]
[containers.network.app.Network]
Subnet = "10.89.0.0/24"

[containers.volume.data]
[containers.volume.data.Volume]
Driver = "local"

[containers.build.custom]
[containers.build.custom.Build]
File = "${FILES_DIR}/Containerfile"
ImageTag = "localhost/custom:latest"
```

Rules:

- Container units continue to use the existing rootful/rootless safety boundary.
- Network and volume Quadlet units remain rootful.
- `${CONFIG_DIR}` and `${FILES_DIR}` substitution behavior remains unchanged.
- `quadlet-runtime.json` remains the authoritative runtime metadata for sync.

## Official Schema

The repository already has `schemas/config.schema.json` and a small in-repo schema validator in
`scripts/first-boot-provision.py`. This feature must replace that schema with the new canonical `config.toml` contract and
keep the in-repo validator unless implementation proves it cannot express a required rule. The schema should produce clear
path-specific errors such as `network.interfaces.eth1.address must be a CIDR string`.

Schema requirements:

- Validate allowed and required keys.
- Validate types, defaults, enums, and port ranges.
- Validate cross-field constraints, such as DHCP range matching the LAN subnet.
- Validate that required service names reference rendered Quadlet units.
- Validate that at least one admin SSH key exists.
- Reject legacy top-level config sections rather than silently accepting or migrating them.
- Be usable by `first-boot-provision validate` and by the bootstrap API before persistent writes.

Avoid adding a third-party schema dependency unless the in-repo validator cannot support a required rule within a small,
auditable implementation.

## Reapply Flow

Fresh provisioning remains unauthenticated because the device has no prior operator credential. Re-apply on an already
provisioned device must require authentication before accepting config bytes.

Proposed flow:

1. Receive `config.toml` or supported config bundle.
2. If `/data/config/config.toml` already exists, require LAN-local authentication.
3. Unpack and validate the candidate config in a temporary directory outside active `/data/config` state.
4. Render all derived state into a candidate config directory.
5. Snapshot or rename the previous `/data/config` into a rollback location.
6. Atomically promote the candidate directory into `/data/config`.
7. Apply LAN, firewall, and Quadlet sync using the same services as boot.
8. Confirm required services become healthy.
9. Delete or age out rollback state only after successful apply.
10. Restore the previous config and re-apply it if activation fails.

Authentication uses an SSH-key challenge-response with an existing admin SSH key. The device issues a nonce for a short
validity window, and the operator signs a request-bound message containing the nonce, target path, and SHA-256 digest of
the submitted config payload. The device verifies the signature against active admin signer keys before accepting config
bytes. This keeps re-apply LAN-local, avoids default credentials, and reuses the existing key-only operator trust model.

## Failure Handling

- Invalid TOML or schema errors return a non-2xx response and leave active config untouched.
- Failed candidate rendering leaves active config untouched.
- Failed authentication returns a non-2xx response before parsing or writing the candidate config.
- Crash before promotion leaves active config untouched.
- Crash after promotion but before confirmation must be recoverable on next boot or next apply by detecting incomplete
  re-apply state.
- Failed service activation restores previous config and reports the failed services.
- Rollback must not delete container volumes or arbitrary `/data` content.

## Documentation Impact

Likely affected pages:

- `docs/src/provisioning.md`
- `docs/src/provisioning/lan-range.md`
- `docs/src/data-flow.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/tutorials/oidc-device-management.md`
- `docs/src/specs/lan-gateway.md`
- `docs/src/specs/update-confirmation.md`
- `docs/src/code-reference/scripts.md`
- `docs/src/code-reference/modules.md`
- `docs/src/features/caddy-authcrunch-cockpit-tutorial/design.md`
- `schemas/config.schema.json`
- `modules/base.nix`
- `modules/first-boot.nix`
- `example/caddy-oidc/config.toml`

## Validation Plan

- Unit tests for schema validation, defaults, and path-specific error messages.
- Unit tests for legacy top-level config tables being rejected.
- Tests for `[users]` admin key extraction and empty-key handling.
- Tests for managed user creation/update/disable behavior.
- Tests for managed users being re-materialized from `/data/config` after reboot.
- Tests for `[network]` defaults matching current LAN gateway behavior.
- Tests for SSH-key challenge-response authentication success and failure paths.
- Tests for candidate config rendering without touching active `/data/config`.
- VM test for authenticated re-apply success.
- VM test for unauthenticated re-apply rejection on an already-provisioned device.
- VM test for invalid config preserving previous state.
- VM test for activation failure rolling back to previous config.

## Risks

- Restructuring `config.toml` intentionally breaks earlier test configs; examples and docs must be updated with the code.
- Runtime user management conflicts with the current `users.mutableUsers = false` posture unless implemented as an explicit
  apply service that safely materializes `/data/config` user state on each boot.
- Authentication design can become too complex for local recovery if it depends on external services.
- Atomic directory replacement on `/data` must be implemented carefully on f2fs.
- Service rollback can restore config files but cannot guarantee application-level container data consistency.
- Adding a third-party schema dependency may increase image closure size.
