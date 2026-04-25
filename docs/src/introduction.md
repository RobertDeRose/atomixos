<!-- rumdl-disable-file MD041 -->

<p align="center">
  <img src="atomixos.png" alt="AtomixOS logo" width="320" />
</p>

**Secure, reproducible operating system for single-board computers, with atomic A/B OTA updates, automatic rollback, and
container-based application deployment.**

AtomixOS is a purpose-built firmware platform for Rock64 (RK3328, aarch64) edge gateway devices. Each device serves as
a network security boundary compliant with EN18031, isolating legacy LAN devices from the internet while providing
managed access through application-layer proxying.

## Why AtomixOS?

Remote embedded devices that receive over-the-air updates face a fundamental reliability problem: if an update fails
mid-write or the new image doesn't boot correctly, the device is bricked. Traditional package-manager approaches (e.g.,
`apt upgrade`) have a measurable failure rate from power loss, partial writes, and dependency conflicts.

AtomixOS eliminates this class of failure through:

- **Atomic A/B updates** -- installs to the inactive slot pair while the active slot stays online; no partial state
- **Automatic rollback** -- U-Boot boot-count logic falls back to the previous working slot after 3 consecutive boot
  failures
- **Hardware watchdog (currently disabled on Rock64)** -- integration and tests are in place; runtime enablement is pending
  final boot-stability validation on hardware
- **Local health-check confirmation** -- commits new slots only after verifying that all services and containers are
  healthy for a sustained 60-second window
- **Signed RAUC bundles** -- reproducible, CA-signed `.raucb` artifacts built from the Nix flake
- **Read-only root filesystem** -- squashfs rootfs with OverlayFS (tmpfs upper layer) prevents runtime drift; every boot
  starts from a known-good state

## Supported Hardware

| Board  | SoC    | Architecture | Storage    |
|--------|--------|--------------|------------|
| Rock64 | RK3328 | aarch64      | 16 GB eMMC |

## Key Properties

- **Reproducible** -- the entire system image is built from a single Nix flake with pinned inputs; same flake, same
  image
- **Immutable** -- the squashfs root filesystem is read-only; writable state lives on a dedicated `/data` partition
- **Testable** -- 9 NixOS VM integration tests validate the full update lifecycle, network security, and rollback
  behavior without physical hardware
- **EN18031 compliant** -- ships without default credentials; per-device credentials are provisioned at factory time; IP
  forwarding is disabled by default

## Network Role

Each AtomixOS device acts as a gateway between an isolated LAN and the internet:

- **WAN (eth0)**: DHCP client, accepts HTTPS (443) and OpenVPN (1194) from the internet
- **LAN (eth1)**: Static IP, runs DHCP server (dnsmasq) and NTP server (chrony) for local devices
- **No routing**: IP forwarding is disabled; LAN devices have zero internet access
- **Application-layer proxying**: Traefik reverse proxy selectively bridges WAN and LAN with authentication (OIDC via
  Microsoft Entra, with local password fallback)

## Quick Start

```sh
# Build the flashable disk image
mise run build:image

# Flash to eMMC (macOS)
mise run flash /dev/disk4

# Run all E2E tests
mise run e2e

# Run all E2E tests inside a Lima VM
mise run e2e --lima
```

See [Building](./building.md) and [Provisioning](./provisioning.md) for detailed instructions.
