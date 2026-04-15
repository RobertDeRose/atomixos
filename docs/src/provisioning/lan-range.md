# LAN Range Configuration

The default LAN subnet is `172.20.30.0/24` with the gateway at `172.20.30.1`. To change this, use the `config:lan-range`
mise task, which updates all configuration files in a single command.

## Usage

```sh
mise run config:lan-range \
  --gateway-cidr 10.50.0.1/24 \
  --dhcp-start 10.50.0.10 \
  --dhcp-end 10.50.0.254
```

## What it Updates

The task modifies four files to keep the LAN configuration consistent:

| File                         | What Changes                                                                               |
|------------------------------|--------------------------------------------------------------------------------------------|
| `modules/networking.nix`     | eth1 static `Address`                                                                      |
| `modules/lan-gateway.nix`    | dnsmasq `dhcp-range`, gateway DHCP option (3), NTP DHCP option (42), chrony `allow` subnet |
| `scripts/os-verification.sh` | Expected eth1 IP in health checks                                                          |

## After Changing

Rebuild:

```sh
mise run check
mise run build:image
```

## Constraints

- Only `/24` subnets are currently supported
- DHCP start and end addresses must be within the specified subnet
- The gateway address (first part of `--gateway-cidr`) is used as the static IP for eth1
