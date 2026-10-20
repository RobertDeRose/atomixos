# Testing

AtomixOS is tested at three levels:

- **Python tests** run the provisioning service and repository scripts, including release promotion, with pytest on
  the host.
- **NixOS VM tests** boot the full OS in QEMU and check updates, rollback, provisioning, networking, and logging. The
  `mise run e2e` task runs the nine core tests; the rest are flake `checks.*` outputs you build directly.
- **Hardware tests** run on a physical Rock64; see [Hardware Testing](hardware-testing.md).

VM tests run on Linux (TCG software emulation) and on macOS (Apple Virtualization Framework, through the nix-darwin
`linux-builder`).

Each `e2e:*` task is a thin wrapper over `scripts/run-e2e-check.sh`. The helper validates the check name, selects the
host architecture, enters Lima when asked, runs Nix, filters known SQLite contention noise, and reports the result the
same way for every test. The interactive debug task uses the same launcher.

## Run the tests

### Provisioning package

```sh
cd scripts/atomixos_provision
uv run --extra dev pytest
ruff check .
```

The `dev` extra holds only test dependencies. Ruff comes from the mise toolchain, which pins its version, and
`mise run check` runs it through hk together with the rest of the repository lint steps.

These tests cover the Litestar API, SSH-signature authentication, config parsing, bundle import, Quadlet rendering and
sync, activation, job tracking, and the service foundation modules.

### Repository Python tests

From the repository root, run the provisioning and repository tests together:

```sh
uv run --project scripts/atomixos_provision --extra dev pytest scripts/atomixos_provision/tests tests
```

The release-promotion tests create temporary local Git remotes. They check initial publication, fast-forwarding the
validated commit while development advances, reruns, conflicting tags, divergent history, and atomic rejection.
They do not publish to GitHub or require release credentials.

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
mise run e2e:rauc-watchdog       # Simulate watchdog resets, verify boot-count rollback
mise run e2e:firewall            # 2-node test: WAN allows provisioned ports, LAN allows SSH/DHCP/NTP
mise run e2e:network-isolation   # 2-node test: LAN gets DHCP/NTP, cannot reach WAN
mise run e2e:ssh-wan-toggle      # Flag file enables/disables SSH on WAN via nftables reload

# Run an individual test inside Lima
mise run e2e:rauc-slots --lima
```

### Additional flake checks

Build any other check by name for your host's system, `aarch64-linux` or `aarch64-darwin`:

```sh
nix build .#checks.aarch64-darwin.nixstasis-client --no-link
nix build .#checks.aarch64-linux.kernel-security --no-link

# Provisioning checks on the Linux target
NIX_CONFIG='max-jobs = 1' ./scripts/nix-with-build-config.sh build --no-link --print-build-logs \
  .#checks.aarch64-linux.first-boot-provision \
  .#checks.aarch64-linux.first-boot-source-discovery
```

The `nixstasis-client` VM check boots AtomixOS against a mock Nixstasis API. It checks registration, reuse of the
`/data/nixstasis` identity across a restart of the registration service, heartbeat polling, a successful mock FRP
transient unit, and that stopping the mock API does not stop local recovery targets.

The `fleet-bootstrap` VM check uses the Nixstasis client's route-profile support with a mock approval and heartbeat API.
It checks the fleet image's loopback-only `127.0.0.1:8080` socket, server selection of the named `atomixos-bootstrap`
profile, the plain-HTTP route and `Host: localhost` rewrite, FRP token withdrawal, and that the token never appears in
rendered configuration, systemd environment output, or the journal. It covers the device side only; the Nixstasis
server's bundle delivery and the public FRPS and Caddy path are outside this check.

The `watchdog-module` check verifies that hardware watchdog enforcement is off by default and that the systemd manager
watchdog settings are rendered only when enforcement is enabled. The `watchdog-missing-device` VM check enables
enforcement without exposing a watchdog device, then verifies that boot continues, RAUC state is unchanged, and an
actionable warning reports that enforcement is unavailable.

The `kernel-security` VM check verifies the stripped kernel exposes the BPF LSM and BTF required by systemd filesystem
sandboxing. It also rejects unsupported-BPF, MTD-probe, boot-storage, and hung-task-sysctl startup diagnostics, and
checks that the runtime `kernel.panic` value is 10, so a panic after `systemd-sysctl` reboots the device.

The `build-configuration` check covers strict schema parsing, merge behavior, timeout bounds, canonical bytes,
provenance, NixOS option mapping, artifact sidecar inputs, and the network-versus-fleet bootstrap transport boundary.
It proves that network mode retains the WAN listener policy while fleet mode renders the loopback socket, omits the WAN
bootstrap service, and suppresses the LAN socket rebind. The `build-config-workflow` check uses an isolated fake Nix
command to cover automatic fixed-path overrides, warning/transport behavior, the included task matrix, Lima command
execution, validation ordering, and retained-link preservation.

Direct flake checks use committed policy. To test a local overlay, create `build.dev.toml` and run
`./scripts/nix-with-build-config.sh flake check`; the warning must appear before effective-policy evaluation.

The `provisioning-export` VM check runs the production export path/service and unprivileged API. It verifies real
UID-separated access, private-file exports without permission changes, concurrent authenticated downloads, root-owned
results, acknowledgement cleanup, and rejection of symlinks and hard links. Package tests additionally cover UUID
correlation, bounded admission, timeouts, cancellation, interrupted-worker finalization, expiry, atomic output,
malformed requests, bounded snapshot reads, and JSON error responses.

## Test descriptions

| Test                | Nodes | What it validates                                                                                                   |
|---------------------|-------|---------------------------------------------------------------------------------------------------------------------|
| `rauc-slots`        | 1     | RAUC detects all 4 A/B slots after first-boot repartitioning creates boot-b/rootfs-b                                |
| `rauc-update`       | 1     | Bundle install writes to inactive slot pair; slot switches from A to B                                              |
| `rauc-rollback`     | 1     | Install to slot B, mark bad, verify automatic rollback to slot A                                                    |
| `rauc-confirm`      | 1     | Health checks pass within timeout, slot committed as good                                                           |
| `rauc-power-loss`   | 1     | Crash VM mid-install, verify slot A is intact after reboot                                                          |
| `rauc-watchdog`     | 1     | Simulate watchdog-triggered resets and verify boot-count rollback                                                   |
| `firewall`          | 2     | WAN node can reach provisioned HTTPS (443) and UDP 1194; LAN node can reach SSH, DHCP, NTP; all other ports blocked |
| `network-isolation` | 2     | LAN node gets DHCP lease and NTP, cannot reach WAN addresses                                                        |
| `ssh-wan-toggle`    | 1     | SSH on WAN blocked by default; enabled when flag file created; disabled when removed                                |

Flake-only checks:

| Test                          | Nodes | What it validates                                                                                                  |
|-------------------------------|-------|--------------------------------------------------------------------------------------------------------------------|
| `nixstasis-client`            | 1     | Nixstasis registration, identity reuse, polling, FRP launch-boundary, and post-enrollment API outage path          |
| `fleet-bootstrap`             | 1     | Loopback fleet socket, named AtomixOS route profile, Host rewrite, withdrawal, and token secrecy                   |
| `watchdog-module`             | 0     | Watchdog option defaults and opt-in systemd manager settings                                                       |
| `build-configuration`         | 0     | Schema, canonical policy, provenance, module mapping, and sidecar inputs                                           |
| `build-config-workflow`       | 0     | Local override wrapper, task matrix, Lima behavior, and per-board retained GC roots                                |
| `cm3-board`                   | 0     | CM3 eMMC paths and RAUC compatible; every U-Boot setting survives into the resolved `.config`; env order           |
| `boot-partition-size`         | 0     | An oversized boot payload fails with a size breakdown; a fitting one builds                                        |
| `uboot-scripts`               | 0     | U-Boot sandbox runs `boot.scr` (failed loads reset, `START_UMS`) and the `PREBOOT`; also a CI job                  |
| `device-tree-overlay`         | 0     | Boot slot DTB comes from the NixOS device-tree package with overlays; ROCK64 watchdog overlay wiring               |
| `os-upgrade-query`            | 0     | Update query sends `X-Compatible`; another board's bundle is skipped before download                               |
| `watchdog-missing-device`     | 1     | Enabled policy without hardware boots, preserves RAUC state, and emits an actionable warning                       |
| `kernel-security`             | 1     | BPF LSM/BTF support is active, runtime `kernel.panic` is 10, and unsupported startup diagnostics are absent        |
| `interface-naming`            | 1     | WAN and LAN are renamed to `wan`/`lan` by hardware match, whichever NIC registers first                            |
| `rootless-storage`            | 1     | Rootless application images are stored under `/data/containers/rootless`, not on the reset-on-boot overlay root    |
| `first-boot-provision`        | 1     | Provisioning import, validation, apply, auth, rollback, and LAN transport behavior                                 |
| `first-boot-source-discovery` | 1     | Boot/USB/bootstrap source precedence, marker behavior, and fleet rebind suppression                                |
| `provisioning-export`         | 1     | Authenticated root-worker export of private workload-owned files, concurrent requests, cleanup, and link rejection |
| `initrd-fresh-flash-marker`   | 1     | Initrd repartitioning creates slot B/data and persists the fresh-flash marker                                      |
| `forensics-podman-log-path`   | 1     | Podman journald output reaches the persistent `/data/logs` path                                                    |
| `forensics-rsyslog-path`      | 1     | Buffered rsyslog output is written to persistent `/data/logs`                                                      |
| `forensics-rsyslog-buffering` | 1     | Rsyslog batches writes instead of synchronously writing every message                                              |
| `forensics-shutdown-flush`    | 1     | The logging shutdown-flush service persists buffered log output                                                    |
| `chrony-wan-recovery`         | 1     | Chrony and its wait-sync probe behave correctly while WAN time sources are offline                                 |
| `nixstasis-module`            | 0     | Nixstasis client module renders its configuration and registration service                                         |
| `boot-script`                 | 0     | The U-Boot script derives the rootfs partition from the selected boot slot (Linux only)                            |
| `lan-defaults`                | 0     | Shipped LAN defaults reach the networkd, dnsmasq, and chrony configuration                                         |
| `partition-layout`            | 0     | Repart partition sizes and labels match the shared partition layout                                                |
| `e2e-launcher`                | 0     | The `scripts/run-e2e-check.sh` launcher used by the `e2e:*` tasks                                                  |

## Platform performance

The `e2e:*` tasks detect the host platform and pick the matching flake output. VM tests run several times faster on
macOS with Apple virtualization than under TCG emulation on Linux or in Lima. `rauc-confirm` gains the least, because
most of its runtime is the fixed 60-second sustained health check.

## Interactive debugging

### Bundle test VM

Use `vm:bundle-test` to boot an interactive AtomixOS VM and try real `config.toml` bundles without hardware:

```sh
mise run vm:bundle-test
```

Each launch uses a fresh temporary disk image, so state from earlier runs is discarded when the VM exits. The VM runner
itself is built through Nix and reused from the store while its inputs are unchanged.

The VM uses the QEMU hardware profile, where the first virtio NIC (`eth0`) is WAN and the second (`eth1`) is LAN.
These host ports are forwarded:

| Host URL/Port                  | Guest service                  |
|--------------------------------|--------------------------------|
| `ssh -p 10022 admin@127.0.0.1` | SSH                            |
| `http://127.0.0.1:8080`        | Bootstrap UI (first boot only) |
| `http://127.0.0.1:8081`        | Caddy HTTP                     |
| `https://127.0.0.1:8443`       | Caddy HTTPS                    |

Build the runner without launching it:

```sh
mise run vm:bundle-test --build-only
```

Apply a bundle from the host during first boot; the browser UI is not a post-provision management console:

```sh
tar --zstd -cvf config.tar.zst -C example/caddy-oidc .
curl -H 'x-config-filename: config.tar.zst' \
  --data-binary @config.tar.zst \
  http://127.0.0.1:8080/api/config
```

For domain-based Caddy examples, map the example domain to localhost when testing from the host:

```sh
curl -k --resolve gateway.example.com:8443:127.0.0.1 \
  https://gateway.example.com:8443/cockpit/
```

For browser testing, add a local hosts entry and include the forwarded HTTPS port in the URL:

```text
127.0.0.1 gateway.example.com
```

Then browse to `https://gateway.example.com:8443/`.

The Cockpit container derives both the real device origin and the VM's forwarded HTTPS origin from `GATEWAY_DOMAIN`,
because Cockpit accepts space-separated origins.

SSH is key-only and uses the provisioned `/data/config/ssh-authorized-keys`. On a fresh VM, use the serial console, or
apply a bundle that contains an admin key, before expecting `ssh -p 10022 admin@127.0.0.1` to work.

### Test REPL

`e2e:debug` launches an interactive QEMU VM for one of the core tests, with a Python REPL:

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

## Run tests with Nix directly

```sh
# Linux (TCG, no KVM required)
nix build .#checks.aarch64-linux.rauc-slots --no-link -L

# macOS (requires nix-darwin with linux-builder enabled)
nix build .#checks.aarch64-darwin.rauc-slots --no-link -L

# Local Darwin eval/builds that depend on nix/tests/rauc-qemu-config.nix should
# use a path flake ref so local files remain visible even if they are untracked.
nix build "path:$PWD#checks.aarch64-darwin.rauc-slots" --no-link -L
```

When iterating on a single Darwin check, evaluate and build the exact derivation with the same `path:` flake ref:

```sh
drv=$(nix eval --raw "path:$PWD#checks.aarch64-darwin.rauc-slots.drvPath")
nix-store -r "$drv"
```

## Test architecture

Tests use the NixOS test framework (`nixos-lib.runTest`). Each test:

1. Defines one or two virtual machines with the full AtomixOS service stack (using `hardware-qemu.nix` instead of
   `hardware-rock64.nix`)
2. Boots the VM(s) and runs a Python test script that interacts via QEMU's monitor interface
3. Asserts on command output, service states, and network behavior

The QEMU target uses a custom RAUC backend that simulates U-Boot's slot selection using files instead of environment
variables, allowing the full A/B update lifecycle to be tested without real hardware. The shared slot mapping for the
RAUC tests lives in `nix/tests/rauc-qemu-config.nix`.

## Continuous integration

Pull requests evaluate the flake, run the `uboot-scripts` sandbox check, and run the provisioning package tests. They
do not build images or run VM tests.
[Developer Tooling](development/tooling.md#github-validation) describes each workflow. Run full builds and VM tests
locally with `./scripts/nix-with-build-config.sh flake check` or the `nix build` commands above; `mise run check` runs
quality checks only.

## Host differences

The provisioning package tests run on macOS and Linux, but some checks need Linux:

- Two setgid directory-mode assertions are skipped on macOS and run on Linux.
- Managed-file access needs Linux `O_PATH` and `/proc/self/fd`. On macOS, a test-only file-open stand-in exercises the
  higher-level behavior, and a test confirms the production boundary fails closed without `O_PATH`. Inode-pinning and
  special-file race tests run on Linux only.
- macOS has no Linux xattrs, so tests there record read-only ACL grants. On Linux the suite applies and reads back the
  real `system.posix_acl_access` ACL, skipping that check only when the filesystem lacks ACL support.
