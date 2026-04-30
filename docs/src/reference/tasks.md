# Task Reference

All tasks are run with `mise run <task>`. Run `mise tasks` to list them.

## Build Tasks

All `build:*` tasks accept `--lima` to run inside a Lima VM and `--vm <name>` to specify which VM (default: `default`).

| Task                | Description                                           |
|---------------------|-------------------------------------------------------|
| `check`             | Verify flake evaluates cleanly (`nix flake check`)    |
| `build`             | Build and retain image artifacts under `.gcroots/`    |
| `build:squashfs`    | Build squashfs rootfs &rarr; `result-squashfs/`       |
| `build:rauc-bundle` | Build signed RAUC bundle &rarr; `result-rauc-bundle/` |
| `build:boot-script` | Build U-Boot boot script &rarr; `result-boot-script/` |

`build` also accepts `-o <path>` to copy the latest `.img` to a path.

## E2E Test Tasks

| Task                    | Description                                               |
|-------------------------|-----------------------------------------------------------|
| `e2e`                   | Run the core 9-task E2E suite sequentially                |
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

| Task    | Description                                                 |
|---------|-------------------------------------------------------------|
| `flash` | Flash image to disk device with dd + progress (macOS/Linux) |

## Configuration Tasks

`config:lan-range`: Update LAN gateway/DHCP range across all config files.

## Utility Tasks

| Task             | Description                                                                                           |
|------------------|-------------------------------------------------------------------------------------------------------|
| `gc`             | Delete old generations and collect unrooted store paths (`--lima`; `--vm <name>` when using `--lima`) |
| `serial:capture` | Capture serial output (1.5 Mbaud, auto-reconnect). `--bg` for background                              |
| `serial:shell`   | Interactive serial shell via minicom (1.5 Mbaud)                                                      |
