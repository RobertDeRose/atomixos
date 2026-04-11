# OS verification service — post-update health check.
# Validates system services and manifest-defined containers
# before committing the RAUC slot.
#
# Only runs AFTER the first boot (when /persist/.completed_first_boot exists).
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
      "multi-user.target"
      "network-online.target"
    ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    # Skip on first boot — first-boot.service handles slot confirmation.
    # This service only runs on subsequent boots (after OTA updates).
    unitConfig.ConditionPathExists = "/persist/.completed_first_boot";

    path = [
      pkgs.rauc
      config.virtualisation.podman.package # use the NixOS-wrapped podman
      pkgs.jq
      pkgs.systemd
      pkgs.iproute2
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = verificationScript;
      RemainAfterExit = true;

      # Give the service enough time for container startup + sustained check
      TimeoutStartSec = 600; # 10 minutes total
    };
  };
}
