# Hardware Testing

> Source: `HARDWARE-TEST-PLAN.md`

This chapter provides the physical verification plan for Rock64 hardware testing. These tests cannot be run in QEMU and
require a physical Rock64 board with eMMC, serial console, and network connectivity.

## Prerequisites

- Rock64 v2 board with 16 GB eMMC module
- USB-to-serial adapter connected to UART2 (1.5 Mbaud)
- USB Ethernet adapter (for eth1/LAN interface)
- Supported USB Ethernet adapter for eth1/LAN (`r8152`, `ax88179_178a`, or `cdc_ether`)
- Built disk image (`atomixos-26.05.img`)
- Built RAUC bundle (`rock64.raucb`)
- Network with DHCP and internet access (for WAN/eth0)
- A second device on the LAN subnet for client testing

## Phase 1: Provisioning & First Boot

### Test 1.1: Flash image and verify U-Boot output

```sh
# Flash the image
mise run flash /dev/disk4    # macOS
# or
sudo dd if=atomixos-26.05.img of=/dev/mmcblk0 bs=4M status=progress

# Connect serial console
screen /dev/tty.usbserial-DM02496T 1500000
```

**Pass criteria**:

- U-Boot banner appears on serial console
- `bootflow scan` finds `boot.scr` on boot-a
- Kernel loads and prints boot messages
- System reaches `multi-user.target`
- If `/boot/config.toml` or a USB seed is present, `first-boot.service` completes provisioning
- Without a seed, the bootstrap UI appears on WAN and LAN port `8080`, and first boot waits indefinitely for operator
  input until a valid config is applied

### Test 1.2: Verify first-boot service

```sh
systemctl status first-boot
[ -f /data/.completed_first_boot ] && cat /data/.completed_first_boot
[ -x "$(command -v rauc)" ] && rauc status
```

**Pass criteria**:

- With a seed config present, `first-boot.service` completed successfully
- Without a seed config, the bootstrap UI is reachable and `first-boot.service` remains waiting
- After provisioning succeeds, the sentinel exists at `/data/.completed_first_boot`
- On RAUC-enabled images, `rauc status` shows the booted slot as "good" after provisioning succeeds

## Phase 2: Kernel & Hardware Detection

### Test 2.1: eMMC and core hardware

```sh
dmesg | grep -i mmc
dmesg | grep -i dwmac
dmesg | grep -i ehci
dmesg | grep -i watchdog
lsblk
```

**Pass criteria**:

- eMMC detected as `/dev/mmcblk1` (or `mmcblk0` depending on boot media)
- Ethernet MAC driver (DWMAC/STMMAC) loaded
- USB host controller (EHCI/OHCI/XHCI) initialized
- Watchdog device (`dw_wdt`) registered

### Test 2.2: USB Ethernet module

```sh
modprobe r8152      # or ax88179_178a/cdc_ether for your adapter
ip link show
```

**Pass criteria**:

- Supported USB Ethernet module loads without errors
- A second Ethernet interface appears in `ip link`
- USB WiFi and Bluetooth are not part of the current image contract

## Phase 3: Network Configuration

### Test 3.1: eth0 is onboard Ethernet

```sh
udevadm info /sys/class/net/eth0 | grep ID_PATH
ip addr show eth0
```

**Pass criteria**:

- `eth0` matches the onboard GMAC (platform path `platform-ff540000.ethernet`)
- eth0 has a DHCP-assigned IP address

### Test 3.2: DHCP server on LAN

Connect a client device to eth1 (USB Ethernet adapter).

```sh
# On the gateway
systemctl status dnsmasq
journalctl -u dnsmasq | tail -20

# On the LAN client
dhclient eth0    # or equivalent
ip addr show
```

**Pass criteria**:

- Client receives an IP in `172.20.30.10-254` range
- Gateway is `172.20.30.1`
- dnsmasq logs the DHCP transaction

### Test 3.3: NTP server on LAN

```sh
# On the gateway
chronyc tracking
chronyc clients

# On the LAN client
ntpdate -q 172.20.30.1
```

**Pass criteria**:

- Chrony is synced to upstream NTP (or using local stratum 10 fallback)
- LAN client can query NTP from `172.20.30.1`

### Test 3.4: LAN isolation

```sh
# On the LAN client
ping -c 3 8.8.8.8          # should fail
curl https://example.com    # should fail
ping -c 3 172.20.30.1       # should succeed
```

**Pass criteria**:

- LAN client cannot reach any internet address
- LAN client can reach the gateway

## Phase 4: Firewall Verification

### Test 4.1: WAN baseline port access

From an external machine (or the WAN side):

```sh
# These should fail until explicitly provisioned
curl -k https://<wan-ip>:443
nc -uz <wan-ip> 1194

# This should fail (connection refused/timeout)
ssh <wan-ip>
```

**Pass criteria**:

- HTTPS (443) is blocked until provisioned
- OpenVPN (1194) is blocked until provisioned
- SSH (22) is blocked

### Test 4.2: SSH-on-WAN toggle

```sh
# Enable SSH on WAN
touch /data/config/ssh-wan-enabled
systemctl start ssh-wan-reload

# Test from WAN side
ssh admin@<wan-ip>    # should now work

# Disable SSH on WAN
rm /data/config/ssh-wan-enabled
systemctl start ssh-wan-reload

# Test from WAN side
ssh admin@<wan-ip>    # should fail again
```

**Pass criteria**:

- SSH is blocked by default
- Creating the flag file and reloading enables SSH
- Removing the flag file and reloading disables SSH

## Phase 5: Services

### Test 5.1: Update confirmation

```sh
systemctl restart os-verification
journalctl -u os-verification -f
```

**Pass criteria**:

- Local service and network checks pass
- 60-second sustained check completes
- Slot is marked as "good"

## Phase 6: Authentication

### Test 6.1: SSH key authentication

```sh
# From an external machine on the LAN
ssh -i ~/.ssh/id_ed25519 admin@172.20.30.1

# Password auth should remain disabled
auth_line="$({ ssh -vv -o PreferredAuthentications=none -o PubkeyAuthentication=no \
  -o BatchMode=yes -o NumberOfPasswordPrompts=0 \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/tmp/atomixos-rock64-known_hosts \
  -o ConnectTimeout=10 admin@172.20.30.1 true; } \
  2>&1 | grep 'Authentications that can continue:' | tail -n 1)"
[ -n "$auth_line" ] && ! printf '%s\n' "$auth_line" | grep -Fq 'password'
```

**Pass criteria**:

- Key-based authentication succeeds
- The auth-method probe exits successfully, confirming `password` is excluded

### Test 6.2: Serial root recovery

```sh
# On the device
fw_setenv _RUT_OH_ 1
reboot

# `_RUT_OH_` should remain a serial-only recovery path
# On UART2/ttyS2 at 1500000 baud, expect serial root autologin on the next boot.

# From an external machine on the LAN after the reboot
ssh -i ~/.ssh/id_ed25519 admin@172.20.30.1
auth_line="$({ ssh -vv -o PreferredAuthentications=none -o PubkeyAuthentication=no \
  -o BatchMode=yes -o NumberOfPasswordPrompts=0 \
  -o StrictHostKeyChecking=accept-new \
  -o UserKnownHostsFile=/tmp/atomixos-rock64-known_hosts \
  -o ConnectTimeout=10 admin@172.20.30.1 true; } \
  2>&1 | grep 'Authentications that can continue:' | tail -n 1)"
[ -n "$auth_line" ] && ! printf '%s\n' "$auth_line" | grep -Fq 'password'

# On the device after boot completes
fw_printenv -n _RUT_OH_    # expect: empty / unset
```

**Pass criteria**:

- `_RUT_OH_` enables one-shot serial root autologin on UART2 only
- SSH behavior on the network is unchanged after the recovery boot
- `_RUT_OH_` is cleared after use

## Phase 7: RAUC Update Lifecycle

### Test 7.1: RAUC status

```sh
rauc status
```

**Pass criteria**:

- Shows 4 slots (boot.0, rootfs.0, boot.1, rootfs.1)
- One pair is marked as booted and good

### Test 7.2: Bundle install

```sh
# Copy bundle to device
scp rock64.raucb admin@172.20.30.1:/data/

# Install
rauc install /data/rock64.raucb
```

**Pass criteria**:

- Install completes without errors
- `rauc status` shows the inactive slot has been written
- `BOOT_ORDER` reflects the new slot priority

### Test 7.3: Boot-count rollback

```sh
# After installing to slot B, intentionally corrupt it
dd if=/dev/zero of=/dev/mmcblk1p4 bs=1M count=1

# Reboot 3 times and observe the serial console
reboot
```

**Pass criteria**:

- Each boot attempt decrements `BOOT_B_LEFT`
- After 3 failures, U-Boot falls back to slot A
- Slot A boots successfully with the previous working image

## Phase 8: Watchdog

### Test 8.1: Build-time backend selection and watchdog presence

Watchdog selection is immutable build policy. Choose one of these snippets in the repository-root `build.dev.toml` for a
local test image, or promote the values to committed `build.toml`:

```toml
# Onboard RK3328 DesignWare watchdog
[watchdog]
enable_hardware = true
backend = "internal"

# For the example external SOM watchdog, use instead:
# backend = "external"

# To disable enforcement completely:
# enable_hardware = false
```

Run `mise run build`; supported `mise` tasks apply `build.dev.toml` automatically and mark outputs `-dev`. Direct Nix
commands use committed `build.toml` only. The backend is required even when `enable_hardware = false`.

For every enabled image, verify the policy and systemd owner:

```sh
cat /etc/atomixos/build.toml
systemctl show --property WatchdogDevice --property RuntimeWatchdogUSec --property RebootWatchdogUSec
journalctl -b --no-pager | grep -E 'Using hardware watchdog|Watchdog running'
```

For `backend = "internal"`, verify the onboard path:

```sh
ls -l /dev/watchdog-internal
readlink -f /dev/watchdog-internal
readlink -f /sys/class/watchdog/watchdog0/device/driver
```

Expected results include `/dev/watchdog-internal -> /dev/watchdog0`, the `dw_wdt` driver, and systemd's
`Synopsys DesignWare Watchdog` message.

For `backend = "external"`, verify the included TI UCC2946 example path:

```sh
run0 i2cdetect -y 1
run0 i2cget -y 1 0x41 0x00 b
run0 i2cget -y 1 0x41 0x01 b
run0 i2cget -y 1 0x41 0x02 b
run0 i2cget -y 1 0x41 0x03 b
external_device=$(readlink -f /dev/watchdog-external)
ls -l /dev/watchdog-external "$external_device"
readlink -f "/sys/class/watchdog/$(basename "$external_device")/device/driver"
```

Expected results include address `0x41` claimed by the PCA/TCA9536-compatible expander, `/dev/watchdog-external`, and
the `gpio-wdt` driver. Systemd remains the sole owner; do not run the legacy `i2cset` kicker.

For `enable_hardware = false`, `systemctl show` must omit `WatchdogDevice`, `RuntimeWatchdogUSec`, and
`RebootWatchdogUSec`. The external always-running device-tree node is omitted; an internal image may still expose an
unarmed `/dev/watchdog-internal`, so verify that PID 1 does not hold the device rather than relying only on node absence.

### Test 8.2: Watchdog-triggered reboot

> This is destructive. Use a sacrificial test device with serial capture, recovery access, and a known-good slot. Active
> enforcement remains disabled by default; do not enable it in release or deployment profiles for this test.

Start serial capture from the host before inducing the hang:

```sh
mise run serial:capture -- --port /dev/cu.usbserial-<id> \
  --log /tmp/rock64-watchdog-reset.log --bg
```

On the device, confirm the active policy and U-Boot state:

```sh
systemctl show --property WatchdogDevice --property RuntimeWatchdogUSec --property RebootWatchdogUSec
fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT
```

On the validated Rock64 test image, the bounded hang fixture is:

```sh
run0 kill -STOP 1
```

This stops PID 1's watchdog kicks without intentionally modifying persistent state. Do not use this method without the
serial and recovery prerequisites; it is a destructive, board-specific test fixture, not a general production command.

**Pass criteria**:

- Record the timestamp when the fixture runs and when the serial reset sequence begins
- With the default 30-second runtime timeout, reset begins no later than 35 seconds after confirmed kick cessation
  (30-second policy plus 5 seconds of measurement and serial-console tolerance)
- Serial console shows a fresh U-Boot TPL/SPL/U-Boot sequence and a new AtomixOS boot
- SSH recovers after the reboot and systemd again reports the selected watchdog device
- U-Boot boot-count evidence is recorded for the current slot

### Test 8.3: Watchdog-triggered rollback (deferred to RAUC OTA testing)

> Deferred until the RAUC OTA testing work exercises installation, boot confirmation, and rollback together. Keep
> serial console attached and have recovery media available when executing it.

```sh
# Install an update bundle to the inactive slot and reboot into it
rauc install /data/rock64.raucb
reboot

# On each boot into the updated slot, induce the lab-validated systemd hang before os-verification can mark it good
fw_printenv BOOT_ORDER BOOT_A_LEFT BOOT_B_LEFT

# Repeat until the updated slot's BOOT_*_LEFT counter reaches 0 and U-Boot selects the previous slot.
```

**Pass criteria**:

- The updated slot receives three watchdog-triggered boot attempts
- Each failed attempt decrements the updated slot's `BOOT_*_LEFT` counter
- After the counter reaches 0, U-Boot boots the previous slot
- The previous slot reaches `multi-user.target` and remains marked good

### Test 8.4: Watchdog soak (deferred to RAUC OTA testing)

> Deferred until the RAUC OTA validation campaign. Run the soak on the same image and workload used for OTA testing.

```sh
# Leave the opt-in watchdog image running under normal workload for 72 hours.
systemctl show --property RuntimeWatchdogUSec --property RebootWatchdogUSec
journalctl -b -p warning..alert
last -x reboot | head
```

**Pass criteria**:

- No unexpected watchdog resets occur during the 72-hour soak
- No recurring warning or error pattern indicates missed watchdog kicks
- Normal update confirmation and local recovery services continue to operate
- Reboot history covers the soak window and contains only operator-initiated reboots

## Task Checklist

| #   | Test                  | Status                              |
|-----|-----------------------|-------------------------------------|
| 1.1 | Flash + U-Boot output |                                     |
| 1.2 | First-boot service    |                                     |
| 2.1 | eMMC + core hardware  |                                     |
| 2.2 | USB Ethernet module   |                                     |
| 3.1 | eth0 is onboard       |                                     |
| 3.2 | DHCP server on LAN    |                                     |
| 3.3 | NTP server on LAN     |                                     |
| 3.4 | LAN isolation         |                                     |
| 4.1 | WAN port access       |                                     |
| 4.2 | SSH-on-WAN toggle     |                                     |
| 5.1 | Update confirmation   |                                     |
| 6.1 | SSH key auth          |                                     |
| 6.2 | Serial root recovery  |                                     |
| 7.1 | RAUC status           |                                     |
| 7.2 | Bundle install        |                                     |
| 7.3 | Boot-count rollback   |                                     |
| 8.1 | Watchdog presence     | Passed: internal and external paths |
| 8.2 | Watchdog reboot       | Passed: internal and external paths |
| 8.3 | Watchdog rollback     | Deferred to RAUC OTA testing        |
| 8.4 | Watchdog soak         | Deferred to RAUC OTA testing        |
