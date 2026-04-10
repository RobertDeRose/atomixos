# RAUC Integration Spec

## ADDED Requirements

### Requirement: RAUC is configured with A/B multi-slot definitions

The RAUC system configuration (`system.conf`) SHALL define two slot pairs: boot slot A + rootfs slot A, and boot
slot B + rootfs slot B. Each slot pair SHALL be mapped to its respective eMMC partitions. The configuration SHALL
specify U-Boot as the bootloader backend.

#### Scenario: RAUC recognizes all slots

- **WHEN** `rauc status` is run on the device
- **THEN** the output lists boot slot A, boot slot B, rootfs slot A, and rootfs slot B with their partition device
  paths, and one slot pair is marked as active

### Requirement: RAUC uses U-Boot bootloader backend

The RAUC configuration SHALL specify `bootloader=uboot` and configure the appropriate U-Boot environment variable names
for slot selection and boot-count tracking.

#### Scenario: RAUC sets U-Boot environment on install

- **WHEN** a RAUC bundle is installed to the inactive slot pair
- **THEN** RAUC updates the U-Boot environment variables to set the newly written slot as primary and resets the boot
  attempt counter

### Requirement: RAUC verifies bundle signatures before installation

RAUC SHALL be configured with a CA certificate (`keyring`) and SHALL reject any bundle not signed by a key trusted by
that CA. Unsigned or incorrectly signed bundles SHALL NOT be installed.

#### Scenario: Valid signed bundle installs successfully

- **WHEN** a bundle signed with a key trusted by the configured CA is provided to `rauc install`
- **THEN** RAUC verifies the signature, writes both boot and rootfs images to the inactive slot pair, and reports
  success

#### Scenario: Invalid signature is rejected

- **WHEN** a bundle with an invalid or untrusted signature is provided to `rauc install`
- **THEN** RAUC refuses to install and returns a signature verification error

### Requirement: RAUC writes to the inactive slot pair only

RAUC SHALL always write updates to the slot pair that is NOT currently booted. It SHALL never overwrite the running boot
partition or root filesystem.

#### Scenario: Update targets inactive slot pair

- **WHEN** the device is booted from slot pair A and `rauc install` is run
- **THEN** RAUC writes the new boot image to boot slot B and the new rootfs image to rootfs slot B (and vice versa)

### Requirement: RAUC bundle contains boot and rootfs images

Each RAUC bundle (`.raucb`) SHALL contain two images: a boot partition image (kernel + DTB) and a rootfs image
(squashfs). RAUC SHALL write both images to their respective partitions in the target slot pair.

#### Scenario: Bundle contains both images

- **WHEN** the RAUC bundle is inspected with `rauc info`
- **THEN** the bundle manifest lists both a boot image and a rootfs image

### Requirement: Update polling service checks for new bundles

A systemd timer (`apollo-update.timer`) SHALL periodically poll the update server for new RAUC bundles. When a new
bundle is available, the service SHALL download it and invoke `rauc install`.

#### Scenario: New bundle is detected and installed

- **WHEN** the update server has a bundle with a version newer than the currently installed version
- **THEN** the polling service downloads the bundle and triggers `rauc install`

#### Scenario: No update available

- **WHEN** the update server reports no newer version
- **THEN** the polling service exits cleanly and waits for the next timer interval

#### Scenario: Download failure is handled gracefully

- **WHEN** the download of a new bundle fails (network error, partial download)
- **THEN** the polling service logs the error, does not invoke `rauc install`, and retries at the next interval

### Requirement: Update client is swappable with hawkBit

The NixOS configuration SHALL include both the simple polling service (`apollo-update`) and the `rauc-hawkbit-updater`
client. Only one SHALL be enabled at a time, selectable via a NixOS configuration flag. Both clients SHALL trigger `rauc
install` for bundle installation.

#### Scenario: Simple polling is enabled by default

- **WHEN** the device boots with default configuration
- **THEN** `apollo-update.timer` is active and `rauc-hawkbit-updater` is not running

#### Scenario: hawkBit client can be enabled

- **WHEN** the NixOS configuration flag for hawkBit is set to true
- **THEN** `rauc-hawkbit-updater` is active and `apollo-update.timer` is not running

### Requirement: NixOS RAUC module is enabled in configuration

The NixOS configuration SHALL enable the RAUC service via `services.rauc` with the appropriate `compatible` string and
CA certificate path.

#### Scenario: RAUC service is active after boot

- **WHEN** the device boots
- **THEN** the `rauc` systemd service is running and `rauc status` returns valid slot information
