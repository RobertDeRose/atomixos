# Project Structure

Where each part of the repository lives. [NixOS Modules](../code-reference/modules.md),
[Nix Derivations](../code-reference/derivations.md), and [Scripts](../code-reference/scripts.md) describe the files in
detail.

```text
flake.nix                          Main flake (pinned nixpkgs release, aarch64-linux)
flake.lock                         Pinned flake inputs
mise.toml                          Tool versions, environment, and named tasks
mise.lock                          Resolved tool downloads
hk.pkl                             Check, fix, pre-commit, and commit-msg steps
build.toml                         Committed immutable build policy
build.dev.toml                     Ignored local build-policy overlay, when present

defaults/
  lan.json                         Built-in fallback LAN gateway, DHCP, DNS, and NTP contract

schemas/
  config.schema.json               JSON Schema for the runtime config.toml

dts/                               Device-tree overlays (internal and external watchdog paths)

modules/
  base.nix                         Shared NixOS config (systemd, ssh, users, OverlayFS root, packages)
  build-configuration.nix          Maps effective build policy to options; installs /etc/atomixos audit files
  kernel-config.nix                Shared stripped kernel baseline for Rock64 and QEMU
  hardware-rock64.nix              RK3328 kernel, device tree, SPI U-Boot env, RAUC slot devices
  hardware-cm3.nix                 Radxa CM3 IO (RK3566) kernel, device tree, eMMC paths, U-Boot env location
  hardware-rockchip.nix            Settings shared by the Rockchip board modules
  hardware-qemu.nix                QEMU aarch64-virt target for testing
  networking.nix                   NIC naming (.link files), wan/lan networkd config
  firewall.nix                     nftables rules, SSH-on-WAN and bootstrap toggles, provisioned inbound
  lan-gateway.nix                  dnsmasq DHCP/DNS, chrony NTP, LAN apply
  rauc.nix                         RAUC system.conf and slot definitions
  watchdog.nix                     systemd hardware watchdog and boot-count service
  os-verification.nix              Post-update health check service
  os-upgrade.nix                   Update polling service
  first-boot.nix                   First-boot provisioning, bootstrap API, apply and export workers
  nixstasis.nix                    Optional Nixstasis client registration and polling
  logging.nix                      Volatile journald plus buffered rsyslog to /data/logs
  boot-storage-debug.nix           Boot storage diagnostics service
  openvpn.nix                      OpenVPN recovery tunnel

nix/
  build-policy.nix                 Typed policy, merge, assertions, and canonical renderer
  partition-layout.nix             Shared partition labels, GUIDs, offsets, and sizes
  uboot.nix                        Rock64 U-Boot (SPI env, RAUC bootmeth, UMS)
  uboot-cm3.nix                    Radxa CM3 IO U-Boot (redundant eMMC env, RAUC bootmeth, UMS)
  uboot-start-ums.nix              Shared U-Boot PREBOOT for START_UMS recovery
  uboot-sandbox.nix                U-Boot sandbox binary for running boot scripts on the build host
  rtl815x-firmware.nix             Realtek USB NIC firmware blobs shared by both boards
  boot-partition.nix               Shared boot-slot vfat derivation
  squashfs.nix                     Squashfs image derivation (closureInfo + mksquashfs)
  rauc-bundle.nix                  Multi-slot RAUC bundle derivation
  boot-script.nix                  U-Boot boot.scr compilation
  image.nix                        Flashable eMMC disk image derivation
  tests/                           Evaluation, command, and NixOS VM integration tests

scripts/
  nix-with-build-config.sh         Fixed-path local override wrapper for Nix commands
  build.sh                         Preflighted atomic retained-artifact build, per board
  run-e2e-check.sh                 Shared E2E architecture, Lima, and Nix launcher
  build-squashfs.sh                Squashfs build template (Nix derivation)
  build-rauc-bundle.sh             RAUC bundle build template (Nix derivation)
  build-image.sh                   Disk image assembly template (Nix derivation)
  boot.cmd                         U-Boot A/B boot script source
  watchdog-boot-count.sh           Boot-count and rollback journal logging
  first-boot.sh                    First-boot provisioning import and slot confirmation
  os-verification.sh               Runtime health check
  os-upgrade.sh                    Runtime update polling
  quadlet-sync.sh                  Rootful and rootless Quadlet sync and startup
  apply-users.py                   Managed user materialization
  lan-gateway-apply.py             LAN gateway, DHCP, DNS, and NTP rendering
  provisioned-firewall-inbound.py  Provisioned WAN/LAN inbound firewall rules
  ssh-wan-toggle.sh                SSH-on-WAN flag check at boot
  ssh-wan-reload.sh                SSH-on-WAN runtime reload
  boot-storage-debug.sh            Boot storage diagnostics
  enable-docs-deployment.py        GitHub Pages enablement through gh
  atomixos_provision/              Provisioning server package (Litestar + uvicorn)
    src/atomixos_provision/        Package source; domain/ holds the auth, config, jobs, and system APIs
    tests/                         pytest suite
    assets/                        Bootstrap UI images (logo and drop zone)

.mise/tasks/
  flash                            Flash a board image to a disk device (macOS/Linux)
  serial/capture                   Serial console capture (1.5 Mbaud, --bg for background)
  serial/shell                     Interactive serial console (minicom)
  config/lan-range                 Update built-in fallback LAN gateway/DHCP defaults
  e2e/rauc-slots ... ssh-wan-toggle  Individual E2E test runners
  e2e/debug                        Interactive QEMU debugging

certs/
  dev.ca.cert.pem                  Development RAUC CA certificate (public)
  dev.signing.cert.pem             Development RAUC signing certificate (public)
  dev.*.key.pem                    Development private keys (committed for dev/test only)

example/                           Example provisioning bundles (Caddy + OIDC reference stack)

docs/
  package.json                     Pinned Docusaurus dependencies
  package-lock.json                Locked npm dependency tree
  docusaurus.config.ts             Site configuration (URL, plugins, theme, broken-link policy)
  sidebars.ts                      Navigation, grouped by reader intent
  site/                            Site code
    css/custom.css                 Brand theme (colors, fonts, intro header, tables, Mermaid)
    client/index.ts                Fonts and Mermaid diagram zoom/fullscreen
    features.ts                    Publishes only delivered features
    static/img/                    Images, also served to the product page
      atomixos-logo.png            Full logo with wordmark: README and the product page hero
      atomixos-mark.png            Atom emblem: the docs introduction header
      atomixos-icon.png            "Ax" element tile: the docs navbar and product page header
      atomixos-favicon.svg         Atom outline: the favicon, with a 64px PNG fallback
    pages/                         Optional standalone React pages
  src/                             Documentation content; README.mdx is the docs introduction

product/                           Product page at the Pages root (index.html, styles.css, and its scripts)

_typos.toml                        Typos checker config
```
