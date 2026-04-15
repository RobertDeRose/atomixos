# Task Reference

All tasks are run with `mise run <task>`. Run `mise tasks` to list them.

## Build Tasks

| Task                | Description                                                |
|---------------------|------------------------------------------------------------|
| `check`             | Verify flake evaluates cleanly (`nix flake check`)         |
| `build`             | Build all image artifacts (depends on all `build:*` tasks) |
| `build:squashfs`    | Build squashfs rootfs &rarr; `result-squashfs/`            |
| `build:rauc-bundle` | Build signed RAUC bundle &rarr; `result-rauc-bundle/`      |
| `build:boot-script` | Build U-Boot boot script &rarr; `result-boot-script/`      |
| `build:image`       | Build flashable disk image &rarr; `result-image/`          |

## E2E Test Tasks

| Task                    | Description                                               |
|-------------------------|-----------------------------------------------------------|
| `e2e`                   | Run all 9 integration tests sequentially                  |
| `e2e:rauc-slots`        | RAUC slot detection after boot                            |
| `e2e:rauc-update`       | Bundle install + slot switch A&rarr;B                     |
| `e2e:rauc-rollback`     | Install &rarr; mark bad &rarr; rollback to previous slot  |
| `e2e:rauc-confirm`      | os-verification health check &rarr; mark-good (~3 min)    |
| `e2e:rauc-power-loss`   | Crash mid-install, verify recovery                        |
| `e2e:rauc-watchdog`     | Watchdog + boot-count rollback                            |
| `e2e:firewall`          | WAN/LAN/VPN port allow/deny (2-node VLAN)                 |
| `e2e:network-isolation` | DHCP/NTP/WAN isolation (2-node VLAN)                      |
| `e2e:ssh-wan-toggle`    | SSH-on-WAN flag enable/disable                            |
| `e2e:debug`             | Interactive QEMU VM for debugging (`-t <test>`, `--keep`) |

## Provisioning Tasks

| Task              | Description                                                 |
|-------------------|-------------------------------------------------------------|
| `flash`           | Flash image to disk device with dd + progress (macOS/Linux) |
| `provision:image` | Generate flashable `.img` file (builds all artifacts first) |
| `provision:emmc`  | Flash directly to eMMC block device (Linux + root only)     |

## Configuration Tasks

| Task               | Description                                           |
|--------------------|-------------------------------------------------------|
| `config:lan-range` | Update LAN gateway/DHCP range across all config files |

## Utility Tasks

| Task     | Description                                               |
|----------|-----------------------------------------------------------|
| `serial` | Launch serial console capture (1.5 Mbaud, auto-reconnect) |
