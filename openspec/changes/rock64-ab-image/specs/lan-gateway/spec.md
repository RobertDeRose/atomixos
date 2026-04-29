# LAN Gateway Spec

## ADDED Requirements

### Requirement: Network interfaces are named deterministically

The NixOS configuration SHALL disable systemd predictable interface names and use systemd-networkd `.link` files to
assign deterministic names: onboard RK3328 GMAC SHALL be `eth0`, USB ethernet adapters SHALL be `eth1`, `eth2`, etc.,
and WiFi dongles SHALL be `wlan0`, `wlan1`, etc. The onboard NIC SHALL be matched by its hardware platform path
(`platform-ff540000.ethernet`).

#### Scenario: Onboard NIC is always eth0

- **WHEN** the Rock64 boots with or without USB network adapters plugged in
- **THEN** the onboard RK3328 GMAC is named `eth0` regardless of USB device enumeration order

#### Scenario: USB NIC is assigned sequential ethN name

- **WHEN** a USB ethernet adapter is plugged into the Rock64
- **THEN** it is assigned the next available `ethN` name (e.g., `eth1`)

#### Scenario: WiFi dongle is assigned wlanN name

- **WHEN** a USB WiFi dongle is plugged into the Rock64
- **THEN** it is assigned the next available `wlanN` name (e.g., `wlan0`)

### Requirement: eth0 is configured as WAN interface

eth0 (onboard NIC) SHALL be configured as a DHCP client to obtain a WAN address from the upstream network.

#### Scenario: eth0 obtains WAN address

- **WHEN** the Rock64 boots and eth0 is connected to a network with a DHCP server
- **THEN** eth0 obtains an IP address via DHCP

### Requirement: eth1 is configured as LAN interface with static IP

eth1 (USB NIC) SHALL be configured with a static IP address of 172.20.30.1/24.

#### Scenario: eth1 has correct static address

- **WHEN** the Rock64 boots with a USB NIC plugged in
- **THEN** eth1 has IP address 172.20.30.1 with netmask 255.255.255.0

### Requirement: IP forwarding is disabled

The kernel parameter `net.ipv4.ip_forward` SHALL be set to `0`. No packet-level routing SHALL occur between any
interfaces. This provides the EN18031 compliance boundary for legacy LAN devices.

#### Scenario: No traffic is routed between interfaces

- **WHEN** a device on the LAN (172.20.30.x) sends a packet destined for a WAN address
- **THEN** the packet is dropped by the Rock64 kernel and never reaches eth0

### Requirement: DHCP server runs on LAN interface

dnsmasq SHALL be configured to serve DHCP on eth1 (LAN) only. The DHCP pool SHALL serve addresses in the 172.20.30.0/24
range (e.g., 172.20.30.10-172.20.30.254), reserving lower addresses for static assignments.

#### Scenario: LAN device obtains IP via DHCP

- **WHEN** a device is connected to the switch on the LAN
- **THEN** it receives an IP address in the 172.20.30.10-172.20.30.254 range from the Rock64's DHCP server

#### Scenario: DHCP only serves LAN

- **WHEN** a DHCP request arrives on eth0 (WAN)
- **THEN** dnsmasq does not respond to it

### Requirement: NTP server runs on LAN interface

chrony SHALL be configured as both an NTP client (syncing from WAN NTP servers via eth0) and an NTP server (serving time
to LAN devices on eth1). NTP service SHALL only accept clients from the 172.20.30.0/24 network.

#### Scenario: Rock64 syncs time from WAN

- **WHEN** the Rock64 boots with WAN connectivity
- **THEN** chrony synchronizes time from upstream NTP servers via eth0

#### Scenario: LAN device syncs time from Rock64

- **WHEN** a LAN device queries NTP at 172.20.30.1
- **THEN** chrony responds with the current time

#### Scenario: NTP rejects non-LAN clients

- **WHEN** an NTP request arrives from a non-172.20.30.0/24 source
- **THEN** chrony does not respond

### Requirement: nftables firewall restricts traffic per interface

nftables SHALL be configured with the following rules:

**eth0 (WAN) inbound**: ALLOW tcp/443 (HTTPS), ALLOW udp/1194 (OpenVPN), ALLOW established/related, DROP all else.
tcp/22 (SSH) is allowed only if the flag file `/data/config/ssh-wan-enabled` exists.

**eth1 (LAN) inbound**: ALLOW udp/67-68 (DHCP), ALLOW udp/123 (NTP), ALLOW tcp/22 (SSH), ALLOW established/related, DROP
all else.

**tun0 (VPN) inbound**: ALLOW tcp/22 (SSH), ALLOW established/related, DROP all else.

**FORWARD chain**: DROP all (no inter-interface routing).

#### Scenario: HTTPS is allowed on WAN

- **WHEN** an HTTPS connection is made to eth0 on port 443
- **THEN** the connection is accepted

#### Scenario: SSH is blocked on WAN by default

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` does not exist
- **THEN** the connection is dropped

#### Scenario: SSH is allowed on WAN when flag is set

- **WHEN** an SSH connection is attempted to eth0 on port 22 and `/data/config/ssh-wan-enabled` exists
- **THEN** the connection is accepted

#### Scenario: SSH is always allowed on LAN

- **WHEN** an SSH connection is attempted to eth1 on port 22
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
`/sys/class/net/eth0/address` and used as the unique device identifier for update confirmation, fleet management, and
device registration.

#### Scenario: Device ID is consistent across reboots

- **WHEN** the device reboots or updates to a new slot
- **THEN** the device identity (eth0 MAC) remains the same
