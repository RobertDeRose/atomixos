# Provisioning

An AtomixOS image ships with no credentials and no operator account. You give each device its identity, users, network
settings, and containers by provisioning it with one `config.toml`, or with a config bundle that holds `config.toml`
plus a `files/` directory of payloads that the containers mount.

To get a device ready:

1. [Flash an image](provisioning/flash-image.md) to the eMMC.
2. Provision it from one of the sources below.
3. Change it later through the signed provisioning API, or reprovision it from scratch.

Fleet images take their first configuration from Nixstasis instead; see [Fleet Bootstrap](provisioning/fleet-bootstrap.md).

## Provision a new device

On first boot, `first-boot.service` looks for configuration in this order and uses the first one it finds:

1. **`/boot/config.toml`.** After flashing, copy `config.toml` onto the `boot-a` FAT partition. It is read only on the
   first boot after a fresh flash, so it is never replayed later.
2. **A USB stick.** Plug in a USB storage device with a labeled filesystem that has `config.toml` at its root. USB
   discovery reads only a plain `config.toml`, not a bundle archive.
3. **The bootstrap console.** If neither seed is present, the device waits for you. Open `http://<device-ip>:8080/` from
   the WAN or LAN side and drop a `config.toml` or a bundle onto the page. Scripts can instead `POST` the same file to
   `/api/config`, as described in [Change a provisioned device](#change-a-provisioned-device); no signature is needed
   before the first configuration is applied.

Bundles are tar archives compressed with gzip (`.tar.gz`, `.tgz`) or zstd (`.tar.zst`, `.tar.zstd`, `.tzst`).
Containers reach bundle payloads through the `${FILES_DIR}` token, and the payloads are mounted read-only unless you
deliberately mount them writable. Use Podman's own spelling for mount options (`ro`, `rw`, `U`, `z`, `Z`); a
misspelled option such as `RO` is rejected. [Runtime Boundaries](runtime-boundaries.md#managed-file-access) has the full
rules.

The device then validates the configuration, saves it under `/data/config/`, creates the declared users, renders the
Quadlet containers, and applies the LAN and firewall settings. It marks the new A/B slot as good only if every step
succeeds. Once provisioned, the bootstrap console and API stop listening on the WAN side and move to the LAN gateway
address, port `8080`.

To confirm the result, sign in as an admin user you declared, with its SSH key:

```sh
ssh admin@<device-ip>
```

[Data Flow](data-flow.md) lists every file the device derives from your configuration.

## Change a provisioned device

Once a device is provisioned, every change goes through the provisioning API and must be signed with the SSH key of an
admin user from the active configuration. Each request:

1. Gets a single-use nonce from `GET /api/nonce`. A nonce expires after five minutes, is spent by any attempt, and is
   valid only until the device reboots.
2. Signs this message with `ssh-keygen -Y sign -n atomixos-reapply`. The method is uppercase, the path is the request
   path, and the digest is the hex SHA-256 of the exact request body (an empty body for `GET`):

   ```text
   atomixos-reapply-v2
   nonce:{nonce}
   method:{method}
   path:{path}
   sha256:{payload_sha256_hex}
   ```

3. Sends the nonce in `X-AtomixOS-Nonce` and the base64-encoded signature file in `X-AtomixOS-Signature`.

For example, to apply a new `config.toml` from a workstation on the LAN:

```sh
device=http://172.20.30.1:8080
key=~/.ssh/id_ed25519
body=config.toml
path=/api/config

nonce=$(curl -fsS "$device/api/nonce" | jq -r .nonce)
digest=$(shasum -a 256 "$body" | cut -d' ' -f1)
signature=$(printf 'atomixos-reapply-v2\nnonce:%s\nmethod:POST\npath:%s\nsha256:%s\n' "$nonce" "$path" "$digest" \
  | ssh-keygen -Y sign -f "$key" -n atomixos-reapply | base64 | tr -d '\n')

curl -fsS -X POST "$device$path" \
  -H 'Content-Type: application/octet-stream' \
  -H "x-config-filename: $body" \
  -H "X-AtomixOS-Nonce: $nonce" \
  -H "X-AtomixOS-Signature: $signature" \
  --data-binary @"$body"
```

The response is `202 Accepted` with a `job_id`, a `state`, and a `job_url` such as `/api/jobs/<job_id>`. Poll the job
until its state is `succeeded` or `failed`; it also reports each step and whether a rollback ran.

A change never edits the running configuration in place. The device builds a complete candidate, swaps it in, restarts
what changed, and runs the health checks. If any step fails, it restores the previous configuration and activates it
again. Changes are applied one at a time; when the queue is full the API answers `409 Conflict`. A queued change that
still has not started after 3,900 seconds, with nothing ahead of it, fails as timed out.

### API routes

| Route                                          | What it does                                                            |
|------------------------------------------------|-------------------------------------------------------------------------|
| `GET /api/health`                              | Reports that the service is running.                                    |
| `GET /api/nonce`                               | Issues a single-use nonce for signing.                                  |
| `POST /api/validate`                           | Validates a `config.toml` or bundle without applying it. Always signed. |
| `POST /api/config`                             | Applies a `config.toml` or bundle and returns a job.                    |
| `GET /api/config/export`                       | Downloads the current configuration as a bundle.                        |
| `PUT /api/config/users/{name}`                 | Creates or replaces a user.                                             |
| `DELETE /api/config/users/{name}`              | Removes a user.                                                         |
| `PATCH /api/config/network`                    | Merges network, LAN, NTP, DNS, and firewall settings.                   |
| `PUT /api/config/containers/{name}`            | Creates or replaces a Quadlet container.                                |
| `DELETE /api/config/containers/{name}`         | Removes a Quadlet container.                                            |
| `PUT /api/config/container-networks/{name}`    | Creates or replaces a Quadlet network.                                  |
| `DELETE /api/config/container-networks/{name}` | Removes a Quadlet network.                                              |
| `PUT /api/config/container-volumes/{name}`     | Creates or replaces a Quadlet volume.                                   |
| `DELETE /api/config/container-volumes/{name}`  | Removes a Quadlet volume.                                               |
| `GET /api/jobs/{job_id}`                       | Returns a job's state, events, result, and rollback status.             |

The device serves the full OpenAPI description at `/schema/openapi.json`.

The typed `PUT`, `PATCH`, and `DELETE` routes always need a signature, even before the first configuration. They load
the current `config.toml`, merge your change, and apply the whole result like `POST /api/config`. Two consequences
follow:

- They are accepted only when no other change is queued or running; otherwise they return `409 Conflict`.
- The device rewrites `config.toml` in canonical form, so comments and the original key order are lost.

## Export a configuration

`GET /api/config/export` (signed, with an empty body) returns `config-bundle.tar.gz`. It contains only `config.toml` and
the managed `files/` directory, and the device's importer accepts it as-is, so you can use it to copy a configuration to
another device.

Keep these limits in mind:

- **It is not a backup.** Container data in Podman volumes is not included; back that up with Podman tooling.
- **It can contain secrets.** Anything in `config.toml` or `files/`, such as TLS private keys, is in the archive.
- **Writes are not paused.** The export waits for any running change to finish, but containers keep writing. Stop
  workloads first if you need an application-consistent copy of writable managed files.
- **It fails rather than truncates.** A tree over the importer's size or member limits, or one that contains symbolic
  links, hard links, or special files, fails with an error.

The API answers `409` when four exports are already pending, `500` when the export fails, and `504` when no result
arrives within 130 seconds. To investigate a failure:

```sh
journalctl -u atomixos-provision-export.service
systemctl status atomixos-provision-export.path atomixos-provision-export.timer
```

## Reprovision a device

To return a device to the unprovisioned state, wipe `/data` and reboot. The A/B slots are untouched. On the next boot
`/boot/config.toml` is not replayed, so the device takes a USB `config.toml` if one is plugged in, and otherwise waits
at the bootstrap console on port `8080`.

## Recover a device

**Rewrite the eMMC over USB.** U-Boot can expose the whole eMMC as a USB mass-storage disk on the board's OTG port, so
you can [flash a new image](provisioning/flash-image.md) to it from your workstation:

- **Any board, from a running device:** run `boot_to_ums` as root. It sets `START_UMS=1` in the U-Boot environment and
  reboots. U-Boot checks the flag before choosing a slot, so it works even when the selected slot cannot boot.
- **Rock64, with no login:** hold the reset button from power-on for five seconds. The CM3 has no button trigger; use
  `boot_to_ums`, set `START_UMS=1` from the U-Boot prompt, or fall back to Rockchip Maskrom recovery.

[Flash an Image](provisioning/flash-image.md#usb-mass-storage) explains how a host eject ends the session.

**Get a root shell on the serial console.** The image keeps `root` locked. On every board, set the U-Boot environment
variable `_RUT_OH_=1` (for example with `fw_setenv _RUT_OH_ 1`); on the next boot the debug UART (UART2, `ttyS2`,
1,500,000 baud) logs in as root instead of showing a login prompt. The variable is cleared as soon as it is used, so it
applies to one boot only. [Physical Recovery](architecture/authentication.md#physical-recovery) covers the details.

**Recover an interrupted change.** If the device loses power or the worker stops in the middle of a change, the change
is finished or rolled back on the next run, and its job reports the real outcome. You do not need to clean anything up.
[Runtime Boundaries](runtime-boundaries.md#apply-transactions-and-finalization) describes how.
