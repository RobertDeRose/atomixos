# OS verification service — post-update health check.
# Validates device-local gateway services before committing the RAUC slot.
#
# Only runs AFTER the first boot (when /data/.completed_first_boot exists).
# On first boot, first-boot.service handles provisioning and marks the slot
# good only when RAUC is enabled.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.atomixos.rauc;
  verificationScript = pkgs.writeShellScript "os-verification" (
    builtins.readFile ../scripts/os-verification.sh
  );
in
{
  # ── os-verification.service ─────────────────────────────────────────────────

  systemd.services.os-verification = lib.mkIf cfg.enable {
    description = "OS update verification - local health check";
    after = [
      "atomixos-apply-users.service"
      "atomixos-config-recover.service"
      "data.mount"
      "lan-gateway-apply.service"
      "provisioned-firewall-inbound.service"
      "quadlet-sync.service"
      "rauc.service"
    ];
    wants = [
      "atomixos-apply-users.service"
      "atomixos-config-recover.service"
      "data.mount"
      "lan-gateway-apply.service"
      "provisioned-firewall-inbound.service"
      "quadlet-sync.service"
      "rauc.service"
    ];
    wantedBy = [ "multi-user.target" ];

    # Skip on first boot — first-boot.service handles slot confirmation.
    # This service only runs on subsequent boots (after OTA updates).
    unitConfig.ConditionPathExists = "/data/.completed_first_boot";
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.rauc
      pkgs.jq
      pkgs.systemd
      pkgs.iproute2
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.shadow
      pkgs.util-linux
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = verificationScript;
      RemainAfterExit = true;

      TimeoutStartSec = 180; # local service checks + sustained check
    };
  };
}
