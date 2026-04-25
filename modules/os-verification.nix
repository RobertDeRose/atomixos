# OS verification service — post-update health check.
# Validates device-local gateway services before committing the RAUC slot.
#
# Only runs AFTER the first boot (when /data/.completed_first_boot exists).
# On first boot, first-boot.service marks the slot good unconditionally.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  verificationScript = pkgs.writeShellScript "os-verification" (
    builtins.readFile ../scripts/os-verification.sh
  );
in
{
  # ── os-verification.service ─────────────────────────────────────────────────

  systemd.services.os-verification = {
    description = "OS update verification - local health check";
    after = [
      "data.mount"
      "multi-user.target"
    ];
    wants = [ "data.mount" ];
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
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = verificationScript;
      RemainAfterExit = true;

      TimeoutStartSec = 180; # local service checks + sustained check
    };
  };
}
