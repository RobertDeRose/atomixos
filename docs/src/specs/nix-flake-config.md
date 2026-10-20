# Nix Flake Configuration

Acceptance contract for the system configurations and artifacts the flake produces. The full output list is in
[Flake Outputs](../reference/flake-outputs.md).

## Requirements

### Flake defines the Rock64 NixOS configuration

`nixosConfigurations.rock64` targets `aarch64-linux` (RK3328) and includes every service module: systemd, OpenSSH,
chrony, dnsmasq, RAUC, nftables, the watchdog integration, and the health-check and update services.

#### Scenario: Rock64 system evaluates cleanly

- Given the flake is checked with `nix flake check`
- Then `nixosConfigurations.rock64` evaluates without errors
- And the system target is `aarch64-linux`

### Flake defines the Radxa CM3 NixOS configuration

`nixosConfigurations.cm3` targets the Radxa CM3 (RK3566) on the CM3 IO Board with the same service modules, the stock
upstream kernel, and RAUC compatible `radxa-cm3-io`.

#### Scenario: CM3 board wiring agrees

- Given `checks.<system>.cm3-board` is built
- Then the CM3 storage paths, RAUC slots, and resolved U-Boot environment settings agree with `fw_env.config`

### Produces the squashfs rootfs image

`packages.aarch64-linux.<board>.squashfs` builds a compressed squashfs root filesystem no larger than the 1024 MiB
rootfs slot.

#### Scenario: Squashfs image fits within its slot

- Given the squashfs is built with `nix build .#rock64.squashfs`
- Then the image is at most 1024 MiB
- And it uses zstd compression with a 1 MiB block size

### Produces a signed RAUC bundle

`packages.aarch64-linux.<board>.rauc-bundle` builds a multi-slot `.raucb` bundle with a boot image (kernel, initrd, DTB,
and `boot.scr`) and a rootfs image (squashfs), signed with the configured signing certificate. Flake builds use the
development signing certificate in `certs/`.

#### Scenario: RAUC bundle is valid

- Given the bundle is built with `nix build .#rock64.rauc-bundle`
- Then the `.raucb` file passes `rauc info --no-verify`
- And it contains images for both the `boot` and `rootfs` slot classes
- And it is signed with the development signing certificate

### Stripped kernel with modular USB peripherals

The Rock64 kernel builds in the drivers needed to boot (eMMC, Ethernet, USB host, watchdog, squashfs, f2fs, OverlayFS) and
builds selected USB Ethernet and USB serial drivers as modules. It is built without Wi-Fi and Bluetooth.

#### Scenario: Kernel has the required drivers

- Given the Rock64 NixOS configuration is evaluated
- Then the kernel sets `MMC_DW_ROCKCHIP=y`, `STMMAC_ETH=y`, `DW_WATCHDOG=y`, and `SQUASHFS=y`
- And `USB_RTL8152`, `USB_NET_AX88179_178A`, and `USB_NET_CDCETHER` are built as modules

#### Scenario: USB serial works for debugging

- Given a USB serial adapter is plugged in
- When the `ftdi_sio` or `cp210x` module is loaded
- Then `/dev/ttyUSB0` appears

### QEMU testing target

`nixosConfigurations.rock64-qemu` targets QEMU `aarch64-virt` with virtio block devices. It shares the service
configuration in `modules/base.nix`, leaves RAUC disabled by default, and the RAUC tests enable it with the file-based
`custom` backend instead of U-Boot.

#### Scenario: QEMU target runs the RAUC tests

- Given a RAUC VM test is built from `checks.<system>.rauc-*`
- When the test VM starts
- Then the services from `modules/base.nix` are present
- And RAUC uses the `custom` file-based backend
