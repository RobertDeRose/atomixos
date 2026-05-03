# LAN Gateway

> Source: `openspec/changes/rock64-ab-image/specs/lan-gateway/spec.md`

## Requirements

### ADDED: Deterministic NIC naming

The onboard RK3328 GMAC is always named `eth0` via a systemd `.link` file matching the platform path
(`platform-ff540000.ethernet`). USB Ethernet adapters and WiFi dongles receive kernel-assigned names.

#### Scenario: Onboard Ethernet is eth0

- Given the Rock64 boots with the onboard Ethernet connected
- Then `ip link` shows `eth0` as the onboard GMAC
- Regardless of USB device enumeration order

### ADDED: eth0 as WAN (DHCP client)

The WAN interface acquires its address via DHCP v4. IPv6 RA is disabled. The DHCP-provided DNS servers are used.

#### Scenario: WAN gets DHCP address

- Given eth0 is connected to a network with a DHCP server
- When the device boots
- Then eth0 acquires an IPv4 address
- And DNS resolution works

### ADDED: eth1 as LAN (static IP)

The LAN interface has a static IP from the provisioned LAN config. When no provisioned LAN config exists or it is
malformed, the fallback static IP is `172.20.30.1/24`. It does not run a DHCP client.

#### Scenario: LAN has static IP

- Given the device has booted
- And `/data/config/lan-settings.json` contains `gateway_ip`
- Then `ip addr show eth1` shows the configured `gateway_ip` with its provisioned prefix

#### Scenario: LAN uses fallback static IP

- Given the device has booted
- And no valid provisioned LAN config is available
- Then `ip addr show eth1` shows `172.20.30.1/24`

### ADDED: IP forwarding disabled

IP forwarding is disabled at the kernel level for both IPv4 and IPv6. The nftables `FORWARD` chain has a `drop` policy
with no exceptions. This creates a hard network boundary compliant with EN18031.

#### Scenario: No packet forwarding

- Given a LAN client sends a packet destined for the internet
- Then the packet is dropped at the gateway
- And it never reaches eth0

### ADDED: DHCP server on LAN

dnsmasq runs on eth1 only. It assigns addresses from the provisioned DHCP range with a 24-hour lease and serves
gateway-local DNS names without forwarding queries upstream.

#### Scenario: LAN client gets DHCP lease

- Given a client is connected to eth1
- When it sends a DHCP discover
- Then it receives an address in the provisioned DHCP range
- And the gateway is the provisioned `gateway_ip`
- And the DNS server is the provisioned `gateway_ip`

#### Scenario: LAN DNS stays local-only

- Given a client on the LAN queries the gateway DNS server
- When the query is for a configured gateway-local name
- Then dnsmasq returns the local gateway address
- And dnsmasq does not forward unknown names to upstream resolvers

### ADDED: NTP server on LAN

chrony acts as both an NTP client (syncing from `pool.ntp.org` via WAN) and an NTP server for LAN clients. Only the
`172.20.30.0/24` subnet is allowed to query.

#### Scenario: LAN client syncs time

- Given a client on the LAN queries NTP at the provisioned `gateway_ip`
- Then it receives a valid time response
- And chrony is synced to an upstream NTP pool

#### Scenario: Offline fallback

- Given the device has no WAN connectivity
- Then chrony uses `local stratum 10` as a fallback
- And LAN clients still receive time (lower accuracy)

### ADDED: nftables firewall

The firewall uses nftables with per-interface rules:

| Interface  | Allowed Inbound                                 |
|------------|-------------------------------------------------|
| eth0 (WAN) | TCP 443, UDP 1194, established/related          |
| eth1 (LAN) | UDP 67-68, UDP 123, TCP 22, established/related |
| tun0 (VPN) | TCP 22, established/related                     |
| FORWARD    | DROP all                                        |

SSH on WAN is controlled by a dynamic nftables rule toggled via `/data/config/ssh-wan-enabled`.

#### Scenario: WAN SSH blocked by default

- Given no flag file exists at `/data/config/ssh-wan-enabled`
- When an SSH connection is attempted from the WAN
- Then the connection is rejected

#### Scenario: WAN SSH enabled with flag

- Given `/data/config/ssh-wan-enabled` is created
- And `ssh-wan-reload.service` is triggered
- Then SSH connections from the WAN are accepted

### ADDED: WAN SSH toggle is manual only

Enabling SSH on WAN requires creating a flag file on the device (via LAN SSH or physical console). There is no automated
mechanism to enable it remotely -- this is a deliberate security constraint.

### ADDED: Device identity via MAC address

The device is identified by the MAC address of eth0 (the onboard Ethernet). This MAC is stable across reboots and
updates, and is used as the `X-Device-ID` header when polling for updates.

#### Scenario: MAC-based identity

- Given `eth0` has MAC `aa:bb:cc:dd:ee:ff`
- When `os-upgrade.service` polls for updates
- Then the request includes `X-Device-ID: aa:bb:cc:dd:ee:ff`
