# Spec Delta

## ADDED Requirements

### Requirement: First boot discovers a local provisioning seed in priority order

On an unprovisioned device, the provisioning flow SHALL search for a `config.toml` seed in a fixed priority order. The
system SHALL detect the fresh-flash case in initrd before `systemd-repart` creates slot B. On a fresh flash where
`boot-b` is absent at that stage, the system SHALL search `/boot/config.toml` first, then an attached USB mass storage
device containing `config.toml`, and finally fall back to a local bootstrap web console if no seed is found.

#### Scenario: Fresh flash uses boot partition seed first

- **WHEN** the device boots for the first time after a fresh flash and initrd detects that `boot-b` is absent before
  repartitioning
- **THEN** the provisioning flow checks `/boot/config.toml` before searching removable USB storage or starting the
  bootstrap web console

#### Scenario: USB seed is used when no boot seed exists

- **WHEN** the device is unprovisioned, `boot-b` is absent, and `/boot/config.toml` is missing
- **THEN** the provisioning flow searches attached USB mass storage for `config.toml` before starting the bootstrap web
  console

#### Scenario: Bootstrap console starts when no seed is found

- **WHEN** the device is unprovisioned and no `config.toml` is found on either `/boot` or attached USB mass storage
- **THEN** the device starts a local bootstrap web console for interactive provisioning

### Requirement: Reprovisioning skips boot partition seed replay

If the device is reprovisioned by wiping `/data` after the slot layout already exists, the provisioning flow SHALL
distinguish that state from a fresh flash by using the initrd-detected fresh-flash marker. When the marker indicates
that slot B already existed before repartitioning, `/boot/config.toml` SHALL NOT be used as a provisioning seed, and
reprovisioning SHALL use USB seed discovery followed by the bootstrap web console.

#### Scenario: Reprovisioned device ignores boot partition seed

- **WHEN** the device boots with `/data` empty after a reprovision reset and the initrd fresh-flash marker indicates
  that slot B already existed
- **THEN** the provisioning flow skips `/boot/config.toml` and searches USB mass storage before starting the bootstrap
  web console

#### Scenario: Wiping /data returns the device to provisioning mode

- **WHEN** `/data` is wiped or reformatted on a device whose slot layout already includes `boot-b`
- **THEN** the next boot re-enters the local provisioning flow rather than treating the device as already provisioned

### Requirement: config.toml defines bounded provisioning data

The local provisioning artifact SHALL be a single `config.toml` file containing only the bounded appliance provisioning
contract: admin SSH keys, provisioned firewall inbound policy, optional LAN settings, explicit health requirements, and
structured Quadlet definitions.

#### Scenario: Minimum valid config.toml includes admin access and stack definition

- **WHEN** a `config.toml` file is accepted for import
- **THEN** it includes at least one admin SSH key, a `[firewall.inbound]` table with at least one TCP or UDP port,
  at least one Quadlet-defined application or service unit, and explicit health requirements

### Requirement: Provisioning renders firewall and LAN runtime state

The device SHALL render accepted provisioning input into JSON runtime state under `/data/config/`. Firewall inbound state
SHALL be written to `/data/config/firewall-inbound.json` as optional `tcp` and `udp` arrays of integer ports in
`1..65535`. LAN state SHALL be written to `/data/config/lan-settings.json` with the validated gateway CIDR, gateway IP,
subnet CIDR, netmask, DHCP range, DNS domain, hostname pattern, and gateway aliases.

#### Scenario: Firewall inbound config is bounded

- **WHEN** provisioning imports `[firewall.inbound]` with TCP or UDP ports
- **THEN** the persisted firewall JSON contains only normalized integer port arrays
- **AND** `provisioned-firewall-inbound.service` applies those ports only as WAN inbound rules

#### Scenario: LAN range excludes gateway

- **WHEN** provisioning imports `[lan]` with a gateway CIDR and DHCP range
- **THEN** the DHCP range is rejected unless it is inside the gateway `/24`, ordered, and excludes the gateway IP

### Requirement: config.toml expresses containers as structured TOML

The `config.toml` format SHALL represent Quadlet units as structured TOML tables rather than raw embedded multiline
Quadlet blobs. The canonical identity shape SHALL be `container.<name>.<section>`, with a required
`[container.<name>]` table that declares `privileged = true|false`. The device SHALL derive the rendered filename,
active path, and runtime mode from the container name plus that privilege flag.

#### Scenario: Structured Quadlet tables map to rendered unit files

- **WHEN** the provisioning flow reads `[container.traefik.Container]`
- **THEN** it treats that table as the `Container` section of the rendered `traefik.container` Quadlet unit under the
  canonical `/data/config/quadlet/` path

#### Scenario: TOML arrays render to repeated Quadlet directives

- **WHEN** a structured Quadlet table contains an array value such as `Network = ["frontend", "backend"]`
- **THEN** the rendered Quadlet unit contains repeated directives for that key rather than a single joined value

### Requirement: Imported provisioning state persists under /data/config

All persisted provisioning-derived configuration SHALL live under `/data/config/`. This SHALL include the imported
`config.toml`, the admin SSH authorized key material, and the rendered Quadlet unit files.

#### Scenario: Imported provisioning state is stored under /data/config

- **WHEN** the provisioning flow successfully imports a `config.toml` seed
- **THEN** the resulting durable operator configuration is written under `/data/config/`

### Requirement: Newly imported provisioning is usable without an extra reboot

When a new `config.toml` is imported on an unprovisioned boot, the device SHALL continue first boot without requiring an
extra reboot before relying on the imported SSH authorized keys or other persisted provisioning-derived runtime state.

#### Scenario: Imported config is usable in the same boot

- **WHEN** the device imports a new `config.toml` from `/boot`, USB, or the bootstrap web console
- **THEN** it applies the imported SSH keys and runtime configuration during that same boot

### Requirement: Rendered Quadlet configuration is activated through the standard system path

Rendered Quadlet files SHALL remain canonically stored under `/data/config/quadlet/`, and the boot process SHALL sync
them into the active Quadlet path for their runtime mode before starting provisioned services. Rootful units SHALL sync
under `/etc/containers/systemd/`, while rootless application units SHALL sync under the managed app user's Quadlet path.

#### Scenario: Imported Quadlet files are synced into the active system path

- **WHEN** provisioning has rendered Quadlet files under `/data/config/quadlet/`
- **THEN** the system syncs rootful and rootless units into their respective active Quadlet paths, reloads systemd, and
  starts the rendered services from those active paths

### Requirement: First boot blocks on required runtime apply steps

The first-boot completion gate SHALL require a discovered `config.toml` to import and validate successfully, then apply
the rendered runtime state before committing the RAUC slot. `lan-gateway-apply.service` and
`provisioned-firewall-inbound.service` failures SHALL prevent the completion sentinel and RAUC `mark-good`. Quadlet sync
failure SHALL be fatal when `/data/config/health-required.json` names required provisioned units.

#### Scenario: Runtime apply failure prevents slot commit

- **WHEN** a discovered `config.toml` imports and validates successfully
- **AND** LAN gateway apply or provisioned firewall apply fails
- **THEN** first boot does not write the completion sentinel
- **AND** the RAUC slot is not marked good

#### Scenario: Required Quadlet failure prevents slot commit

- **WHEN** a discovered `config.toml` imports and validates successfully
- **AND** Quadlet sync fails while health requirements name provisioned units
- **THEN** first boot does not write the completion sentinel
- **AND** the RAUC slot is not marked good

### Requirement: Quadlet runtime constraints are explicit

Provisioned containers SHALL be rendered into canonical Quadlet files before activation. Rootful containers require
`privileged = true` and SHALL be forced to `Network=host`. Rootless containers SHALL run as the managed app user, use
`Network=pasta`, and have non-loopback published ports rewritten to `127.0.0.1`. Runtime metadata SHALL be persisted to
`/data/config/quadlet-runtime.json`.

#### Scenario: Rootless published ports bind to loopback

- **WHEN** a rootless provisioned container declares `PublishPort = ["10080:80"]`
- **THEN** the rendered Quadlet contains `PublishPort=127.0.0.1:10080:80`

#### Scenario: Privileged containers use host networking

- **WHEN** a provisioned container declares `privileged = true`
- **THEN** the rendered Quadlet contains `Network=host`

### Requirement: Bootstrap web console supports upload and basic form generation

When no provisioning seed file is found, the device SHALL start a constrained local bootstrap web console. The console
SHALL support uploading an existing `config.toml` or supported config bundle, and generating a new `config.toml` from a
basic form for admin SSH keys and application stack provisioning.

#### Scenario: Generated config is shown back to the operator after apply

- **WHEN** an operator uses the bootstrap form to generate and apply a valid `config.toml`
- **THEN** the bootstrap UI shows the final applied `config.toml` content back to the operator

#### Scenario: Generated config can be downloaded after apply

- **WHEN** an operator uses the bootstrap form to generate and apply a valid `config.toml`
- **THEN** the bootstrap UI offers a direct download for that final applied `config.toml`

### Requirement: Bootstrap endpoint supports programmatic config import

The bootstrap service SHALL expose a constrained local API endpoint that accepts a complete `config.toml` payload or a
supported config bundle for programmatic local import using the same validation and persistence path as the web console.
The programmatic endpoint SHALL be `POST /api/config` and return JSON success or validation-error responses.

#### Scenario: Programmatic upload returns JSON

- **WHEN** a local client POSTs `config.toml` to `/api/config`
- **THEN** the bootstrap service validates and imports the payload
- **AND** the response is JSON indicating success or the validation error

### Requirement: Bootstrap web console is exposed only on the LAN bootstrap endpoint

The bootstrap web console SHALL bind to the LAN bootstrap address and remain reachable only from the LAN interface. The
default local endpoint SHALL be `172.20.30.1:8080`.

#### Scenario: Bootstrap console listens on the LAN bootstrap endpoint

- **WHEN** the device starts the bootstrap web console
- **THEN** it listens on `172.20.30.1:8080` and is reachable from the LAN interface without opening the same endpoint on
  WAN

#### Scenario: Existing config.toml can be uploaded through the bootstrap console

- **WHEN** an operator opens the bootstrap web console on an unprovisioned device
- **THEN** the console allows uploading an existing `config.toml` or supported config bundle for local import

#### Scenario: Basic form can generate a config.toml

- **WHEN** an operator uses the bootstrap web console without an existing seed file
- **THEN** the console presents a basic form that can generate a valid `config.toml` and apply it locally

#### Scenario: Programmatic client can upload config.toml directly

- **WHEN** a local client POSTs a complete `config.toml` payload or supported config bundle to the bootstrap API endpoint
- **THEN** the bootstrap service validates and imports it through the same path used by the web console upload flow
