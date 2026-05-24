# LAN Range Configuration

The default LAN subnet is `172.20.30.0/24` with the gateway at `172.20.30.1`. Operators should change deployed devices by
setting `[network.dnsmasq]` or `[network.interfaces.eth1]` in `config.toml` and applying the config through the normal
candidate promotion path.

The `config:lan-range` mise task remains a development helper for changing built-in defaults in the image source before
a rebuild.

## Runtime Config

```toml
[network.dnsmasq]
gateway_cidr = "10.50.0.1/24"
dhcp_start = "10.50.0.10"
dhcp_end = "10.50.0.254"

[network.interfaces.eth1]
mode = "static"
address = "10.50.0.1/24"
```

If both `network.dnsmasq.gateway_cidr` and `network.interfaces.eth1.address` are present, they must match. If only one is
present, it becomes the effective LAN gateway CIDR for dnsmasq, chrony, DHCP options, and the eth1 address.

## Development Helper

```sh
mise run config:lan-range \
  --gateway-cidr 10.50.0.1/24 \
  --dhcp-start 10.50.0.10 \
  --dhcp-end 10.50.0.254
```

## What it Updates

The task modifies the built-in fallback LAN defaults used by development images:

| File                      | What Changes                                                                                             |
|---------------------------|----------------------------------------------------------------------------------------------------------|
| `modules/lan-gateway.nix` | fallback eth1 `Address`, dnsmasq `dhcp-range`, DHCP options 3/6/42, gateway hosts, chrony `allow` subnet |

## After Changing

Rebuild:

```sh
mise run check
mise run build
```

## Constraints

- Runtime config supports `/16` through `/30` LAN gateway prefixes
- DHCP start and end addresses must be within the specified subnet
- The gateway address (first part of `--gateway-cidr`) is used as the static IP for eth1
