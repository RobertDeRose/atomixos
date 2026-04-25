# Nix Flake Configuration

> Source: `openspec/changes/rock64-ab-image/specs/nix-flake-config/spec.md`

## Requirements

### ADDED: Flake defines Rock64 NixOS configuration

The flake provides `nixosConfigurations.rock64` targeting `aarch64-linux` (RK3328). The configuration includes all
service modules: systemd, openssh, chrony, dnsmasq, RAUC, nftables, watchdog, and the health-check/update services.

#### Scenario: Rock64 system evaluates cleanly

- Given the flake is checked with `nix flake check`
- Then `nixosConfigurations.rock64` evaluates without errors
- And the system target is `aarch64-linux`

### ADDED: Produces squashfs rootfs image

The flake builds a compressed squashfs root filesystem via `packages.aarch64-linux.squashfs`. The image must not exceed
the partition slot size (1 GB).

#### Scenario: Squashfs image fits within slot

- Given the squashfs is built with `nix build .#squashfs`
- Then the resulting image is less than or equal to 1 GB
- And it uses zstd compression with 1 MB block size

### ADDED: Produces signed RAUC bundle

The flake builds a multi-slot RAUC bundle (`.raucb`) containing both boot
(kernel + initrd + DTB + boot.scr) and rootfs (squashfs) images,
signed with the project's CA key.

#### Scenario: RAUC bundle is valid

- Given the bundle is built with `nix build .#rauc-bundle`
- Then the `.raucb` file passes `rauc info --no-verify`
- And it contains entries for both `boot` and `rootfs` slots
- And it is signed with the development CA certificate

### ADDED: Stripped kernel with modular USB support

The kernel is configured with built-in drivers for essential hardware (eMMC, Ethernet, USB host, watchdog, squashfs,
f2fs) and loadable modules for USB peripherals (WiFi, Bluetooth, USB-serial).

#### Scenario: Kernel has required drivers

- Given the NixOS configuration is evaluated
- Then the kernel includes `MMC_DW_ROCKCHIP=y`, `STMMAC_ETH=y`, `DW_WATCHDOG=y`, `SQUASHFS=y`
- And WiFi drivers (RTL8XXXU, MT76_USB, etc.) are built as modules

#### Scenario: USB serial works for debugging

- Given a USB-serial adapter is plugged in
- When the `ftdi_sio` or `cp210x` module is loaded
- Then `/dev/ttyUSB0` appears

### ADDED: OpenVPN as system service

OpenVPN is included in the rootfs for recovery tunnel access. It does not auto-start; it requires a config file at
`/data/config/openvpn/client.conf`.

#### Scenario: OpenVPN service is conditional

- Given no OpenVPN config file exists on `/data`
- Then `openvpn-recovery.service` does not start
- When a config file is placed at `/data/config/openvpn/client.conf`
- And the service is started manually
- Then a `tun0` interface appears

### ADDED: QEMU testing target

The flake provides `nixosConfigurations.rock64-qemu` targeting `aarch64-virt` with virtio block devices. It shares the
full service configuration from `base.nix` but uses a custom RAUC backend (file-based) instead of U-Boot.

#### Scenario: QEMU target boots and runs tests

- Given the QEMU configuration is built
- When a test VM is started
- Then all services from `base.nix` are present
- And RAUC uses the custom file-based backend
