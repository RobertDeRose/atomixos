# Network Topology

Each AtomixOS device can use two Ethernet interfaces to keep LAN-side services isolated from WAN-side management and
application ingress.

## Interface Roles

```text
                    ┌─────────────────────────────┐
  WAN (internet) ──►│ eth0                         │
                    │   DHCP client                │
                    │   Accepts: HTTPS (443),      │
                    │           OpenVPN (1194)      │
                    │                               │
                    │   ip_forward = OFF            │
                    │   FORWARD chain: DROP all     │
                    │                               │
                    │ eth1                          │◄── LAN (isolated)
                    │   Static: 172.20.30.1/24     │
                    │   DHCP server (dnsmasq)       │
                    │   NTP server (chrony)         │
                    └─────────────────────────────┘
```

## WAN Interface (eth0)

- Mapped to the onboard RK3328 GMAC via systemd `.link` file (platform path `platform-ff540000.ethernet`)
- DHCP v4 client via systemd-networkd
- Uses DHCP-provided DNS servers
- Firewall allows inbound HTTPS (443) and OpenVPN (1194) only

## LAN Interface (eth1)

- USB Ethernet adapter (any supported chipset: r8152, ax88179, cdc_ether)
- Static IP: `172.20.30.1/24`
- Runs dnsmasq DHCP server: pool `172.20.30.10` -- `172.20.30.254`, 24h lease
- Runs chrony NTP server: serves time to `172.20.30.0/24` only
- DNS forwarding is disabled (`port=0` in dnsmasq)

## Isolation Model

IP forwarding is explicitly disabled at the kernel level:

```nix
boot.kernel.sysctl = {
  "net.ipv4.ip_forward" = 0;
  "net.ipv6.conf.all.forwarding" = 0;
};
```

The nftables `FORWARD` chain has a `drop` policy with no exceptions. LAN devices get DHCP and NTP but have zero internet
access. Application-layer proxying through Traefik is the only path between WAN and LAN, and it requires authentication.

## NIC Naming

Deterministic interface naming uses systemd `.link` files rather than udev rules:

| Link File        | Match                                            | Name                                       |
|------------------|--------------------------------------------------|--------------------------------------------|
| `10-onboard-eth` | Platform path `platform-ff540000.ethernet`       | `eth0`                                     |
| `20-usb-eth`     | USB Ethernet drivers (r8152, ax88179, cdc_ether) | enabled as modules in Rock64 kernel config |
| `30-wifi`        | WiFi drivers                                     | kernel default                             |

The onboard Ethernet is always `eth0` regardless of USB device enumeration order. USB Ethernet adapters receive
kernel-assigned names (e.g., `eth1`, `eth2`).

## Firewall Summary

| Interface  | Direction | Allowed Ports                                 |
|------------|-----------|-----------------------------------------------|
| eth0 (WAN) | Inbound   | TCP 443 (HTTPS), UDP 1194 (OpenVPN)           |
| eth0 (WAN) | Inbound   | TCP 22 (SSH) -- only with flag file           |
| eth1 (LAN) | Inbound   | UDP 67-68 (DHCP), UDP 123 (NTP), TCP 22 (SSH) |
| tun0 (VPN) | Inbound   | TCP 22 (SSH)                                  |
| any        | Forward   | DROP (no exceptions)                          |

SSH on WAN is controlled by the presence of `/data/config/ssh-wan-enabled`. See the [Firewall
module](../code-reference/modules.md#firewallnix) for implementation details.
