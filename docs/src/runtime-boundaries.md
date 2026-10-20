# Runtime Boundaries

AtomixOS draws hard lines between what the image owns, what the operator provisions, and which process may change what.
This page states those lines and the rules that enforce them. [Data Flow](data-flow.md) shows the same pieces in motion.

## Immutable Platform

The image owns boot, the kernel and initrd, RAUC, firewall defaults, SSH policy, local provisioning, the LAN gateway
services, the optional Nixstasis client, and update confirmation. All of it lives in the
active squashfs slot and changes only through a RAUC update.

## Persistent Operator State

`/data/config/` holds the runtime configuration imported by provisioning. RAUC never writes to `/data`.

The Nixstasis client, when enabled, is image code, not a provisioned container. Its identity, remote-access keys, and
scratch state live in `/data/nixstasis/`, so remote access survives slot switches without mixing into `/data/config`.
The commands Nixstasis may run on the device come from an allowlist fixed in the image, and that list is empty by
default.

## Bootstrap Transport

`build.toml` chooses how the provisioning API is reached before and after provisioning:

| Transport           | Before provisioning                            | After provisioning                       |
|---------------------|------------------------------------------------|------------------------------------------|
| `network` (default) | WAN and LAN, port `8080`                       | The provisioned LAN gateway address only |
| `nixstasis`         | `127.0.0.1:8080`, through the Nixstasis tunnel | `127.0.0.1:8080`                         |

Fleet mode adds no network fallback and never opens the WAN bootstrap port. The tunnel starts only after the device is
approved and Nixstasis grants a separate `remote_access_token` lease; see
[Nixstasis Enrollment](architecture/nixstasis-enrollment.md).

The API is socket-activated. `atomixos-bootstrap.socket` owns the listen address, and `atomixos-bootstrap.service` only
uses the socket it inherits from systemd.

The first-boot Boot UI is a browser wrapper around the same API. Uploads go through `/apply`, protected by a bootstrap
CSRF token and browser origin checks rather than operator authentication; programmatic `POST /api/config` calls on first
boot do not need that token. The Boot UI is not a management interface. After the first successful provisioning, only a
one-time result page for the submitted job stays readable, and nothing else in the UI accepts changes.

## Provisioning Privilege Boundary

The network-facing API runs as the unprivileged `atomixos-provision` user. It validates requests, authenticates
re-applies, renders candidates in tmpfs, and reads approved provisioning state. It never changes the host. Root-written
`/data/config` state is group-readable by `atomixos-provision` for this reason, except the owner-only apply receipt.

Host changes belong to a root worker, `atomixos-provision-apply.service`, started by a systemd path unit watching
`/run/atomixos-provision/queue/*.ready`:

- **Staging.** The API writes a complete candidate tree, the validated bundle files, and a manifest of relative paths,
  owners, modes, sizes, and SHA-256 hashes under `/run/atomixos-provision`. It then publishes a ready marker using the
  same queue reservation that fixed its position. Reservations are refreshed while staging, so slow imports keep their
  place; expired ones remove unpublished staging.
- **Queue.** Jobs run one at a time in first-in, first-out order. A full queue answers `409 Conflict`.
- **Verification.** The worker checks every manifest path, owner, mode, hash, and expected entry, rejects symlinks and
  anything that is not a regular file, and enforces the source size limit before it reads the staged request. It reads
  without blocking, so a FIFO planted in the staging tree cannot stall it.
- **Re-rendering.** The worker re-renders `/data/config-candidate` from the verified, signed request bytes instead of
  trusting the API's candidate.

Only the worker, and maintenance commands run with `ATOMIXOS_PROVISION_WORKER_ACTIVE=1`, write `/data/config`
directly. Partial-update endpoints are just another input to this boundary; they never edit derived JSON, Quadlet units,
systemd drop-ins, firewall state, or users themselves. A successful partial update rewrites `config.toml` in canonical
generated form.

The API keeps operation IDs and tags on every route, and the running service publishes its live OpenAPI schema.

## Apply Transactions and Finalization

Before promotion, the worker writes a root-only apply receipt into the candidate. The receipt ties the job ID and the
source digest to the transaction's phase and result:

- `promoted` means the candidate is in place but not yet proven.
- `committed` means activation and health checks passed. Only this phase proves success.

The worker removes a claimed job only after its result file is written. If it stops part-way, its finalizer looks at
the receipt and:

- discards an interrupted first apply,
- rolls back an interrupted re-apply, or
- finishes cleanup for a committed apply,

then compares the receipt with the claimed manifest before publishing the authoritative result.

Recovery follows these rules:

- A rollback merges the failed and restored managed-user lists before removing the failed tree, and reactivates the
  restored configuration before publishing the result. Rollback activation failures are included in that result.
- A durable marker spans a rollback from restore through reactivation, so an interrupted rollback activation is rerun.
- Recovery at boot leaves activation and WAN reconciliation to the services that run after it, and never waits on them.
- Recovery in the same boot finishes transport work first: it retries the WAN firewall reconciliation for a first apply
  and the delayed move to the LAN gateway address for a re-apply, then publishes the result. These follow-ups run only
  while the matching job is still unpublished, and never again afterwards. Fleet mode never schedules a move to the LAN
  address.
- A client polling for results may abandon only a job that has not been claimed. A claimed job stays open until the
  worker or its finalizer publishes the result. Result read errors are retried and fail the wait only if they persist
  for a full reconciliation interval.

The apply service has 3900 seconds to stop, which covers the 3600-second activation budget plus recovery.
`atomixos-provision-apply-retry.timer` restarts the service 30 seconds after each run, because claiming a job removes
its `.ready` trigger; the service starts only while a ready job or an active claim exists.

Result files in `/run/atomixos-provision/results` are writable by root and readable by the API group only. Claiming
and abandoning queued jobs share `/run/atomixos-provision/queue.lock`.

## Bundle Export

Exports run in a separate root service, `atomixos-provision-export.service`, triggered by
`atomixos-provision-export.path`. The API sends only empty, UUID-named request files, never paths or commands. The
worker has no network access and cannot write `/data`; it can still read files a workload has re-owned, without the API
needing root.

The archive:

- contains only `config.toml` and `files/`, snapshotted under the provisioning lock;
- omits `files/` when it does not exist, and stores an existing empty `files/` as an empty directory entry;
- contains only relative, single-link regular files and empty directories, and rejects symlinks, hard links, and
  special files;
- stays within the importer's size, member, and count limits while it is being written, even if a file grows during the
  copy.

The worker's run is limited to 120 seconds (`TimeoutStartSec`), and its finalizer, which records interrupted requests
as failures, has a separate 60-second limit (`TimeoutStopSec`). A request stays claimed until its archive or error is
published, so a failed result write is retried by the finalizer or the next worker run. While the worker is idle,
`atomixos-provision-export.timer` runs cleanup every minute and expires abandoned requests, acknowledgements, and
results after five minutes (`RETENTION_SECONDS` in `export_worker.py`). All export state is boot-local, under
`/run/atomixos-provision/export`. The API-side limits are listed under
[Export a configuration](provisioning.md#export-a-configuration).

## The config.toml Contract

The machine-readable schema is `schemas/config.schema.json`. The importer validates against it with the Draft 2020-12
`jsonschema` validator, then normalizes the values and checks rules that span fields. A complete example:

```toml
version = 1

[users.admin]
isAdmin = true
ssh_key = "ssh-ed25519 ..."

[network.firewall.inbound.wan]
tcp = [443]
udp = [1194]

[network]
dns_servers = ["1.1.1.1"]
dns_search_domains = ["lan.example"]
default_gateway = "192.0.2.1"

[network.interfaces.wan]
mode = "dhcp"

[network.interfaces.lan]
mode = "static"
address = "172.20.30.1/24"

[network.dnsmasq]
gateway_cidr = "172.20.30.1/24"
dhcp_start = "172.20.30.10"
dhcp_end = "172.20.30.254"
domain = "local"
gateway_aliases = ["atomixos"]
hostname_pattern = "atomixos-{mac}"

[network.ntp]
servers = ["time.cloudflare.com"]

[activation]
required = ["myapp"]
timeout_seconds = 300
settle_seconds = 0
restart = []
allow_degraded = []
strategy = "rollback"

[containers.container.myapp]
privileged = false

[containers.container.myapp.Container]
Image = "ghcr.io/example/myapp:latest"
PublishPort = ["10080:8080"]
```

- **Firewall.** WAN ports stay closed unless listed. LAN stays open unless `[network.firewall.inbound.lan]` lists ports,
  which turns it into an allowlist.
- **LAN gateway.** `[network.dnsmasq]` is optional; missing fields use the default LAN gateway. `[network.ntp]` is
  optional and defaults to Cloudflare NTP.
- **Host network.** `network.dns_servers`, `network.dns_search_domains`, `network.default_gateway`, and
  `network.interfaces.<name>` are optional. Interface DNS and search values override the top-level ones for that
  interface. The top-level IPv4 default gateway applies to `wan`; set a per-interface gateway for other interfaces.
  With no gateway set, none is rendered, and an empty gateway string is invalid. `lan` must stay static because it is
  the LAN gateway.
- **Activation.** `required` names provisioned container services that must become active. `timeout_seconds`,
  `settle_seconds`, `restart`, and `allow_degraded` are optional. Units may only be declared container services, never
  arbitrary systemd units. `strategy` accepts only `rollback`, so a failed activation always rolls back.

## Firewall JSON

`/data/config/firewall-inbound.json` has optional `wan` and `lan` objects, each with optional `tcp` and `udp` arrays of
ports from `1` to `65535`:

```json
{
  "wan": {
    "tcp": [443],
    "udp": [1194]
  },
  "lan": {
    "tcp": [443]
  }
}
```

Rules are added to the `wan` or `lan` interface only for scopes that are present. Forwarding stays dropped.

## LAN JSON

`/data/config/lan-settings.json` is generated from `config.toml` and read by `lan-gateway-apply.py`:

```json
{
  "gateway_cidr": "172.20.30.1/24",
  "gateway_ip": "172.20.30.1",
  "subnet_cidr": "172.20.30.0/24",
  "netmask": "255.255.255.0",
  "dhcp_start": "172.20.30.10",
  "dhcp_end": "172.20.30.254",
  "domain": "local",
  "hostname_pattern": "atomixos-{mac}",
  "gateway_aliases": ["atomixos"]
}
```

The DHCP range must sit inside the gateway subnet, run from low to high, and leave out the gateway address. Gateway
prefixes from `/16` to `/30` are supported. Both `network.interfaces.lan.address` and `network.dnsmasq.gateway_cidr`
describe the LAN gateway; if both are set and differ, validation fails before anything is promoted.

## Host Network JSON

`/data/config/host-network.json` is generated from `config.toml` and also read by `lan-gateway-apply.py`. Top-level
DNS, search, and gateway values go into the generated `10-wan.network` drop-in for `wan` unless a `wan` value
overrides them. Other configured Ethernet interfaces get `30-atomixos-ethN.network` units.

```json
{
  "dns_servers": ["1.1.1.1"],
  "dns_search_domains": ["lan.example"],
  "default_gateway": "192.0.2.1",
  "interfaces": {
    "wan": {"mode": "dhcp"},
    "lan": {
      "mode": "static",
      "address": "172.20.30.1/24",
      "dns_servers": ["172.20.30.1"],
      "dns_search_domains": ["lan"]
    }
  }
}
```

Interface keys are `wan` and `lan` for the built-in roles, and `ethN` for additional Ethernet interfaces. A key that
names the physical WAN or LAN interface, such as `eth0` on QEMU, is rejected; use `wan` or `lan`. Wi-Fi is not
supported. These files never add firewall rules, NAT, IP forwarding, or forward-chain exceptions.

## Activation Policy JSON

`/data/config/activation-policy.json` is generated from `[activation]`:

```json
{
  "required": ["myapp"],
  "timeout_seconds": 300,
  "settle_seconds": 0,
  "restart": [],
  "allow_degraded": [],
  "allow_degraded_configured": false,
  "strategy": "rollback"
}
```

Activation runs the standard activation hook, restarts the listed services, waits `settle_seconds`, and then checks the
required services within `timeout_seconds`. An invalid policy fails closed and rolls back. When no policy file exists,
the older `health-required.json` is used instead.

`allow_degraded_configured` records whether `allow_degraded` was set. If it was left out, failed services that are not
required are reported but tolerated. If it was set, any failed service that is neither required nor listed fails the
activation.

## Quadlet Safety Boundary

Containers are rendered into canonical Quadlet files under `/data/config/quadlet/` and then synced into Podman's
systemd search paths:

- **Rootful containers** need `privileged = true` and always use `Network=host`.
- **Rootless containers** run as `appsvc`, always use `Network=pasta`, and have every non-loopback `PublishPort`
  rewritten to `127.0.0.1`.

Bundles may include `files/`, and Quadlet values may use `${CONFIG_DIR}` and `${FILES_DIR}` to mount files from
`/data/config/` without hard-coding host paths.

An admin who can sign configuration is a device administrator. A signed configuration may define rootful or rootless
workloads with any supported Quadlet or Podman option, including privileged ones. Authentication decides who holds that
power; the renderer checks structure and platform rules, not workload policy.

## Managed-file Access

Bundle `files/` are deployment inputs and are installed read-only unless a mount asks for write access:

| Mode                | Owner and group              | Directories | Files  | ACL                      |
|---------------------|------------------------------|-------------|--------|--------------------------|
| Read-only (default) | `root`, `atomixos-provision` | `0550`      | `0440` | Read access for `appsvc` |
| Writable            | `appsvc`                     | `0750`      | `0640` | None                     |

The named-user ACL lets rootless containers read the files even though they drop host supplementary groups, and it
keeps workloads from changing modes or ownership. `/data` must support POSIX ACLs; if an ACL cannot be applied,
reconciliation fails.

Reconciliation works on verified file descriptors and never follows symlinks:

- it rejects symlinks and special files;
- it counts every file and directory under `files/` against the bundle's member limit (4096 by default) and fails
  before changing anything in an oversized tree;
- it rejects directories nested more than 64 levels below `files/`.

A trusted integrator may request writable `Volume`, `Mount`, or `PodmanArgs` access. The renderer keeps that
configuration and warns when a mount overlaps managed files without being clearly read-only:

- Overlap includes mounts of `${CONFIG_DIR}` or any other ancestor, as well as `${FILES_DIR}` and anything under it.
- Paths are normalized lexically, without following symlinks; `/` and `//` prefixes are treated alike.
- A `type=glob` mount is judged by the directory before its first wildcard, so `${CONFIG_DIR}/*` covers `files/`.
- `PodmanArgs` are parsed as combined or separate arguments, with quoting, including attached forms such as
  `-v${FILES_DIR}/state:/state:rw`. Warnings name the directive they came from.

Named volumes, single-field anonymous volumes such as `Volume=/data/config/files` (a container path, not a host
source), and `type=volume` mounts never touch managed host files. Host bind sources must be absolute or start with
`${CONFIG_DIR}` or `${FILES_DIR}`. Relative sources are rejected in `Volume=`, bind `Mount=`, and `PodmanArgs`, because
Quadlet and Podman would resolve them from different directories. A `Volume=` source containing `/` counts as a path,
since volume names cannot contain `/`, so `data/state:/state` is rejected too.

Writable application state belongs in Podman named volumes. Back it up and restore it with Podman tools; it is not part
of AtomixOS provisioning.
