# Provisioning

Deploy AtomixOS to a Rock64 device by building a [flashable disk image](./provisioning/flash-image.md) and writing it
to eMMC with `dd` (or `mise run flash`).

## After Provisioning

On first boot:

1. U-Boot loads `boot.scr` from boot-a, echoes build ID, boots the kernel with initrd
2. The initrd mounts the selected squashfs slot at `/run/rootfs-base`, then `sysroot.mount`
   assembles `/` as OverlayFS with a tmpfs-backed upper/work directory under `/run/overlay-root`
3. Initrd `systemd-repart` creates the `/data` partition (f2fs) on first boot using the remaining eMMC space
4. Initrd persists a fresh-flash marker so switched-root provisioning can distinguish a new flash from a later
   reprovisioned `/data` wipe
5. `first-boot.service` looks for `/boot/config.toml` only on a fresh flash, then USB `config.toml`, then starts the
   bootstrap web console on `172.20.30.1:8080`
6. The imported config is validated, persisted under `/data/config/`, rendered into canonical Quadlet files, and synced
   into the active rootful and rootless Quadlet paths
7. `first-boot.service` writes the sentinel file after provisioning import/validation succeeds and marks the RAUC slot as
   good when RAUC is enabled
8. Network interfaces come up (eth0 via DHCP, eth1 static); `systemd-networkd-wait-online` uses 30s timeout with `anyInterface=true`
9. Services start: dnsmasq, chrony, sshd, and the RAUC update timer when RAUC is enabled

The device is then ready to receive OTA updates and serve LAN clients.

## Reprovisioning

Wiping `/data` returns the device to the unprovisioned state without changing the A/B slot layout.

On the next boot:

1. Initrd sees that `boot-b` already exists, so it does not mark the boot as a fresh flash
2. `/boot/config.toml` is not replayed
3. `first-boot.service` searches USB `config.toml` sources first
4. If no USB seed is found, the bootstrap web console starts on `172.20.30.1:8080`

Imported operator state remains bounded to `/data/config/`, including the imported `config.toml`, rendered Quadlet
files, admin SSH authorized keys, and other provisioning-derived runtime inputs.

## USB Recovery Mode

If the reset button is held from power-on for 10 seconds, U-Boot enters USB
mass storage mode instead of booting Linux. The
Rock64 OTG USB port then exposes the full eMMC as a removable disk, allowing the host to write a fresh image directly.
