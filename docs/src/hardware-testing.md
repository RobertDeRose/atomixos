# Hardware Testing

> Source: `HARDWARE-TEST-PLAN.md`

This chapter provides the physical verification plan for Rock64 hardware testing. These tests cannot be run in QEMU and
require a physical Rock64 board with eMMC, serial console, and network connectivity.

## Prerequisites

- Rock64 v2 board with 16 GB eMMC module
- USB-to-serial adapter connected to UART2 (1.5 Mbaud)
- USB Ethernet adapter (for eth1/LAN interface)
- USB WiFi dongle (for WiFi module testing)
- USB Bluetooth dongle (for BT module testing)
- Built disk image (`atomixos-25.11.img`)
- Built RAUC bundle (`rock64.raucb`)
- Network with DHCP and internet access (for WAN/eth0)
- A second device on the LAN subnet for client testing

## Phase 1: Provisioning & First Boot

### Test 1.1: Flash image and verify U-Boot output

```sh
# Flash the image
mise run flash /dev/disk4    # macOS
# or
sudo dd if=atomixos-25.11.img of=/dev/mmcblk0 bs=4M status=progress

# Connect serial console
screen /dev/tty.usbserial-DM02496T 1500000
```

**Pass criteria**:

- U-Boot banner appears on serial console
- `bootflow scan` finds `boot.scr` on boot-a
- Kernel loads and prints boot messages
- System reaches `multi-user.target`
- `first-boot.service` runs and marks slot as good

### Test 1.2: Verify first-boot service

```sh
systemctl status first-boot
cat /data/.completed_first_boot
rauc status
```

**Pass criteria**:

- `first-boot.service` completed successfully
- Sentinel file exists at `/data/.completed_first_boot`
- RAUC shows the booted slot as "good"

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

### Test 2.2: WiFi and Bluetooth modules

```sh
modprobe mt7601u    # or the appropriate driver for your dongle
ip link show
modprobe btusb
dmesg | grep -i bluetooth
```

**Pass criteria**:

- WiFi module loads without errors
- A wireless interface appears in `ip link`
- Bluetooth module loads and hci device appears in `dmesg`

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

### Test 4.1: WAN port access

From an external machine (or the WAN side):

```sh
# These should succeed (connection accepted or TLS handshake)
curl -k https://<wan-ip>:443
nc -uz <wan-ip> 1194

# This should fail (connection refused/timeout)
ssh <wan-ip>
```

**Pass criteria**:

- HTTPS (443) is reachable
- OpenVPN (1194) is reachable
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

### Test 8.1: Hardware watchdog presence

```sh
dmesg | grep -i watchdog
ls /dev/watchdog*
```

**Pass criteria**:

- `dw_wdt` driver is loaded
- `/dev/watchdog` device exists

### Test 8.2: Watchdog-triggered reboot

> **Warning**: This test intentionally hangs systemd. Use only on test devices.

```sh
# Freeze PID 1 (systemd) to stop watchdog kicks
kill -STOP 1

# Wait 30+ seconds -- the hardware watchdog should force a reboot
```

**Pass criteria**:

- Device reboots within ~30 seconds of the SIGSTOP
- Serial console shows watchdog reset
- U-Boot boot-count is decremented for the current slot

## Task Checklist

| #   | Test                     | Status |
|-----|--------------------------|--------|
| 1.1 | Flash + U-Boot output    |        |
| 1.2 | First-boot service       |        |
| 2.1 | eMMC + core hardware     |        |
| 2.2 | WiFi + Bluetooth modules |        |
| 3.1 | eth0 is onboard          |        |
| 3.2 | DHCP server on LAN       |        |
| 3.3 | NTP server on LAN        |        |
| 3.4 | LAN isolation            |        |
| 4.1 | WAN port access          |        |
| 4.2 | SSH-on-WAN toggle        |        |
| 5.1 | Update confirmation      |        |
| 6.1 | SSH key auth             |        |
| 6.2 | Serial root recovery     |        |
| 7.1 | RAUC status              |        |
| 7.2 | Bundle install           |        |
| 7.3 | Boot-count rollback      |        |
| 8.1 | Watchdog presence        |        |
| 8.2 | Watchdog reboot          |        |
