# Feature: rock64-ab-image

## Overview

### Why

- Rock64 devices need a robust OTA update model that keeps the previous system bootable while a new image is written and
  verified.
- The device is also the LAN isolation boundary for downstream legacy equipment, so networking, authentication, and
  recovery behavior must be explicit parts of the platform design.
- Early exploration included an on-device Cockpit/Traefik management path and password-oriented fallback flows, but the
  implemented platform moved to a smaller appliance baseline: Podman stays on-device for workloads, while remote web
  management is expected to live in the Nixstasis environment instead of the device image itself.

### What Changes

- Introduce a NixOS flake that builds the Rock64 system, flashable image, signed RAUC bundle, and QEMU test target
- Implement an A/B layout with per-slot boot partitions, squashfs rootfs slots, and `/data` created on first boot by
  initrd `systemd-repart`
- Use RAUC plus U-Boot bootmeth for slot switching and rollback, with `rauc status mark-good` used for confirmation
- Keep Podman, OpenVPN, OpenSSH, chrony, dnsmasq, nftables, and the update client in the device image
- Remove the local Cockpit/Traefik management stack from the final device design while preserving application workloads
  through Podman
- Use SSH-key-only operator access, locked local passwords, and `_RUT_OH_` as a physical serial recovery path
- Support provisioning-aware first boot through the bounded `config.toml` contract defined by the
  `first-boot-local-provisioning` follow-on change
- Keep the update client swappable between the default `os-upgrade` polling path and a future hawkBit path

### Capabilities

### New Capabilities

- `nix-flake-config`: Rock64/QEMU flake outputs, stripped kernel, core runtime services, and build artifacts
- `partition-layout`: Flashable image layout with U-Boot raw region, slot A in the image, and slot B plus `/data`
  provisioned on first boot
- `rauc-integration`: RAUC system configuration, signed multi-slot bundle building, slot definitions, and update client
  integration
- `boot-rollback`: U-Boot boot-count logic and RAUC-driven slot confirmation / rollback behavior
- `watchdog`: Hardware-watchdog-oriented design, with QEMU validation and hardware re-enablement tracked separately
- `update-confirmation`: Local `os-verification` health checks before committing updated slots
- `lan-gateway`: Deterministic NIC naming, DHCP/NTP on LAN, nftables policy, and no packet forwarding between WAN and
  LAN

### Follow-on Changes

- `first-boot-local-provisioning`: Refines the day-0 and reprovisioning flow, the `config.toml` contract, and the
  `/data/config/` persistence boundary
- `durable-journald-logs`: Defines the current runtime log durability model and the still-incomplete initrd forensic
  redesign

### Impact

- **Affected code**: `flake.nix`, shared/system modules, image and bundle derivations, U-Boot boot script, RAUC config,
  first-boot/update services, and QEMU tests
- **Affected storage layout**: raw U-Boot region, per-slot boot/rootfs partitions, and durable operator/runtime state on
  `/data`
- **Affected operations**: flash/build workflow, first boot, update confirmation, rollback, LAN gateway bring-up, and
  remote recovery
- **Security**: no embedded login credentials, key-only operator access, WAN SSH disabled by default, and no default
  packet forwarding between networks

## Design

This document is maintained as the current source of truth for the foundational Rock64 A/B image design. Where the
implementation diverged from early exploration, the current design is described directly and explicit divergence notes
are kept only when they explain an important technical decision.

### Context

AtomixOS is a secure, reproducible operating system for single-board computers. The initial target is Rock64 (RK3328,
aarch64) hardware. The platform must tolerate failed updates and power loss without bricking the device, while keeping
the base image small enough to fit two rootfs slots plus persistent state on 16 GB eMMC.

The implemented platform centers on:

- NixOS built as a read-only squashfs image
- RAUC-managed A/B updates
- U-Boot boot-count rollback
- Podman for on-device application workloads
- LAN gateway services (dnsmasq, chrony, nftables)
- SSH-key-only operator access and a physical serial recovery path
- Nixstasis-oriented remote management rather than a permanent local web-management stack inside the device image

### Goals / Non-Goals

**Goals**

- Atomic A/B updates that only write the inactive slot pair
- Automatic rollback when a new slot fails to boot or cannot stay healthy
- A read-only appliance baseline with durable state isolated under `/data`
- Deterministic networking and strict LAN/WAN isolation behavior
- A small runtime closure that still supports Podman workloads and recovery access
- A QEMU target that shares the real configuration for rapid iteration and test coverage

**Non-Goals**

- Running a permanent Cockpit/Traefik management surface directly on the device
- Embedding device credentials or per-device secrets in the base image
- Generic provisioning engines such as cloud-init
- Server-side update infrastructure design
- Full logging durability redesign in this change

### Decisions

### 1. Use RAUC for A/B updates

**Decision:** Use RAUC as the update framework for multi-slot installs, signature verification, and slot metadata.

**Rationale:** RAUC fits the NixOS ecosystem well, supports multi-image bundles, and integrates cleanly with the U-Boot
boot-count model the device uses.

### 2. Use a read-only squashfs rootfs with OverlayFS at boot

**Decision:** The runtime system is a read-only squashfs lower layer combined with a tmpfs-backed OverlayFS upper/work
layer assembled in initrd.

**Rationale:** This keeps the runtime root immutable, avoids drift across boots, and makes the A/B slot boundary easy to
reason about. Mutable state lives outside the rootfs on `/data`.

### 3. Partition the eMMC as raw U-Boot + per-slot boot/rootfs + `/data`

**Decision:** The flashable image contains raw U-Boot plus `boot-a` and `rootfs-a`. On first boot, initrd
`systemd-repart` creates `boot-b`, `rootfs-b`, and the persistent `data` partition from the remaining space.

**Rationale:** This keeps the shipped image small and deterministic while still resulting in a full A/B layout on-device.
Per-slot boot partitions avoid a shared `/boot` single point of failure.

The current target layout is:

```text
0-16 MiB     raw U-Boot region
128 MiB      boot-a (vfat)
1024 MiB     rootfs-a (squashfs/raw)
128 MiB      boot-b (vfat, created on first boot)
1024 MiB     rootfs-b (raw, created on first boot)
remainder    /data (f2fs, created on first boot)
```

### 4. Use U-Boot bootmeth plus RAUC mark-good for slot commit

**Decision:** U-Boot bootmeth handles slot choice and boot-count decrement. Linux confirms a healthy slot with
`rauc status mark-good`.

**Rationale:** This matches the current Rock64 implementation and keeps the rollback model aligned with RAUC's slot view.

**Technical note:** Earlier investigation explored alternatives because raw eMMC env writes were risky on this hardware
path. The current implementation relies on SPI-backed environment handling plus `rauc status mark-good`, which is what
the live system and tests now use.

### 5. Keep the device image small and remove local Cockpit/Traefik management

**Decision:** Keep Podman on-device for application workloads, but do not ship a local Cockpit/Traefik management stack
as part of the final base image.

**Rationale:** The local web-management path added closure size and operational complexity that no longer matches the
intended remote-management model. The current design expects remote web access to be hosted from the Nixstasis side,
while the device itself remains focused on SSH, update logic, LAN gateway behavior, and workload runtime support.

### 6. Keep OpenVPN in the rootfs as a recovery path

**Decision:** OpenVPN remains a rootfs service for recovery-oriented remote access.

**Rationale:** It provides a durable management path independent of application containers and is useful when WAN SSH is
disabled by policy.

### 7. Make first boot provisioning-aware

**Decision:** A valid provisioning import is part of the production first-boot contract, not a post-boot manual step.

**Rationale:** A device that boots Linux but lacks operator credentials and required workload intent is not actually ready
for deployment. The detailed contract is defined in the `first-boot-local-provisioning` follow-on change, but the core
foundational design is now provisioning-aware:

- fresh-flash detection happens in initrd
- first boot can import from `/boot/config.toml`, USB media, or a LAN-local bootstrap UI
- imported operator intent persists under `/data/config/`
- first boot calls `rauc status mark-good` only after provisioning import/validation succeeds

### 8. Use local health confirmation for updated slots

**Decision:** `os-verification.service` validates device-local health before committing an updated slot.

**Rationale:** Slot confirmation should not depend on external connectivity. The implemented checks are intentionally
bounded:

- `dnsmasq.service` is active
- `chronyd.service` is active
- `eth0` has a WAN IPv4 address
- `eth1` is `172.20.30.1`
- each unit listed in `/data/config/health-required.json` is active
- the checks stay healthy for a sustained 60-second window

If those checks pass, `os-verification.service` calls `rauc status mark-good`.

### 9. Enforce deterministic networking and strict LAN/WAN separation

**Decision:** The onboard GMAC is always `eth0`, the USB LAN adapter becomes `eth1`, and packet forwarding stays off.

**Rationale:** The device identity, WAN policy, and LAN gateway behavior all depend on stable interface roles.

The effective network model is:

- `eth0`: WAN DHCP client
- `eth1`: LAN gateway at `172.20.30.1/24`
- dnsmasq serves DHCP only on LAN
- chrony serves NTP only on LAN
- nftables allows WAN HTTPS/OpenVPN, LAN DHCP/NTP/SSH/bootstrap UI, and no forwarding
- WAN SSH stays off unless `/data/config/ssh-wan-enabled` exists

### 10. Use SSH-key-only operator access with physical serial recovery

**Decision:** Operator accounts are declared by config under `[users.<name>]`, remain password-locked, and use SSH keys
from `/data/config/ssh-authorized-keys/<user>`. Root is also locked by default. `_RUT_OH_` is a physical serial-only
recovery path, not a network authentication mode.

**Rationale:** This matches the implemented security posture and removes ambiguity around password-based operator access.

### 11. Keep the update client hawkBit-ready, but default to simple polling

**Decision:** `os-upgrade.timer` is the default update client. The design still reserves a future hawkBit path through a
configuration switch, but the current implementation keeps the simple polling path as the active one.

**Rationale:** The device-side architecture should not block future fleet-management integration, but the default runtime
should stay small and directly testable.

### 12. Keep runtime log durability simple and bounded

**Decision:** Runtime logs use volatile journald plus buffered rsyslog writes to `/data/logs`, with a slot-local forensic
ring for key lifecycle events.

**Rationale:** This keeps the general logging path lightweight while still persisting important state transitions.

**Technical note:** The initrd forensic persistence path is currently disabled pending redesign. That follow-on work is
tracked in `durable-journald-logs`.

### Risks / Trade-offs

- **Watchdog on hardware is still staged**: the design includes the hardware watchdog path, but live Rock64 enablement is
  still gated on stable hardware validation.
- **Provisioning is now part of the first-boot success contract**: this is correct for production, but it means invalid
  provisioning blocks slot confirmation.
- **No local web-management stack in the base image**: this reduces closure size and appliance complexity, but shifts
  remote-management responsibility to Nixstasis-hosted services.
- **Full image updates consume more bandwidth than delta approaches**: acceptable for the current phase.
- **Initrd forensic durability is incomplete**: runtime durability exists, but the earliest boot persistence path still
  needs a safer redesign.

### Related Follow-on Changes

- `first-boot-local-provisioning` refines the provisioning contract, source-order logic, and `/data/config/` layout
- `durable-journald-logs` refines the runtime log-durability model and tracks the incomplete initrd redesign

## Requirements

### boot-rollback

#### ADDED Requirements

### Requirement: U-Boot tracks boot attempts per slot

U-Boot SHALL maintain a boot-attempt counter for each slot (`BOOT_A_LEFT`, `BOOT_B_LEFT`). On each boot attempt, the
counter for the selected slot SHALL be decremented. If the counter reaches zero, U-Boot SHALL fall back to the other
slot on the next boot.

#### Scenario: Boot counter decrements on each boot

- **WHEN** the device boots and the active slot has `BOOT_A_LEFT=3`
- **THEN** U-Boot decrements the slot counter before attempting the boot

#### Scenario: Slot switches when counter reaches zero

- **WHEN** the active slot's boot counter reaches `0`
- **THEN** U-Boot selects the other slot on the next boot

### Requirement: U-Boot boot order reflects the next slot priority

U-Boot SHALL use `BOOT_ORDER` to determine slot priority, and RAUC installation SHALL make the newly written inactive
slot the next slot to attempt.

#### Scenario: RAUC install changes the preferred slot

- **WHEN** RAUC installs a bundle to slot B while slot A is active
- **THEN** the next boot attempts slot B before slot A

### Requirement: Successful confirmation commits the slot with RAUC

After successful first-boot validation or post-update confirmation, Linux SHALL call `rauc status mark-good` for the
booted slot.

#### Scenario: First boot commits the slot after valid provisioning

- **WHEN** `first-boot.service` successfully imports and validates provisioning state
- **THEN** it calls `rauc status mark-good` for the booted slot

#### Scenario: Updated slot is committed after local verification

- **WHEN** `os-verification.service` confirms the booted slot is healthy
- **THEN** it calls `rauc status mark-good` for the booted slot

### Requirement: Rollback preserves the previous working slot

If a newly installed slot cannot boot successfully or never reaches a committed state, U-Boot SHALL eventually fall back
to the previous working slot.

#### Scenario: Failed update triggers automatic rollback

- **WHEN** a new image is installed to slot B and slot B fails repeatedly until its boot counter is exhausted
- **THEN** U-Boot falls back to slot A

#### Scenario: Previous slot remains intact

- **WHEN** the device rolls back from slot B to slot A
- **THEN** slot A still contains the previously working image because updates only write the inactive slot pair

### Requirement: Rock64 uses the active U-Boot environment path supported by the platform

The Rock64 rollback design SHALL use the platform's active U-Boot environment path together with RAUC's U-Boot backend
rather than relying on ad hoc slot bookkeeping in Linux.

#### Scenario: Linux and U-Boot agree on slot identity

- **WHEN** Linux determines the booted slot and calls `rauc status mark-good`
- **THEN** the same slot identity is used by the U-Boot / RAUC rollback path

### lan-gateway

#### LAN Gateway Requirements

### Requirement: Network interfaces are named deterministically

The NixOS configuration SHALL disable systemd predictable interface names and use systemd-networkd `.link` files to
assign deterministic names: onboard RK3328 GMAC SHALL be `eth0`, USB ethernet adapters SHALL be `eth1`, `eth2`, etc.,
    The onboard NIC SHALL be matched by its hardware platform path (`platform-ff540000.ethernet`). USB WiFi dongles are
    not part of the current Rock64 support contract.

#### Scenario: Onboard NIC is always eth0

- **WHEN** the Rock64 boots with or without USB network adapters plugged in
- **THEN** the onboard RK3328 GMAC is named `eth0` regardless of USB device enumeration order

#### Scenario: USB NIC is assigned sequential ethN name

- **WHEN** a USB ethernet adapter is plugged into the Rock64
- **THEN** it is assigned the next available `ethN` name (e.g., `eth1`)

### Requirement: eth0 is configured as WAN interface

eth0 (onboard NIC) SHALL be configured as a DHCP client to obtain a WAN address from the upstream network.

#### Scenario: eth0 obtains WAN address

- **WHEN** the Rock64 boots and eth0 is connected to a network with a DHCP server
- **THEN** eth0 obtains an IP address via DHCP

### Requirement: eth1 is configured as LAN interface with static IP

eth1 (USB NIC) SHALL be configured with the provisioned LAN gateway IP and prefix. If no valid provisioned LAN config
exists, it SHALL fall back to `172.20.30.1/24`.

#### Scenario: eth1 has correct static address

- **WHEN** the Rock64 boots with a USB NIC plugged in and a valid LAN config is present
- **THEN** eth1 has the provisioned gateway IP and prefix

#### Scenario: eth1 falls back to default static address

- **WHEN** the Rock64 boots with no valid provisioned LAN config
- **THEN** eth1 has IP address `172.20.30.1` with netmask `255.255.255.0`

### Requirement: IP forwarding is disabled

The kernel parameter `net.ipv4.ip_forward` SHALL be set to `0`. No packet-level routing SHALL occur between any
interfaces. This provides the EN18031 compliance boundary for legacy LAN devices.

#### Scenario: No traffic is routed between interfaces

- **WHEN** a device on the LAN (172.20.30.x) sends a packet destined for a WAN address
- **THEN** the packet is dropped by the Rock64 kernel and never reaches eth0

### Requirement: DHCP server runs on LAN interface

dnsmasq SHALL be configured to serve DHCP on eth1 (LAN) only. The DHCP pool SHALL use the provisioned LAN DHCP range,
reserving lower addresses for static assignments.

#### Scenario: LAN device obtains IP via DHCP

- **WHEN** a device is connected to the switch on the LAN
- **THEN** it receives an IP address in the provisioned DHCP range from the Rock64's DHCP server

#### Scenario: DHCP only serves LAN

- **WHEN** a DHCP request arrives on eth0 (WAN)
- **THEN** dnsmasq does not respond to it

### Requirement: NTP server runs on LAN interface

chrony SHALL be configured as both an NTP client (syncing from WAN NTP servers via eth0) and an NTP server (serving time
to LAN devices on eth1). NTP service SHALL accept clients from the provisioned LAN subnet. When no valid provisioned LAN
config exists, it SHALL accept clients from the fallback `172.20.30.0/24` subnet.

#### Scenario: Rock64 syncs time from WAN

- **WHEN** the Rock64 boots with WAN connectivity
- **THEN** chrony synchronizes time from upstream NTP servers via eth0

#### Scenario: LAN device syncs time from Rock64

- **WHEN** a LAN device queries NTP at the provisioned LAN gateway IP
- **THEN** chrony responds with the current time

#### Scenario: NTP rejects non-LAN clients

- **WHEN** an NTP request arrives from a source outside the provisioned LAN subnet
- **THEN** chrony does not respond

### Requirement: nftables firewall restricts traffic per interface

nftables SHALL be configured with the following rules:

**eth0 (WAN) inbound**: ALLOW established/related, DROP all else by default. Provisioned firewall state MAY add
application or VPN ports from `/data/config/firewall-inbound.json` under the `wan` scope. TCP/22 (SSH) is allowed only
if the flag file `/data/config/ssh-wan-enabled` exists.

**eth1 (LAN) inbound**: ALLOW all inbound traffic by default. If provisioned firewall state includes a `lan` scope with
TCP or UDP ports in `/data/config/firewall-inbound.json`, the provisioned LAN ports SHALL be appended to the
platform-required LAN ports instead of replacing them.

**tun0 (VPN) inbound**: ALLOW TCP/22 (SSH), ALLOW established/related, DROP all else.

**FORWARD chain**: DROP all (no inter-interface routing).

#### Scenario: WAN application ports are provisioned

- **WHEN** `/data/config/firewall-inbound.json` contains `wan.tcp = [443]`
- **AND** `provisioned-firewall-inbound.service` applies the provisioned state
- **THEN** HTTPS connections to eth0 on port 443 are accepted

#### Scenario: LAN application ports are provisioned

- **WHEN** `/data/config/firewall-inbound.json` contains `lan.tcp = [443]`
- **AND** `provisioned-firewall-inbound.service` applies the provisioned state
- **THEN** inbound connections to eth1 on TCP 443 are accepted

#### Scenario: LAN remains open without explicit LAN scope

- **WHEN** `/data/config/firewall-inbound.json` does not contain a `lan` scope with any ports
- **THEN** inbound connections to eth1 remain accepted by the default LAN-open rule

#### Scenario: Provisioned LAN ports append to required platform ports

- **WHEN** `/data/config/firewall-inbound.json` contains `lan.tcp = [443]`
- **AND** `provisioned-firewall-inbound.service` applies the provisioned state
- **THEN** inbound connections to eth1 on TCP 443 are accepted
- **AND** the platform-required LAN ports remain accepted

#### Scenario: WAN application ports are closed before provisioning

- **WHEN** no provisioned firewall state allows TCP/443 or UDP/1194
- **THEN** new inbound connections to eth0 on TCP/443 and UDP/1194 are dropped

#### Scenario: SSH is blocked on WAN by default

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` does not exist
- **THEN** the connection is dropped

#### Scenario: SSH is allowed on WAN when flag is set

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` exists
- **THEN** the connection is accepted

#### Scenario: SSH is always allowed on LAN

- **WHEN** an SSH connection is attempted to eth1 on port 22
- **THEN** the connection is accepted

#### Scenario: DNS is allowed on LAN

- **WHEN** a DNS query is sent to eth1 on TCP/53 or UDP/53
- **THEN** the packet is accepted

#### Scenario: Bootstrap UI is allowed on LAN by default

- **WHEN** a connection is made to eth1 on TCP/8080
- **THEN** the connection is accepted

#### Scenario: SSH is allowed over VPN

- **WHEN** an SSH connection is attempted via the tun0 interface on port 22
- **THEN** the connection is accepted

#### Scenario: No forwarding between interfaces

- **WHEN** any packet arrives that would be forwarded between interfaces
- **THEN** the packet is dropped by the FORWARD chain

### Requirement: WAN SSH toggle is manual only

SSH access on eth0 (WAN) SHALL be controlled by the presence of the flag file `/data/config/ssh-wan-enabled`. In the
production design, this flag is an explicit operator-controlled toggle rather than an automatically managed runtime rule.

#### Scenario: Flag file enables WAN SSH

- **WHEN** `/data/config/ssh-wan-enabled` is created
- **THEN** the nftables rule for SSH on eth0 becomes active on the next firewall reload or reboot

#### Scenario: Flag file removal disables WAN SSH

- **WHEN** `/data/config/ssh-wan-enabled` is removed
- **THEN** SSH connections to eth0 are dropped on the next firewall reload or reboot

### Requirement: Device identity uses eth0 MAC address

The device identity SHALL be derived from the MAC address of eth0 (onboard NIC). This address SHALL be readable from
`/sys/class/net/eth0/address`, normalized to compact lowercase 12-hex format, and used as the unique device identifier
for update confirmation, fleet management, and device registration.

#### Scenario: Device ID is consistent across reboots

- **WHEN** the device reboots or updates to a new slot
- **THEN** the device identity (eth0 MAC) remains the same

### nix-flake-config

#### Nix Flake Requirements

### Requirement: The flake defines Rock64 and QEMU system configurations

The flake SHALL define `nixosConfigurations.rock64` for the real Rock64 hardware target and
`nixosConfigurations.rock64-qemu` for the shared QEMU test target.

#### Scenario: Flake evaluates successfully

- **WHEN** `nix flake check` is run against the repository
- **THEN** the flake evaluates without errors
- **AND** both `nixosConfigurations.rock64` and `nixosConfigurations.rock64-qemu` are present

#### Scenario: System configuration targets `aarch64-linux`

- **WHEN** the Rock64 configuration is built
- **THEN** its system outputs target `aarch64-linux`

### Requirement: The flake produces a read-only squashfs root filesystem

The flake SHALL produce a squashfs image as `packages.aarch64-linux.squashfs`. The image SHALL contain the system
closure required for the appliance baseline and SHALL be sized to fit within the 1 GiB rootfs slot.

#### Scenario: Squashfs image builds successfully

- **WHEN** `nix build .#squashfs` is run
- **THEN** a squashfs image is produced

#### Scenario: Squashfs image fits the slot budget

- **WHEN** the squashfs image is built
- **THEN** the resulting image is no larger than the configured 1 GiB slot limit

### Requirement: The flake produces a signed RAUC bundle and flashable image

The flake SHALL expose a signed RAUC bundle as `packages.aarch64-linux.rauc-bundle` and a flashable device image as
`packages.aarch64-linux.image`.

#### Scenario: RAUC bundle builds successfully

- **WHEN** `nix build .#rauc-bundle` is run
- **THEN** a signed `.raucb` file is produced that passes `rauc info`

#### Scenario: Flashable image builds successfully

- **WHEN** `nix build .#image` is run
- **THEN** a flashable Rock64 disk image is produced containing U-Boot, `boot-a`, and `rootfs-a`

### Requirement: The configuration uses a stripped kernel with modular USB peripheral support

The Rock64 configuration SHALL use a stripped kernel profile with RK3328-required storage, networking, USB host,
watchdog, squashfs, f2fs, and overlay support built in. Selected USB Ethernet and USB serial support SHALL be available
as modules. USB WiFi support is not part of the current Rock64 image until specific hardware and firmware are selected.

#### Scenario: Kernel boots on Rock64 hardware

- **WHEN** the built kernel and DTB are loaded by U-Boot on a Rock64 board
- **THEN** the kernel boots and detects the required Rock64 hardware path

#### Scenario: Optional supported USB peripherals load on demand

- **WHEN** a supported USB Ethernet or USB serial device is connected
- **THEN** the matching kernel module can be loaded without rebuilding the image

### Requirement: The device image includes the core appliance runtime

The Rock64 configuration SHALL include systemd, Podman, OpenSSH, OpenVPN, chrony, dnsmasq, nftables, and the services
required for the A/B update system, first-boot provisioning flow, and LAN gateway role.

#### Scenario: Core runtime services are available after boot

- **WHEN** the Rock64 boots the built image
- **THEN** systemd is PID 1
- **AND** Podman is available for application workloads
- **AND** SSH, LAN gateway, and update services are present in the system configuration

### Requirement: Local web management is not part of the base image

The base Rock64 image SHALL NOT require Cockpit or Traefik to be built into the system closure.

#### Scenario: Appliance baseline excludes local management stack

- **WHEN** the Rock64 image is built
- **THEN** the core platform remains bootable and manageable without a local Cockpit/Traefik stack in the image itself

### Requirement: The flake exposes a QEMU testing target that shares the core configuration

The `rock64-qemu` target SHALL reuse the shared base system configuration while swapping only the hardware-specific
pieces needed for `aarch64-virt` test execution.

#### Scenario: QEMU target boots successfully

- **WHEN** the QEMU test target is built and run
- **THEN** the system boots with the shared AtomixOS runtime and test harness overrides

#### Scenario: QEMU target stays close to hardware target

- **WHEN** the Rock64 and QEMU configurations are compared
- **THEN** they share the same core service, firewall, and update logic while differing only in hardware/test-specific
  details

### partition-layout

#### Partition Layout Requirements

### Requirement: eMMC partition layout supports A/B boot and root filesystem slots

The eMMC SHALL be partitioned with the following layout: a raw U-Boot region in the first 16 MB, two vfat boot
partitions (slot A and slot B, 128 MB each), two squashfs root filesystem partitions (slot A and slot B, 1 GB each),
and an f2fs `/data` partition consuming the remaining space. The flashable image contains slot A only (`boot-a` and
`rootfs-a`); slot B and `/data` are created on first boot by initrd `systemd-repart`.

#### Scenario: Partition table matches specification

- **WHEN** the flashable image is inspected before first boot
- **THEN** the GPT contains `boot-a` and `rootfs-a`, with U-Boot written at the RK3328 boot ROM expected offset in the raw
  pre-partition region
- **AND WHEN** the device completes its first boot
- **THEN** initrd `systemd-repart` creates `boot-b`, `rootfs-b`, and an f2fs `/data` partition in the remaining space

### Requirement: Per-slot boot partitions contain kernel and DTB

Each boot slot (A and B) SHALL contain the Linux kernel image and device tree blob for that slot's corresponding rootfs.
RAUC SHALL update the boot partition and rootfs partition atomically as part of a single bundle install.

#### Scenario: Boot partition matches its rootfs slot

- **WHEN** the device boots from slot A
- **THEN** U-Boot loads the kernel and DTB from boot slot A, which matches the kernel version in rootfs slot A

#### Scenario: Boot partition is updated atomically with rootfs

- **WHEN** a RAUC bundle is installed
- **THEN** both the boot partition and rootfs partition for the target slot are written as a single operation

### Requirement: Flashable image and flash workflow deploy the initial slot-A system

The build outputs SHALL include a flashable image that writes U-Boot to the correct raw offset, populates `boot-a` with
the first kernel/initrd/DTB payload, writes the first squashfs image to `rootfs-a`, and leaves the remaining eMMC space
unallocated so initrd `systemd-repart` can create `boot-b`, `rootfs-b`, and `/data` on first boot.

#### Scenario: First boot after flashing

- **WHEN** the flashable image has been written to the device and the system reboots
- **THEN** U-Boot loads the kernel from boot slot A, mounts rootfs slot A as the root filesystem, and the system reaches
  multi-user.target

#### Scenario: Flash workflow warns before overwriting an existing target

- **WHEN** the operator invokes the flashing workflow against an already-populated target device
- **THEN** the workflow requires explicit operator confirmation before overwriting the target

### Requirement: U-Boot is written at correct RK3328 offset

The provisioning script SHALL write U-Boot (idbloader.img and u-boot.itb) to the eMMC at the offsets required by the
RK3328 boot ROM (sector 64 for idbloader, sector 16384 for u-boot.itb). U-Boot SHALL be sourced from the nixpkgs
`ubootRock64` package.

#### Scenario: U-Boot loads from eMMC

- **WHEN** the Rock64 powers on with the provisioned eMMC
- **THEN** the RK3328 boot ROM finds and executes U-Boot from the expected eMMC offsets

### Requirement: /data partition survives updates

The /data partition SHALL NOT be modified by RAUC updates or rootfs slot switches. It SHALL persist across all
updates and rollbacks.

#### Scenario: Data survives an A/B slot switch

- **WHEN** a file is written to /data, then an update switches the active slot from A to B
- **THEN** the file is still present and unmodified on /data after the slot switch

### Requirement: Boot configuration uses U-Boot environment for slot selection

U-Boot SHALL use RAUC bootmeth environment variables (`BOOT_ORDER`, `BOOT_A_LEFT`, `BOOT_B_LEFT`) to select the next boot
slot. RAUC bootmeth SHALL provide the selected boot and root partition identities to `boot.scr`.

#### Scenario: U-Boot selects correct slot pair

- **WHEN** U-Boot reads `BOOT_ORDER=A B` and `BOOT_A_LEFT=3`
- **THEN** RAUC bootmeth selects slot A before loading `boot.scr`
- **AND** `boot.scr` loads kernel and DTB from boot slot A and passes slot A's lower-device identity to initrd

### rauc-integration

#### RAUC Integration Requirements

### Requirement: RAUC is configured with A/B multi-slot definitions

The RAUC system configuration (`system.conf`) SHALL define two slot pairs: boot slot A + rootfs slot A, and boot
slot B + rootfs slot B. Each slot pair SHALL be mapped to its respective eMMC partitions. The configuration SHALL
specify U-Boot as the bootloader backend.

#### Scenario: RAUC recognizes all slots

- **WHEN** `rauc status` is run on the device
- **THEN** the output lists boot slot A, boot slot B, rootfs slot A, and rootfs slot B with their partition device
  paths, and one slot pair is marked as active

### Requirement: RAUC uses U-Boot bootloader backend

The RAUC configuration SHALL specify `bootloader=uboot` and configure the appropriate U-Boot environment variable names
for slot selection and boot-count tracking.

#### Scenario: RAUC install selects the newly written slot for the next boot

- **WHEN** a RAUC bundle is installed to the inactive slot pair
- **THEN** the newly written slot becomes the next slot attempted on reboot

### Requirement: RAUC verifies bundle signatures before installation

RAUC SHALL be configured with a CA certificate (`keyring`) and SHALL reject any bundle not signed by a key trusted by
that CA. Unsigned or incorrectly signed bundles SHALL NOT be installed.

#### Scenario: Valid signed bundle installs successfully

- **WHEN** a bundle signed with a key trusted by the configured CA is provided to `rauc install`
- **THEN** RAUC verifies the signature, writes both boot and rootfs images to the inactive slot pair, and reports
  success

#### Scenario: Invalid signature is rejected

- **WHEN** a bundle with an invalid or untrusted signature is provided to `rauc install`
- **THEN** RAUC refuses to install and returns a signature verification error

### Requirement: RAUC writes to the inactive slot pair only

RAUC SHALL always write updates to the slot pair that is NOT currently booted. It SHALL never overwrite the running boot
partition or root filesystem.

#### Scenario: Update targets inactive slot pair

- **WHEN** the device is booted from slot pair A and `rauc install` is run
- **THEN** RAUC writes the new boot image to boot slot B and the new rootfs image to rootfs slot B (and vice versa)

### Requirement: RAUC bundle contains boot and rootfs images

Each RAUC bundle (`.raucb`) SHALL contain two images: a boot partition image (kernel + DTB) and a rootfs image
(squashfs). RAUC SHALL write both images to their respective partitions in the target slot pair.

#### Scenario: Bundle contains both images

- **WHEN** the RAUC bundle is inspected with `rauc info`
- **THEN** the bundle manifest lists both a boot image and a rootfs image

### Requirement: Default update client polls for new bundles

A systemd timer (`os-upgrade.timer`) SHALL periodically poll the update server for new RAUC bundles. When a new bundle
is available, the service SHALL download it and invoke `rauc install`.

#### Scenario: New bundle is detected and installed

- **WHEN** the update server has a bundle with a version newer than the currently installed version
- **THEN** the polling service downloads the bundle and triggers `rauc install`

#### Scenario: No update available

- **WHEN** the update server reports no newer version
- **THEN** the polling service exits cleanly and waits for the next timer interval

#### Scenario: Download failure is handled gracefully

- **WHEN** the download of a new bundle fails (network error, partial download)
- **THEN** the polling service logs the error, does not invoke `rauc install`, and retries at the next interval

### Requirement: Update client is swappable with hawkBit

The design SHALL reserve a configuration switch for a future hawkBit-based update client while keeping the simple
polling path as the implemented default.

#### Scenario: Simple polling is enabled by default

- **WHEN** the device boots with default configuration
- **THEN** `os-upgrade.timer` is active
- **AND** the simple polling path is the active update client

#### Scenario: hawkBit client can be enabled

- **WHEN** the NixOS configuration flag for hawkBit is set to true
- **THEN** the configuration reserves the hawkBit path instead of the default polling path

### Requirement: NixOS RAUC module is enabled in configuration

The NixOS configuration SHALL enable the RAUC service via `services.rauc` with the appropriate `compatible` string and
CA certificate path.

#### Scenario: RAUC service is active after boot

- **WHEN** the device boots
- **THEN** the `rauc` systemd service is running and `rauc status` returns valid slot information

### update-confirmation

#### Update Confirmation Requirements

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

### Requirement: Sustained confirmation commits the slot with RAUC

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

### watchdog

#### Watchdog Requirements

### Requirement: Hardware watchdog target is defined but deferred

The NixOS configuration SHALL keep RK3328 hardware watchdog manager settings disabled for the current release while
Rock64 boot reliability is validated. The deferred target settings are `RuntimeWatchdogSec=30s` and
`RebootWatchdogSec=10min`.

#### Scenario: Watchdog fires on system hang

- **WHEN** the current release boots
- **THEN** `RuntimeWatchdogSec` is not set by the AtomixOS watchdog module

#### Scenario: Normal operation does not trigger watchdog

- **WHEN** boot-stability validation approves active watchdog enforcement
- **THEN** the deferred target is to set `RuntimeWatchdogSec=30s`

### Requirement: Reboot watchdog target is deferred

The NixOS configuration SHALL not set `RebootWatchdogSec` in the current release. The deferred target is `10min`.

#### Scenario: Hung reboot is recovered

- **WHEN** the current release boots
- **THEN** `RebootWatchdogSec` is not set by the AtomixOS watchdog module

### Requirement: Watchdog timeout is configured appropriately

The deferred target values SHALL remain documented as `RuntimeWatchdogSec=30s` and `RebootWatchdogSec=10min`.

#### Scenario: Watchdog configuration values are applied

- **WHEN** the device boots the current release
- **THEN** the watchdog module leaves `systemd.settings.Manager = { }`

### Requirement: Watchdog reset interacts with boot-count rollback

When the hardware watchdog triggers a reset, the subsequent reboot SHALL go through U-Boot's normal boot sequence, which
decrements the boot attempt counter. This means repeated watchdog-triggered resets on a bad image lead to automatic
rollback.

#### Scenario: Watchdog reset leads to rollback after repeated failures

- **WHEN** a new image causes the system to hang on every boot attempt, triggering the watchdog each time
- **THEN** U-Boot's boot counter decrements to zero and the device rolls back to the previous working slot

## Source Metadata

```yaml
schema: spec-driven
created: 2026-04-09
```

## Source

Converted from `openspec/changes/rock64-ab-image/` during the OpenSpec-to-feature-spec migration.
