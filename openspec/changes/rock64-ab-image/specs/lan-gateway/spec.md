# LAN Gateway Spec

## ADDED Requirements

### Requirement: Network interfaces are named deterministically

The NixOS configuration SHALL disable systemd predictable interface names and use systemd-networkd `.link` files to
assign deterministic names: onboard RK3328 GMAC SHALL be `eth0`, USB ethernet adapters SHALL be `eth1`, `eth2`, etc.,
    The onboard NIC SHALL be matched by its hardware platform path (`platform-ff540000.ethernet`). USB WiFi dongles are
    not part of the current Rock64 support contract.

#### Scenario: Onboard NIC is always eth0

- **WHEN** the Rock64 boots with or without USB network adapters plugged in
- **THEN** the onboard RK3328 GMAC is named `eth0` regardless of USB device enumeration order

#### Scenario: USB NIC is assigned sequential ethN name

- **WHEN** a USB ethernet adapter is plugged into the Rock64
- **THEN** it is assigned the next available `ethN` name (e.g., `eth1`)

### Requirement: eth0 is configured as WAN interface

eth0 (onboard NIC) SHALL be configured as a DHCP client to obtain a WAN address from the upstream network.

#### Scenario: eth0 obtains WAN address

- **WHEN** the Rock64 boots and eth0 is connected to a network with a DHCP server
- **THEN** eth0 obtains an IP address via DHCP

### Requirement: eth1 is configured as LAN interface with static IP

eth1 (USB NIC) SHALL be configured with the provisioned LAN gateway IP and prefix. If no valid provisioned LAN config
exists, it SHALL fall back to `172.20.30.1/24`.

#### Scenario: eth1 has correct static address

- **WHEN** the Rock64 boots with a USB NIC plugged in and a valid LAN config is present
- **THEN** eth1 has the provisioned gateway IP and prefix

#### Scenario: eth1 falls back to default static address

- **WHEN** the Rock64 boots with no valid provisioned LAN config
- **THEN** eth1 has IP address `172.20.30.1` with netmask `255.255.255.0`

### Requirement: IP forwarding is disabled

The kernel parameter `net.ipv4.ip_forward` SHALL be set to `0`. No packet-level routing SHALL occur between any
interfaces. This provides the EN18031 compliance boundary for legacy LAN devices.

#### Scenario: No traffic is routed between interfaces

- **WHEN** a device on the LAN (172.20.30.x) sends a packet destined for a WAN address
- **THEN** the packet is dropped by the Rock64 kernel and never reaches eth0

### Requirement: DHCP server runs on LAN interface

dnsmasq SHALL be configured to serve DHCP on eth1 (LAN) only. The DHCP pool SHALL use the provisioned LAN DHCP range,
reserving lower addresses for static assignments.

#### Scenario: LAN device obtains IP via DHCP

- **WHEN** a device is connected to the switch on the LAN
- **THEN** it receives an IP address in the provisioned DHCP range from the Rock64's DHCP server

#### Scenario: DHCP only serves LAN

- **WHEN** a DHCP request arrives on eth0 (WAN)
- **THEN** dnsmasq does not respond to it

### Requirement: NTP server runs on LAN interface

chrony SHALL be configured as both an NTP client (syncing from WAN NTP servers via eth0) and an NTP server (serving time
to LAN devices on eth1). NTP service SHALL accept clients from the provisioned LAN subnet. When no valid provisioned LAN
config exists, it SHALL accept clients from the fallback `172.20.30.0/24` subnet.

#### Scenario: Rock64 syncs time from WAN

- **WHEN** the Rock64 boots with WAN connectivity
- **THEN** chrony synchronizes time from upstream NTP servers via eth0

#### Scenario: LAN device syncs time from Rock64

- **WHEN** a LAN device queries NTP at the provisioned LAN gateway IP
- **THEN** chrony responds with the current time

#### Scenario: NTP rejects non-LAN clients

- **WHEN** an NTP request arrives from a source outside the provisioned LAN subnet
- **THEN** chrony does not respond

### Requirement: nftables firewall restricts traffic per interface

nftables SHALL be configured with the following rules:

**eth0 (WAN) inbound**: ALLOW established/related, DROP all else by default. Provisioned firewall state MAY add
application or VPN ports from `/data/config/firewall-inbound.json`. TCP/22 (SSH) is allowed only if the flag file
`/data/config/ssh-wan-enabled` exists.

**eth1 (LAN) inbound**: ALLOW UDP/53 (DNS), ALLOW UDP/67-68 (DHCP), ALLOW UDP/123 (NTP), ALLOW TCP/22 (SSH), ALLOW
TCP/53 (DNS), ALLOW TCP/8080 (bootstrap UI), ALLOW established/related, DROP all else.

**tun0 (VPN) inbound**: ALLOW TCP/22 (SSH), ALLOW established/related, DROP all else.

**FORWARD chain**: DROP all (no inter-interface routing).

#### Scenario: WAN application ports are provisioned

- **WHEN** `/data/config/firewall-inbound.json` contains TCP/443
- **AND** `provisioned-firewall-inbound.service` applies the provisioned state
- **THEN** HTTPS connections to eth0 on port 443 are accepted

#### Scenario: WAN application ports are closed before provisioning

- **WHEN** no provisioned firewall state allows TCP/443 or UDP/1194
- **THEN** new inbound connections to eth0 on TCP/443 and UDP/1194 are dropped

#### Scenario: SSH is blocked on WAN by default

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` does not exist
- **THEN** the connection is dropped

#### Scenario: SSH is allowed on WAN when flag is set

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` exists
- **THEN** the connection is accepted

#### Scenario: SSH is always allowed on LAN

- **WHEN** an SSH connection is attempted to eth1 on port 22
- **THEN** the connection is accepted

#### Scenario: DNS is allowed on LAN

- **WHEN** a DNS query is sent to eth1 on TCP/53 or UDP/53
- **THEN** the packet is accepted

#### Scenario: Bootstrap UI is allowed on LAN

- **WHEN** a connection is made to eth1 on TCP/8080
- **THEN** the connection is accepted

#### Scenario: SSH is allowed over VPN

- **WHEN** an SSH connection is attempted via the tun0 interface on port 22
- **THEN** the connection is accepted

#### Scenario: No forwarding between interfaces

- **WHEN** any packet arrives that would be forwarded between interfaces
- **THEN** the packet is dropped by the FORWARD chain

### Requirement: WAN SSH toggle is manual only

SSH access on eth0 (WAN) SHALL be controlled by the presence of the flag file `/data/config/ssh-wan-enabled`. In the
production design, this flag is an explicit operator-controlled toggle rather than an automatically managed runtime rule.

#### Scenario: Flag file enables WAN SSH

- **WHEN** `/data/config/ssh-wan-enabled` is created
- **THEN** the nftables rule for SSH on eth0 becomes active on the next firewall reload or reboot

#### Scenario: Flag file removal disables WAN SSH

- **WHEN** `/data/config/ssh-wan-enabled` is removed
- **THEN** SSH connections to eth0 are dropped on the next firewall reload or reboot

### Requirement: Device identity uses eth0 MAC address

The device identity SHALL be derived from the MAC address of eth0 (onboard NIC). This address SHALL be readable from
`/sys/class/net/eth0/address`, normalized to compact lowercase 12-hex format, and used as the unique device identifier
for update confirmation, fleet management, and device registration.

#### Scenario: Device ID is consistent across reboots

- **WHEN** the device reboots or updates to a new slot
- **THEN** the device identity (eth0 MAC) remains the same
