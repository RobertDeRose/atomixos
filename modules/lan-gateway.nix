# LAN gateway services: DHCP server (dnsmasq) and NTP server (chrony).
# The Rock64 acts as DHCP and NTP server for isolated LAN devices.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── DHCP server via dnsmasq ──────────────────────────────────────────────────

  services.dnsmasq = {
    enable = true;
    settings = {
      # Only listen on LAN interface
      interface = "eth1";
      bind-interfaces = true;

      # DHCP pool
      dhcp-range = "172.20.30.10,172.20.30.254,255.255.255.0,24h";

      # Gateway is the Rock64 itself
      dhcp-option = [
        "3,172.20.30.1" # Default gateway
        "6" # Empty DNS — no DNS for LAN devices
        "42,172.20.30.1" # NTP server
      ];

      # No DNS forwarding — LAN devices don't need internet DNS
      port = 0; # Disable DNS server in dnsmasq

      # Logging
      log-dhcp = true;
    };
  };

  # ── NTP server via chrony ────────────────────────────────────────────────────

  services.chrony = {
    enable = true;
    extraConfig = ''
      # Sync from upstream NTP servers (via WAN / eth0)
      pool pool.ntp.org iburst

      # Serve time to LAN devices on 172.20.30.0/24
      allow 172.20.30.0/24

      # Deny all other clients
      deny all

      # If we lose upstream NTP, still serve time to LAN
      # (using our own clock as fallback)
      local stratum 10
    '';
  };
}
