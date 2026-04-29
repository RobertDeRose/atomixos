# Project Structure

```text
flake.nix                          Main flake (pinned nixpkgs release, aarch64-linux)
flake.lock                         Pinned nixpkgs
mise.toml                          Tool versions, build tasks, hooks

modules/
  base.nix                         Shared NixOS config (systemd, ssh, auth, closure opts)
  hardware-rock64.nix              RK3328 kernel, DTB, eMMC/watchdog drivers
  hardware-qemu.nix                QEMU aarch64-virt target for testing
  networking.nix                   NIC naming (.link files), eth0/eth1 config
  firewall.nix                     nftables rules (WAN/LAN/VPN/FORWARD)
  lan-gateway.nix                  dnsmasq DHCP, chrony NTP, IP forwarding off
  rauc.nix                         RAUC system.conf, slot definitions
  watchdog.nix                     systemd watchdog config
  os-verification.nix              Post-update health check service
  os-upgrade.nix                   Update polling + hawkBit toggle
  first-boot.nix                   First-boot provisioning import + slot commit
  forensics.nix                    Tier 0 forensic ring + journald/rsyslog durability
  boot-storage-debug.nix           Boot-partition mount helpers for debugging
  openvpn.nix                      OpenVPN recovery tunnel

nix/
  squashfs.nix                     Squashfs image derivation (closureInfo + mksquashfs)
  rauc-bundle.nix                  Multi-slot RAUC bundle derivation
  boot-script.nix                  U-Boot boot.scr compilation
  image.nix                        Flashable eMMC disk image derivation
  tests/                           NixOS VM integration tests (nixos-lib.runTest)
    rauc-slots.nix                 RAUC slot detection + custom backend
    rauc-update.nix                Bundle install + slot switch
    rauc-rollback.nix              Install -> mark-bad -> rollback
    rauc-confirm.nix               os-verification health check -> mark-good
    rauc-power-loss.nix            Crash mid-install, verify recovery
    rauc-watchdog.nix              Watchdog + boot-count rollback
    firewall.nix                   2-node WAN/LAN port allow/deny
    initrd-fresh-flash-marker.nix  Initrd fresh-flash detection
    first-boot-provision.nix       Provisioning import + Quadlet rendering
    first-boot-source-discovery.nix USB/boot seed discovery rules
    forensics-*.nix                Forensic ring, journald, rsyslog durability tests
    network-isolation.nix          2-node DHCP/NTP/WAN isolation
    ssh-wan-toggle.nix             SSH-on-WAN flag enable/disable

scripts/
  build-squashfs.sh                Squashfs build template (Nix derivation)
  build-rauc-bundle.sh             RAUC bundle build template (Nix derivation)
  build-image.sh                   Disk image assembly template (Nix derivation)
  os-verification.sh               Runtime health check script
  os-upgrade.sh                    Runtime update polling script
  ssh-wan-toggle.sh                SSH-on-WAN flag check
  ssh-wan-reload.sh                SSH-on-WAN runtime reload
  first-boot.sh                    First-boot provisioning import + mark-good
  first-boot-provision.py          Provisioning importer/bootstrap/Quadlet renderer
  quadlet-sync.sh                  Rootful/rootless Quadlet sync + startup
  forensic-log.sh                  Tier 0 forensic ring reader/writer
  forensics-slot-transition.sh     Slot transition forensic marker helper
  boot.cmd                         U-Boot A/B boot script source
  fw_env.config                    U-Boot env config (reference only, not installed)

.mise/tasks/
  flash                            Flash image to disk device (macOS/Linux)
  serial/
    capture                        Serial console capture (1.5 Mbaud, --bg for background)
    shell                          Interactive serial console (minicom)
  config/
    lan-range                      Update LAN gateway/DHCP range across all configs
  e2e/
    rauc-slots ... ssh-wan-toggle  Individual E2E test runners
    debug                          Interactive QEMU debugging
  docs/
    build                          Build the documentation site
    serve                          Serve docs locally with hot reload

certs/
  dev.ca.cert.pem                  Development RAUC CA certificate (public)
  dev.signing.cert.pem             Development RAUC signing certificate (public)
  dev.*.key.pem                    Development private keys

docs/
  book.toml                        mdBook configuration
  src/                             Documentation source (this site)

_typos.toml                        Typos checker config
```
