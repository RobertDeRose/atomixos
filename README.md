# Rock64 A/B Image

NixOS-based firmware image for the Rock64 (Rockchip RK3328, aarch64) with atomic A/B OTA updates, automatic rollback, and hardware watchdog protection. The device serves as a network security boundary (EN18031) for legacy LAN devices.

## Goals

- **Atomic OTA updates** -- write to the inactive slot pair while the active slot keeps running
- **Automatic rollback** -- U-Boot boot-count logic falls back to the previous good slot after 3 failed boots
- **Hardware watchdog** -- systemd kicks the RK3328 watchdog every 30s; a hung system reboots and triggers rollback
- **Local health-check confirmation** -- validates system services and manifest-defined containers before committing a new slot via `rauc status mark-good`
- **Signed RAUC bundles** -- reproducible `.raucb` files built as Nix flake outputs
- **Network isolation** -- LAN devices cannot reach the internet; the Rock64 is the sole gateway
- **EN18031 compliance** -- no default passwords, unique per-device credentials set during provisioning

## Architecture

### eMMC partition layout (16 GB)

```text
Offset     Size       Content          Filesystem
0          4 MB       U-Boot           raw (idbloader + u-boot.itb)
4 MB       32 MB      boot slot A      vfat (kernel + DTB)
36 MB      32 MB      boot slot B      vfat (kernel + DTB)
68 MB      1 GB       rootfs slot A    squashfs (zstd, 1 MB block)
1092 MB    1 GB       rootfs slot B    squashfs (zstd, 1 MB block)
2116 MB    ~13.5 GB   /persist         f2fs (containers, state, logs)
```

### Network topology

```
                    ┌─────────────────────────────┐
   WAN (internet) ──┤ eth0  DHCP client            │
                    │       HTTPS (443)             │
                    │       OpenVPN (1194)           │
                    │                               │
                    │       Rock64 gateway           │
                    │       ip_forward = OFF         │
                    │       no NAT, no routing       │
                    │                               │
   LAN (isolated) ──┤ eth1  172.20.30.1/24          │
                    │       DHCP server (dnsmasq)   │
                    │       NTP server (chrony)      │
                    └─────────────────────────────┘
```

LAN devices get DHCP and NTP but have zero internet access. Application-layer proxying (Traefik, running as a container)
selectively bridges WAN and LAN with authentication.

### Update and rollback flow

```text
1. os-upgrade.service polls update server for new .raucb bundle
2. rauc install writes boot + rootfs to the INACTIVE slot pair
3. RAUC sets U-Boot env: BOOT_ORDER=B A, BOOT_B_LEFT=3
4. Device reboots into new slot
5. U-Boot decrements BOOT_B_LEFT on each boot attempt
6. os-verification.service runs health checks:
   - eth0 has WAN address, eth1 is 172.20.30.1
   - dnsmasq, chronyd running
   - containers from /persist/config/health-manifest.yaml are healthy
   - sustained 60s stability check
7a. All pass  → rauc status mark-good (slot committed)
7b. Any fail  → exit non-zero, boot-count continues to decrement
8. After 3 failed boots → U-Boot falls back to previous good slot
```

The hardware watchdog ensures hung systems reboot within 30s, feeding into the same boot-count rollback path.

### Squashfs rootfs (~333 MB compressed)

The read-only root filesystem contains the full NixOS system closure:

- Stripped Linux 6.19 kernel (RK3328 drivers built-in, WiFi/BT as modules)
- systemd, podman, OpenVPN, openssh, chrony, dnsmasq, nftables, RAUC
- python3Minimal for Cockpit's SSH-based Python bridge
- Cockpit itself runs as a pod (`quay.io/cockpit/ws`), not in the rootfs

### Authentication (EN18031)

The image ships with no embedded credentials. During provisioning:

- `/persist/config/admin-password-hash` -- unique sha-512 password hash per device
- `/persist/config/ssh-authorized-keys/admin` -- operator's SSH public key

Remote SSH is key-only. Localhost SSH allows password auth so the Cockpit pod can connect to the host. OIDC (Microsoft
Entra via Traefik forward-auth) is the primary web auth when internet is available; the provisioned password is the
LAN/offline fallback.

## Project structure

```
flake.nix                          Main flake (nixos-25.11, aarch64-linux)
flake.lock                         Pinned nixpkgs
mise.toml                          Tool versions, build tasks, hooks

modules/
  base.nix                         Shared NixOS config (systemd, podman, ssh, auth, closure opts)
  hardware-rock64.nix              RK3328 kernel, DTB, eMMC/watchdog drivers
  hardware-qemu.nix                QEMU aarch64-virt target for testing
  networking.nix                   NIC naming (.link files), eth0/eth1 config
  firewall.nix                     nftables rules (WAN/LAN/VPN/FORWARD)
  lan-gateway.nix                  dnsmasq DHCP, chrony NTP, IP forwarding off
  rauc.nix                         RAUC system.conf, slot definitions
  watchdog.nix                     systemd watchdog config
  os-verification.nix              Post-update health check service
  os-upgrade.nix                   Update polling + hawkBit toggle
  openvpn.nix                      OpenVPN recovery tunnel

nix/
  squashfs.nix                     Squashfs image derivation (closureInfo + mksquashfs)
  rauc-bundle.nix                  Multi-slot RAUC bundle derivation
  boot-script.nix                  U-Boot boot.scr compilation
  image.nix                        Flashable eMMC disk image derivation

scripts/
  build-squashfs.sh                Squashfs build template (Nix derivation)
  build-rauc-bundle.sh             RAUC bundle build template (Nix derivation)
  build-image.sh                   Disk image assembly template (Nix derivation)
  os-verification.sh               Runtime health check script
  os-upgrade.sh                    Runtime update polling script
  ssh-wan-toggle.sh                SSH-on-WAN flag check
  ssh-wan-reload.sh                SSH-on-WAN runtime reload
  boot.cmd                         U-Boot A/B boot script source
  fw_env.config                    Redundant U-Boot env storage config

.mise/tasks/provision/
  image                            Generate flashable .img file
  emmc                             Flash directly to eMMC block device (Linux only)

certs/
  ca.cert.pem                      RAUC CA certificate (public)
  signing.cert.pem                 RAUC signing certificate (public)
  *.key.pem                        Private keys (gitignored)
```

## Building

Builds require an aarch64-linux system (native or cross). All outputs target `aarch64-linux`.

### With mise (recommended)

```sh
# Install tools and hooks
mise install

# Check the flake evaluates cleanly
mise run check

# Build individual artifacts
mise run build:squashfs        # result-squashfs/
mise run build:rauc-bundle     # result-rauc-bundle/
mise run build:boot-script     # result-boot-script/
mise run build:image           # result-image/

# Build everything
mise run build
```

### With nix directly

```sh
nix flake check
nix build .#squashfs -o result-squashfs
nix build .#rauc-bundle -o result-rauc-bundle
nix build .#boot-script -o result-boot-script
nix build .#image -o result-image

# Run the QEMU testing VM
nix run .#rock64-qemu-vm
```

## Provisioning

### Option 1: Flashable disk image

Build an `.img` file that can be written to eMMC (or SD card) with `dd` or Etcher:

```sh
mise run provision:image -o rock64.img
dd if=rock64.img of=/dev/mmcblkN bs=4M status=progress
```

The image includes U-Boot, boot slot A (kernel + DTB), and rootfs slot A (squashfs). On first boot, `systemd-repart`
automatically creates and formats the `/persist` partition (f2fs) using all remaining eMMC space.

### Option 2: Direct eMMC provisioning

For factory provisioning with the eMMC attached as a block device (requires Linux + root):

```sh
mise run provision:emmc /dev/mmcblk1 /path/to/uboot /path/to/kernel /path/to/dtb /path/to/squashfs
```

This partitions the eMMC, writes U-Boot, deploys the first image to slot A, and leaves the persist region for `systemd-repart` to create on first boot.

### Post-boot setup

After first boot, provision per-device credentials (EN18031 -- no default passwords):

```sh
# Set admin password (unique per device)
mkpasswd -m sha-512 | ssh admin@<device> 'cat > /persist/config/admin-password-hash'

# Deploy SSH public key
ssh admin@<device> 'cat > /persist/config/ssh-authorized-keys/admin' < ~/.ssh/id_ed25519.pub
```

## Flake outputs

| Output | Description |
|---|---|
| `nixosConfigurations.rock64` | Real hardware NixOS system |
| `nixosConfigurations.rock64-qemu` | QEMU aarch64-virt testing target |
| `packages.aarch64-linux.squashfs` | Compressed squashfs root filesystem |
| `packages.aarch64-linux.rauc-bundle` | Signed multi-slot `.raucb` bundle |
| `packages.aarch64-linux.boot-script` | Compiled U-Boot `boot.scr` |
| `packages.aarch64-linux.image` | Flashable eMMC disk image (U-Boot + boot-a + rootfs-a) |
| `apps.aarch64-linux.rock64-qemu-vm` | QEMU VM runner |

## Status

Implementation is in progress. 59 of 104 tasks complete. All core implementation tasks are done; remaining tasks are verification, hardware testing, and Cockpit pod/auth integration. See `openspec/changes/rock64-ab-image/tasks.md` for details.
