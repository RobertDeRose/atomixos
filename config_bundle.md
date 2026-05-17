# Config Bundle Design

## Purpose

Define the next provisioning contract for AtomixOS as a config bundle rather
than a single-purpose application manifest.

The platform goal is:

- NixOS provides a stable, reproducible, upgradable A/B OTA foundation.
- The application layer is the real purpose of the platform.
- The deployment contract must stay generic enough for end users to deploy
  whatever they want, however they want, within the platform's supported
  runtime and security boundaries.

This document captures the intended config bundle design in full detail so it
can be used as the source of truth for importer validation, preprocessing, and
future implementation.

## High-Level Direction

The provisioning artifact should become a config bundle with two concerns:

- `config.toml` contains OS-level and platform-level customization that maps
  directly to platform-managed resources such as users, SSH keys, firewall
  rules, activation requirements, and container definitions.
- `files/` contains arbitrary application-specific files that the platform does
  not interpret semantically. Containers may mount these files wherever they
  need them.

This avoids hard-coding application-specific concepts such as Traefik routing
config directly into the schema while still allowing the bundle to carry the
files applications actually need.

## Bundle Formats

The platform should support both:

- a plain `config.toml` upload/import
- a compressed bundle archive upload/import

Supported bundle archive formats:

- `config.tar.gz`
- `config.tgz`
- `config.tar.zst`
- `config.tzst`

Bundle layout rules:

- `config.toml` must exist at the archive top level
- `files/` is optional
- no other top-level entries are allowed
- archive entries must be relative paths only
- absolute paths and `..` traversal are invalid
- regular files and directories are allowed
- symlinks, devices, fifos, and other special archive member types are rejected

Expected layout:

```text
bundle/
├── config.toml
└── files/
    ├── traefik/
    │   └── dynamic.yml
    └── app/
        └── config.yaml
```

Imported durable layout:

```text
/data/config/
  config.toml
  ssh-authorized-keys/<user>
  admin-signers
  health-required.json
  quadlet/
    *.container
    *.network
    *.volume
    *.pod
    *.image
    *.build
  files/
    ... arbitrary imported bundle files ...
```

## Scope of `config.toml`

`config.toml` is for platform-owned configuration only.

It should express:

- admin SSH keys
- minimal firewall ingress policy
- required activation units
- container definitions

It should not attempt to embed full application configuration when files are a
better fit. Application-specific configuration belongs under `files/` and is
mounted by containers as needed.

## Schema Goals

The schema should:

- be easy to validate mechanically in the importer
- keep the namespace small
- leave implementation details under OS ownership whenever possible
- preserve future implementation freedom
- distinguish between rootful and rootless runtime behavior without forcing the
  user to understand all low-level runtime details

## Top-Level Schema

Current intended top-level structure:

```toml
version = 2

[users.admin]
isAdmin = true
ssh_key = "ssh-ed25519 AAAA..."

[network.firewall.inbound.wan]
tcp = [80, 443]
udp = [1194]

[network.ntp]
servers = ["time.cloudflare.com"]

[activation]
required = ["traefik", "whoami"]

[containers.container.<name>]
privileged = true | false

[containers.container.<name>.Unit]
...

[containers.container.<name>.Container]
...

[containers.container.<name>.Install]
...
```

The namespace uses `containers.<type>.<name>` so container, network, volume, and
build Quadlet resources live under one top-level `containers` table.

## Formal Schema Specification

This section is deliberately strict so the Python importer can validate against
it directly.

### Root Table

Allowed keys:

- `version`
- `users`
- `network`
- `activation`
- `os_upgrade`
- `containers`

Required keys:

- `version`
- `users`
- `activation`
- `containers`

#### `version`

- type: integer
- required value: `1`

Any other version is rejected.

### `users`

Required table.

Each key is a managed username. At least one user must be declared.

For each user `<name>`, allowed keys are:

- `isAdmin`
- `ssh_key`

#### `users.<name>.isAdmin`

- type: boolean
- optional, defaults to `false`
- at least one user must set `isAdmin = true`

#### `users.<name>.ssh_key`

- type: string
- required for admin users
- written to `/data/config/ssh-authorized-keys/<name>`
- admin keys are also written to `/data/config/admin-signers` for re-apply
  signature verification

No password hash or password-based operator login is supported.

### `network`

Optional table.

Allowed keys:

- `dnsmasq`
- `ntp`
- `firewall`

Unknown legacy network keys are rejected.

### `network.firewall`

Optional table.

Allowed keys:

- `inbound`

### `network.firewall.inbound`

Optional table.

Allowed keys:

- `wan`
- `lan`

Each scope may contain:

- `tcp`
- `udp`

At least one of `tcp` or `udp` should be present.

#### `network.firewall.inbound.<scope>.tcp`

- type: non-empty array of integers
- each integer must be a valid TCP port in range `1..65535`

#### `network.firewall.inbound.<scope>.udp`

- type: non-empty array of integers
- each integer must be a valid UDP port in range `1..65535`

Firewall semantics:

- `wan` entries are inbound ports to allow on the WAN side
- `lan` entries switch LAN from default-open to an explicit allowlist merged
  with platform-required LAN ports
- only allow semantics are exposed
- default policy remains drop
- the user does not configure default policy

Rationale:

- the platform already owns WAN vs LAN policy boundaries
- there is no cross-network exposure at the OS level beyond what applications
  choose to expose
- the schema should stay intentionally narrow for now

### `network.dnsmasq`

Optional table for LAN DHCP/DNS settings. Omitted fields use the fallback LAN
gateway contract.

Allowed keys:

- `enable`
- `interface`
- `gateway_cidr`
- `dhcp_start`
- `dhcp_end`
- `domain`
- `hostname_pattern`
- `gateway_aliases`

`enable` must remain true and `interface`, when provided, must be `eth1`.

### `network.ntp`

Optional table for upstream NTP servers.

Allowed keys:

- `servers`

#### `network.ntp.servers`

- type: non-empty array of non-empty strings
- defaults to `["time.cloudflare.com"]`
- whitespace and control characters are rejected before rendering chrony config

### `activation`

Required table.

Allowed keys:

- `required`

Required keys:

- `required`

#### `activation.required`

- type: non-empty array of non-empty strings
- each item names a required application/service unit
- each item must correspond to a declared container name

### `containers`

Required table.

- allowed keys: `container`, `network`, `volume`, `build`
- `container` is required and must be a non-empty table
- each resource key is a Quadlet resource name
- container names must be non-empty and may not contain `/`, NUL, `.` or `..`

For each container `<name>`, the following subtables are allowed:

- `[containers.container.<name>]`
- `[containers.container.<name>.Unit]`
- `[containers.container.<name>.Container]`
- `[containers.container.<name>.Install]`
- other systemd pass-through sections may be allowed in the future, but the
  initial importer should validate only the sections it explicitly supports

#### `[containers.container.<name>]`

Required table.

Allowed keys:

- `privileged`

Required keys:

- `privileged`

##### `containers.container.<name>.privileged`

- type: boolean

Semantics:

- `true` means the container is platform-managed as a rootful/system workload
- `false` means the container is platform-managed as a rootless workload

This flag intentionally hides lower-level runtime details from the schema.

The OS retains ownership of the implementation details behind this distinction.

#### `[containers.container.<name>.Unit]`

Optional table.

- type: table of scalar or repeated values supported by the importer
- rendered directly into the Quadlet `[Unit]` section

#### `[containers.container.<name>.Container]`

Required table.

- type: table
- must include at least `Image`
- values are rendered into the Quadlet `[Container]` section after platform
  preprocessing and validation

#### `[containers.container.<name>.Install]`

Optional table.

- type: table
- rendered into the Quadlet `[Install]` section

## Runtime Ownership Model

The platform owns runtime details that should not yet be user-configurable.

### Rootful / `privileged = true`

The platform interprets this as a rootful system-managed container.

Current intended semantics:

- render as a rootful/system Quadlet
- `Network=host` is automatically applied
- this gives the platform freedom to change the low-level implementation later
  while preserving the higher-level contract

The schema user should not have to understand:

- rootful Quadlet placement
- systemd system-unit wiring
- host namespace exposure details

### Rootless / `privileged = false`

The platform interprets this as a rootless platform-managed app workload.

The OS owns:

- the dedicated app user
- linger setup
- shared rootless network setup
- user-level Quadlet placement and lifecycle wiring

These details should not be exposed directly in `config.toml` yet.

## Shared Rootless Network Model

All rootless application containers should share one private rootless container
network with each other.

Intent:

- rootless app containers can communicate with each other without complex
  per-application networking config
- the platform creates and owns the shared rootless network
- the user should not need to model this in `config.toml`

Important clarification:

- the shared private network is for the rootless app tier
- there is no assumed shared private network between a rootful ingress
  container and the rootless app tier

## Rootful Ingress and Rootless App Tier

The expected application architecture is:

- a rootful ingress container such as Traefik
- rootless application containers behind it
- rootless apps share a private rootless network with each other
- ingress to selected rootless apps happens through explicit high-port publish
  rules, not through a shared network with the rootful ingress container

The rootful ingress container should not be assumed to share a private Podman
network with rootless workloads.

## Rootless PublishPort Rules

For rootless containers, the platform should enforce loopback-only host
publishing.

If a rootless container contains:

- `PublishPort = ["10080:80"]`

the importer should rewrite it to:

- `PublishPort=127.0.0.1:10080:80`

If a rootless container contains:

- `PublishPort = ["127.0.0.1:10080:80"]`

keep it as-is.

If it contains:

- `PublishPort = ["localhost:10080:80"]`

normalize it to:

- `127.0.0.1:10080:80`

If it specifies any non-loopback bind address, the importer should:

- replace it with `127.0.0.1`
- emit a warning that the value was rewritten

This preserves a clean and supportable contract:

- rootless backends may publish high ports to loopback
- they are not directly exposed to the outside world
- ingress services may route to those loopback ports explicitly

## Rootful `Network=host` Semantics

For `privileged = true`, the current design preference is to treat the
container as host-networked.

Implications:

- Podman does not need to manage published-port NAT rules for that container
- the container binds directly to host ports like a normal host process
- host nftables still controls whether those ports are reachable

This is why exposing inbound host ports remains a platform-level firewall
concern rather than something delegated entirely to container runtime behavior.

## Firewall and Redirects

The schema should not try to model HTTP-to-HTTPS redirect as a raw nftables
rule.

Reason:

- nftables can redirect traffic from one port to another
- nftables cannot transform plain HTTP into HTTPS
- redirecting TCP port 80 to 443 at the packet level would send HTTP bytes to a
  TLS listener and is not equivalent to a proper HTTP redirect

So:

- opening 80 and 443 belongs in `network.firewall.inbound.wan`
- HTTP-to-HTTPS redirect must still be handled by an HTTP-aware service such as
  Traefik or a future platform-managed redirect helper

The schema should not currently encode Traefik-specific redirect behavior.

## Generic Files Mounting

Application-specific files are carried under `files/` and may be mounted by
containers wherever needed.

Examples:

- Traefik dynamic config
- reverse proxy certificates
- application YAML/JSON config
- templated config files

This avoids hard-coding application-specific configuration structure into
`config.toml`.

## Path Token Preprocessing

The importer should preprocess string values in rendered Quadlet data for the
following tokens:

- `${CONFIG_DIR}` -> `/data/config`
- `${FILES_DIR}` -> `/data/config/files`

The names should be:

- `CONFIG_DIR`
- `FILES_DIR`

These substitutions should be implemented by the importer itself rather than
depending on native TOML or systemd expansion behavior.

Rationale:

- makes the contract explicit
- keeps behavior reproducible
- avoids relying on ambiguous runtime expansion semantics

## Validation Rules for Importer

The importer should validate:

- `version == 2`
- at least one `users.<name>` entry is an admin with a non-empty `ssh_key`
- `network.firewall.inbound.<scope>.tcp` and `udp`, when present, are valid port arrays
- `activation.required` is a non-empty string array
- `containers.container` exists and defines at least one container
- each container defines `privileged`
- each container defines `[Container]` with `Image`
- `activation.required` names correspond to declared containers
- bundle layout is valid when importing archives
- bundle top level is limited to `config.toml` and optional `files/`
- archive member paths are safe

The importer should preprocess:

- path tokens
- rootless loopback-only `PublishPort`
- any platform-owned rewrites implied by `privileged`

The importer should emit warnings for:

- rootless non-loopback `PublishPort` values that were rewritten to loopback

## Upload and API Behavior

The bootstrap web UI and API should support both:

- plain `config.toml`
- config bundle archives

Web upload support:

- raw `config.toml`
- `config.tar.gz`
- `config.tgz`
- `config.tar.zst`
- `config.tzst`

API support should accept raw request bodies and use filename hints when
available to determine whether the payload is a plain config or bundle archive.

The platform should continue to support simple `config.toml` upload because it
is convenient for early bootstrap and debugging.

## Why This Direction

This design is preferred because:

- it keeps the schema small
- it leaves runtime details under OS ownership
- it avoids application-specific hard-coding
- it gives the platform freedom to change implementation later
- it supports both rootful and rootless application models
- it supports arbitrary application file payloads cleanly
- it remains easy to validate in the importer

## Non-Goals Right Now

Not part of the initial schema surface:

- per-interface firewall customization
- changing firewall default policy
- arbitrary nftables rule authoring
- exposing rootful vs rootless user/linger/network details directly
- assuming rootful ingress shares a private Podman network with rootless apps
- hard-coded Traefik-specific routing semantics in `config.toml`
- migration compatibility with the old design, since there are no users of the
  old design yet
