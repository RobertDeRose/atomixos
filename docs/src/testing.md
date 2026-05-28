# Testing

The core `mise run e2e` task runs 9 NixOS VM integration tests that validate the RAUC update lifecycle, network
security, and rollback behavior. Additional provisioning, management-client, and forensics checks are also available
directly under the flake `checks.*` outputs. Tests run on both Linux (TCG software emulation) and macOS (Apple
Virtualization Framework).

## Running Tests

### Provisioning package

```sh
cd scripts/atomixos_provision
uv run --extra dev pytest
uv run --extra dev ruff check .
```

These tests cover the Litestar API, SSH-signature auth helpers, config parsing,
bundle import, Quadlet rendering/sync, activation, job tracking, and service
foundation modules.

### All tests

```sh
mise run e2e

# Run all tests inside a Lima VM
mise run e2e --lima
mise run e2e --lima --vm my-builder
```

### Individual tests

```sh
mise run e2e:rauc-slots          # RAUC sees all 4 A/B slots after boot
mise run e2e:rauc-update         # Bundle install writes to inactive slot pair, slot switches A->B
mise run e2e:rauc-rollback       # Install to B, mark bad, verify rollback to A
mise run e2e:rauc-confirm        # os-verification health checks pass, slot marked good (~3 min)
mise run e2e:rauc-power-loss     # Crash VM mid-install, verify slot A intact after reboot
mise run e2e:rauc-watchdog       # Freeze systemd to trigger watchdog, verify boot-count rollback
mise run e2e:firewall            # 2-node test: WAN allows HTTPS/VPN, LAN allows SSH/DHCP/NTP
mise run e2e:network-isolation   # 2-node test: LAN gets DHCP/NTP, cannot reach WAN
mise run e2e:ssh-wan-toggle      # Flag file enables/disables SSH on WAN via nftables reload

# Run an individual test inside Lima
mise run e2e:rauc-slots --lima
```

### Additional flake checks

```sh
nix build .#checks.aarch64-darwin.nixstasis-client --no-link
nix build .#checks.aarch64-linux.nixstasis-client --no-link
```

The `nixstasis-client` VM check boots AtomixOS with a mock Nixstasis API. It
validates registration, `/data/nixstasis` identity reuse across a registration
service restart, heartbeat polling, the FRP transient-unit launch boundary, and
that stopping the mock API does not stop local recovery targets.

## Test Descriptions

| Test                | Nodes | What it validates                                                                                         |
|---------------------|-------|-----------------------------------------------------------------------------------------------------------|
| `rauc-slots`        | 1     | RAUC detects all 4 A/B slots after first-boot repartitioning creates boot-b/rootfs-b                      |
| `rauc-update`       | 1     | Bundle install writes to inactive slot pair; slot switches from A to B                                    |
| `rauc-rollback`     | 1     | Install to slot B, mark bad, verify automatic rollback to slot A                                          |
| `rauc-confirm`      | 1     | Health checks pass within timeout, slot committed as good                                                 |
| `rauc-power-loss`   | 1     | Crash VM mid-install, verify slot A is intact after reboot                                                |
| `rauc-watchdog`     | 1     | Freeze systemd to trigger watchdog reboot, verify boot-count rollback                                     |
| `firewall`          | 2     | WAN node can reach HTTPS (443) and VPN (1194); LAN node can reach SSH, DHCP, NTP; all other ports blocked |
| `network-isolation` | 2     | LAN node gets DHCP lease and NTP, cannot reach WAN addresses                                              |
| `ssh-wan-toggle`    | 1     | SSH on WAN blocked by default; enabled when flag file created; disabled when removed                      |

Additional flake-only checks:

| Test               | Nodes | What it validates                                                                                         |
|--------------------|-------|-----------------------------------------------------------------------------------------------------------|
| `nixstasis-client` | 1     | Nixstasis registration, identity reuse, polling, FRP launch-boundary, and post-enrollment API outage path |

## Platform Performance

The mise task wrappers auto-detect the platform and select the correct flake output.

| Test                | macOS (apple-virt) | Linux (TCG, Lima) | Speedup   |
|---------------------|--------------------|-------------------|-----------|
| `rauc-slots`        | 34s                | 132s              | 3.9x      |
| `rauc-update`       | 25s                | 137s              | 5.5x      |
| `rauc-rollback`     | 22s                | 120s              | 5.5x      |
| `rauc-confirm`      | 95s                | 171s              | 1.8x      |
| `rauc-power-loss`   | 46s                | 184s              | 4.0x      |
| `rauc-watchdog`     | 57s                | 315s              | 5.5x      |
| `firewall`          | 65s                | 205s              | 3.2x      |
| `network-isolation` | 68s                | --                | --        |
| `ssh-wan-toggle`    | 35s                | --                | --        |
| **Total**           | **~7.5 min**       | **~21 min**       | **~3.7x** |

The `rauc-confirm` test has the smallest speedup because most of its runtime is a fixed 60-second sustained health check
timer.

## Interactive Debugging

### Bundle Test VM

Use `vm:bundle-test` to boot an interactive AtomixOS VM for exercising real
`config.toml` bundles without physical hardware:

```sh
mise run vm:bundle-test
```

Each launch uses a fresh temporary VM disk image. The VM runner is still built
through Nix and reused from the store when inputs have not changed, but runtime
state from previous bundle tests is discarded when the VM exits.

The VM uses the QEMU hardware profile with `eth0` as WAN and a second virtio NIC
as LAN. Host ports are forwarded for common operator workflows:

| Host URL/Port                  | Guest service        |
|--------------------------------|----------------------|
| `ssh -p 10022 admin@127.0.0.1` | SSH                  |
| `http://127.0.0.1:8080`        | Bootstrap/reapply UI |
| `http://127.0.0.1:8081`        | Caddy HTTP           |
| `https://127.0.0.1:8443`       | Caddy HTTPS          |

Build the runner without launching it:

```sh
mise run vm:bundle-test --build-only
```

Apply a bundle from the host:

```sh
tar --zstd -cvf config.tar.zst -C example/caddy-oidc .
curl -H 'x-config-filename: config.tar.zst' \
  --data-binary @config.tar.zst \
  http://127.0.0.1:8080/api/config
```

For domain-based Caddy examples, map the example domain to localhost while
testing from the host:

```sh
curl -k --resolve gateway.example.com:8443:127.0.0.1 \
  https://gateway.example.com:8443/cockpit/
```

For browser testing, add a local hosts entry and include the forwarded HTTPS
port in the URL:

```text
127.0.0.1 gateway.example.com
```

Then browse to `https://gateway.example.com:8443/`.

The Cockpit container generates both the real device origin and the VM forwarded
HTTPS origin from `GATEWAY_DOMAIN` because Cockpit accepts space-separated
origins.

SSH is key-only and uses the provisioned `/data/config/ssh-authorized-keys`
state. On a fresh VM, use the serial console or apply a bundle containing an
admin key before expecting `ssh -p 10022 admin@127.0.0.1` to succeed.

Launch an interactive QEMU VM with a Python REPL:

```sh
# Debug the default test (rauc-slots)
mise run e2e:debug

# Debug a specific test
mise run e2e:debug -t update
mise run e2e:debug -t confirm
mise run e2e:debug -t watchdog

# Keep VM state between runs
mise run e2e:debug -t slots --keep
```

Available test short names: `slots`, `update`, `rollback`, `confirm`, `power-loss`, `watchdog`, `firewall`, `net-iso`,
`ssh-toggle`.

Inside the REPL:

```python
gateway.start()                          # boot the VM
gateway.wait_for_unit("multi-user.target")
gateway.succeed("rauc status")           # run a command
gateway.shell_interact()                 # drop into a root shell
gateway.screenshot("name")              # save a screenshot
# Ctrl+D to exit
```

## Running Tests with Nix Directly

```sh
# Linux (TCG, no KVM required)
nix build .#checks.aarch64-linux.rauc-slots --no-link -L

# macOS (requires nix-darwin with linux-builder enabled)
nix build .#checks.aarch64-darwin.rauc-slots --no-link -L

# Local Darwin eval/builds that depend on nix/tests/rauc-qemu-config.nix should
# use a path flake ref so local files remain visible even if they are untracked.
nix build "path:$PWD#checks.aarch64-darwin.rauc-slots" --no-link -L
```

When iterating on a single Darwin check locally, evaluate and build the exact
derivation with the same `path:` flake ref:

```sh
drv=$(nix eval --raw "path:$PWD#checks.aarch64-darwin.rauc-slots.drvPath")
nix-store -r "$drv"
```

## Test Architecture

Tests use the NixOS test framework (`nixos-lib.runTest`). Each test:

1. Defines one or two virtual machines with the full AtomixOS service stack (using `hardware-qemu.nix` instead of
   `hardware-rock64.nix`)
2. Boots the VM(s) and runs a Python test script that interacts via QEMU's monitor interface
3. Asserts on command output, service states, and network behavior

The QEMU target uses a custom RAUC backend that simulates U-Boot's slot selection using files instead of environment
variables, allowing the full A/B update lifecycle to be tested without real hardware. The shared slot mapping for the
RAUC tests lives in `nix/tests/rauc-qemu-config.nix`.
