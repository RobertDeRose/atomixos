# Design

This document is maintained as the current source of truth for the foundational Rock64 A/B image design. Where the
implementation diverged from early exploration, the current design is described directly and explicit divergence notes
are kept only when they explain an important technical decision.

## Context

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

## Goals / Non-Goals

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
- Full initrd forensic-log persistence redesign in this change

## Decisions

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

**Decision:** The `admin` account remains password-locked and uses SSH keys from `/data/config/ssh-authorized-keys/admin`.
Root is also locked by default. `_RUT_OH_` is a physical serial-only recovery path, not a network authentication mode.

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

## Risks / Trade-offs

- **Watchdog on hardware is still staged**: the design includes the hardware watchdog path, but live Rock64 enablement is
  still gated on stable hardware validation.
- **Provisioning is now part of the first-boot success contract**: this is correct for production, but it means invalid
  provisioning blocks slot confirmation.
- **No local web-management stack in the base image**: this reduces closure size and appliance complexity, but shifts
  remote-management responsibility to Nixstasis-hosted services.
- **Full image updates consume more bandwidth than delta approaches**: acceptable for the current phase.
- **Initrd forensic durability is incomplete**: runtime durability exists, but the earliest boot persistence path still
  needs a safer redesign.

## Follow-on Changes

- `first-boot-local-provisioning` refines the provisioning contract, source-order logic, and `/data/config/` layout
- `durable-journald-logs` refines the runtime log-durability model and tracks the incomplete initrd redesign
