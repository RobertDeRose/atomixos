# LAN gateway services: DHCP server (dnsmasq) and NTP server (chrony).
# The Rock64 acts as DHCP and NTP server for isolated LAN devices.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  lanGatewayApply = pkgs.runCommand "lan-gateway-apply" { } ''
    mkdir -p "$out/bin"
    install -m0755 ${../scripts/lan-gateway-apply.py} "$out/bin/lan-gateway-apply"
  '';
in
{
  # ── DHCP server via dnsmasq ──────────────────────────────────────────────────

  services.dnsmasq = {
    enable = true;
    # We intentionally run dnsmasq as LAN-only DHCP/DNS authority. Avoid the
    # module's default resolv-file flag, which is ignored when no-resolv is set.
    resolveLocalQueries = false;
    settings = {
      # Only listen on LAN interface
      interface = "eth1";
      bind-dynamic = true; # Wait for eth1 to appear (unlike bind-interfaces which fails immediately)
      local-service = true;
      no-resolv = true;

      conf-file = "/etc/dnsmasq.d/atomixos-lan.conf";

      # Logging
      log-dhcp = true;
    };
  };

  # ── NTP server via chrony ────────────────────────────────────────────────────

  services.chrony = {
    enable = true;
    # Rock64 boards have an RK808 RTC, but chronyd holding /dev/rtc open causes
    # systemd-timedated to log repeated busy warnings. NTP is authoritative for
    # AtomixOS, so do not let chrony track/trim the RTC.
    enableRTCTrimming = false;
    servers = [ ];
    initstepslew.enabled = false;
    extraConfig = ''
      # Sync from Cloudflare's public, non-leap-smearing NTP service via WAN.
      server time.cloudflare.com iburst

      # Step large RTC drift whenever upstream time becomes available.
      makestep 1.0 -1

      # Serve time to LAN devices from the applied LAN config.
      include /etc/atomixos/chrony-lan.conf

      # Deny all other clients
      deny all

      # If we lose upstream NTP, still serve time to LAN
      # (using our own clock as fallback)
      local stratum 10
    '';
  };

  environment.etc."systemd/network/20-lan.network.d/50-atomixos.conf".text = ''
    [Network]
    Address=172.20.30.1/24
  '';

  environment.etc."dnsmasq.d/atomixos-lan.conf".text = ''
    dhcp-range=172.20.30.10,172.20.30.254,255.255.255.0,24h
    dhcp-option=3,172.20.30.1
    dhcp-option=6,172.20.30.1
    dhcp-option=42,172.20.30.1
    domain=local
    expand-hosts
    addn-hosts=/etc/atomixos/dnsmasq-hosts
    local=/local/
    port=53
  '';

  environment.etc."atomixos/dnsmasq-hosts".text = ''
    172.20.30.1 atomixos atomixos.local
  '';

  environment.etc."atomixos/chrony-lan.conf".text = ''
    # Managed at runtime by lan-gateway-apply.
    allow 172.20.30.0/24
  '';

  systemd.services.lan-gateway-apply = {
    description = "Apply provisioned LAN gateway settings";
    after = [ "data.mount" ];
    wants = [ "data.mount" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig = {
      ConditionPathExists = "/data/config/lan-settings.json";
      RequiresMountsFor = [ "/data" ];
    };

    path = [
      pkgs.coreutils
      pkgs.iproute2
      pkgs.python3Minimal
      pkgs.systemd
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${lanGatewayApply}/bin/lan-gateway-apply";
    };
  };
}
