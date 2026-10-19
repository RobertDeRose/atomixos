# RAUC Integration

Acceptance contract for RAUC slots, bundles, and update delivery. The update cycle is explained in
[Update and Rollback](../architecture/update-rollback.md).

## Requirements

### A/B multi-slot configuration

RAUC `system.conf` defines two slot pairs, A and B. Each pair has a boot partition (the parent) and a rootfs partition
that inherits its slot assignment.

#### Scenario: RAUC sees all slots

- Given the device has booted
- When `rauc status` runs
- Then four slots are listed: `boot.0` (A), `rootfs.0` (A), `boot.1` (B), and `rootfs.1` (B)
- And one pair is marked as booted

### U-Boot bootloader backend

RAUC uses the `uboot` backend to set slot priority and boot counts through U-Boot environment variables. The QEMU RAUC
tests use the `custom` backend, which keeps the same state in files under `/var/lib/rauc/`.

#### Scenario: RAUC can switch slots

- Given slot A is active
- When `rauc install` writes a bundle to slot B
- Then RAUC sets `BOOT_ORDER=B A` and `BOOT_B_LEFT=3`
- And the next boot loads slot B

### Bundle signature verification

RAUC verifies bundles against its keyring: the development CA (`certs/dev.ca.cert.pem`) unless
`atomixos.rauc.keyringCert` sets a production CA. Unsigned bundles and bundles signed by another CA are rejected. The
bundle formats are `-plain +verity`, so `plain` bundles are refused.

#### Scenario: Invalid bundle is rejected

- Given a `.raucb` bundle signed with a different key
- When `rauc install` runs
- Then the install fails with a signature verification error
- And no slot data is modified

### Writes to the inactive slot only

RAUC writes only to the slot pair that is not booted. The active slot is never modified during an update.

#### Scenario: Active slot is protected

- Given slot A is booted
- When `rauc install` runs
- Then data is written to `boot-b` and `rootfs-b` only
- And `boot-a` and `rootfs-a` are unchanged

### Bundle contains boot and rootfs

Each bundle holds two raw images, `boot.vfat` (kernel, initrd, DTB, and `boot.scr`) and `rootfs.squashfs`. Both are
installed to the target slot pair as one update.

#### Scenario: Bundle structure

- Given a bundle is built with `nix build .#rock64.rauc-bundle`
- When `rauc info` runs on it
- Then it lists a `boot` image and a `rootfs` image, both of type `raw`
- And its `compatible` value is `rock64`
- And a `.#cm3.rauc-bundle` bundle's `compatible` value is `radxa-cm3-io`

### Update polling service

`os-upgrade.service` polls the provisioned update server on a timer, downloads a newer bundle, and installs it with
RAUC. It does nothing until `/data/config/os-upgrade.json` names an update server.

#### Scenario: Polling finds a new version

- Given the update server offers a newer bundle
- When the timer fires
- Then the bundle is downloaded to `/data/rauc/bundles`
- And `rauc install` runs
- And the device reboots into the new slot

#### Scenario: Polling identifies the board

- Given a device whose RAUC compatible is `radxa-cm3-io`
- When the timer fires
- Then the update query includes `X-Compatible: radxa-cm3-io`
- And a response whose `compatible` is `rock64` is skipped without downloading the bundle

### hawkBit mode installs the package only

`os-upgrade.useHawkbit = true` disables the polling service and installs the `rauc-hawkbit-updater` package; see
[Update Polling](../architecture/update-rollback.md#update-polling) for what that means for updates.

#### Scenario: hawkBit mode

- Given `os-upgrade.useHawkbit = true`
- Then the `os-upgrade` polling timer is not created
- And the `rauc-hawkbit-updater` package is installed
- And no `rauc-hawkbit-updater` systemd service is created

### NixOS RAUC module

RAUC is enabled through the upstream NixOS `services.rauc` module, configured from `atomixos.rauc.*`. The `rauc`
client is on the system path.

#### Scenario: RAUC is available

- Given the device has booted
- When `rauc --version` runs
- Then it prints a version string
- And `rauc.service` is active
