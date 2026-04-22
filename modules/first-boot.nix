# First-boot initialization — runs once on initial device boot.
#
# Marks the RAUC slot as good unconditionally (no health manifest or
# container images exist yet on first boot) and writes a sentinel file
# (/persist/.completed_first_boot) so it never runs again.
#
# os-verification.service has the inverse condition — it only runs after
# the sentinel exists (i.e. on all boots AFTER the first).
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

let
  firstBootScript = pkgs.writeShellScript "first-boot" (builtins.readFile ../scripts/first-boot.sh);
  ubootEnvTools = self.packages.${pkgs.system}.uboot-env-tools;
in
{
  systemd.services.first-boot = {
    description = "First-boot initialization (mark slot good, write sentinel)";
    after = [
      "multi-user.target"
    ];
    wantedBy = [ "multi-user.target" ];

    # Only run if the sentinel does NOT exist (first boot only)
    unitConfig.ConditionPathExists = "!/persist/.completed_first_boot";

    # RAUC needs to be on PATH to call `rauc status mark-good`
    path = [
      pkgs.rauc
      ubootEnvTools
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = firstBootScript;
      RemainAfterExit = true;
    };
  };
}
