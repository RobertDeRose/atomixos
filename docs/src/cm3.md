# Radxa CM3 IO Board

Run AtomixOS on a Radxa ROCK 3 Compute Module (CM3, RK3566) mounted on the **Radxa CM3 IO Board**. This target is not
the Rock64 (RK3328) or the Raspberry Pi CM4 IO carrier board. Every build names its board, so pass `--board cm3`.

## Build and flash

1. Build the CM3 artifacts on an `aarch64-linux` builder (or macOS with a Linux builder):

   ```sh
   mise run build --board cm3
   ```

   The image is `.gcroots/cm3/current/image/atomixos-cm3-<release>.img`, and the RAUC bundle is `cm3.raucb`.
   [Building](building.md) covers the retained links, `nix build .#cm3` outputs, and local overrides.
2. Check the storage numbering before you flash a production module; see
   [Before the first flash](#before-the-first-flash).
3. Flash the eMMC with `mise run flash --board cm3`, as described in [Flash an Image](provisioning/flash-image.md).

| Item            | Value                                                                         |
|-----------------|-------------------------------------------------------------------------------|
| Flake outputs   | `nixosConfigurations.cm3`, `.#cm3` (and `.#cm3.image`, `.#cm3.rauc-bundle`)   |
| RAUC compatible | `radxa-cm3-io`                                                                |
| U-Boot config   | `radxa-cm3-io-rk3566_defconfig`                                               |
| Device tree     | `rockchip/rk3566-radxa-cm3-io.dtb`                                            |
| Kernel          | Stripped like the Rock64, plus RK3566 eMMC, power, and SCMI drivers; no audio |

The image layout matches the Rock64: SPL at sector 64, the U-Boot FIT at sector 16384, and slot A from 16 MiB.

## Storage and boot

The CM3 boots only from the on-module eMMC and ignores the IO board's SD card:

- Device-tree aliases fix the numbering in both U-Boot and Linux: `mmc0` is the eMMC (`fe310000.mmc`) and `mmc1` is the
  SD slot, so Linux always sees the eMMC as `/dev/mmcblk0`.
- U-Boot scans only `mmc0`, using only the RAUC boot method. The boot command sets `boot_targets` to `mmc0` because
  Rockchip's default order would try the SD card first. It sets `boot_targets` instead of passing `mmc0` as a scan
  label, because U-Boot refuses labelled scans once `bootmeth order` is set. If the selected slot fails to boot, the
  boot command resets so the RAUC try counter can fall back.
- Root, `/boot`, `/data`, the RAUC slots, `systemd-repart`, and `fw_env.config` use fixed `/dev/mmcblk0pN` paths, not
  GPT labels. Every AtomixOS image shares the same labels, so an inserted SD card could otherwise win.
- The U-Boot environment is redundant: two 32 KiB records in the reserved eMMC boot gap at offsets `0x3f8000` and
  `0x3f0000`. The CM3 does not use SPI NOR flash (`/dev/mtd0`), which some modules do not populate.
- The boot command and `boot_targets` are saved in the eMMC environment on first boot. A changed `CONFIG_BOOTCOMMAND`
  reaches a deployed board only after its environment is reset, for example by reflashing.
- The kernel, device tree, and initrd use the RK3568 U-Boot default load addresses; the Rock64 `ramdisk_addr_r`
  override does not apply.

If SPI NOR is fitted and holds an old SPL or bootloader, it can take precedence over the image on the eMMC. Check the
U-Boot version in the serial output.

## Ports and console

- **Serial console:** UART2 at 1,500,000 baud, 3.3 V, on the IO board's 40-pin header: pin 6 GND, pin 8 TX, pin 10 RX.
  Root is locked; for a one-boot serial root shell, use [Physical Recovery](architecture/authentication.md#physical-recovery).
- **Network:** GMAC1 (`fe010000.ethernet`) is the WAN port, named `wan`; a USB Ethernet adapter is `lan`.
  [NIC Naming](architecture/network-topology.md#nic-naming) explains the matching.
- **USB recovery:** the RK3566 OTG port (DWC3) offers the same USB mass-storage recovery as the Rock64, triggered by
  `boot_to_ums` or `START_UMS=1`. There is no reset-button trigger, because the Rock64 recovery GPIO is not valid on the
  CM3. `mise run flash:maskrom` rewrites the eMMC over Rockchip Maskrom even when U-Boot is broken; see
  [Rockchip Maskrom](provisioning/flash-image.md#rockchip-maskrom-cm3).

## Watchdog

The CM3 always uses the internal RK3566 watchdog (`fe600000`). If `build.toml` sets `enable_hardware = true` with
`backend = "external"`, evaluation prints a warning and still uses the internal watchdog. [Build Configuration](reference/build-configuration.md)
describes the watchdog settings.

## OTA updates

A CM3 sends `X-Compatible: radxa-cm3-io` when it polls for updates, and the update server must answer with a CM3
bundle. A response naming another board's compatible string is skipped without downloading; see
[Update Polling](architecture/update-rollback.md#update-polling).

## Before the first flash

Confirm the storage numbering on new hardware before you flash a production module:

1. Boot a known-good OS image, such as a Radxa or Armbian image, and check that the eMMC is `mmcblk0`:

   ```sh
   lsblk -o NAME,PATH,SIZE,TYPE,MODEL,TRAN,PARTLABEL
   readlink -f /sys/class/block/mmcblk0/device
   for d in /sys/class/mmc_host/mmc*/device; do echo "$d"; done
   ```

2. In U-Boot, check `mmc list` and that U-Boot can read and write the redundant environment at the offsets above.
3. Flash the AtomixOS CM3 image and confirm that `fw_printenv` and `fw_setenv` match `fw_env.config`.
4. Confirm that `systemd-repart` creates `boot-b`, `rootfs-b`, and `data` on the eMMC, not on an SD card.
5. Exercise the RAUC mark-good, simulated failed boot, and rollback cycle.

On a new board, also check the GMAC, both USB host and OTG controllers, the RK817 PMIC, and the watchdog, along with eMMC
and serial boot. Enable the hardware watchdog and deploy production RAUC updates only after boot, power-loss recovery,
and rollback tests pass.
