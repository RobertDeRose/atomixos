# nftables firewall configuration.
# Per-interface rules with manual SSH-on-WAN toggle.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  sshWanToggle = pkgs.writeShellScript "ssh-wan-toggle" (
    builtins.readFile ../scripts/ssh-wan-toggle.sh
  );

  sshWanReload = pkgs.writeShellScript "ssh-wan-reload" (
    builtins.readFile ../scripts/ssh-wan-reload.sh
  );

  provisionedFirewallInbound = pkgs.runCommand "provisioned-firewall-inbound" { } ''
    mkdir -p "$out/bin"
    install -m0755 ${../scripts/provisioned-firewall-inbound.py} "$out/bin/provisioned-firewall-inbound"
  '';
in
{
  # ── Enable nftables ──────────────────────────────────────────────────────────

  networking.firewall.enable = false; # Disable NixOS default iptables firewall
  networking.nftables.enable = true;

  networking.nftables.tables.filter = {
    family = "inet";
    content = ''
      chain input {
        type filter hook input priority 0; policy drop;

        # Allow loopback
        iif "lo" accept

        # Allow established/related connections on all interfaces
        ct state established,related accept

        # -- eth1 (LAN) rules --
        iifname "eth1" udp dport { 53, 67, 68, 123 } accept  comment "LAN infra"
        iifname "eth1" tcp dport { 22, 53, 8080 } accept     comment "LAN infra"

        # -- tun0 (VPN) rules --
        iifname "tun0" tcp dport 22 accept   comment "SSH over VPN"

        # Everything else is dropped by default policy
      }

      chain forward {
        type filter hook forward priority 0; policy drop;
        # No forwarding between interfaces — EN18031 compliance boundary
      }

      chain output {
        type filter hook output priority 0; policy accept;
      }
    '';
  };

  # ── Dynamic SSH-on-WAN toggle ────────────────────────────────────────────────
  #
  # SSH on eth0 is controlled by the presence of /data/config/ssh-wan-enabled
  # A systemd service checks this flag and adds/removes the nftables rule.

  systemd.services.ssh-wan-toggle = {
    description = "Toggle SSH access on WAN based on flag file";
    after = [
      "nftables.service"
      "network-online.target"
    ];
    wants = [
      "nftables.service"
      "network-online.target"
    ];
    wantedBy = [ "multi-user.target" ];

    path = [ pkgs.nftables ];

    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = sshWanToggle;
    };
  };

  # Also provide a reload path so the flag can be toggled at runtime
  systemd.services.ssh-wan-reload = {
    description = "Reload SSH-on-WAN firewall rule";
    after = [ "ssh-wan-toggle.service" ];

    path = [
      pkgs.nftables
      pkgs.gawk
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = sshWanReload;
    };
  };

  systemd.services.provisioned-firewall-inbound = {
    description = "Apply provisioned WAN inbound firewall rules";
    after = [
      "data.mount"
      "nftables.service"
    ];
    wants = [
      "data.mount"
      "nftables.service"
    ];
    wantedBy = [ "multi-user.target" ];

    unitConfig = {
      ConditionPathExists = "/data/config/firewall-inbound.json";
      RequiresMountsFor = [ "/data" ];
    };

    path = [
      pkgs.nftables
      pkgs.python3Minimal
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${provisionedFirewallInbound}/bin/provisioned-firewall-inbound";
    };
  };
}
