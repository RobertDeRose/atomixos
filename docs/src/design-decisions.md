# Design Decisions

> Source: `openspec/changes/rock64-ab-image/design.md`

This chapter documents the key architectural decisions made during the design of AtomixOS, including the rationale,
alternatives considered, and known trade-offs.

## Context

AtomixOS is a greenfield project for secure, reproducible single-board computer appliances deployed remotely. The initial
hardware target is Rock64 (RK3328, aarch64) with 16 GB eMMC storage.

## Decision 1: RAUC over SWUpdate

**Choice**: RAUC for A/B slot management.

**Rationale**: RAUC has native U-Boot integration, well-documented slot configuration, and a straightforward NixOS
module. SWUpdate offers more flexibility (scripted handlers, delta updates) but adds complexity that isn't needed for
the current use case.

**Trade-off**: RAUC's update model is image-based (full slot writes), which means no delta updates. A full rootfs write
(~300 MB) takes longer than a delta, but is simpler and more reliable.

## Decision 2: Squashfs rootfs

**Choice**: Read-only squashfs root filesystem with OverlayFS (tmpfs upper layer).

**Rationale**: Squashfs eliminates runtime drift -- every boot starts from a known-good state. It compresses well (zstd,
1 MB blocks), fitting the NixOS closure into the 1 GB slot with room to spare. A single OverlayFS (squashfs lower +
tmpfs upper) set up in the initrd provides a unified writable root, which is required for systemd's mount namespace
sandboxing (PrivateTmp, ProtectHome, etc.) to work correctly. Writable state lives on `/data` (f2fs).

**Trade-off**: Any runtime state not explicitly persisted to `/data` is lost on reboot. This is intentional for an
appliance but requires careful placement of writable directories.

## Decision 3: Per-slot boot partitions

**Choice**: Each A/B slot has its own boot partition (vfat) containing the kernel, initrd, DTB, and boot script.

**Rationale**: Pairing boot and rootfs in the same slot ensures they are always consistent. If kernel and rootfs were in
different slot pairs, a failed update could leave mismatched versions.

**Alternative considered**: Single shared boot partition with both kernels. Rejected because it creates a single point
of failure and complicates the U-Boot boot script.

## Decision 4: eMMC partition layout

**Choice**: Fixed layout: 16 MB raw U-Boot, 128 MB boot A/B, 1 GB rootfs A/B, remaining space for `/data`.

**Rationale**: 128 MB per boot slot provides ample space for the kernel (~25 MB compressed), initrd, DTB, and boot
script. 1 GB per rootfs slot gives 2-3x headroom over the current squashfs size (~300-400 MB). The `/data` partition
(~13.3 GB) holds containers, logs, and configuration.

**Risk**: If the NixOS closure grows beyond 1 GB, the rootfs slot size must be increased, which reduces `/data` space
and requires re-provisioning all devices.

## Decision 5: U-Boot from nixpkgs

**Choice**: Use `pkgs.ubootRock64` from nixpkgs rather than a custom U-Boot build.

**Rationale**: The nixpkgs U-Boot package is tested, reproducible, and tracks upstream releases. Custom patches are
applied via the kernel config (not U-Boot patches), keeping the build simple.

**Trade-off**: Limited to the U-Boot version and configuration in nixpkgs. The current version (2025.10) lacks
`setexpr`, requiring a manual if/elif chain for boot counter decrement.

## Decision 6: Watchdog strategy

**Choice**: systemd hardware watchdog with 30s runtime / 10min reboot timeouts.

**Rationale**: 30 seconds is aggressive enough to detect hangs quickly but avoids false triggers during normal operation
(e.g., heavy container startup). The 10-minute reboot timeout is generous because clean shutdown may need time to stop
containers.

**Integration**: Watchdog reboots feed directly into the boot-count rollback path -- a hung system on a new slot
automatically rolls back within ~90 seconds (3 watchdog cycles).

## Decision 7: Local health-check (no phone-home)

**Choice**: `os-verification.service` runs local checks only. No external server is contacted for update confirmation.

**Rationale**: The device must be self-sufficient. If the WAN is down after an update, the device should still be able
to commit the slot (or roll back) based on local service health. Phoning home would create a dependency on network
availability during the critical confirmation window.

## Decision 8: Optional Nixstasis-based remote management

**Choice**: Move remote web management out of the device image and support Nixstasis as an optional control plane.

**Rationale**: The Nixstasis client already establishes reverse tunnels and receives short-lived SSH credentials from the
server. Hosting Cockpit and the auth layer in Nixstasis removes first-boot registry pulls, reduces device complexity,
and keeps the device focused on local gateway and update responsibilities.

**Trade-off**: Remote management now depends on successful Nixstasis enrollment and tunnel establishment. Local recovery
falls back to SSH rather than an on-device HTTPS UI.

## Decision 9: OpenVPN in rootfs

**Choice**: Include OpenVPN in the root filesystem (not as a container).

**Rationale**: OpenVPN provides a recovery tunnel for remote management. If it ran as a container and the container
runtime failed, there would be no remote access. Including it in the rootfs ensures it survives container-layer
failures.

## Decision 10: Network isolation (no IP forwarding)

**Choice**: Disable IP forwarding at the kernel level. The nftables `FORWARD` chain drops all packets.

**Rationale**: EN18031 requires a hard network boundary. LAN devices must not be able to reach the internet.
Application-layer proxying through Traefik is the only controlled path between WAN and LAN.

## Decision 11: NIC naming via .link files

**Choice**: Use systemd `.link` files for deterministic NIC naming rather than udev rules.

**Rationale**: `.link` files are the native systemd-networkd mechanism and are processed earlier in boot than udev
rules. They match on stable platform paths (e.g., `platform-ff540000.ethernet` for the onboard GMAC), ensuring `eth0` is
always the onboard Ethernet regardless of USB enumeration order.

## Decision 12: nftables firewall

**Choice**: nftables with per-interface rules, replacing iptables.

**Rationale**: nftables is the modern Linux firewall framework with better performance and a cleaner rule syntax. The
NixOS `networking.nftables` module provides native integration.

## Decision 13: hawkBit-ready architecture

**Choice**: Design the update system to be swappable between polling and hawkBit push models.

**Rationale**: The initial deployment uses simple HTTP polling (`os-upgrade.service`). As the fleet scales, migration to
hawkBit provides centralized update management, rollout policies, and device inventory. The `os-upgrade.useHawkbit`
option makes this a configuration change, not an architectural change.

## Decision 14: QEMU testing target

**Choice**: Provide a `rock64-qemu` NixOS configuration that shares the full service stack with the hardware target but
uses virtio devices and a file-based RAUC backend.

**Rationale**: Hardware testing is slow and requires physical devices. QEMU testing validates all software behavior
(RAUC lifecycle, firewall rules, health checks) in CI-friendly VMs. The custom RAUC backend simulates U-Boot's slot
selection using files.

## Decision 15: EN18031 authentication

**Choice**: Hybrid approach -- OIDC (Microsoft Entra) as primary web auth, local password as fallback, SSH key-only for
remote access.

**Rationale**: OIDC provides SSO and audit logging when internet is available. The local password ensures access when
the device is offline or on the LAN. SSH key-only prevents brute-force attacks on the management interface.

## Decision 16: Squashfs closure optimization

**Choice**: Aggressive closure size reduction through overlays, disabled features, and stripped dependencies.

**Techniques applied**:

- `crun` without CRIU (removes python3, saving ~102 MB)
- Disabled: documentation, man pages, fonts, XDG, sudo, bash completion
- Emptied `defaultPackages` and `fsPackages`
- Disabled: bcache, kexec, LVM

**Result**: Approximately 27% reduction in closure size compared to a default NixOS system with the same services.

## Decision 17: Three-tier logging model

**Choice**: Keep general host and application logging volatile, but store a small bounded set of critical lifecycle and
update events in a slot-local forensic ring on each boot partition.

**Rationale**: Making the full journal persistent would increase steady-state eMMC wear and still would not tie
forensics to the exact boot slot involved in an update or rollback. A dedicated Tier 0 ring under `/boot/forensics`
keeps the most important records with the slot they describe, survives reboot and slot changes, and remains bounded to
`28 MiB` per boot slot. The rest of the system stays memory-first: journald uses volatile storage with a runtime cap,
and Podman logs to journald by default.

**Trade-off**: Tier 0 is intentionally not a complete journal. Operators get durable markers for boot progression,
update/install/confirm flows, rollback triggers, and shutdown, but detailed service logs still need to be collected
externally or inspected before reboot.

## Risks and Trade-offs

| Risk                              | Mitigation                                                                                            |
|-----------------------------------|-------------------------------------------------------------------------------------------------------|
| eMMC wear from frequent writes    | `/data` uses f2fs (wear-leveling aware); squashfs slots are written only during updates               |
| U-Boot env corruption             | Redundant environment storage at two offsets; power-loss safe                                         |
| 1 GB rootfs slot too small        | Current closure is ~300-400 MB; aggressive optimization keeps headroom                                |
| Missing health manifest           | `first-boot.service` unconditionally commits; `os-verification` skips container checks if no manifest |
| Cockpit/Traefik container failure | OpenVPN in rootfs provides alternate remote access                                                    |
| No delta updates                  | Full-image updates are ~300 MB; acceptable on broadband WAN connections                               |
| No automatic WAN SSH              | Deliberate security constraint; manual flag file required                                             |
