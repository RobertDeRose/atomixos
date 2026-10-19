# Network interface configuration.
# Deterministic NIC naming and interface setup.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.atomixos.network;
  chronyWanOnlineScript = pkgs.writeShellScript "chrony-wan-online" ''
    [ "$IFACE" = "${cfg.wanInterface}" ] || exit 0
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
  options.atomixos.network = {
    wanInterface = lib.mkOption {
      type = lib.types.str;
      default = "wan";
      description = ''
        Name of the WAN interface. On hardware the onboard NIC is renamed to it
        by wanLinkMatch. Kernel names such as eth0 depend on probe order, so a
        hardware name must be one the kernel never assigns.
      '';
    };

    lanInterface = lib.mkOption {
      type = lib.types.str;
      default = "lan";
      description = "Name of the LAN interface, the USB Ethernet adapter renamed by lanLinkMatch.";
    };

    wanLinkMatch = lib.mkOption {
      type = lib.types.nullOr (lib.types.attrsOf lib.types.str);
      default = null;
      example = {
        Path = "platform-ff540000.ethernet";
      };
      description = ''
        systemd .link [Match] settings that identify the onboard WAN NIC. Each
        hardware board sets this; null configures no rename.
      '';
    };

    lanLinkMatch = lib.mkOption {
      type = lib.types.nullOr (lib.types.attrsOf lib.types.str);
      default = {
        Driver = "r8152 ax88179_178a cdc_ether";
      };
      description = ''
        systemd .link [Match] settings that identify the USB LAN adapter. The
        first match is renamed to lanInterface; further adapters keep their
        kernel names. Null configures no rename.
      '';
    };
  };

  config = {
    # ── Disable predictable interface names ──────────────────────────────────────

    networking.usePredictableInterfaceNames = false;

    # ── Use systemd-networkd for network management ─────────────────────────────

    networking.useNetworkd = true;
    systemd.network.enable = true;
    services.resolved.enable = true;

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
          ${pkgs.systemd}/bin/networkctl status ${cfg.wanInterface} --no-pager | ${pkgs.gnugrep}/bin/grep 'State: routable' >/dev/null || exit 0
          IFACE=${cfg.wanInterface} ${chronyWanOnlineScript}
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
    # Rename to names the kernel never assigns, so the result does not depend on
    # which NIC registers first. A rename to eth0 fails when a USB adapter got
    # eth0 first, which would leave the onboard WAN port named eth1 (LAN).

    systemd.network.links."10-wan" = lib.mkIf (cfg.wanLinkMatch != null) {
      matchConfig = cfg.wanLinkMatch;
      linkConfig.Name = cfg.wanInterface;
    };

    systemd.network.links."20-lan" = lib.mkIf (cfg.lanLinkMatch != null) {
      matchConfig = cfg.lanLinkMatch;
      linkConfig.Name = cfg.lanInterface;
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

    # ── WAN — DHCP client ───────────────────────────────────────────────────────

    systemd.network.networks."10-wan" = {
      matchConfig = {
        Name = cfg.wanInterface;
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

    # ── LAN — Static IP ─────────────────────────────────────────────────────────

    systemd.network.networks."20-lan" = {
      matchConfig = {
        Name = cfg.lanInterface;
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
  };
}
