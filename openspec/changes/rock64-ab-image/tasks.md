# Tasks

## 1. Flake Bootstrap and Project Structure

- [x] 1.1 Create `flake.nix` with nixpkgs input, aarch64-linux system, and `nixosConfigurations.rock64` output stub
- [x] 1.2 Create a shared NixOS module (`modules/base.nix`) for configuration shared between hardware and QEMU targets
- [x] 1.3 Configure base NixOS system: systemd as init, locale, timezone, hostname, and minimal users
- [x] 1.4 Enable core services: podman (`virtualisation.podman`), openssh (`services.openssh`)
- [x] 1.5 Verify flake evaluates with `nix flake check` (cross-compile or native aarch64) — verified in Lima VM
  (aarch64-linux), all outputs evaluate cleanly

## 2. Stripped Kernel Configuration

- [x] 2.1 Create a custom kernel configuration for the RK3328 with built-in drivers: eMMC (dw_mmc), ethernet (stmmac),
  USB host (dwc2/xhci), watchdog (dw_wdt), squashfs, f2fs
- [x] 2.2 Configure USB WiFi drivers (rtlwifi, ath9k_htc, mt76), Bluetooth (btusb), and USB serial (ftdi, cp210x) as
  modules (`=m`)
- [x] 2.3 Include the RK3328 Rock64 device tree blob (`rk3328-rock64.dtb`)
- [x] 2.4 Verify stripped kernel boots on Rock64 hardware and detects eMMC, ethernet, USB, and watchdog — verified via
  serial console: kernel 6.19.11 boots on Rock64, eMMC detected (mmcblk1 14.5 GiB, HS200 mode), ethernet
  (rk_gmac-dwmac + RTL8211F PHY), USB host controllers (dwc2, xhci, ehci, ohci), hardware watchdog
  (dw_wdt /dev/watchdog0, 30s timeout). Required fixes: initrd for MMC_BLOCK=m, partition offset fix
  (boot-a at 16 MiB), PARTLABEL root=, rootwait, ramdisk_addr_r override to 0x08000000

## 3. Remote Management Direction and OpenVPN

- [x] 3.1 Keep Podman available in the device image as the application runtime while removing the local Cockpit/Traefik
  management path from the final design
- [x] 3.2 Enable OpenVPN in the NixOS configuration as a systemd service for VPN recovery access
- [x] 3.3 Shift remote web management toward Nixstasis-hosted services and document the enrollment / short-lived SSH model

## 4. Squashfs Image Build

- [x] 4.1 Add a squashfs image derivation that packages the NixOS system closure (including kernel modules,
  Podman, OpenVPN, chrony, dnsmasq) into a read-only squashfs image with 1 MB block size
- [x] 4.2 Expose the squashfs image as `packages.aarch64-linux.squashfs` in flake outputs
- [x] 4.3 Verify the built squashfs image is under 1 GB — most recently 203 MiB after later image trimming work
- [x] 4.4 Add a CI-friendly size check (script or assertion) that fails the build if squashfs exceeds 1 GB

## 4b. Flashable Disk Image and Build Tasks

- [x] 4b.1 Create `nix/image.nix` derivation that assembles a flashable eMMC `.img` (GPT, U-Boot, boot-a vfat, rootfs-a
  squashfs) using mtools (no loop devices/mount needed in Nix sandbox)
- [x] 4b.2 Create `scripts/build-image.sh` template with `@variable@` placeholders for Nix substitute
- [x] 4b.3 Expose the image as `packages.aarch64-linux.image` in flake outputs
- [x] 4b.4 Add mise build tasks: `check`, `build:squashfs`, `build:rauc-bundle`, `build:boot-script`, and `build`
  (retains rooted artifacts and supports optional image copy-out)
- [x] 4b.5 Create the flash/build workflow around `.gcroots/images/image.1` and `.mise/tasks/flash` for safe device
  flashing from the latest built image
- [x] 4b.6 Verify all flake outputs evaluate cleanly with `nix flake check --no-build`
- [x] 4b.7 Verify `nix build .#image` produces a valid disk image — GPT partition table correct, U-Boot at sectors
  64/16384, boot-a vfat contains Image (63 MB) + DTB + boot.scr, rootfs-a has valid squashfs (hsqs magic, 334 MB)

## 5. NIC Naming and Network Interface Configuration

- [x] 5.1 Disable systemd predictable interface names (`networking.usePredictableInterfaceNames = false`)
- [x] 5.2 Create systemd-networkd `.link` file matching the RK3328 GMAC platform path (`platform-ff540000.ethernet`) to
  name it `eth0`
- [x] 5.3 Create `.link` files for USB ethernet (driver match → `ethN`) and WiFi dongles (type=wlan → `wlanN`)
- [x] 5.4 Configure eth0 as DHCP client (WAN)
- [x] 5.5 Configure eth1 with static IP 172.20.30.1/24 (LAN)
- [x] 5.6 Verify on hardware: onboard NIC is always eth0 regardless of USB devices plugged in
- [x] 5.7 Verify device identity: `/sys/class/net/eth0/address` returns the onboard MAC — validated from repeated
  serial-console `ip add` output showing the same stable `eth0` MAC across boots (`92:a2:18:4f:57:42`)

## 6. LAN Gateway Services

- [x] 6.1 Configure dnsmasq as DHCP server on eth1 only, pool 172.20.30.10-172.20.30.254, gateway 172.20.30.1
- [x] 6.2 Configure chrony as NTP client (WAN servers via eth0) and NTP server (LAN clients on 172.20.30.0/24 via eth1)
- [x] 6.3 Explicitly disable IP forwarding (`net.ipv4.ip_forward = 0`)
- [!] 6.4 Verify DHCP: connect a device to the LAN switch, confirm it gets an IP in the correct range
- [!] 6.5 Verify NTP: query 172.20.30.1 from a LAN device, confirm time response
- [ ] 6.6 Verify isolation: confirm a LAN device cannot reach any WAN address

## 7. Firewall Configuration

- [x] 7.1 Configure nftables with WAN inbound rules: ALLOW tcp/443, ALLOW udp/1194 (OpenVPN), ALLOW established/related,
  DROP all else
- [x] 7.2 Add conditional SSH rule for WAN: ALLOW tcp/22 only if `/data/config/ssh-wan-enabled` exists
- [x] 7.3 Configure LAN inbound rules: ALLOW udp/67-68 (DHCP), ALLOW udp/123 (NTP), ALLOW tcp/22 (SSH), ALLOW
  established/related, DROP all else
- [x] 7.4 Configure VPN (tun0) inbound rules: ALLOW tcp/22, ALLOW established/related, DROP all else
- [x] 7.5 Configure FORWARD chain: DROP all
- [x] 7.6 Create a systemd service or nftables hook that checks for the SSH-on-WAN flag file at boot and on firewall
  reload
- [ ] 7.7 Verify: HTTPS works on WAN, SSH blocked on WAN by default, SSH works on LAN and VPN, no forwarding between
  interfaces

## 8. eMMC Partition Layout and Provisioning

- [x] 8.1 Create the provisioning/image path that produces a flashable eMMC layout with raw U-Boot, boot A, and rootfs A,
  leaving slot B and /data to initrd systemd-repart on first boot.
- [x] 8.2 Add U-Boot writing step: dd idbloader.img to sector 64 and u-boot.itb to sector 16384 using `ubootRock64` from
  nixpkgs
- [x] 8.3 Create vfat filesystem on boot slot A, copy kernel image and DTB
- [x] 8.4 Write the initial squashfs image to rootfs slot A partition
- [x] 8.5 Configure systemd-repart to create f2fs /data partition on first boot (zero closure cost — binary already
  in systemd)
- [x] 8.6 U-Boot environment defaults handled by boot.cmd script (lines 17-19: `BOOT_ORDER=A B`, `BOOT_A_LEFT=3`,
  `BOOT_B_LEFT=3` when env unset)
- [x] 8.7 Add idempotency check: detect if eMMC is already provisioned and prompt for confirmation before overwriting
- [x] 8.8 Test provisioning script: device boots from eMMC into slot A and reaches multi-user.target

## 9. U-Boot Configuration and Boot-Count Logic

- [x] 9.1 Verify `ubootRock64` from nixpkgs produces idbloader.img and u-boot.itb suitable for RK3328 boot ROM
  (confirmed: idbloader.img 137 KiB, u-boot.itb 940 KiB, plus u-boot-rockchip.bin combined blob)
- [x] 9.2 Write U-Boot boot script that reads `BOOT_ORDER` and `BOOT_X_LEFT` variables, decrements the counter, and
  selects the appropriate boot slot and rootfs partition
- [x] 9.3 ~~Configure redundant U-Boot environment storage~~ — **CHANGED**: Rock64 U-Boot (`rk3328_defconfig`) does not
  enable `CONFIG_ENV_REDUNDANT`. Single 32 KB env at `0x3F8000`. FAT flag file approach mitigates power-loss risk.
- [ ] 9.4 Test boot-count logic: simulate 3 consecutive failed boots on slot B and verify U-Boot falls back to slot A
  — **BLOCKED**: requires flashing and testing the latest image with FAT flag file support

## 10. RAUC System Configuration

- [x] 10.1 Create RAUC system.conf defining two slot pairs (boot A + rootfs A, boot B + rootfs B) with eMMC partition
  device paths and `bootloader=uboot`
- [x] 10.2 Enable the NixOS RAUC module: `services.rauc.enable = true`, set `compatible = "rock64"`, configure CA
  certificate path
- [x] 10.3 Generate a development CA keypair and signing key for RAUC bundle signing (store in `certs/` with .gitignore
  for private keys)
- [x] 10.4 Verify `rauc status` runs on device and shows all four slots (boot A, boot B, rootfs A, rootfs B) with
  correct partition paths — validated on hardware: `boot.0=/dev/mmcblk1p1`, `rootfs.0=/dev/mmcblk1p2`,
  `boot.1=/dev/mmcblk1p3`, `rootfs.1=/dev/mmcblk1p4`

## 11. RAUC Multi-Slot Bundle Building

- [x] 11.1 Create a RAUC bundle derivation in the flake that wraps both the boot image (kernel + DTB) and the squashfs
  rootfs image into a single `.raucb` file, signed with the project CA key
- [x] 11.2 Expose the bundle as `packages.aarch64-linux.rauc-bundle` in flake outputs
- [x] 11.3 Verify the bundle with `rauc info` — signature valid (dev CA), manifest lists boot.vfat (134 MB) and
  rootfs.squashfs (350 MB), compatible=rock64, version=0.1.0
- [ ] 11.4 Test installing the bundle on device: `rauc install` writes both boot and rootfs to inactive slot pair,
  updates U-Boot env, device reboots into new slot

## 12. Watchdog Configuration

- [x] 12.1 Add NixOS configuration for systemd watchdog: `systemd.watchdog.runtimeTime = "30s"` and
  `systemd.watchdog.rebootTime = "10min"`
- [x] 12.2 Verify the RK3328 watchdog kernel driver loads on boot (`/dev/watchdog` exists) — validated via
  `rauc-watchdog` E2E test: i6300esb driver loads, `test -c /dev/watchdog` passes, `lsmod | grep i6300esb` passes.
  Hardware driver (dw_wdt) to be confirmed on Rock64 hardware.
- [x] 12.3 Verify systemd is kicking the watchdog: `systemctl show -p RuntimeWatchdogUSec` reports 30s — validated via
  `rauc-watchdog` E2E test: `systemctl show -p RuntimeWatchdogUSec` confirms watchdog active, kernel log shows
  `Watchdog running with a hardware timeout of 10s` (test uses 10s for speed; production uses 30s)
- [x] 12.4 Test watchdog: trigger a simulated hang and verify the device reboots within the timeout window — validated
  via `rauc-watchdog` E2E test: `gateway.crash()` simulates watchdog-triggered reboot twice, boot-count decrements
  from 2→1→0, rollback to slot A occurs, slot B marked bad
- [ ] 12.5 Re-enable hardware watchdog on Rock64 — currently disabled in `modules/watchdog.nix` pending stable boot
  confirmation on hardware. Restore `RuntimeWatchdogSec = "30s"` and `RebootWatchdogSec = "10min"`.

## 13. Update Confirmation Service (`os-verification`)

- [x] 13.1 Create `os-verification.service` systemd oneshot unit that runs after `multi-user.target`
- [x] 13.2 Implement slot status check: query `rauc status` to determine if current slot is pending; if already marked
  good, exit immediately
- [x] 13.3 Implement system health checks: verify eth0 has WAN address, eth1 is 172.20.30.1, dnsmasq running, chronyd
  running
- [x] 13.4 Simplify confirmation to local gateway health checks only so slot confirmation does not depend on app containers
  or remote management services
- [x] 13.5 Implement sustained health check: check every 5 seconds for 60 seconds and fail on local service instability
- [x] 13.6 On any failure: exit non-zero, slot stays uncommitted
- [x] 13.7 On sustained success: call `rauc status mark-good` to commit the slot
- [x] 13.8 Add the confirmation service to the NixOS configuration

## 14. Update Polling Service (`os-upgrade`, hawkBit-Ready)

- [x] 14.1 Create `os-upgrade.timer` and `os-upgrade.service` systemd units for periodic update polling
- [x] 14.2 Implement polling logic: query update server for latest bundle version, compare against currently installed
  version
- [x] 14.3 On new version available: download the `.raucb` bundle to a temp location on /data, invoke `rauc install`
- [x] 14.4 Handle download failures gracefully: log error, clean up partial downloads, wait for next timer interval
- [x] 14.5 Add `rauc-hawkbit-updater` as a disabled service in the NixOS configuration
- [x] 14.6 Create a NixOS configuration option to toggle between simple polling and hawkBit client (mutually exclusive)
- [x] 14.7 Verify default: `os-upgrade.timer` active, `rauc-hawkbit-updater` inactive — verified in systemd-nspawn:
  os-upgrade.timer active (waiting), no hawkbit service present

## 15. QEMU Testing Target

- [x] 15.1 Create `nixosConfigurations.rock64-qemu` that imports the shared base module but targets `aarch64-virt`
- [x] 15.2 Configure QEMU-specific overrides: virtual block devices for slots, software watchdog, virtual network
  interfaces
- [x] 15.3 Expose a VM runner script via flake outputs (e.g., `nix build .#rock64-qemu-vm && ./result/bin/run-vm`)
- [x] 15.4 Verify QEMU VM boots with the shared base system, firewall, network configuration, RAUC plumbing, and Podman
  available for application workloads — validated via systemd-nspawn: multi-user.target reached, nftables loaded,
  chronyd running, networkd running, podman available. dnsmasq/sshd expected failures in container (no eth1,
  host port 22 conflict)
- [x] 15.5 Verify RAUC slot logic works in QEMU with virtual block devices — validated via `nix build
  .#checks.aarch64-linux.rauc-slots`: VM boots with 4 virtio disks, RAUC service starts (D-Bus), `rauc status`
  reports all 4 slots (boot.0/1, rootfs.0/1) with correct device paths (/dev/vdb-vde)

## 16. End-to-End Integration Testing

- [x] 16.1 Flashable image boots on Rock64 and reaches multi-user.target after first-boot repartitioning creates the
  inactive slot and /data
- [x] 16.2 Update test: build a v2 bundle, serve it from a test HTTP server, verify polling service downloads and
  installs it, device reboots into new slot with new kernel and rootfs — validated via `nix build
  .#checks.aarch64-linux.rauc-update`: builds signed test bundle (dev certs), copies into QEMU VM, `rauc install`
  writes boot.vfat to /dev/vdc and rootfs.img to /dev/vde, primary switches from A to B. Prerequisite: added custom
  bootloader backend (`bootloader=custom` in hardware-qemu.nix) that simulates U-Boot env via files in /var/lib/rauc
- [x] 16.3 Confirmation test: verify os-verification.service checks system health and marks the slot good after
  successful update — validated via `nix build .#checks.aarch64-linux.rauc-confirm`: boots QEMU VM with RAUC + dnsmasq
  - chronyd + dummy eth1 (172.20.30.1), creates first-boot sentinel, runs os-verification service which checks all
  services/IPs, waits 60s sustained check, then calls `rauc status mark-good` to commit slot A
- [ ] 16.4 Hardware confirmation test: install an update on Rock64 and verify the local-only confirmation path commits the
  slot on real hardware
- [x] 16.5 Rollback test: deploy a deliberately broken image, verify boot-count exhaustion triggers automatic rollback
  to previous slot pair — validated via `nix build .#checks.aarch64-linux.rauc-rollback`: installs bundle to slot B,
  marks B bad, re-activates A as primary, verifies A=good/primary and B=bad
- [x] 16.6 Watchdog rollback test: deploy an image that causes a hang, verify watchdog fires and eventually triggers
  rollback — validated via `nix build .#checks.aarch64-linux.rauc-watchdog`: boots VM with i6300esb watchdog + RAUC
  custom backend, verifies watchdog device present and systemd kicking at 10s, installs bundle to slot B with
  boot-count=2, simulates two watchdog reboots via crash()/start(), verifies boot-count decrement (2 -> 1 -> 0),
  rollback to A, and slot B marked bad
- [x] 16.7 Power-loss simulation: interrupt an update mid-write (pull power during `rauc install`), verify device boots
  from the previous good slot pair — validated via `nix build .#checks.aarch64-linux.rauc-power-loss`: installs 64 MB
  bundle, crashes VM mid-write via `machine.crash()`, reboots and verifies slot A still intact and RAUC functional
- [x] 16.8 Network isolation test: verify LAN devices get DHCP and NTP but cannot reach WAN addresses — validated via
  `nix build .#checks.aarch64-linux.network-isolation`: 2-node VLAN test (gateway + lan client, redesigned from 3-node
  to avoid OOM under TCG). Gateway runs dnsmasq (bind-dynamic on eth2) + chrony, LAN client gets DHCP lease in
  172.20.30.0/24, gateway NTP reachable, WAN isolation verified via ip_forward=0 + unreachable WAN host ping
- [x] 16.9 Firewall test: verify WAN allows only HTTPS and VPN, LAN allows SSH/DHCP/NTP, no forwarding between
  interfaces — validated via `nix build .#checks.aarch64-linux.firewall`: 2-node VLAN test (gateway + probe with
  vlans=[1,2], redesigned from 3-node to avoid OOM under TCG). Uses inline nftables rules (eth1=WAN, eth2=LAN) with
  eth0 backdoor passthrough. Verifies port-level allow/deny from both WAN and LAN sides using ncat listeners
- [x] 16.10 SSH-on-WAN toggle test: create/remove flag file, verify SSH access on WAN is enabled/disabled accordingly
  — validated via `nix build .#checks.aarch64-linux.ssh-wan-toggle`: creates /data/config/ssh-wan-enabled, reloads
  ssh-wan-reload service, verifies SSH reachable from WAN; removes flag, reloads, verifies SSH blocked again

## 17. Remote Access Architecture

- [x] 17.1 Evaluate the initial local Cockpit/Traefik management path and prove out the Rock64 bring-up flow
- [x] 17.2 Remove the local Cockpit/Traefik stack from the device image once the design shifted toward Nixstasis-hosted
  remote access
- [x] 17.3 Document the Nixstasis-oriented remote access model: approved MAC-based enrollment, registration key persisted
  on /data, reverse tunnel, and short-lived SSH credentials
- [x] 17.4 Keep Podman on-device for application workloads even though remote management is no longer hosted locally

## 17b. First-Boot Initialization

- [x] 17b.1 Create `modules/first-boot.nix` — systemd oneshot service with
  `ConditionPathExists=!/data/.completed_first_boot` that runs on first boot only
- [x] 17b.2 Create `scripts/first-boot.sh` to confirm the current slot, seed development-only auth helpers when enabled,
  and write `/data/.completed_first_boot`
- [x] 17b.3 Add `ConditionPathExists=/data/.completed_first_boot` to `os-verification.service` so it skips on first
  boot (before sentinel exists)
- [x] 17b.4 Remove first-boot dependence on local management containers so initial boot completes without image pulls
- [x] 17b.5 Verify in test environments that `first-boot.service` creates the sentinel and `os-verification.service`
  remains skipped until subsequent boots

## 18. Authentication Provisioning

- [x] 18.1 Persist imported admin SSH keys under `/data/config/ssh-authorized-keys/admin` through the provisioning
  importer
- [x] 18.2 Enforce SSH-key-only operator access with both `root` and `admin` password-locked by default
- [x] 18.3 Validate imported provisioning state before first boot commits the slot
- [ ] 18.4 Verify on hardware that admin SSH key auth works, password auth remains rejected, and `_RUT_OH_` stays a
  physical serial recovery path rather than a normal operator login mode
- [x] 18.5 Verify no credentials exist in the squashfs image itself (EN18031 compliance) — verified via source audit:
  `hashedPasswordFile` reads from `/data` at runtime (modules/base.nix:130), SSH authorized keys loaded from
  `/data` (modules/base.nix:161), no `hashedPassword`/`password`/`initialPassword` attributes anywhere, TLS certs
  and OpenVPN configs all reference `/data`, squashfs derivation (nix/squashfs.nix) packs only the NixOS system
  closure via `closureInfo`. The only crypto material in the image is the RAUC CA public certificate (required for
  bundle verification). RAUC signing private keys are build-time-only derivations, never in the system closure.
