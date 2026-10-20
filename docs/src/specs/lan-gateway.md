# LAN Gateway

Acceptance contract for interface naming, LAN services, isolation, and the firewall. The design is explained in
[Network Topology](../architecture/network-topology.md).

## Requirements

### Deterministic NIC naming

On hardware, the onboard Ethernet is always named `wan` and the USB Ethernet adapter `lan`, regardless of probe order.
Wi-Fi is not supported. The per-board `.link` matches are listed in
[NIC Naming](../architecture/network-topology.md#nic-naming). The QEMU target keeps `wan` and `lan`.

#### Scenario: Onboard Ethernet is wan

- Given a Rock64 or CM3 boots with onboard Ethernet connected
- Then `ip link` shows `wan` as the onboard GMAC
- Regardless of USB device enumeration order

### wan is the WAN DHCP client

The WAN interface gets its address over DHCPv4 and uses the DHCP-provided DNS servers. IPv6 router advertisements are
ignored.

#### Scenario: WAN gets a DHCP address

- Given `wan` is connected to a network with a DHCP server
- When the device boots
- Then `wan` has an IPv4 address
- And DNS resolution works

### lan is the LAN with a static address

The LAN interface uses the static address from the provisioned LAN settings and runs no DHCP client.
`network.dnsmasq.gateway_cidr` and `network.interfaces.lan.address` describe the same LAN gateway CIDR; when both are
set they must match before the config is promoted. Without valid provisioned LAN settings, the address is
`172.20.30.1/24`.

#### Scenario: LAN has its static address

- Given the device has booted
- And `/data/config/lan-settings.json` contains `gateway_ip`
- Then `ip addr show lan` shows that `gateway_ip` with its provisioned prefix

#### Scenario: LAN gateway sources must agree

- Given `config.toml` sets `network.dnsmasq.gateway_cidr`
- And `config.toml` sets `network.interfaces.lan.address`
- When the values differ
- Then provisioning validation fails before the config is promoted

#### Scenario: LAN uses the fallback address

- Given the device has booted
- And no valid provisioned LAN settings exist
- Then `ip addr show lan` shows `172.20.30.1/24`

### IP forwarding is disabled

IPv4 and IPv6 forwarding are off in the kernel, and the nftables `forward` chain drops everything. This is the hard
network boundary that EN18031 requires.

#### Scenario: No packet forwarding

- Given a LAN client sends a packet addressed to the internet
- Then the gateway drops it
- And it never leaves through `wan`

### DHCP server on the LAN

dnsmasq runs on `lan` only. It leases addresses from the provisioned DHCP range for 24 hours and answers DNS only for
gateway-local names, without forwarding queries upstream.

#### Scenario: LAN client gets a DHCP lease

- Given a client is connected to `lan`
- When it sends a DHCP discover
- Then it receives an address in the provisioned DHCP range
- And its gateway, DNS server, and NTP server are the provisioned `gateway_ip`

#### Scenario: LAN DNS stays local

- Given a LAN client queries the gateway's DNS server
- When the query is for a configured gateway-local name
- Then dnsmasq returns the local gateway address
- And dnsmasq does not forward unknown names to upstream resolvers

### NTP server on the LAN

chrony syncs from the provisioned `ntp_servers` over WAN (`time.cloudflare.com` by default) and serves time to the
provisioned LAN subnet only. Without valid provisioned LAN settings, it serves `172.20.30.0/24`.

#### Scenario: LAN client syncs time

- Given a LAN client queries NTP at the provisioned `gateway_ip`
- Then it receives a valid time response
- And chrony is synced to an upstream server

#### Scenario: Offline fallback

- Given the device has no WAN connectivity
- Then chrony falls back to `local stratum 10`
- And LAN clients still receive time, at lower accuracy

### nftables firewall

The `input` chain drops by default and accepts loopback and established or related traffic on every interface.

| Interface  | Allowed inbound                                                                                                |
|------------|----------------------------------------------------------------------------------------------------------------|
| wan (WAN)  | Provisioned `wan` ports; TCP 22 when SSH on WAN is enabled; TCP 8080 before provisioning (`network` transport) |
| lan (LAN)  | Everything by default; with provisioned `lan` ports, only those plus TCP 22, 53, 8080 and UDP 53, 67, 68, 123  |
| tun0 (VPN) | TCP 22                                                                                                         |
| forward    | Nothing                                                                                                        |

`provisioned-firewall-inbound.service` applies `/data/config/firewall-inbound.json`. The dynamic SSH-on-WAN rule follows
`/data/config/ssh-wan-enabled`. With the `nixstasis` bootstrap transport, WAN TCP 8080 is never opened.

#### Scenario: WAN ports are closed before provisioning

- Given no provisioned firewall state exists
- When a connection is attempted to `wan` on TCP 443 or UDP 1194
- Then the packet is dropped

#### Scenario: Provisioned WAN ports are allowed

- Given `/data/config/firewall-inbound.json` lists TCP 443 and UDP 1194 under `wan`
- And `provisioned-firewall-inbound.service` has applied it
- Then inbound traffic on `wan` TCP 443 and UDP 1194 is accepted

#### Scenario: Provisioned LAN ports restrict the LAN

- Given `/data/config/firewall-inbound.json` lists TCP 443 under `lan`
- And `provisioned-firewall-inbound.service` has applied it
- Then `lan` accepts TCP 443 and the platform-required LAN ports
- And other inbound LAN traffic is dropped

#### Scenario: WAN SSH blocked by default

- Given `/data/config/ssh-wan-enabled` does not exist
- When an SSH connection is attempted from the WAN
- Then the packet is dropped

#### Scenario: WAN SSH enabled with the flag

- Given `/data/config/ssh-wan-enabled` is created
- And `ssh-wan-reload.service` runs
- Then SSH connections from the WAN are accepted

### WAN SSH toggle is manual only

Enabling SSH on WAN requires creating the flag file on the device, from the LAN or the physical console. Nothing enables
it remotely; this is a deliberate security constraint.

### Device identity comes from the wan MAC

The device is identified by the MAC address of `wan`, the onboard Ethernet. It is stable across reboots and updates
and is sent as the `X-Device-ID` header when polling for updates; when the `wan` address cannot be read, the header is
`unknown`.

#### Scenario: MAC-based identity

- Given `wan` has MAC `aa:bb:cc:dd:ee:ff`
- When `os-upgrade.service` polls for updates
- Then the request includes `X-Device-ID: aabbccddeeff`
