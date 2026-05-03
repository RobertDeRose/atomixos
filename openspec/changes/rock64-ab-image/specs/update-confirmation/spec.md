# Update Confirmation Spec

## ADDED Requirements

### Requirement: `os-verification.service` validates local post-update health

A systemd oneshot service (`os-verification.service`) SHALL run after boot on systems that have already completed the
separate first-boot provisioning flow. It SHALL perform device-local health checks and SHALL NOT depend on external
network reachability for slot confirmation.

#### Scenario: Gateway services are validated

- **WHEN** `os-verification.service` runs after boot on a pending slot
- **THEN** it checks that `dnsmasq.service` and `chronyd.service` are active
- **AND** it checks that `eth0` has a WAN IPv4 address
- **AND** it checks that `eth1` matches the provisioned LAN gateway IP from `/data/config/lan-settings.json`
- **AND** it falls back to `172.20.30.1` when no valid provisioned LAN settings exist

#### Scenario: Service exits early for already-good slots

- **WHEN** the device boots a slot that RAUC already reports as good
- **THEN** `os-verification.service` exits without re-running the confirmation flow

### Requirement: Provisioned health requirements come from `/data/config/health-required.json`

If `/data/config/health-required.json` exists, `os-verification.service` SHALL read it as the list of provisioned units
that must be active before the slot can be committed.

#### Scenario: Required provisioned units are active

- **WHEN** `/data/config/health-required.json` lists one or more provisioned units
- **THEN** `os-verification.service` checks that each corresponding `${name}.service` is active

#### Scenario: Required provisioned unit is missing or inactive

- **WHEN** any unit named in `/data/config/health-required.json` is not active
- **THEN** `os-verification.service` exits with a non-zero status
- **AND** the slot remains uncommitted

#### Scenario: No explicit provisioned health requirements exist

- **WHEN** `/data/config/health-required.json` is absent or empty
- **THEN** `os-verification.service` uses the gateway health checks alone

### Requirement: Sustained health check catches unstable services

After the initial checks pass, `os-verification.service` SHALL continue checking health for a sustained 60-second window
using a 5-second interval.

#### Scenario: Health remains stable for the sustained window

- **WHEN** all confirmation checks continue to pass for 60 seconds
- **THEN** the slot is eligible to be committed

#### Scenario: A required service becomes unhealthy during the sustained window

- **WHEN** `dnsmasq.service`, a required provisioned unit, or another required check fails during the 60-second window
- **THEN** `os-verification.service` exits with a non-zero status
- **AND** the slot remains uncommitted

### Requirement: Successful confirmation commits the slot with RAUC

When the confirmation checks succeed, `os-verification.service` SHALL call `rauc status mark-good` for the booted slot.

#### Scenario: Slot is committed after successful checks

- **WHEN** all required checks pass for the sustained confirmation window
- **THEN** `os-verification.service` calls `rauc status mark-good`
- **AND** the booted slot becomes committed

### Requirement: Failed confirmation leaves the slot pending rollback

If confirmation fails, the system SHALL NOT commit the slot.

#### Scenario: Repeated failed confirmation leads to rollback

- **WHEN** the device repeatedly boots an updated slot that never passes confirmation
- **THEN** the slot remains uncommitted
- **AND** the U-Boot / RAUC rollback path can eventually fall back to the previous working slot

### Requirement: First boot uses a separate provisioning-aware commit path

Initial first boot SHALL be handled by `first-boot.service`, not `os-verification.service`.

#### Scenario: First boot is gated on valid provisioning

- **WHEN** the device boots for the first time after flash or reprovisioning
- **THEN** `first-boot.service` owns the provisioning import and validation flow
- **AND** the initial slot is committed only after valid provisioning state exists
