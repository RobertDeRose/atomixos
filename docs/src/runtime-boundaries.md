# Runtime Boundaries

AtomixOS separates immutable platform code from operator-provisioned runtime behavior.

## Immutable Platform

The image owns boot, kernel, initrd, RAUC, firewall defaults, SSH policy, local provisioning, LAN gateway services,
OpenVPN recovery plumbing, and update confirmation logic. These live in the active squashfs slot and are replaced only by
RAUC updates.

## Persistent Operator State

`/data/config/` owns runtime configuration imported during provisioning. RAUC slot writes do not modify `/data`.

Before initial provisioning, the bootstrap API is reachable on WAN and LAN and exposes `POST /api/config` for complete
`config.toml` files or supported config bundles. First-boot Boot UI submissions use a CSRF bootstrap token, not operator
authentication; first-boot programmatic `/api/config` submissions do not require that UI token. After provisioning, the
bootstrap API narrows to the LAN gateway endpoint. It uses the same validation, candidate promotion, activation, and
rollback path as the web console. Programmatic
clients receive `202 Accepted` with `job_id`, initial `state`, `job_url`, and a `Location: /api/jobs/{job_id}` header, then
poll the job resource for final success, failure, rollback status, and service deployment events.

Authenticated partial config endpoints are only another input to that same boundary. They load the
current desired `config.toml`, produce a complete candidate config, preserve existing bundle
`files/` payloads, and run the normal candidate promotion and activation path. They never edit
derived `/data/config/*.json`, Quadlet units, systemd drop-ins, firewall state, or users directly.
Successful partial updates rewrite `/data/config/config.toml` in generated canonical TOML form.

The API routes retain operation IDs and domain tags in code, and the production
bootstrap service exposes live OpenAPI schema routes for online clients. Response
bodies are typed in the provisioning package schemas while preserving the current
JSON shapes.

The accepted `config.toml` schema is:

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

[network.interfaces.eth0]
mode = "dhcp"

[network.interfaces.eth1]
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

WAN ports stay deny-by-default unless listed. LAN stays open by default; if `[network.firewall.inbound.lan]` is
present with any ports, LAN switches to an explicit allowlist for only those ports. `[network.dnsmasq]` is optional;
omitted fields use the fallback LAN gateway contract. `[network.ntp]` is optional and defaults to Cloudflare NTP.
Top-level `network.dns_servers`, `network.dns_search_domains`, `network.default_gateway`, and
`network.interfaces.<ethN>` are optional host network controls. Interface-specific DNS/search values override top-level
DNS/search values for that interface. Absence means no static gateway is rendered; empty gateway strings are invalid.
The top-level IPv4 default gateway applies to `eth0`; use an interface-specific IPv4 gateway for other Ethernet
interfaces. `eth1` must remain static because it is the LAN gateway.
The machine-readable schema is committed at
`schemas/config.schema.json` and the import path validates against it before semantic checks.

`[activation]` controls candidate activation and health-check behavior. `required` lists provisioned Quadlet services that
must become active. Optional `timeout_seconds`, `settle_seconds`, `restart`, and `allow_degraded` values render into
`/data/config/activation-policy.json`. Unit references are limited to declared container services; activation policy does
not allow arbitrary systemd unit manipulation. `strategy` currently supports only `rollback`, preserving fail-closed
candidate rollback on activation failure.

## Firewall JSON

`/data/config/firewall-inbound.json` is a JSON object with optional `wan` and `lan` objects. Each scope may contain
optional `tcp` and `udp` arrays of integer ports in `1..65535`.

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

Provisioned rules are added to WAN `eth0` or LAN `eth1` only when the matching scope is present. WAN remains
deny-by-default for new inbound traffic. LAN is open by default, but an explicit `lan` scope replaces that default-open
rule with the configured allowlist. Forwarding remains dropped.

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

The DHCP range must stay inside the gateway subnet, must be ordered, and must not include the gateway IP. Supported LAN
gateway prefixes are `/16` through `/30`.

`network.interfaces.eth1.address` and `network.dnsmasq.gateway_cidr` both describe the LAN gateway CIDR. If either is set,
the import path renders one effective LAN gateway CIDR into `lan-settings.json`; if both are set and differ, validation
fails before candidate promotion.

## Host Network JSON

`/data/config/host-network.json` is generated from `config.toml` and includes the validated host resolver, route, and
interface fields consumed by `lan-gateway-apply.py`. Top-level DNS/search/default-gateway values render into the generated
`10-wan.network` drop-in for `eth0` unless an explicit `eth0` value overrides them. Additional Ethernet interfaces render
as `30-atomixos-ethN.network` units when explicitly configured.

```json
{
  "dns_servers": ["1.1.1.1"],
  "dns_search_domains": ["lan.example"],
  "default_gateway": "192.0.2.1",
  "interfaces": {
    "eth0": {"mode": "dhcp"},
    "eth1": {
      "mode": "static",
      "address": "172.20.30.1/24",
      "dns_servers": ["172.20.30.1"],
      "dns_search_domains": ["lan"]
    }
  }
}
```

Only supported Ethernet names matching `ethN` are accepted. WiFi remains unsupported. Rendering these files does not add
firewall rules, NAT, IP forwarding, or FORWARD-chain exceptions.

## Activation Policy JSON

`/data/config/activation-policy.json` is generated from `[activation]` and consumed by the re-apply activation path.

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

The activation path runs the existing activation hook first, then applies configured provisioned-service restarts, waits
for `settle_seconds`, and checks required service health within `timeout_seconds`. Invalid rendered activation policy fails
closed through the normal rollback path. Legacy `health-required.json` remains as a compatibility input when no activation
policy file exists. `allow_degraded_configured` records whether the operator explicitly set `allow_degraded`; omitted
`allow_degraded` preserves the previous behavior of reporting but tolerating failed non-required services, while an
explicit list makes other failed non-required services fail activation.

## Quadlet Safety Boundary

Provisioned containers are rendered into canonical Quadlet files under `/data/config/quadlet/` before being synced into
Podman systemd search paths.

Rootful containers require `privileged = true` and are forced onto `Network=host`. Rootless containers use the `appsvc`
user, are forced onto `Network=pasta`, and non-loopback `PublishPort` binds are rewritten to `127.0.0.1`.

Bundle imports may include `files/`; Quadlet values may reference `${CONFIG_DIR}` and `${FILES_DIR}` to bind files from
`/data/config/` without embedding host-specific absolute paths in the seed.
