# Radxa CM3 on the Radxa CM3 IO Board

This target is for the ROCK 3 Compute Module (RK3566) attached to the **Radxa CM3 IO Board**. It is **not** the
ROCK64/RK3328 or the Raspberry Pi CM4 IO carrier board. The CM3 target is separately selectable and keeps ROCK64 as the
default build with its `rock64` RAUC compatibility string; ROCK64 image files are named
`atomixos-rock64-<release>.img`.

## Build

Run on an `aarch64-linux` builder (or macOS using the existing Linux builder):

```sh
mise run build --board cm3
nix eval --raw .#nixosConfigurations.cm3.config.hardware.deviceTree.name
nix build .#checks.aarch64-linux.cm3-board
nix build .#cm3 -o result-cm3
```

`result-cm3/` holds one subdirectory per shipped artifact: the image is `result-cm3/image/atomixos-cm3-<release>.img`,
the RAUC bundle is `result-cm3/rauc-bundle/cm3.raucb`, and U-Boot is in `result-cm3/uboot/`. Build a single artifact
with, for example, `nix build .#cm3.image`. U-Boot uses `radxa-cm3-io-rk3566_defconfig` and the kernel boots with the
`rockchip/rk3566-radxa-cm3-io.dtb` device tree. The image layout matches ROCK64 (SPL @ sector 64, U-Boot FIT @ sector
16384, slot A starts at 16 MiB). The kernel is **unstripped**, keeping RK3566 MMC, power management, Ethernet, and USB
support available.

`mise run build` defaults to ROCK64; use `mise run build --board cm3` for this board. Builds are retained independently
under `.gcroots/rock64/` and `.gcroots/cm3/`; the CM3 image is `.gcroots/cm3/current/image/`. The corresponding flake
outputs are `.#rock64.image` and `.#cm3.image`.

## First boot / storage warning

**Do not flash a production module until the storage checks below pass.** The CM3 target boots only from the
on-module eMMC and ignores the IO board SD card:

- Device numbering is fixed by the device tree aliases: `mmc0` is the eMMC (`fe310000.mmc`) and `mmc1` is the SD slot,
  in both U-Boot and Linux. Linux therefore always sees the eMMC as `/dev/mmcblk0`.
- U-Boot scans only `mmc0`, with only the RAUC bootmeth: the boot command sets `boot_targets` to `mmc0`, because
  Rockchip's default order would try the SD card first. It sets `boot_targets` rather than passing `mmc0` as a scan
  label, because once `bootmeth order` is set U-Boot refuses labelled scans and reports zero bootflows. If the
  selected slot fails to boot, the boot command resets so the RAUC try counter can fall back.
- The boot command and `boot_targets` are saved in the eMMC environment on first boot, so a changed
  `CONFIG_BOOTCOMMAND` reaches a deployed board only after its environment is reset (for example, by reflashing).
- Root, `/boot`, `/data`, the RAUC slots, `systemd-repart`, and `fw_env.config` use fixed `/dev/mmcblk0pN` paths rather
  than GPT labels, because every AtomixOS image shares the same labels and an inserted SD card could otherwise win.
- U-Boot A/B environment: two 32-KiB records in the reserved eMMC user-area boot gap at offsets `0x3f8000` and `0x3f0000`.
- Kernel, DTB, and initrd use the RK3568 U-Boot default load addresses; the ROCK64 `ramdisk_addr_r` override is not
  applied.
- Serial UART2 at 1,500,000 baud; GMAC1 at `fe010000.ethernet`.

Confirm the numbering on a working OS image, e.g. a Radxa or Armbian image:

```sh
lsblk -o NAME,PATH,SIZE,TYPE,MODEL,TRAN,PARTLABEL
readlink -f /sys/class/block/mmcblk0/device
for d in /sys/class/mmc_host/mmc*/device; do echo "$d"; done
```

Then validate U-Boot's `mmc list` and whether it can read/write the redundant environment at the intended offsets. Only
after those checks should you flash the CM3 AtomixOS image, confirm `fw_printenv`/`fw_setenv` match `fw_env.config`, and
exercise the RAUC mark-good, simulated failed boot, and rollback cycle. Confirm that `systemd-repart` creates `boot-b`,
`rootfs-b`, and `data` on **the eMMC rather than the removable SD card**.

The board may have no populated SPI NOR flash (as on some CM3 modules). This target uses eMMC for the environment and
does not access `/dev/mtd0`. U-Boot has the same USB mass storage (UMS) recovery as ROCK64 on the RK3566 OTG port
(DWC3): setting `START_UMS=1` with `fw_setenv` exposes the eMMC over USB on the next boot. U-Boot checks it in `PREBOOT`,
before slot selection, so it works even if the selected slot's boot files are broken (`boot.scr` checks it too). Only
the hold-button trigger is disabled, because the ROCK64 recovery GPIO is not valid on CM3. Rockchip Maskrom recovery
remains available as a fallback. A stale SPL or bootloader in SPI NOR (when fitted) may override the image on eMMC, so
verify U-Boot's version via serial output.

## Bring-up checks

On new CM3 hardware, verify GMAC, both USB host/OTG controllers, the RK817 PMIC, and watchdog operation in addition to
eMMC and serial boot. The CM3 always uses the internal RK3566 watchdog (`fe600000`); if `build.toml` selects
`backend = "external"`, evaluation warns and still uses the internal one. Do not enable hardware watchdog or deploy
production RAUC updates until boot, power-loss recovery, and rollback tests succeed.

## OTA updates

A CM3 sends `X-Compatible: radxa-cm3-io` when polling, and the update server must answer with a CM3 bundle. A response
naming another board's `compatible` is skipped without downloading; see
[Update Polling](architecture/update-rollback.md#update-polling).
