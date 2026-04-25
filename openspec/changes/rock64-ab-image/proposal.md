# Proposal

## Why

- Rock64-based devices need a robust over-the-air update mechanism that guarantees devices remain bootable even if an
  update fails or power is lost mid-write. The current Debian-based update system using apt packages has a ~3% failure
  rate during upgrades due to power loss, requiring manual SSH intervention to restore Cockpit access. Without atomic
  A/B updates and automatic rollback, failed updates in the field brick devices and require physical or remote manual
  intervention — unacceptable for a fleet of thousands of remotely deployed devices.

## What Changes

- Introduce a NixOS flake that builds a read-only squashfs root filesystem targeting the Rock64 (aarch64, RK3328) with a
  stripped kernel
- Implement an A/B partition layout on the 16 GB eMMC with per-slot boot partitions and RAUC managing slot switching
- Include the kernel and DTB in the per-slot boot partitions so kernel updates are atomic with rootfs updates — no
  shared boot partition
- Include WiFi/BT USB dongle drivers as kernel modules in the squashfs for optional peripheral support
- Configure U-Boot boot-count logic so failed boots automatically roll back to the previous good slot
- Enable hardware watchdog (RK3328) via systemd so hung systems reboot into the fallback slot
- Add a local health-check confirmation service (`os-verification`) — validates system services and manifest-defined
  containers are running before committing the slot via `rauc status mark-good`
- Run Cockpit as a pod (`quay.io/cockpit/ws`) that SSHes into the host, with `python3Minimal` in the rootfs to support
  the Cockpit Python bridge
- Include OpenVPN in the rootfs as a recovery management path
- Configure EN18031-compliant user authentication: no default passwords, per-device credentials from `/data/config/`,
  OIDC (Microsoft Entra) as primary auth with provisioned password as LAN/offline fallback
- Configure the Rock64 as a LAN gateway: DHCP server, NTP server, and network isolation boundary (no IP forwarding, no
  NAT) for EN18031 compliance of legacy downstream devices
- Configure predictable NIC naming: onboard NIC → eth0 (WAN), USB NIC → eth1+ (LAN), WiFi dongles → wlan0+
- Configure nftables firewall: HTTPS on WAN, SSH on LAN and VPN, DHCP and NTP on LAN, with manual-only SSH on WAN via
  flag file
- Build RAUC bundles (`.raucb`) as a multi-slot flake output (boot partition + squashfs rootfs), signed with a project
  CA
- Provide an initial install script that partitions eMMC (1 GB rootfs slots), writes U-Boot, deploys the first image,
  and provisions per-device credentials
- Create a systemd timer/service for polling an update server and triggering RAUC installs, designed to be swappable
  with rauc-hawkbit-updater
- Add a QEMU/aarch64-virt testing target as a first-class flake output for fast development iteration

## Capabilities

### New Capabilities

- `nix-flake-config`: NixOS flake defining the Rock64 host configuration (stripped kernel with WiFi/BT modules, DTB,
  systemd, podman, python3Minimal, OpenVPN, openssh, chrony, squashfs output, QEMU testing target, NIC naming, closure
  size optimizations)
- `partition-layout`: eMMC partition scheme (U-Boot raw, per-slot boot A/B vfat, rootfs A/B squashfs 1 GB each, /data
  f2fs) and initial provisioning script with credential creation
- `rauc-integration`: RAUC system configuration, multi-slot bundle building, slot definitions, U-Boot bootloader
  backend, update polling service, and hawkBit-ready architecture
- `boot-rollback`: U-Boot environment boot-count logic and RAUC mark-good/mark-bad lifecycle for automatic rollback
- `watchdog`: Hardware watchdog (RK3328) enablement via systemd watchdog configuration
- `update-confirmation`: Local health-check service (`os-verification`) that validates system services and
  manifest-defined containers before committing the slot
- `lan-gateway`: Network isolation boundary with DHCP server, NTP server, nftables firewall, NIC naming (eth0 WAN, eth1
  LAN), and manual SSH-on-WAN toggle for EN18031 compliance
- `user-auth`: EN18031-compliant authentication — no default passwords, hashedPasswordFile from /data, SSH authorized
  keys from /data, OIDC primary with password fallback, localhost-only SSH password auth for Cockpit pod

### Modified Capabilities

## Impact

- **New repository infrastructure**: Entire NixOS flake, RAUC config, U-Boot environment scripts, partition tooling,
  network configuration, and firewall rules are net-new
- **Dependencies**: NixOS (nixpkgs 25.11), RAUC, U-Boot for RK3328 (from nixpkgs), squashfs-tools, f2fs-tools,
  python3Minimal, OpenVPN, chrony, dnsmasq, nftables, Cockpit pod image (`quay.io/cockpit/ws`)
- **Hardware**: Targets Rock64 boards with 16 GB eMMC; requires aarch64 cross-compilation or native build
- **External systems**: Assumes an update server (e.g., Azure Blob Storage) will host signed `.raucb` bundles —
  server-side infrastructure is out of scope for this change
- **Security**: Introduces a CA keypair for RAUC bundle signing; key management practices need to be established.
  Network isolation (no IP forwarding) provides EN18031 compliance boundary for legacy LAN devices. Firewall restricts
  WAN access to HTTPS and VPN only. EN18031-compliant authentication: no default passwords, unique per-device
  credentials provisioned at initial flash.
- **Device identity**: Uses onboard NIC (eth0) MAC address as device identifier — existing convention
