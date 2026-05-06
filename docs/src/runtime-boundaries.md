# Runtime Boundaries

AtomixOS separates immutable platform code from operator-provisioned runtime behavior.

## Immutable Platform

The image owns boot, kernel, initrd, RAUC, firewall defaults, SSH policy, local provisioning, LAN gateway services,
OpenVPN recovery plumbing, and update confirmation logic. These live in the active squashfs slot and are replaced only by
RAUC updates.

## Persistent Operator State

`/data/config/` owns runtime configuration imported during provisioning. RAUC slot writes do not modify `/data`.

The bootstrap API is LAN-local and exposes `POST /api/config` for complete `config.toml` files or supported config
bundles. It uses the same validation and persistence path as the web console and returns JSON success or validation
errors for programmatic clients.

The accepted `config.toml` schema is:

```toml
version = 1

[admin]
ssh_keys = ["ssh-ed25519 ..."]

[firewall.inbound]
tcp = [443]
udp = [1194]

[lan]
gateway_cidr = "172.20.30.1/24"
dhcp_start = "172.20.30.10"
dhcp_end = "172.20.30.254"
domain = "local"
gateway_aliases = ["atomixos"]
hostname_pattern = "atomixos-{mac}"

[health]
required = ["myapp"]

[container.myapp]
privileged = false

[container.myapp.Container]
Image = "ghcr.io/example/myapp:latest"
PublishPort = ["10080:8080"]
```

`[firewall.inbound]` is required and must contain at least one TCP or UDP port. `[lan]` is optional; omitted fields use
the fallback LAN gateway contract.

## Firewall JSON

`/data/config/firewall-inbound.json` is a JSON object with optional `tcp` and `udp` arrays of integer ports in
`1..65535`.

```json
{
  "tcp": [443],
  "udp": [1194]
}
```

Provisioned rules are added only on WAN `eth0`. The baseline firewall remains deny-by-default for new eth0 inbound
traffic and drops all forwarding.

## LAN JSON

`/data/config/lan-settings.json` is generated from `config.toml` and includes the validated runtime fields consumed by
`lan-gateway-apply.py`.

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

The DHCP range must stay inside the `/24` gateway subnet, must be ordered, and must not include the gateway IP.

## Quadlet Safety Boundary

Provisioned containers are rendered into canonical Quadlet files under `/data/config/quadlet/` before being synced into
Podman systemd search paths.

Rootful containers require `privileged = true` and are forced onto `Network=host`. Rootless containers use the `appsvc`
user, are forced onto `Network=pasta`, and non-loopback `PublishPort` binds are rewritten to `127.0.0.1`.

Bundle imports may include `files/`; Quadlet values may reference `${CONFIG_DIR}` and `${FILES_DIR}` to bind files from
`/data/config/` without embedding host-specific absolute paths in the seed.
