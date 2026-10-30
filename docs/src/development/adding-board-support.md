# Adding Board Support

AtomixOS supports boards one at a time. Each board gets its own hardware module, bootloader, flake outputs, build
choices, evaluation test, and guide; the image layout, update flow, and provisioning stay the same on every board. The
Radxa CM3 IO board is a complete worked example: `modules/hardware-cm3.nix`, `nix/uboot-cm3.nix`,
`nix/tests/cm3-board.nix`, and the [Radxa CM3 IO Board](../cm3.md) guide.

Below, `<board>` is the board's short name, such as `rock64` or `cm3`. It names the flake outputs, the build
artifacts, and the `.gcroots/<board>/` directory.

## 1. Name the board

Add `<board>` to the `atomixos.board` enum in `modules/base.nix`. The option selects the board's U-Boot environment
tools and names its RAUC bundle, image, and other artifacts.

## 2. Write the hardware module

Create `modules/hardware-<board>.nix` and set `atomixos.board = "<board>";`. For a Rockchip SoC, import
`./hardware-rockchip.nix`, which supplies what the Rockchip boards share:

- no NixOS-managed bootloader, because U-Boot boots the slots;
- a `noauto` `/boot` that stays unmounted at runtime, so RAUC can write boot slot A while slot B runs;
- systemd-repart without discard, so it never trims the SPL and U-Boot area before the first partition;
- the Realtek USB NIC firmware, the `boot_to_ums` helper, and the serial console on `ttyS2`;
- the `_RUT_OH_` serial root recovery.

A board on another SoC family must provide the equivalents itself.

The module then sets the board-specific parts:

| Concern            | What to set                                                                                         |
|--------------------|-----------------------------------------------------------------------------------------------------|
| Kernel             | `boot.kernelPackages`; start from a stock kernel and strip it only after the board boots            |
| Device tree        | `hardware.deviceTree.name`, plus any overlays the board needs                                       |
| Initrd             | `boot.initrd.availableKernelModules` for the eMMC host controller and `squashfs`                    |
| Storage            | `boot.initrd.systemd.repart.device`, `fileSystems."/boot".device`, and `fileSystems."/data".device` |
| U-Boot environment | `environment.etc."fw_env.config"`, matching U-Boot's environment offset, size, and redundant copy   |
| RAUC               | `atomixos.rauc.compatible`, unique to the board, and the four `atomixos.rauc.slots` devices         |
| WAN port           | `atomixos.network.wanLinkMatch`, usually the onboard NIC's platform `Path`                          |
| Watchdog           | a udev rule that links the SoC watchdog to `/dev/watchdog-internal`                                 |

Use fixed eMMC device paths rather than partition labels: every AtomixOS image has the same GPT labels, so a label could
resolve to an SD card or USB stick. The partition layout itself comes from `nix/partition-layout.nix` and is the same on
every board; [Partition Layout](../architecture/partition-layout.md) explains it. [Network
Topology](../architecture/network-topology.md#nic-naming) explains how `wanLinkMatch` names the WAN port `wan`.

## 3. Build the bootloader

Add `nix/uboot-<board>.nix`. The U-Boot build must keep the features the update and recovery flows rely on:

- the RAUC A/B boot method and a persistent environment, in the place `fw_env.config` names;
- `bootcmd` ending in `reset`, so a failed load counts as a failed boot attempt;
- USB mass storage (`CONFIG_CMD_USB_MASS_STORAGE`) and its USB gadget driver, for `START_UMS` recovery;
- FAT write support, so U-Boot can save its environment and update boot state.

`nix/uboot.nix` (Rock64) and `nix/uboot-cm3.nix` show both an environment in SPI flash and a redundant environment in
the eMMC.

## 4. Wire it into the flake

In `flake.nix`:

1. Add `nixosConfigurations.<board>`, with `./modules/base.nix`, `./modules/build-configuration.nix`, and the new
   hardware module, following `nixosConfigurations.cm3`.
2. Add a `boards.<board>` entry with:
   - `nixosConfig`, the board's NixOS configuration;
   - `uboot`, the new bootloader package;
   - `bootScript`, with the serial console and `earlycon` in `bootargsBase`, the reset-button GPIO in
     `recoveryButtonPin` (or `""`), and an initrd address in `ramdiskAddr` (or `""` for U-Boot's default).

`mkBoardPackages` then builds `.#<board>` and each artifact on its own, such as `.#<board>.image` and
`.#<board>.rauc-bundle`.

## 5. Add it to the build tasks

Add `<board>` to:

- the `--board` choices of `build`, `build:squashfs`, `build:rauc-bundle`, and `build:boot-script` in `mise.toml`;
- the board check in `scripts/build.sh`;
- the `--board` choices and the board list in `.mise/tasks/flash`.

## 6. Test it

Add `nix/tests/<board>-board.nix`, an evaluation check like `nix/tests/cm3-board.nix`. It should assert the board name,
device tree, RAUC compatible, repart device, `wan` link match, and that `fw_env.config` agrees with the U-Boot
environment settings. Register it in both check sets in `flake.nix`, then run:

```sh
nix build .#checks.aarch64-linux.<board>-board
mise run build --board <board>
```

Then flash a board and work through [Hardware Testing](../hardware-testing.md), including an update, a rollback, and USB
mass storage recovery.

## 7. Document it

- Write a board guide like the [Radxa CM3 IO Board](../cm3.md) page: building, first boot, ports, and serial pins.
  Register it in `docs/sidebars.ts`.
- Add the board to the supported-hardware table on the introduction page (`docs/src/README.mdx`), to
  [Flake Outputs](../reference/flake-outputs.md), and to the boards table on the product page (`product/index.html`).
