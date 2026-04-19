# RAUC Integration

> Source: `openspec/changes/rock64-ab-image/specs/rauc-integration/spec.md`

## Requirements

### ADDED: A/B multi-slot configuration

RAUC `system.conf` defines two slot pairs (A and B), each containing a boot partition and a rootfs partition. The boot
partition is the parent; the rootfs partition inherits its slot assignment.

#### Scenario: RAUC sees all slots

- Given the device has booted
- When `rauc status` is run
- Then 4 slots are listed: boot.0 (A), rootfs.0 (A), boot.1 (B), rootfs.1 (B)
- And one pair is marked as "booted"

### ADDED: U-Boot bootloader backend

RAUC uses the `uboot` backend to communicate slot priority and boot-count via U-Boot environment variables. On the QEMU
target, a `custom` backend simulates the same behavior using files.

#### Scenario: RAUC can switch slots

- Given slot A is active
- When `rauc install` writes a bundle to slot B
- Then RAUC sets `BOOT_ORDER=B A` and `BOOT_B_LEFT=3`
- And the next boot loads from slot B

### ADDED: Bundle signature verification

RAUC verifies bundle signatures against the CA keyring (`dev.ca.cert.pem`). Unsigned or invalidly signed bundles are
rejected.

#### Scenario: Invalid bundle is rejected

- Given a `.raucb` bundle signed with a different key
- When `rauc install` is attempted
- Then the install fails with a signature verification error
- And no slot data is modified

### ADDED: Writes to inactive slot only

RAUC only writes to the slot pair that is not currently booted. The active slot is never modified during an update.

#### Scenario: Active slot is protected

- Given slot A is booted
- When `rauc install` runs
- Then data is written to boot-b and rootfs-b only
- And boot-a and rootfs-a remain unchanged

### ADDED: Bundle contains boot and rootfs

Each RAUC bundle contains two images: a vfat boot image (kernel + initrd + DTB + boot.scr)
and the squashfs rootfs. Both are installed
atomically to the target slot pair.

#### Scenario: Bundle structure

- Given a bundle is built with `nix build .#rauc-bundle`
- When `rauc info` is run on the bundle
- Then it shows an image for `boot` (type: raw) and an image for `rootfs` (type: raw)
- And the `compatible` field is `rock64`

### ADDED: Update polling service

The `os-upgrade.service` polls an update server on a timer, downloads new bundles, and installs them via RAUC. It is
designed to be replaced with `rauc-hawkbit-updater` for server-push updates.

#### Scenario: Polling finds new version

- Given the update server has a newer bundle
- When the timer fires
- Then the bundle is downloaded to `/persist`
- And `rauc install` is run
- And the device reboots into the new slot

### ADDED: Swappable with hawkBit

The `os-upgrade` module has a `useHawkbit` option that switches from the polling service to `rauc-hawkbit-updater`. This
is disabled by default.

#### Scenario: hawkBit mode

- Given `os-upgrade.useHawkbit = true`
- Then the `os-upgrade` polling timer is not created
- And `rauc-hawkbit-updater` package is included in the system

### ADDED: NixOS RAUC module

RAUC is enabled via the upstream NixOS `services.rauc` module and wired from `atomixos.rauc.*` options. The `rauc`
client is available in the system environment.

#### Scenario: RAUC is available

- Given the device has booted
- When `rauc --version` is run
- Then a valid version string is returned
- And `rauc.service` is active
