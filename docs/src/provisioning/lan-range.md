# LAN Range

The LAN side defaults to the `172.20.30.0/24` subnet, with the device at `172.20.30.1` and DHCP leases from
`172.20.30.10` to `172.20.30.254`. Change it per device in `config.toml`; change the built-in default only when you
build your own images.

## Change the range on a device

1. Set the gateway address, and optionally the DHCP range, in `config.toml`:

   ```toml
   [network.dnsmasq]
   gateway_cidr = "10.50.0.1/24"
   dhcp_start = "10.50.0.10"
   dhcp_end = "10.50.0.254"

   [network.interfaces.lan]
   mode = "static"
   address = "10.50.0.1/24"
   ```

2. Apply the configuration as usual, either when you [provision](../provisioning.md) the device or as a signed change.

You can set the gateway in either `network.dnsmasq.gateway_cidr` or `network.interfaces.lan.address`. If you set both,
they must match. The resulting address is used for the `lan` interface, the DHCP and DNS server, the NTP server, and
the router, DNS, and NTP options handed to LAN clients. After the change, the provisioning console and API listen on
the new gateway address, port `8080`.

The configuration is rejected unless:

- the gateway prefix is between `/16` and `/30`;
- the DHCP start and end addresses lie inside the gateway's subnet, and the start is not after the end;
- the DHCP range does not include the gateway address.

## Change the built-in default

The fallback range for images you build lives in `defaults/lan.json`. Change it with the `config:lan-range` task, then
validate and rebuild:

```sh
mise run config:lan-range \
  --gateway-cidr 10.50.0.1/24 \
  --dhcp-start 10.50.0.10 \
  --dhcp-end 10.50.0.254
mise run check
mise run build --board <board>
```

The task rewrites only the gateway, subnet, and DHCP fields in `defaults/lan.json`. A `config.toml` setting still
overrides the default on each device.
