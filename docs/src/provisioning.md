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
   bootstrap web console on WAN and LAN port `8080`; after provisioning it narrows to the LAN gateway endpoint
   and waits indefinitely for operator input when no seed is present
6. The imported config is validated, persisted under `/data/config/`, rendered into canonical Quadlet files, and synced
   into the active rootful and rootless Quadlet paths
7. `first-boot.service` applies Quadlets, LAN settings, and provisioned firewall rules, then marks the RAUC slot as good
   only if those runtime apply steps succeed
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
4. If no USB seed is found, the bootstrap web console starts on WAN and LAN port `8080`

Imported operator state remains bounded to `/data/config/`, including the imported `config.toml`, rendered Quadlet
files, admin SSH authorized keys, and other provisioning-derived runtime inputs.

## Provisioning Service API

The bootstrap console is backed by a long-lived Litestar service. API routes are
grouped by domain but still wired explicitly by the app factory:

| Route                                          | Behavior                                                                        |
|------------------------------------------------|---------------------------------------------------------------------------------|
| `GET /api/health`                              | Returns service liveness.                                                       |
| `GET /api/nonce`                               | Issues a single-use nonce for SSH-signature authentication.                     |
| `POST /api/validate`                           | Validates a `config.toml` or config bundle without applying it.                 |
| `POST /api/config`                             | Accepts a config source and returns `202 Accepted` with a job URL.              |
| `GET /api/config/export`                       | Returns the current canonical `config.toml` bytes.                              |
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

Mutating apply jobs are single-flight. Clients poll the returned job URL for
progress and final status. `POST /api/validate` always requires SSH-signature
authentication; provisioned-device re-apply through `POST /api/config` requires
the same nonce and signature headers, while first-boot programmatic config
submission remains unauthenticated.

Before initial provisioning, browser operators can use the Boot UI at `/` to
upload a config bundle or paste `config.toml`. Browser submissions post to
`/apply` with the bootstrap CSRF token, receive an asynchronous job progress
view, and poll first-boot-only HTML fragments until the apply job succeeds or
fails. These UI routes are hidden from the live OpenAPI schema and are unavailable
after provisioning completes, except for the one-time terminal status fragment for
the job just submitted by the Boot UI.

Partial config endpoints always require SSH-signature authentication, including before initial
provisioning. Mutating partial endpoints load the current `/data/config/config.toml`, merge the typed
request into a full desired-state document, render canonical generated TOML, and submit that full
candidate through the same asynchronous validate/render/promote/activate/rollback job path as
`POST /api/config`. They do not mutate derived JSON, Quadlet, firewall, network, or user state
directly. The generated `config.toml` remains the exported backup artifact; comments and original TOML
ordering are not preserved after a successful partial update.

## USB Recovery Mode

If the reset button is held from power-on for 5 seconds, U-Boot enters USB
mass storage mode instead of booting Linux. The
Rock64 OTG USB port then exposes the full eMMC as a removable disk, allowing the host to write a fresh image directly.
