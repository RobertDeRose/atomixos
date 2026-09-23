# Provisioning

Deploy AtomixOS to a Rock64 device by building a [flashable disk image](./provisioning/flash-image.md) and writing it
to eMMC with `dd` (or `mise run flash`).

## After Provisioning

On first boot:

1. U-Boot loads `boot.scr` from boot-a, echoes build ID, boots the kernel with initrd
2. The initrd mounts the selected squashfs slot at `/run/rootfs-base`, then `sysroot.mount`
   assembles `/` as OverlayFS with a tmpfs-backed upper/work directory under `/run/overlay-root`
3. Initrd `systemd-repart` creates the `/data` partition (f2fs) on first boot using the remaining eMMC space
4. Initrd persists a fresh-flash marker so switched-root provisioning can distinguish a new flash from a later
   reprovisioned `/data` wipe
5. `first-boot.service` looks for `/boot/config.toml` only on a fresh flash, then USB `config.toml`, then starts the
   socket-activated bootstrap web console on WAN and LAN port `8080`; after provisioning the socket is rebound to the
   LAN gateway endpoint and first boot waits indefinitely for operator input when no seed is present
6. The imported config is validated, persisted under `/data/config/`, rendered into managed user inputs and canonical
   Quadlet files, and synced into the active rootful and rootless Quadlet paths
7. `first-boot.service` applies managed users, Quadlets, LAN settings, and provisioned firewall rules, then marks the
   RAUC slot as good only if those runtime apply steps succeed
8. Network interfaces come up (eth0 via DHCP, eth1 static); `systemd-networkd-wait-online` uses 30s timeout with `anyInterface=true`
9. Services start: dnsmasq, chrony, sshd, and the RAUC update timer when RAUC is enabled

The device is then ready to receive OTA updates and serve LAN clients.

For the canonical persisted state and runtime schemas, see [Firmware Data Flow](./data-flow.md) and
[Runtime Boundaries](./runtime-boundaries.md).

## Reprovisioning

Wiping `/data` returns the device to the unprovisioned state without changing the A/B slot layout.

On the next boot:

1. Initrd sees that `boot-b` already exists, so it does not mark the boot as a fresh flash
2. `/boot/config.toml` is not replayed
3. `first-boot.service` searches USB `config.toml` sources first
4. If no USB seed is found, the socket-activated bootstrap web console starts on WAN and LAN port `8080`

Imported operator state remains bounded to `/data/config/`, including the imported `config.toml`, rendered Quadlet
files, admin SSH authorized keys, and other provisioning-derived runtime inputs.

## Provisioning Service API

The bootstrap console is backed by a long-lived Litestar service running as the
unprivileged `atomixos-provision` user. API routes are grouped by domain but
still wired explicitly by the app factory:

| Route                                          | Behavior                                                                        |
|------------------------------------------------|---------------------------------------------------------------------------------|
| `GET /api/health`                              | Returns service liveness.                                                       |
| `GET /api/nonce`                               | Issues a single-use nonce for SSH-signature authentication.                     |
| `POST /api/validate`                           | Validates a `config.toml` or config bundle without applying it.                 |
| `POST /api/config`                             | Accepts a config source and returns `202 Accepted` with a job URL.              |
| `GET /api/config/export`                       | Returns the complete deterministic `config-bundle.tar.gz` archive.              |
| `PUT /api/config/users/{name}`                 | Creates or replaces a declared user and applies the full config.                |
| `DELETE /api/config/users/{name}`              | Removes a declared user and applies the full config.                            |
| `PATCH /api/config/network`                    | Merges network, LAN, NTP, DNS, and firewall fields and applies the full config. |
| `PUT /api/config/containers/{name}`            | Creates or replaces a declared Quadlet container.                               |
| `DELETE /api/config/containers/{name}`         | Removes a declared Quadlet container.                                           |
| `PUT /api/config/container-networks/{name}`    | Creates or replaces a declared Quadlet network.                                 |
| `DELETE /api/config/container-networks/{name}` | Removes a declared Quadlet network.                                             |
| `PUT /api/config/container-volumes/{name}`     | Creates or replaces a declared Quadlet volume.                                  |
| `DELETE /api/config/container-volumes/{name}`  | Removes a declared Quadlet volume.                                              |
| `GET /api/jobs/{job_id}`                       | Returns current provisioning job status, events, result, and rollback state.    |

### API authentication and transport

On a provisioned device, `/api/validate`, `/api/config`, all typed partial routes,
and `/api/config/export` require SSH-signature authentication. Clients request a
single-use nonce from `GET /api/nonce`, then sign:

```text
atomixos-reapply-v2
nonce:{nonce}
method:{request_method}
path:{request_path}
sha256:{payload_sha256_hex}
```

The request carries the base64 SSH signature in `X-AtomixOS-Signature` and the
nonce in `X-AtomixOS-Nonce`; nonces expire after five minutes and are single-use.
The method is uppercase. Nonces are scoped to the current boot so queued work
cannot carry authorization across a reboot.
Binary config submissions use `application/octet-stream` and identify the source
with `x-config-filename` (for example `config.toml` or `config.tar.zst`); the
server also detects supported archive magic bytes. Signatures cover the exact raw
request body. JSON partial requests sign their exact JSON body. A `GET` export has
an empty body, so its signed digest is SHA-256 of zero bytes. The export response is
`application/gzip` with a `config-bundle.tar.gz` attachment. The deterministic
archive contains only top-level `config.toml` and managed `files/` payloads; it
excludes generated runtime state, markers, signer material, and unrelated config
files. The live transport contract is available at `/schema/openapi.json`.

On production staged systems, mutating apply jobs are accepted into a bounded
FIFO queue and applied one at a time. Clients receive `409 Conflict` when the
queue is full, and otherwise poll the returned job URL for progress and final
status. Non-staged development/test config roots keep the direct single-flight
job guard. `POST /api/validate` always requires SSH-signature authentication;
provisioned-device re-apply through `POST /api/config` requires the same nonce
and signature headers, while first-boot programmatic config submission remains
unauthenticated.

On production systems, mutating jobs are staged by the unprivileged API under
`/run/atomixos-provision` after validation and candidate rendering. The staged
job also retains the exact request bytes and verified authorization envelope. A root-owned
`atomixos-provision-apply.path` unit watches ready markers and starts the
`atomixos-provision-apply.service` oneshot worker. The worker verifies the staged
manifest and tree, re-verifies the signature against the active administrator
keys, consumes the nonce in root-owned state, and reconstructs the requested
operation from the signed method, path, and body. It then renders verified state
into `/data/config-candidate` and performs promotion, activation, rollback, and
recovery. This keeps HTTP parsing unprivileged while preserving the same
operator-visible API responses and rollback behavior. Result handoff files are
root-writable/group-readable, and queue claim/abandon operations share a runtime
lock so timed-out queued jobs cannot race with the root worker claiming them.

Before initial provisioning, browser operators can use the Boot UI at `/` to
upload or drop a config bundle or `config.toml`. Browser submissions post to
`/apply` with the bootstrap CSRF token, receive an asynchronous job progress
view, and poll first-boot-only HTML fragments until the apply job succeeds or
fails. These UI routes are hidden from the live OpenAPI schema and are unavailable
after provisioning completes, except for the one-time terminal status fragment for
the job just submitted by the Boot UI.

Partial config endpoints always require SSH-signature authentication, including before initial
provisioning. Mutating partial endpoints load the current `/data/config/config.toml`, merge the typed
request into a full desired-state document, render canonical generated TOML, and submit that full
candidate through the same asynchronous validate/render/promote/activate/rollback job path as
`POST /api/config`. On staged production systems, partial endpoints require the staged queue to be
otherwise empty and return `409 Conflict` when another staged job is queued or active. They do not
mutate derived JSON, Quadlet, firewall, network, or user state
directly. The generated `config.toml` is the canonical desired-state member of the exported backup artifact; comments and
original TOML ordering are not preserved after a successful partial update. Bundle export also includes managed
`/data/config/files/` payloads and excludes generated runtime state, markers, signer material, and unrelated config
files. Managed payloads are installed read-only by default. Trusted integrators may deliberately mount `${FILES_DIR}`
writable; AtomixOS accepts the Quadlet configuration and emits a warning because any resulting changes are included in
later config exports. Mutable application data should normally use Podman volumes and is intentionally excluded from
config export. Use Podman tooling when volume data must be backed up, restored, or transferred; AtomixOS provisioning
does not own that runtime-data lifecycle. The archive can be imported through the same bundle importer into a clean
config root.

## USB Recovery Mode

If the reset button is held from power-on for 5 seconds, U-Boot enters USB
mass storage mode instead of booting Linux. The
Rock64 OTG USB port then exposes the full eMMC as a removable disk, allowing the host to write a fresh image directly.
