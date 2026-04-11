# Design

## Context

This is a greenfield project — no existing NixOS configuration, RAUC setup, or image build pipeline exists. The target
hardware is the Rock64 board (Rockchip RK3328 SoC, aarch64) with 16 GB eMMC.

These devices are deployed remotely in the thousands and growing. They serve as network gateways for legacy downstream
devices, providing a security/compliance boundary (EN18031). The current Debian-based system suffers from a ~3% update
failure rate due to power loss during apt-based upgrades, requiring manual SSH recovery via VPN.

The Rock64 acts as:

- An OTA-updatable edge compute platform (NixOS + podman containers)
- A network security boundary between WAN and an isolated LAN of legacy devices
- A management hub with Cockpit (web UI via pod) and application-layer proxying (Traefik) to LAN devices
- The sole communication path to legacy devices via TCP sockets the Rock64 opens to them

The 16 GB eMMC is the primary constraint. A/B root filesystem slots must coexist with persistent storage for containers,
state, and logs.

## Goals / Non-Goals

**Goals:**

- Atomic over-the-air updates: writing to the inactive slot pair (boot + rootfs) while the active slot continues running
- Automatic rollback via U-Boot boot-count logic if a new image fails to boot
- Hardware watchdog ensuring hung systems reboot and trigger rollback
- Local health-check confirmation before committing a new slot — validates system services and manifest-defined
  containers are running
- Signed RAUC bundles (`.raucb`) built as a Nix flake output for reproducible, verifiable images
- Initial provisioning script to partition eMMC and deploy the first image
- Systemd-based update polling service, designed to be swappable with hawkBit client
- Network isolation: LAN devices cannot reach the internet; Rock64 is the sole access point
- Cockpit as a pod (`quay.io/cockpit/ws`) that SSHes into the host — keeps the squashfs small while providing web
  management
- `python3Minimal` in the rootfs to support Cockpit's SSH-based Python bridge
- EN18031-compliant user authentication: no default passwords, unique per-device credentials set during provisioning
- QEMU testing target for fast development iteration without hardware

**Non-Goals:**

- Update server infrastructure (Azure Blob Storage, CDN, HTTP API) — assumed to exist; out of scope
- hawkBit server deployment — device side is hawkBit-ready, but server is deferred
- Delta/differential updates — first version uses full squashfs images; delta optimization is a future concern
- Multi-board support — this targets Rock64 (RK3328) only; other boards are future work
- Traefik configuration — The image defines the Traefik systemd service (same raw-podman pattern as Cockpit), but the
  container image lives on `/persist` and configuration files on `/persist/config/traefik/`. The provisioning task
  writes default config and a self-signed TLS certificate.
- Container orchestration — the image provides podman + Cockpit; what containers run is determined by the application
  layer and health manifest

## Decisions

### 1. RAUC as the update framework

**Choice**: RAUC over SWUpdate or custom scripts.

**Rationale**: RAUC has first-class U-Boot integration (boot-count via environment variables), a NixOS module in nixpkgs
(`services.rauc`), cryptographic bundle verification, and a D-Bus API for integration. SWUpdate is comparable but has
weaker NixOS ecosystem support. Custom scripts are brittle and would reimplement what RAUC already provides.

**Alternatives considered**:

- **SWUpdate**: Capable, but less NixOS community support and no existing nixpkgs module.
- **Mender**: SaaS-oriented, heavier footprint, less suitable for constrained eMMC.
- **Custom dd-based scripts**: No verification, no rollback, no slot management — unacceptable for production.

### 2. Read-only squashfs root filesystem

**Choice**: squashfs for rootfs with a separate writable /persist partition.

**Rationale**: squashfs provides excellent compression (current image: ~333 MB compressed with zstd at 1 MB block size),
integrity (immutable), and simplicity (no fsck needed). The A/B design requires two copies of the rootfs — compression
is essential to fit within the 16 GB eMMC budget. Mutable state lives on the /persist partition (f2fs), mounted at boot.

The build uses `mksquashfs` with `-b 1048576` (1 MB block size, the maximum) which gives zstd more context for pattern
matching and reduces the compressed size by ~9% compared to the default 128 KB block size. Runtime impact is negligible
on a 1-4 GB RAM device with long-running services.

**Alternatives considered**:

- **ext4 with dm-verity**: More complex, larger on disk, marginal integrity benefit over squashfs for this use case.
- **erofs**: Newer, less tooling support in NixOS.

### 3. Kernel in per-slot boot partitions with modules in squashfs

**Choice**: Each A/B slot gets its own small vfat boot partition containing the kernel and DTB. Kernel modules
(including WiFi/BT USB dongle drivers) live inside the squashfs rootfs.

**Rationale**: U-Boot cannot read squashfs, so the kernel must be on a U-Boot-accessible filesystem. A shared /boot
partition would be a single point of failure — if a kernel update corrupts it, both slots are dead. Per-slot boot
partitions make kernel updates atomic with rootfs updates. RAUC supports multi-slot bundles that write both the boot
partition and rootfs partition in a single install operation.

The kernel is stripped to only RK3328-required drivers (eMMC, ethernet, USB host, watchdog, squashfs, f2fs) built-in.
Optional USB peripheral drivers (WiFi: rtlwifi/ath9k_htc/mt76, Bluetooth: btusb) are built as modules (`=m`) and
included in the squashfs. They compress to nearly nothing and only consume RAM when loaded.

**Alternatives considered**:

- **Shared /boot partition**: Simpler but single point of failure. Rejected because a corrupted shared /boot bricks both
  slots.
- **FIT image in raw partition**: Works but less standard tooling; vfat is simpler for U-Boot.
- **Overlayfs for optional modules**: Unnecessary complexity; modules in squashfs are effectively free when not loaded.

### 4. eMMC partition layout

**Choice**: Fixed partition table with raw U-Boot, per-slot vfat boot partitions, two squashfs slots, and f2fs /persist.

```text
Offset     Size       Content          Filesystem
0          4 MB       U-Boot           raw (idbloader @ sector 64, u-boot.itb @ sector 16384)
4 MB       128 MB     boot slot A      vfat (kernel + DTB for slot A)
132 MB     128 MB     boot slot B      vfat (kernel + DTB for slot B)
260 MB     1 GB       rootfs slot A    squashfs (NixOS system + kernel modules)
1284 MB    1 GB       rootfs slot B    squashfs (NixOS system + kernel modules)
2308 MB    ~13.3 GB   /persist         f2fs (containers, state, logs, health manifest)
```

**Rationale**: Per-slot boot partitions eliminate the shared /boot single point of failure. 128 MB per boot partition
accommodates the uncompressed aarch64 kernel Image (~63 MB) plus DTB and boot.scr with room for growth. The 1 GB rootfs
slots accommodate the NixOS system closure (currently ~333 MB compressed) with room for growth. The initial design
targeted 200 MB slots but this proved unrealistic for NixOS + Podman + networking stack. f2fs is chosen for /persist
because it's designed for flash storage (wear leveling awareness, power-loss resilience). The layout leaves ~13.3 GB for
/persist, which holds container images, application data, and logs.

**Alternatives considered**:

- **ext4 for /persist**: Works, but f2fs is purpose-built for eMMC/flash and handles power loss better.

### 5. U-Boot from nixpkgs with boot-count via RAUC integration

**Choice**: Use the `ubootRock64` package from nixpkgs. Use RAUC's built-in U-Boot bootloader backend with environment
variables for boot-count tracking. Enable redundant U-Boot environment storage.

**Rationale**: Rock64/RK3328 has mainline U-Boot support, and nixpkgs packages it. No custom U-Boot build needed. RAUC
natively supports U-Boot via environment variable manipulation. On install, RAUC sets the active slot and resets the
boot attempt counter. U-Boot decrements on each boot attempt; if it reaches zero without the system marking good, U-Boot
switches to the other slot. Redundant env storage (two copies) protects against power loss during env write.

Key U-Boot environment variables:

- `BOOT_ORDER`: slot priority (e.g., `A B`)
- `BOOT_A_LEFT` / `BOOT_B_LEFT`: remaining boot attempts per slot (e.g., `3`)

### 6. Watchdog strategy

**Choice**: Hardware watchdog (RK3328 built-in) driven by systemd's watchdog integration.

**Rationale**: systemd can kick the hardware watchdog at a configurable interval. If systemd hangs (kernel panic,
deadlock, OOM), the hardware watchdog fires and triggers a hard reboot. Combined with U-Boot boot-count, this means a
hung system reboots and U-Boot decrements the attempt counter — leading to automatic rollback if the system can't stay
up.

Configuration:

- `RuntimeWatchdogSec=30s` — systemd kicks the watchdog every 30s
- `RebootWatchdogSec=10min` — if reboot itself hangs, force reset after 10 minutes

### 7. Local health-check confirmation (not phone-home)

**Choice**: A systemd oneshot service that performs local health checks and calls `rauc status mark-good` to commit the
slot. No network/phone-home dependency.

**Rationale**: A phone-home approach couples update success to network availability — if the update server is down, the
device rolls back even though it's perfectly functional. This is unacceptable for remotely deployed devices with
potentially unreliable connectivity. Local health checks verify what actually matters: are the system services and
application containers running?

**Flow**:

1. Device boots into new slot
2. `os-verification.service` starts after `multi-user.target`
3. Check system health: eth0 has WAN address, eth1 is 172.20.30.1, dnsmasq running, chronyd running
4. If `/persist/config/health-manifest.yaml` exists, check each container listed is in "running" state (timeout: 5 minutes) — this includes the Cockpit pod
5. If no manifest exists (bare/unprovisioned image), skip container checks
6. Sustain all checks passing for 60 seconds (catch restart loops — check every 5s)
7. All pass → `rauc status mark-good`
8. Any fail → exit non-zero, slot stays uncommitted, boot-count continues to decrement

The health manifest is placed on `/persist/config/` by the device provisioning process (initial flash or remote
provisioning service), not shipped in the image. This allows different deployments to define different health criteria.

**Alternatives considered**:

- **Phone-home to update server**: Creates unnecessary rollbacks when network is down. Rejected.
- **No confirmation (trust boot success)**: Insufficient — a device that boots but has broken containers would be
  considered "good." Rejected.

### 8. Cockpit as a pod with python3Minimal in the rootfs

**Choice**: Run Cockpit as a container pod (`quay.io/cockpit/ws`) that SSHes into the host to execute a Python bridge.
Include `python3Minimal` in the squashfs rootfs to support the bridge.

**Rationale**: The original design placed Cockpit directly in the squashfs rootfs. Investigation revealed that Cockpit's
NixOS module pulls in gcc (230 MB RPATH leak) and full python3 (102 MB) into the runtime closure, adding ~330 MB to the
squashfs. This was unacceptable for an embedded image.

The pod-based approach (`quay.io/cockpit/ws`) is Cockpit's official container deployment model. The Cockpit pod SSHes
into the host on localhost and spawns a Python bridge process. This requires Python on the host, but `python3Minimal`
(30 MB on disk, 7 MB compressed in squashfs) provides a minimal Python 3.13 interpreter with no SSL, no sqlite, no
readline, and no external dependencies. Its `allowedReferences` guard ensures its closure contains only glibc and bash
(both already in the image). No SSL is acceptable because the transport is SSH.

Cockpit runs on `/persist` as a pod managed by podman (via Quadlet or systemd unit). Container images are pulled during
provisioning or first boot. The health-check confirmation service validates that the Cockpit pod is running before
committing a slot.

**Alternatives considered**:

- **Cockpit native in rootfs**: Reliable (survives container failures) but closure size is prohibitive. Rejected due to
  gcc/python3 dependency chain.
- **Cockpit native with closure surgery**: Attempted but the gcc RPATH leak comes from deep in the NixOS module system
  (pam, shadow) and cannot be cleanly removed without patching nixpkgs. Rejected as too fragile.
- **No Cockpit**: Unacceptable — web management is a core requirement for the device.

### 9. OpenVPN in the rootfs

**Choice**: Include OpenVPN in the squashfs rootfs as a system service for recovery management access.

**Rationale**: OpenVPN provides an out-of-band SSH access path via VPN tunnel. It's a belt-and-suspenders recovery
mechanism in case Cockpit or Traefik has issues. Since it's in the rootfs, it survives any container-layer failures.
With the A/B update system, it should rarely be needed, but having it available costs very little.

### 10. Network architecture — LAN isolation boundary

**Choice**: The Rock64 acts as a network isolation boundary. `ip_forward` is OFF. No NAT. No packet-level routing
between eth0 (WAN) and eth1 (LAN). Application-layer proxying only via Traefik (container).

**Rationale**: EN18031 compliance requires network security for connected devices. The legacy devices on the LAN cannot
be made compliant themselves, so the Rock64 provides the compliance boundary. By disabling IP forwarding entirely, no
packet can traverse from LAN to WAN or vice versa at the kernel level. Only user-space processes that explicitly bind
both interfaces (Traefik, device control service) can bridge the gap, and they do so selectively with authentication.

Network topology:

- eth0 (WAN): DHCP client, internet-facing. Accepts HTTPS (443) and OpenVPN (1194).
- eth1 (LAN): Static 172.20.30.1/24. Serves DHCP, NTP. Accepts SSH (22).
- tun0 (VPN): SSH access for remote recovery.
- The Rock64 opens TCP sockets to LAN devices to push commands; devices reply on the same socket.
- LAN devices have zero internet access.

### 11. NIC naming via systemd link files

**Choice**: Disable systemd predictable interface names. Use systemd-networkd `.link` files matching on hardware path
for the onboard NIC and driver/type for USB peripherals.

**Rationale**: The onboard RK3328 GMAC must always be eth0 (WAN, device identity via MAC). USB NICs must be eth1, eth2,
etc. (LAN). WiFi dongles must be wlan0, wlan1, etc. Matching on the RK3328 GMAC's fixed platform hardware path
(platform-ff540000.ethernet) guarantees eth0 is always the internal NIC regardless of USB device enumeration order.

Device identity: `eth0` MAC address = device ID (existing convention, read from `/sys/class/net/eth0/address`).

### 12. Firewall via nftables

**Choice**: nftables with static rules in the image and a manual SSH-on-WAN toggle via flag file.

Rules:

- eth0 (WAN) inbound: ALLOW tcp/443 (HTTPS), ALLOW udp/1194 (OpenVPN), ALLOW established/related, DROP all else. SSH
  (tcp/22) allowed only if `/persist/config/ssh-wan-enabled` flag file exists.
- eth1 (LAN) inbound: ALLOW udp/67-68 (DHCP), ALLOW udp/123 (NTP), ALLOW tcp/22 (SSH), ALLOW established/related, DROP
  all else.
- tun0 (VPN) inbound: ALLOW tcp/22 (SSH), ALLOW established/related, DROP all else.
- FORWARD chain: DROP all (no inter-interface routing).

The SSH-on-WAN flag is a persistent file on `/persist/config/`. Toggled manually via Cockpit, API, or SSH. No automated
opening — eliminates the security risk of an attacker forcing the flag.

### 13. hawkBit-ready architecture

**Choice**: Design the device-side update client to be swappable between a simple polling service and the
`rauc-hawkbit-updater` client via a NixOS configuration flag.

**Rationale**: At thousands of devices, hawkBit's fleet management (staged rollouts, per-device status, rollback
campaigns) is valuable. But deploying the hawkBit server (Java/Spring Boot + DB) adds operational complexity that should
be deferred until the core A/B infrastructure is proven. Since both clients ultimately trigger `rauc install`,
everything downstream (RAUC slots, confirmation, rollback) is identical regardless of which client is active.

The NixOS config includes both services with one enabled by default:

- `os-upgrade` (simple polling timer) — **enabled by default**
- `rauc-hawkbit-updater` — **disabled by default**, flip a flag to switch

### 14. QEMU testing target

**Choice**: Add a `nixosConfigurations.rock64-qemu` flake output that shares 95% of the real config but targets
`aarch64-virt` for QEMU testing.

**Rationale**: Building and flashing real hardware for every iteration is slow. A QEMU target allows testing NixOS
configuration, systemd services, podman, RAUC slot logic, and the confirmation service without hardware.
Hardware-specific testing (U-Boot boot-count, real watchdog, eMMC) still requires a physical Rock64.

Flake outputs:

- `nixosConfigurations.rock64` — real hardware target
- `nixosConfigurations.rock64-qemu` — QEMU testing target
- `packages.aarch64-linux.squashfs` — root filesystem image
- `packages.aarch64-linux.rauc-bundle` — signed multi-slot `.raucb` bundle

### 15. EN18031-compliant user authentication (Option 4 Hybrid)

**Choice**: No default passwords. Unique per-device credentials provisioned during initial flash. OIDC (Microsoft Entra
via Traefik forward-auth) is the primary auth when internet is available; provisioned password is the LAN/offline
fallback.

**Rationale**: EN18031 prohibits default passwords. The image ships with no embedded credentials —
`users.users.admin.hashedPasswordFile` points to `/persist/config/admin-password-hash`, which is created during
provisioning with a unique sha-512 hash (from `mkpasswd`). SSH authorized keys are loaded at runtime from
`/persist/config/ssh-authorized-keys/%u` (per-user key files), not baked into the image.

**Authentication flows**:

- **WAN (internet available)**: Traefik forward-auth requires OIDC (Microsoft Entra). After OIDC, request reaches
  Cockpit. User types provisioned password to authenticate the SSH bridge session. This provides two-factor access: OIDC
  identity + device password. (Future: a custom `[bearer]` auth command could trust `X-Forwarded-User` from Traefik and
  use an SSH service key for SSO, but this requires careful trust boundary management.)
- **LAN (internet unavailable)**: Traefik routes directly to Cockpit (ipAllowList middleware bypasses OIDC for
  172.20.30.0/24). User sees Cockpit login page, authenticates with provisioned password.
- **SSH from WAN**: Key-only (password auth disabled globally, enabled only for localhost via `Match Address
  127.0.0.1,::1`).
- **SSH from LAN/VPN**: Key-preferred, password fallback.

**SSH localhost password auth**: The Cockpit pod SSHes to the host on localhost to spawn its Python bridge. `Match
Address 127.0.0.1,::1` in sshd_config enables password authentication only for loopback connections, allowing the
Cockpit pod to authenticate with the provisioned password. Remote SSH remains key-only.

**Provisioning creates**:

- `/persist/config/admin-password-hash` — sha-512 password hash
- `/persist/config/ssh-authorized-keys/admin` — operator's SSH public key
- `/persist/config/traefik/traefik.yaml` — Traefik static config (entrypoints, providers)
- `/persist/config/traefik/dynamic/cockpit.yaml` — Cockpit reverse proxy route + TLS cert paths
- `/persist/config/traefik/dynamic/oidc.yaml.disabled` — OIDC forward-auth template (rename to enable)
- `/persist/config/traefik/certs/server.{crt,key}` — self-signed TLS certificate (EC P-256, 10-year)
- `/persist/config/health-manifest.yaml` — container health entries (cockpit-ws, traefik)

**Alternatives considered**:

- **Default password with forced change on first login**: Violates EN18031 — the default password exists in the image
  and is the same across all devices.
- **Certificate-only auth**: Operationally complex for field deployment; requires PKI infrastructure.
- **OIDC-only**: Fails when internet is unavailable; LAN access is a core requirement.

### 16. Squashfs closure size optimization

**Choice**: Aggressively reduce the NixOS system closure size through targeted NixOS option overrides and mksquashfs
tuning.

**Applied optimizations** (cumulative reduction: 126 MB / 27% from initial 459 MB):

- `security.pam.services.su.forwardXAuth = lib.mkForce false` — Removed xauth + 9 X11 libraries (~6.5 MB uncompressed)
- `system.fsPackages = lib.mkForce []` — Removed dosfstools/e2fsprogs from system PATH
- `boot.bcache.enable = false` — Disabled bcache (defaults to true), suppresses udev rules
- `boot.kexec.enable = false` — No kexec on A/B image device
- `services.lvm.enable = false` — No LVM/device-mapper, suppresses udev rules
- `mksquashfs -b 1048576` (1 MB block size) — 32 MB (9%) compression improvement over default 128 KB

**Rejected optimization**: `lib.mkForce` on `environment.corePackages` to strip default GNU tools was attempted but
reverted. Investigation showed nearly all tools remain in the nix store as transitive deps of systemd/perl/shadow —
removing them from PATH saves zero bytes in the squashfs but creates maintenance risk (silently suppressing future NixOS
module additions).

**Structural deps that cannot be removed within NixOS**:

| Package | Size | Reason |
|---|---|---|
| linux-6.19 kernel + modules | ~308 MB | Kernel build tree + modules |
| systemd | ~69 MB | Core init — pulls elfutils, p11-kit, tpm2-tss, cracklib, lvm2 |
| podman ecosystem | ~150 MB | podman, netavark, cni-plugins, gvproxy, runc, fuse-overlayfs |
| perl | ~59 MB | NixOS activation scripts (setup-etc.pl, update-users-groups.pl) |

## Risks / Trade-offs

**[Risk] eMMC wear from frequent updates** → squashfs writes to raw partitions on each update. Mitigation: f2fs on
/persist handles wear leveling for frequent writes; rootfs updates should be infrequent (weekly/monthly, not hourly).
eMMC controllers have internal wear leveling.

**[Risk] U-Boot environment storage corruption** → U-Boot env is typically stored on eMMC at a fixed offset. Power loss
during env write could corrupt it. Mitigation: U-Boot supports redundant environment storage (two copies); enable this
in the U-Boot configuration.

**[Risk] 1 GB slot size insufficient** → If the NixOS system closure grows beyond 1 GB compressed, updates will fail.
Current image is ~333 MB compressed, leaving significant headroom. The initial 200 MB target proved unrealistic for
NixOS + Podman + networking stack. Mitigation: monitor image size in CI (build fails if squashfs exceeds 1 GB); the 1 GB
limit provides 3x headroom over current size.

**[Risk] Health manifest missing on first boot** → If the provisioner doesn't place the manifest, the confirmation
service marks good immediately. This is intentional for development but means an unprovisioned device in production
won't have container health checks. Mitigation: provisioning process must include manifest deployment; document this
requirement.

**[Risk] Cockpit/Traefik pod failure independent of rootfs** → Since Cockpit and Traefik run as pods rather than native
in the rootfs, container-layer failures (missing image, pull failure, OCI runtime error) could break the management
interface independently of the OS. Mitigation: the health-check confirmation service validates both pods via the health
manifest before committing a slot. The OpenVPN recovery path remains available in the rootfs. A debug rootful pod can be
deployed for emergency access.

**[Risk] python3Minimal insufficient for Cockpit bridge** → `python3Minimal` strips SSL, sqlite, readline, and other
modules. If a future Cockpit version requires these, the bridge will fail. Mitigation: `python3Minimal`'s
`allowedReferences` guard catches closure growth at build time. If full python3 is ever needed, the Cockpit pod approach
must be reconsidered.

**[Risk] Provisioning credential management** → EN18031 requires unique per-device passwords. The provisioning script
must create `/persist/config/admin-password-hash`, `/persist/config/ssh-authorized-keys/admin`, Traefik configuration,
and the health manifest. If these are missing, the device has no usable credentials or web access and requires
re-provisioning. Mitigation: provisioning script validates all credential and config files exist before completing.

**[Trade-off] No delta updates** → Full image writes use more bandwidth and take longer. Acceptable for initial version;
RAUC supports adaptive updates (casync) that can be added later.

**[Trade-off] No automated WAN SSH opening** → If Cockpit breaks at runtime (not during update), the only remote access
paths are VPN+SSH or manually enabling the SSH-on-WAN flag. The A/B update system with confirmation should prevent
Cockpit from being committed in a broken state, making runtime failures rare.

**[Trade-off] hawkBit deferred** → No staged rollouts, fleet visibility, or campaign management initially. Acceptable
because the device-side architecture supports hawkBit with a flag flip when ready.

**[Trade-off] Reduced /persist space** → Moving from 200 MB to 1 GB rootfs slots and 32 MB to 128 MB boot slots reduces
/persist from ~15 GB to ~13.3 GB. This is acceptable — 13.3 GB is still ample for container images, application data,
and logs. The boot partition increase was necessary because the uncompressed aarch64 kernel Image is ~63 MB.
