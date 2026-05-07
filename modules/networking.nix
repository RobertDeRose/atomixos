# Network interface configuration.
# Deterministic NIC naming and interface setup.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  chronyWanOnlineScript = pkgs.writeShellScript "chrony-wan-online" ''
    [ "$IFACE" = "eth0" ] || exit 0
    echo "[chrony-wan-online] bringing chrony online for $IFACE"
    ${pkgs.systemd}/bin/systemctl start chronyd.service
    for _ in $(seq 1 10); do
      if ${pkgs.chrony}/bin/chronyc tracking >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    ${pkgs.chrony}/bin/chronyc online
    ${pkgs.chrony}/bin/chronyc burst 4/4
  '';
in
{
  # ── Disable predictable interface names ──────────────────────────────────────

  networking.usePredictableInterfaceNames = false;

  # ── Use systemd-networkd for network management ─────────────────────────────

  networking.useNetworkd = true;
  systemd.network.enable = true;

  services.networkd-dispatcher = {
    enable = true;
    rules.chrony-wan-online = {
      onState = [ "routable" ];
      script = "IFACE=\"$IFACE\" ${chronyWanOnlineScript}";
    };
  };

  systemd.services.chrony-wan-online-startup = {
    description = "Bring chrony online when WAN is already routable";
    after = [
      "chronyd.service"
      "networkd-dispatcher.service"
    ];
    wants = [
      "chronyd.service"
      "networkd-dispatcher.service"
    ];
    wantedBy = [ "multi-user.target" ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = pkgs.writeShellScript "chrony-wan-online-startup" ''
        ${pkgs.systemd}/bin/networkctl status eth0 --no-pager | ${pkgs.gnugrep}/bin/grep 'State: routable' >/dev/null || exit 0
        IFACE=eth0 ${chronyWanOnlineScript}
      '';
    };
  };

  # Don't let network-online.target block boot indefinitely. The device must
  # boot and confirm its RAUC slot even without WAN connectivity. "any" means
  # network-online.target is reached as soon as at least one interface has a
  # carrier, rather than waiting for all interfaces to be fully configured.
  systemd.network.wait-online = {
    anyInterface = true;
    timeout = 30; # seconds — give DHCP a chance, but don't block forever
  };

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
      DHCPServer = false; # dnsmasq handles DHCP
      IPv6AcceptRA = false;
      # The LAN USB NIC may be unplugged at boot. Keep the interface configured
      # without carrier so the gateway IP from the 20-lan drop-in managed by
      # lan-gateway-apply is still present for dnsmasq/chrony when clients appear.
      ConfigureWithoutCarrier = true;
    };
  };

  # ── Disable IP forwarding (EN18031 compliance boundary) ──────────────────────

  boot.kernel.sysctl = {
    "net.ipv4.ip_forward" = 0;
    "net.ipv6.conf.all.forwarding" = 0;
  };
}
