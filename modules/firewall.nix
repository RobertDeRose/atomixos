# nftables firewall configuration.
# Per-interface rules with manual SSH-on-WAN toggle.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.atonic.firewall;

  sshWanToggle = pkgs.writeShellScript "ssh-wan-toggle" (
    builtins.readFile ../scripts/ssh-wan-toggle.sh
  );

  sshWanReload = pkgs.writeShellScript "ssh-wan-reload" (
    builtins.readFile ../scripts/ssh-wan-reload.sh
  );

  bootstrapWanToggle = pkgs.writeShellScript "bootstrap-wan-toggle" ''
    set -euo pipefail

    nft -a list chain inet filter input 2>/dev/null \
      | awk '/ATOMIXOS_BOOTSTRAP_WAN/ {print $NF}' \
      | while IFS= read -r handle; do
        [ -n "$handle" ] || continue
        nft delete rule inet filter input handle "$handle"
      done

    if [ -f /data/config.atomixos-promotion-pending ] \
      || { [ ! -f /data/config/config.toml ] && [ ! -f /data/config/admin-signers ]; }; then
      nft add rule inet filter input iifname "${cfg.wanInterface}" tcp dport 8080 accept comment "ATOMIXOS_BOOTSTRAP_WAN"
    fi
  '';

  provisionedFirewallInbound = pkgs.runCommand "provisioned-firewall-inbound" { } ''
    mkdir -p "$out/bin"
    install -m0755 ${../scripts/provisioned-firewall-inbound.py} "$out/bin/provisioned-firewall-inbound"
  '';
in
{
  options.atonic.firewall = {
    wanInterface = lib.mkOption {
      type = lib.types.str;
      default = "eth0";
      description = "WAN interface name used by nftables and provisioned inbound rules.";
    };

    lanInterface = lib.mkOption {
      type = lib.types.str;
      default = "eth1";
      description = "LAN interface name used by nftables rules.";
    };

    extraInputRules = lib.mkOption {
      type = lib.types.lines;
      default = "";
      description = "Additional input-chain rules for test-only backdoors or deployment-specific allowances.";
    };
  };

  config = {
    # ── Enable nftables ────────────────────────────────────────────────────────

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

          ${cfg.extraInputRules}

          # First-boot WAN bootstrap access is reconciled by bootstrap-wan-toggle.service.

          # -- eth1 (LAN) rules --
          iifname "${cfg.lanInterface}" accept comment "ATOMIXOS_LAN_DEFAULT_OPEN"

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

    # ── Dynamic SSH-on-WAN toggle ──────────────────────────────────────────────
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

      path = [
        pkgs.gawk
        pkgs.nftables
      ];

      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
        ExecStart = sshWanToggle;
      };
    };

    systemd.services.bootstrap-wan-toggle = {
      description = "Toggle first-boot bootstrap API access on WAN";
      after = [
        "data.mount"
        "nftables.service"
      ];
      wants = [
        "data.mount"
        "nftables.service"
      ];
      wantedBy = [ "multi-user.target" ];

      unitConfig.RequiresMountsFor = [ "/data" ];

      path = [
        pkgs.gawk
        pkgs.nftables
      ];

      serviceConfig = {
        Type = "oneshot";
        ExecStart = bootstrapWanToggle;
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
      description = "Apply provisioned LAN and WAN inbound firewall rules";
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
        Environment = [
          "ATOMIXOS_FIREWALL_WAN_INTERFACE=${cfg.wanInterface}"
          "ATOMIXOS_FIREWALL_LAN_INTERFACE=${cfg.lanInterface}"
        ];
        ExecStart = "${provisionedFirewallInbound}/bin/provisioned-firewall-inbound";
      };
    };
  };
}
