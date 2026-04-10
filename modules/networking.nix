# Network interface configuration.
# Deterministic NIC naming and interface setup.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Disable predictable interface names ──────────────────────────────────────

  networking.usePredictableInterfaceNames = false;

  # ── Use systemd-networkd for network management ─────────────────────────────

  networking.useNetworkd = true;
  systemd.network.enable = true;

  # ── NIC naming via systemd .link files ───────────────────────────────────────

  # Onboard RK3328 GMAC → eth0 (WAN)
  systemd.network.links."10-onboard-eth" = {
    matchConfig = {
      Path = "platform-ff540000.ethernet";
    };
    linkConfig = {
      Name = "eth0";
    };
  };

  # USB ethernet adapters → eth1, eth2, ...
  systemd.network.links."20-usb-eth" = {
    matchConfig = {
      Driver = "r8152 ax88179_178a cdc_ether";
    };
    linkConfig = {
      NamePolicy = "kernel";
    };
  };

  # WiFi dongles → wlan0, wlan1, ...
  systemd.network.links."30-wifi" = {
    matchConfig = {
      Type = "wlan";
    };
    linkConfig = {
      NamePolicy = "kernel";
    };
  };

  # ── eth0 (WAN) — DHCP client ────────────────────────────────────────────────

  systemd.network.networks."10-wan" = {
    matchConfig = {
      Name = "eth0";
    };
    networkConfig = {
      DHCP = "ipv4";
      IPv6AcceptRA = false;
    };
    dhcpV4Config = {
      UseDNS = true;
      UseNTP = false; # We use chrony for NTP
    };
  };

  # ── eth1 (LAN) — Static IP ──────────────────────────────────────────────────

  systemd.network.networks."20-lan" = {
    matchConfig = {
      Name = "eth1";
    };
    networkConfig = {
      Address = "172.20.30.1/24";
      DHCPServer = false; # dnsmasq handles DHCP
      IPv6AcceptRA = false;
    };
  };

  # ── Disable IP forwarding (EN18031 compliance boundary) ──────────────────────

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 0;
    "net.ipv6.conf.all.forwarding" = 0;
  };
}
