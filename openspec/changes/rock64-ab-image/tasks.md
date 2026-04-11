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
- [ ] 2.4 Verify stripped kernel boots on Rock64 hardware and detects eMMC, ethernet, USB, and watchdog
- [ ] 2.5 Verify WiFi/BT modules load on demand when USB dongles are plugged in

## 3. Cockpit Pod and OpenVPN in Rootfs

- [x] 3.1 Configure Cockpit to run as a pod (`quay.io/cockpit/ws`) with `python3Minimal` in the rootfs for the SSH-based
  Python bridge
- [x] 3.2 Enable OpenVPN in the NixOS configuration as a systemd service for VPN recovery access
- [ ] 3.3 Verify Cockpit pod starts on boot, is accessible via HTTPS, and shows podman container management
- [ ] 3.4 Verify OpenVPN creates tun0 interface when a VPN connection is established

## 4. Squashfs Image Build

- [x] 4.1 Add a squashfs image derivation that packages the NixOS system closure (including kernel modules,
  python3Minimal, OpenVPN, chrony, dnsmasq) into a read-only squashfs image with 1 MB block size
- [x] 4.2 Expose the squashfs image as `packages.aarch64-linux.squashfs` in flake outputs
- [x] 4.3 Verify the built squashfs image is under 1 GB — 334 MB (zstd-19, 30.47% compression ratio)
- [x] 4.4 Add a CI-friendly size check (script or assertion) that fails the build if squashfs exceeds 1 GB

## 4b. Flashable Disk Image and Build Tasks

- [x] 4b.1 Create `nix/image.nix` derivation that assembles a flashable eMMC `.img` (GPT, U-Boot, boot-a vfat, rootfs-a
  squashfs) using mtools (no loop devices/mount needed in Nix sandbox)
- [x] 4b.2 Create `scripts/build-image.sh` template with `@variable@` placeholders for Nix substitute
- [x] 4b.3 Expose the image as `packages.aarch64-linux.image` in flake outputs
- [x] 4b.4 Add mise TOML build tasks: `check`, `build:squashfs`, `build:rauc-bundle`, `build:boot-script`,
  `build:image`, `build` (depends on all)
- [x] 4b.5 Create `.mise/tasks/provision/image` file task to copy built `.img` to user-specified output path
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
- [ ] 5.6 Verify on hardware: onboard NIC is always eth0 regardless of USB devices plugged in
- [ ] 5.7 Verify device identity: `/sys/class/net/eth0/address` returns the onboard MAC

## 6. LAN Gateway Services

- [x] 6.1 Configure dnsmasq as DHCP server on eth1 only, pool 172.20.30.10-172.20.30.254, gateway 172.20.30.1
- [x] 6.2 Configure chrony as NTP client (WAN servers via eth0) and NTP server (LAN clients on 172.20.30.0/24 via eth1)
- [x] 6.3 Explicitly disable IP forwarding (`net.ipv4.ip_forward = 0`)
- [ ] 6.4 Verify DHCP: connect a device to the LAN switch, confirm it gets an IP in the correct range
- [ ] 6.5 Verify NTP: query 172.20.30.1 from a LAN device, confirm time response
- [ ] 6.6 Verify isolation: confirm a LAN device cannot reach any WAN address

## 7. Firewall Configuration

- [x] 7.1 Configure nftables with WAN inbound rules: ALLOW tcp/443, ALLOW udp/1194 (OpenVPN), ALLOW established/related,
  DROP all else
- [x] 7.2 Add conditional SSH rule for WAN: ALLOW tcp/22 only if `/persist/config/ssh-wan-enabled` exists
- [x] 7.3 Configure LAN inbound rules: ALLOW udp/67-68 (DHCP), ALLOW udp/123 (NTP), ALLOW tcp/22 (SSH), ALLOW
  established/related, DROP all else
- [x] 7.4 Configure VPN (tun0) inbound rules: ALLOW tcp/22, ALLOW established/related, DROP all else
- [x] 7.5 Configure FORWARD chain: DROP all
- [x] 7.6 Create a systemd service or nftables hook that checks for the SSH-on-WAN flag file at boot and on firewall
  reload
- [ ] 7.7 Verify: HTTPS works on WAN, SSH blocked on WAN by default, SSH works on LAN and VPN, no forwarding between
  interfaces

## 8. eMMC Partition Layout and Provisioning

- [x] 8.1 Create the provisioning task (`.mise/tasks/provision/emmc`) that partitions the eMMC: raw U-Boot region (4
  MB), boot A (vfat, 128 MB), boot B (vfat, 128 MB), rootfs A (1 GB), rootfs B (1 GB). Persist partition deferred to
  systemd-repart on first boot.
- [x] 8.2 Add U-Boot writing step: dd idbloader.img to sector 64 and u-boot.itb to sector 16384 using `ubootRock64` from
  nixpkgs
- [x] 8.3 Create vfat filesystem on boot slot A, copy kernel image and DTB
- [x] 8.4 Write the initial squashfs image to rootfs slot A partition
- [x] 8.5 Configure systemd-repart to create f2fs /persist partition on first boot (zero closure cost — binary already
  in systemd)
- [x] 8.6 U-Boot environment defaults handled by boot.cmd script (lines 17-19: `BOOT_ORDER=A B`, `BOOT_A_LEFT=3`,
  `BOOT_B_LEFT=3` when env unset)
- [x] 8.7 Add idempotency check: detect if eMMC is already provisioned and prompt for confirmation before overwriting
- [ ] 8.8 Test provisioning script: device boots from eMMC into slot A and reaches multi-user.target

## 9. U-Boot Configuration and Boot-Count Logic

- [x] 9.1 Verify `ubootRock64` from nixpkgs produces idbloader.img and u-boot.itb suitable for RK3328 boot ROM
  (confirmed: idbloader.img 137 KiB, u-boot.itb 940 KiB, plus u-boot-rockchip.bin combined blob)
- [x] 9.2 Write U-Boot boot script that reads `BOOT_ORDER` and `BOOT_X_LEFT` variables, decrements the counter, and
  selects the appropriate boot slot and rootfs partition
- [x] 9.3 Configure redundant U-Boot environment storage (two copies at different eMMC offsets)
- [ ] 9.4 Test boot-count logic: simulate 3 consecutive failed boots on slot B and verify U-Boot falls back to slot A

## 10. RAUC System Configuration

- [x] 10.1 Create RAUC system.conf defining two slot pairs (boot A + rootfs A, boot B + rootfs B) with eMMC partition
  device paths and `bootloader=uboot`
- [x] 10.2 Enable the NixOS RAUC module: `services.rauc.enable = true`, set `compatible = "rock64"`, configure CA
  certificate path
- [x] 10.3 Generate a development CA keypair and signing key for RAUC bundle signing (store in `certs/` with .gitignore
  for private keys)
- [ ] 10.4 Verify `rauc status` runs on device and shows all four slots (boot A, boot B, rootfs A, rootfs B) with
  correct partition paths

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
- [ ] 12.2 Verify the RK3328 watchdog kernel driver loads on boot (`/dev/watchdog` exists)
- [ ] 12.3 Verify systemd is kicking the watchdog: `systemctl show -p RuntimeWatchdogUSec` reports 30s
- [ ] 12.4 Test watchdog: trigger a simulated hang and verify the device reboots within the timeout window

## 13. Update Confirmation Service (`os-verification`)

- [x] 13.1 Create `os-verification.service` systemd oneshot unit that runs after `multi-user.target`
- [x] 13.2 Implement slot status check: query `rauc status` to determine if current slot is pending; if already marked
  good, exit immediately
- [x] 13.3 Implement system health checks: verify eth0 has WAN address, eth1 is 172.20.30.1, dnsmasq running, chronyd
  running
- [x] 13.4 Implement manifest loading: read `/persist/config/health-manifest.yaml` if it exists; if missing, skip
  container checks
- [x] 13.5 Implement container health checks: wait up to 5 minutes for all manifest containers to reach "running" state,
  checking every 10 seconds
- [x] 13.6 Implement sustained health check: check every 5 seconds for 60 seconds; detect container restarts or stops;
  fail if any instability detected
- [x] 13.7 On sustained success: call `rauc status mark-good` to commit the slot
- [x] 13.8 On any failure: exit non-zero, slot stays uncommitted
- [x] 13.9 Add the confirmation service to the NixOS configuration

## 14. Update Polling Service (`os-upgrade`, hawkBit-Ready)

- [x] 14.1 Create `os-upgrade.timer` and `os-upgrade.service` systemd units for periodic update polling
- [x] 14.2 Implement polling logic: query update server for latest bundle version, compare against currently installed
  version
- [x] 14.3 On new version available: download the `.raucb` bundle to a temp location on /persist, invoke `rauc install`
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
- [x] 15.4 Verify QEMU VM boots with systemd, podman, Cockpit, firewall, and network configuration functional —
  validated via systemd-nspawn: multi-user.target reached, nftables loaded, chronyd running, networkd running,
  podman socket active. dnsmasq/sshd expected failures in container (no eth1, host port 22 conflict)
- [ ] 15.5 Verify RAUC slot logic works in QEMU with virtual block devices

## 16. End-to-End Integration Testing

- [ ] 16.1 Full provisioning test: run provisioning script on Rock64, verify first boot to multi-user.target with all
  services (Cockpit pod, DHCP, NTP, firewall)
- [ ] 16.2 Update test: build a v2 bundle, serve it from a test HTTP server, verify polling service downloads and
  installs it, device reboots into new slot with new kernel and rootfs
- [ ] 16.3 Confirmation test: verify os-verification.service checks system health and marks the slot good after
  successful update
- [ ] 16.4 Confirmation with manifest: place a health manifest on /persist, deploy containers, verify confirmation
  checks containers and commits only when all are healthy
- [ ] 16.5 Rollback test: deploy a deliberately broken image, verify boot-count exhaustion triggers automatic rollback
  to previous slot pair
- [ ] 16.6 Watchdog rollback test: deploy an image that causes a hang, verify watchdog fires and eventually triggers
  rollback
- [ ] 16.7 Power-loss simulation: interrupt an update mid-write (pull power during `rauc install`), verify device boots
  from the previous good slot pair
- [ ] 16.8 Network isolation test: verify LAN devices get DHCP and NTP but cannot reach WAN addresses
- [ ] 16.9 Firewall test: verify WAN allows only HTTPS and VPN, LAN allows SSH/DHCP/NTP, no forwarding between
  interfaces
- [ ] 16.10 SSH-on-WAN toggle test: create/remove flag file, verify SSH access on WAN is enabled/disabled accordingly

## 17. Cockpit Pod Configuration

- [x] 17.1 Create a Quadlet or systemd unit for the Cockpit pod (`quay.io/cockpit/ws`) that SSHes into the host on
  localhost — raw systemd service using podman run, host networking, zero closure cost
- [x] 17.2 Configure cockpit.conf for the pod (listen address, certificate paths, allowed origins) — COCKPIT_WS_ARGS env
  sets --address=127.0.0.1 --port=9090 --no-tls; config mounted from /persist/config/cockpit
- [x] 17.3 Integrate Cockpit pod with Traefik reverse proxy (routing, TLS termination) — traefik.nix raw systemd service
  (same pattern as cockpit.nix: podman run docker.io/library/traefik:v3, host networking, zero closure cost). TLS
  from /persist/config/traefik/certs/, reverse-proxies to Cockpit on 127.0.0.1:9090, HTTP→HTTPS redirect.
  Provisioning writes config + self-signed cert.
- [x] 17.4 Evaluate Cockpit OAuth/bearer token flow for OIDC pass-through from Traefik — Cockpit supports [bearer] auth
  scheme but still needs SSH credentials for the bridge. Recommended: "OIDC gatekeeper + Cockpit password"
  (two-factor: identity via OIDC + device password). Alternative: custom [bearer] command trusting X-Forwarded-User
  with SSH service key (SSO, future). OIDC template with chain middleware written to provisioning.
- [ ] 17.5 Verify Cockpit pod can SSH to host using provisioned password and spawn Python bridge via python3Minimal
- [x] 17.6 Add Cockpit pod to the health manifest for os-verification service validation — provisioning task creates
  /persist/config/health-manifest.yaml with cockpit-ws and traefik container entries

## 17b. First-Boot Initialization and Container Image Pulls

- [x] 17b.1 Create `modules/first-boot.nix` — systemd oneshot service with
  `ConditionPathExists=!/persist/.completed_first_boot` that runs on first boot only
- [x] 17b.2 Create `scripts/first-boot.sh` — marks RAUC slot good unconditionally and writes
  `/persist/.completed_first_boot` sentinel
- [x] 17b.3 Add `ConditionPathExists=/persist/.completed_first_boot` to `os-verification.service` so it skips on first
  boot (before sentinel exists)
- [x] 17b.4 Add `ExecStartPre=podman pull` to `cockpit-ws.service` and `traefik.service` for automatic container image
  fetch on first boot (cached no-op on subsequent boots)
- [x] 17b.5 Verify in nspawn: `first-boot.service` runs and creates sentinel, `os-verification.service` is skipped
  (condition unmet), both container services attempt pull (fail expected in nspawn — no network)

## 18. Authentication Provisioning

- [x] 18.1 Update `.mise/tasks/provision/emmc` to prompt for and create `/persist/config/admin-password-hash` (sha-512
  via mkpasswd) — interactive password prompt with confirmation, min 8 chars
- [x] 18.2 Update `.mise/tasks/provision/emmc` to accept and deploy SSH public key to
  `/persist/config/ssh-authorized-keys/admin` — via --ssh-key flag, accepts key string or .pub file path
- [x] 18.3 Add provisioning validation: fail if credential files are missing after provisioning — validation step
  re-mounts persist read-only and checks files exist and are non-empty
- [ ] 18.4 Verify device boots with provisioned credentials: SSH key auth works, password auth works via Cockpit pod on
  localhost
- [ ] 18.5 Verify no credentials exist in the squashfs image itself (EN18031 compliance)
