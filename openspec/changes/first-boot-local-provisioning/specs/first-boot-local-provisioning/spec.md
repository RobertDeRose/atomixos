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
contract: admin password hash, admin SSH keys, explicit health requirements, and structured Quadlet definitions.

#### Scenario: Minimum valid config.toml includes admin access and stack definition

- **WHEN** a `config.toml` file is accepted for import
- **THEN** it includes `admin.password_hash`, at least one admin SSH key, at least one Quadlet-defined application or
  service unit, and explicit health requirements

### Requirement: config.toml expresses Quadlet as structured TOML

The `config.toml` format SHALL represent Quadlet units as structured TOML tables rather than raw embedded multiline
Quadlet blobs. The canonical identity shape SHALL be `quadlet.<type>.<name>.<section>`, where the device derives the
destination filename, destination path, and file mode from the unit type and name.

#### Scenario: Structured Quadlet tables map to rendered unit files

- **WHEN** the provisioning flow reads `[quadlet.container.traefik.Container]`
- **THEN** it treats that table as the `Container` section of the rendered `traefik.container` Quadlet unit under the
  canonical `/data/config/quadlet/` path

#### Scenario: TOML arrays render to repeated Quadlet directives

- **WHEN** a structured Quadlet table contains an array value such as `Network = ["frontend", "backend"]`
- **THEN** the rendered Quadlet unit contains repeated directives for that key rather than a single joined value

### Requirement: Imported provisioning state persists under /data/config

All persisted provisioning-derived configuration SHALL live under `/data/config/`. This SHALL include the imported
`config.toml`, the admin password hash, the admin SSH authorized key material, and the rendered Quadlet unit files.

#### Scenario: Imported provisioning state is stored under /data/config

- **WHEN** the provisioning flow successfully imports a `config.toml` seed
- **THEN** the resulting durable operator configuration is written under `/data/config/`

### Requirement: Rendered Quadlet configuration is activated through the standard system path

Rendered Quadlet files SHALL remain canonically stored under `/data/config/quadlet/`, and the boot process SHALL sync
them into the active rootful Quadlet path under `/etc/containers/systemd/` before starting the provisioned container or
pod services.

#### Scenario: Imported Quadlet files are synced into the active system path

- **WHEN** provisioning has rendered Quadlet files under `/data/config/quadlet/`
- **THEN** the system syncs those files into `/etc/containers/systemd/`, reloads systemd, and starts the rendered
  container or pod services from that active path

### Requirement: Bootstrap web console supports upload and basic form generation

When no provisioning seed file is found, the device SHALL start a constrained local bootstrap web console. The console
SHALL support uploading an existing `config.toml` and generating a new `config.toml` from a basic form for admin
credentials and application stack provisioning.

### Requirement: Bootstrap web console is exposed only on the LAN bootstrap endpoint

The bootstrap web console SHALL bind to the LAN bootstrap address and remain reachable only from the LAN interface. The
default local endpoint SHALL be `172.20.30.1:8080`.

#### Scenario: Bootstrap console listens on the LAN bootstrap endpoint

- **WHEN** the device starts the bootstrap web console
- **THEN** it listens on `172.20.30.1:8080` and is reachable from the LAN interface without opening the same endpoint on
  WAN

#### Scenario: Existing config.toml can be uploaded through the bootstrap console

- **WHEN** an operator opens the bootstrap web console on an unprovisioned device
- **THEN** the console allows uploading an existing `config.toml` for local import

#### Scenario: Basic form can generate a config.toml

- **WHEN** an operator uses the bootstrap web console without an existing seed file
- **THEN** the console presents a basic form that can generate a valid `config.toml` and apply it locally
