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

**Choice**: defer active systemd hardware watchdog enforcement while keeping 30s runtime / 10min reboot timeouts as the
target settings.

**Rationale**: Rock64 boot reliability validation is not complete. The target values remain documented, but the current
release leaves `systemd.settings.Manager = { }` to avoid watchdog-triggered reset loops during development.

**Integration**: Once enabled, watchdog reboots feed directly into the boot-count rollback path.

## Decision 7: Local health-check (no phone-home)

**Choice**: `os-verification.service` runs local checks only. No external server is contacted for update confirmation.

**Rationale**: The device must be self-sufficient. If the WAN is down after an update, the device should still be able
to commit the slot (or roll back) based on local service health. Phoning home would create a dependency on network
availability during the critical confirmation window.

## Decision 8: Optional Nixstasis-based remote management

**Choice**: Move remote web management out of the device image and support Nixstasis as an optional control plane.

**Rationale**: The Nixstasis client already establishes reverse tunnels and receives short-lived SSH credentials from the
server. Hosting remote web management and the auth layer in Nixstasis removes first-boot registry pulls, reduces device
complexity, and keeps the device focused on local gateway and update responsibilities.

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
WAN application or VPN ports are opened only by provisioned firewall state. Packet forwarding between WAN and LAN stays
disabled.

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
hawkBit can provide centralized update management, rollout policies, and device inventory. The `os-upgrade.useHawkbit`
option currently reserves this path and installs the package, but AtomixOS does not configure an operational hawkBit
service yet.

## Decision 14: QEMU testing target

**Choice**: Provide a `rock64-qemu` NixOS configuration that shares the full service stack with the hardware target but
uses virtio devices and a file-based RAUC backend.

**Rationale**: Hardware testing is slow and requires physical devices. QEMU testing validates all software behavior
(RAUC lifecycle, firewall rules, health checks) in CI-friendly VMs. The custom RAUC backend simulates U-Boot's slot
selection using files.

## Decision 15: EN18031 authentication

**Choice**: no default passwords, locked local root password, no built-in operator account, SSH key-only access, serial
break-glass recovery, and optional Nixstasis-based remote management.

**Rationale**: The base image does not host the web management/authentication stack. SSH key-only access and locked
passwords prevent brute-force attacks on the device, while Nixstasis handles remote management credentials outside the
device image.

## Decision 16: Squashfs closure optimization

**Choice**: Aggressive closure size reduction through overlays, disabled features, and stripped dependencies.

**Techniques applied**:

- `crun` without CRIU (removes python3, saving ~102 MB)
- Disabled: documentation, man pages, fonts, XDG, sudo, bash completion
- Emptied `defaultPackages` and `fsPackages`
- Disabled: bcache, kexec, LVM

**Result**: Approximately 27% reduction in closure size compared to a default NixOS system with the same services.

## Decision 17: Two-tier runtime logging model

**Choice**: Use tmpfs-first `journald` during runtime for host and container log ingress, then drain it through an
`rsyslog` RAM queue that appends buffered logs to `/data/logs`.

**Rationale**: Making the full journal always persistent would increase steady-state eMMC wear. The selected design keeps
runtime logging memory-first, caps journal memory use, routes Podman logs through the same path, and still retains
broader diagnostics durably on `/data/logs` in larger sequential batches instead of many small writes.

**Trade-off**: This is a bounded-loss durability model rather than an always-durable one. Sudden power loss can still
drop the newest in-memory journal or rsyslog queue entries, but routine runtime writes remain much friendlier to eMMC
than fully persistent journal storage.

## Risks and Trade-offs

| Risk                                  | Mitigation                                                                                                                                                                            |
|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| eMMC wear from frequent writes        | `/data` uses f2fs (wear-leveling aware); squashfs slots are written only during updates                                                                                               |
| U-Boot env corruption                 | Single-copy environment storage; corruption is handled through normal recovery and reprovisioning flows                                                                               |
| 1 GB rootfs slot too small            | Current closure is ~300-400 MB; aggressive optimization keeps headroom                                                                                                                |
| Missing or empty health-required list | `first-boot.service` commits only when RAUC is enabled; `os-verification` uses gateway health checks alone unless `/data/config/health-required.json` names additional required units |
| Provisioned application failure       | OpenVPN in rootfs and SSH key-only access provide alternate recovery paths                                                                                                            |
| No delta updates                      | Full-image updates are ~300 MB; acceptable on broadband WAN connections                                                                                                               |
| No automatic WAN SSH                  | Deliberate security constraint; manual flag file required                                                                                                                             |
