# Hardware Test Plan

Physical verification of AtomixOS on Rock64 (RK3328). Covers the 18 remaining tasks that cannot be validated in
software alone.

## Prerequisites

- Rock64 v2 board with 16 GB eMMC
- USB-to-eMMC adapter (or eMMC module with SD adapter)
- USB ethernet adapter (for LAN port -- Rock64 has one onboard NIC)
- USB WiFi dongle (rtlwifi, ath9k_htc, or mt76 chipset)
- USB Bluetooth dongle
- Laptop or second device on the LAN switch for client-side verification
- Serial console cable (USB-to-TTY, 1500000 baud, ttyS2) -- highly recommended for U-Boot and early boot debugging
- Built image: `result-image/atomixos-25.11.img`
- Built RAUC bundle: `result-rauc-bundle/`

## Phase 1: Provisioning and First Boot

### Flash the image

```sh
# Option A: flashable image via dd
dd if=result-image/atomixos-25.11.img of=/dev/mmcblkN bs=4M status=progress

# Option B: full provisioning with credentials (requires Linux + root)
mise run provision:emmc /dev/mmcblk1 \
  result-image/uboot result-image/Image result-image/rk3328-rock64.dtb result-squashfs \
  --ssh-key ~/.ssh/id_ed25519.pub
```

### Task 8.8 -- Provisioning boots to multi-user.target

1. Insert eMMC into Rock64, remove SD card, connect serial console
2. Power on
3. **Verify U-Boot output on serial**: idbloader loads, u-boot.itb starts, boot.scr runs
4. Verify kernel boots: `Booting slot A (attempts left: 2)` on serial
5. Wait for login prompt or SSH access

```sh
# From the device (serial console or SSH)
systemctl is-system-running          # expect: running or degraded
systemctl list-units --failed        # note any failures
```

**Pass criteria**: Device reaches `multi-user.target`. `systemd-repart` creates `/persist` (f2fs) on first boot.
`first-boot.service` runs and creates `/persist/.completed_first_boot`.

### Task 16.1 -- Full provisioning end-to-end

Run all Phase 1-4 checks on a freshly provisioned device. This is the meta-task -- it passes when all other tasks pass.

---

## Phase 2: Kernel and Hardware Detection

### Task 2.4 -- Stripped kernel boots and detects hardware

```sh
# On the device
uname -r                             # expect: 6.19.x
cat /proc/cpuinfo                    # expect: AArch64 Cortex-A53
lsblk                                # expect: mmcblk1 with p1-p5 partitions
ip link show eth0                    # expect: onboard stmmac ethernet
ls /dev/watchdog*                    # expect: /dev/watchdog0 (dw_wdt)
dmesg | grep -i 'mmc\|emmc\|dwmmc'  # expect: eMMC detected
dmesg | grep -i 'stmmac\|ethernet'  # expect: ethernet driver loaded
dmesg | grep -i 'watchdog\|wdt'     # expect: dw_wdt driver loaded
dmesg | grep -i 'xhci\|usb'         # expect: USB host controller(s) detected
```

**Pass criteria**: All four subsystems (eMMC, ethernet, USB, watchdog) detected in dmesg with correct drivers.

### Task 2.5 -- WiFi/BT modules load on demand

1. Plug in USB WiFi dongle
2. Plug in USB Bluetooth dongle

```sh
lsusb                                # expect: WiFi and BT devices listed
lsmod | grep -E 'rtlwifi|ath9k|mt76|btusb'
ip link show                         # expect: wlan0 appears
dmesg | tail -20                     # expect: firmware loaded, interface registered
hciconfig                            # expect: Bluetooth HCI device (if btusb loaded)
```

**Pass criteria**: WiFi module loads and creates `wlan0`. Bluetooth module loads and creates HCI device.

---

## Phase 3: Network Configuration

### Task 5.6 -- Onboard NIC is always eth0

```sh
# With NO USB ethernet plugged in
ip link show eth0
cat /sys/class/net/eth0/device/uevent | grep DRIVER  # expect: stmmac

# Now plug in USB ethernet adapter
sleep 5
ip link show                         # expect: eth0 is still onboard, USB NIC is eth1 or ethN
cat /sys/class/net/eth0/device/uevent | grep DRIVER  # still stmmac
```

**Pass criteria**: `eth0` is always the onboard RK3328 GMAC (stmmac driver), regardless of USB devices.

### Task 5.7 -- Device identity via MAC address

```sh
cat /sys/class/net/eth0/address      # expect: consistent onboard MAC (starts with Rock64 OUI)
```

**Pass criteria**: MAC address is the factory-assigned onboard MAC, not a random or USB adapter MAC.

### Task 6.4 -- DHCP serves LAN clients

Connect a laptop to the LAN port (USB ethernet on the gateway, or onboard if you have a switch).

```sh
# On the LAN client laptop
sudo dhclient -v eth0                # or let NetworkManager handle it
ip addr show                         # expect: IP in 172.20.30.10-254
ip route show                        # expect: default via 172.20.30.1
```

**Pass criteria**: Client gets IP in 172.20.30.10-254 range via DHCP from dnsmasq.

### Task 6.5 -- NTP serves LAN clients

```sh
# On the LAN client laptop
ntpdate -q 172.20.30.1              # or: chronyc sources (if chrony installed)
# Alternative:
sntp 172.20.30.1
```

**Pass criteria**: NTP response received from 172.20.30.1 (chrony).

### Task 6.6 -- LAN isolation (no WAN access)

```sh
# On the LAN client laptop (connected to LAN port)
ping -c 3 8.8.8.8                   # expect: FAIL (no route or timeout)
ping -c 3 1.1.1.1                   # expect: FAIL
curl -s https://example.com          # expect: FAIL

# On the gateway device itself
cat /proc/sys/net/ipv4/ip_forward   # expect: 0
```

**Pass criteria**: LAN client cannot reach any WAN address. `ip_forward` is 0.

---

## Phase 4: Firewall Verification

### Task 7.7 -- Port-level firewall rules

From a device on the **WAN** side (or the gateway's WAN IP):

```sh
# From WAN
nmap -p 22,443,1194 <gateway-wan-ip>
# expect: 443 open (HTTPS/Traefik), 1194 open (OpenVPN), 22 filtered/closed

# Verify SSH blocked on WAN by default
ssh admin@<gateway-wan-ip>           # expect: connection refused/timeout
```

From a device on the **LAN** side:

```sh
# From LAN (172.20.30.x)
ssh admin@172.20.30.1                # expect: connection accepted (key or password)
nmap -p 22,67,123 172.20.30.1       # expect: all open
```

Test SSH-on-WAN toggle:

```sh
# On the gateway
touch /persist/config/ssh-wan-enabled
systemctl start ssh-wan-reload

# From WAN
ssh admin@<gateway-wan-ip>           # expect: NOW works

# Disable again
rm /persist/config/ssh-wan-enabled
systemctl start ssh-wan-reload

# From WAN
ssh admin@<gateway-wan-ip>           # expect: blocked again
```

Test no forwarding:

```sh
# From LAN client -- try to reach a WAN address through the gateway
traceroute 8.8.8.8                   # expect: no hops beyond gateway, timeout
```

**Pass criteria**: WAN allows only 443+1194 (and 22 when toggled). LAN allows 22+67+123. No forwarding.

---

## Phase 5: Containers and Services

### Task 3.3 -- Cockpit pod starts and is accessible via HTTPS

```sh
# On the gateway
systemctl status cockpit-ws          # expect: active (running)
podman ps                            # expect: cockpit-ws container running
curl -sk https://localhost:443       # expect: Cockpit login page (via Traefik)
```

From a LAN client browser: navigate to `https://172.20.30.1`. Expect Cockpit login page with container management.

**Pass criteria**: Cockpit pod running, HTTPS accessible via Traefik on port 443.

### Task 3.4 -- OpenVPN creates tun0

This requires a VPN server and a provisioned client config at `/persist/config/openvpn/client.conf`.

```sh
# Provision the VPN config
cat > /persist/config/openvpn/client.conf << 'EOF'
# Your OpenVPN client config here
EOF

systemctl start openvpn-recovery
ip link show tun0                    # expect: tun0 interface exists
ip addr show tun0                    # expect: VPN IP assigned
```

**Pass criteria**: `tun0` interface created with assigned VPN IP.

### Task 17.5 -- Cockpit SSH bridge with python3Minimal

```sh
# On the gateway
which python3                        # expect: path to python3Minimal
python3 --version                    # expect: 3.x (minimal)

# From a browser, log into Cockpit at https://172.20.30.1
# Use admin username + provisioned password
# Navigate to Terminal tab
# Verify you get a working root shell
```

**Pass criteria**: Cockpit pod SSHes to localhost, spawns Python bridge via python3Minimal, interactive terminal works.

### Task 16.4 -- Confirmation with health manifest and containers

This requires both cockpit-ws and traefik containers running:

```sh
# On the gateway -- verify health manifest
cat /persist/config/health-manifest.yaml
# expect: cockpit-ws and traefik entries

# Verify both containers are running
podman ps                            # expect: cockpit-ws AND traefik running

# Simulate an update confirmation cycle
# (after installing a RAUC bundle to slot B and rebooting into it)
systemctl status os-verification     # expect: ran and succeeded
journalctl -u os-verification       # expect: all checks passed, slot marked good
rauc status                          # expect: booted slot marked "good"
```

**Pass criteria**: `os-verification` reads the health manifest, waits for both containers, runs 60s sustained check,
and marks the slot good.

---

## Phase 6: Authentication

### Task 18.4 -- Provisioned credentials work

```sh
# SSH key auth (from your workstation, WAN or LAN)
ssh -i ~/.ssh/id_ed25519 admin@172.20.30.1    # expect: logged in, no password prompt

# Password auth via Cockpit (from browser)
# Navigate to https://172.20.30.1
# Login with admin + provisioned password       # expect: Cockpit dashboard
```

**Pass criteria**: SSH key auth works from LAN. Password auth works via Cockpit pod on localhost.

---

## Phase 7: RAUC Update Lifecycle

### Task 10.4 -- RAUC status on device

```sh
rauc status
# expect:
#   Compatible: rock64
#   Boot slot: boot.0 (booted, good)
#   Slots: boot.0 (/dev/mmcblk1p1), boot.1 (/dev/mmcblk1p2),
#          rootfs.0 (/dev/mmcblk1p3), rootfs.1 (/dev/mmcblk1p4)
```

**Pass criteria**: `rauc status` shows all 4 slots with correct device paths.

### Task 11.4 -- Bundle install on device

Copy the RAUC bundle to the device and install:

```sh
# From your workstation
scp result-rauc-bundle/*.raucb admin@172.20.30.1:/tmp/

# On the device
rauc install /tmp/*.raucb
# expect: boot.1 and rootfs.1 written, BOOT_ORDER updated to "B A"

rauc status                          # expect: slot B is "inactive, good"
```

Reboot and verify the device boots into slot B:

```sh
reboot
# After reboot:
rauc status                          # expect: booted from boot.1/rootfs.1
```

**Pass criteria**: Bundle installs to inactive slot pair, U-Boot env updated, device reboots into new slot.

### Task 9.4 -- Boot-count rollback after 3 failures

This is destructive -- it intentionally corrupts slot B to test rollback. Do this after completing task 11.4.

```sh
# Install bundle to slot B
rauc install /tmp/*.raucb

# Corrupt the rootfs on slot B so it can't boot
dd if=/dev/zero of=/dev/mmcblk1p4 bs=1M count=1

# Set U-Boot to try slot B
fw_setenv BOOT_ORDER "B A"
fw_setenv BOOT_B_LEFT 3
reboot
```

Watch on serial console:

```text
Boot 1: "Booting slot B (attempts left: 2)" → kernel panic (corrupted rootfs)
Boot 2: "Booting slot B (attempts left: 1)" → kernel panic
Boot 3: "Booting slot B (attempts left: 0)" → skips B
         "Booting slot A (attempts left: 2)" → boots successfully
```

**Pass criteria**: After 3 failed boots on slot B, U-Boot falls back to slot A. Device recovers.

---

## Phase 8: Watchdog on Real Hardware

### Tasks 12.2-12.4 (hardware confirmation)

These were verified in QEMU E2E tests with i6300esb. Confirm the real dw_wdt driver works the same:

```sh
ls /dev/watchdog*                    # expect: /dev/watchdog0
dmesg | grep -i wdt                  # expect: dw_wdt driver loaded
systemctl show -p RuntimeWatchdogUSec  # expect: 30s (production value)
cat /proc/sys/kernel/watchdog         # expect: 1

# To test a real watchdog reboot (CAUTION: this will hard-reboot the device):
# echo 1 > /proc/sysrq-trigger      # (Alt+SysRq+c equivalent -- triggers crash)
# Or simply: kill -STOP 1            # freeze PID 1 (systemd), watchdog should fire in 30s
```

**Pass criteria**: dw_wdt driver present, systemd kicking at 30s, device reboots within timeout when systemd is frozen.

---

## Task Checklist

Mark each task as you complete it. Update `openspec/changes/rock64-ab-image/tasks.md` with results.

| Task | Description | Result |
|---|---|---|
| 8.8 | Provisioning boots to multi-user.target | |
| 16.1 | Full provisioning E2E on hardware | |
| 2.4 | Kernel detects eMMC, ethernet, USB, watchdog | |
| 2.5 | WiFi/BT modules load with USB dongles | |
| 5.6 | Onboard NIC is always eth0 | |
| 5.7 | Device identity (onboard MAC) | |
| 6.4 | DHCP serves LAN clients | |
| 6.5 | NTP serves LAN clients | |
| 6.6 | LAN isolation (no WAN access) | |
| 7.7 | Firewall ports correct on all interfaces | |
| 3.3 | Cockpit pod HTTPS accessible | |
| 3.4 | OpenVPN creates tun0 | |
| 17.5 | Cockpit SSH bridge with python3Minimal | |
| 16.4 | Confirmation with manifest + containers | |
| 18.4 | Provisioned credentials work | |
| 10.4 | `rauc status` shows all 4 slots | |
| 11.4 | Bundle install to inactive slot | |
| 9.4 | Boot-count rollback after 3 failures | |
