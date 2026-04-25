# First-boot initialization — runs once on initial device boot.
#
# Marks the RAUC slot as good unconditionally (no health manifest or
# container images exist yet on first boot) and writes a sentinel file
# (/data/.completed_first_boot) so it never runs again.
#
# os-verification.service has the inverse condition — it only runs after
# the sentinel exists (i.e. on all boots AFTER the first).
{
  config,
  lib,
  pkgs,
  self,
  developmentMode ? false,
  developmentAdminPasswordHashFile ? "",
  ...
}:

let
  firstBootScript = pkgs.writeShellScript "first-boot" (builtins.readFile ../scripts/first-boot.sh);
  ubootEnvTools = self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools;
  trimmedDevAdminPasswordHash = lib.strings.trim devAdminPasswordHash;
  devAdminPasswordHash =
    if
      developmentMode
      && developmentAdminPasswordHashFile != ""
      && builtins.pathExists developmentAdminPasswordHashFile
    then
      builtins.readFile developmentAdminPasswordHashFile
    else
      "";
  firstBootEnv =
    lib.optionalAttrs (trimmedDevAdminPasswordHash != "") {
      ATOMIXOS_DEV_ADMIN_PASSWORD_HASH = trimmedDevAdminPasswordHash;
    }
    // lib.optionalAttrs developmentMode {
      ATOMIXOS_DEV_ENABLE_SSH_WAN = "1";
    };
in
{
  systemd.services.first-boot = {
    description = "First-boot initialization (mark slot good, write sentinel)";
    after = [
      "data.mount"
      "multi-user.target"
    ];
    wants = [ "data.mount" ];
    wantedBy = [ "multi-user.target" ];

    # Only run if the sentinel does NOT exist (first boot only)
    unitConfig.ConditionPathExists = "!/data/.completed_first_boot";
    unitConfig.RequiresMountsFor = [ "/data" ];

    # RAUC needs to be on PATH to call `rauc status mark-good`
    path = [
      pkgs.rauc
      pkgs.coreutils
      pkgs.systemd
      ubootEnvTools
    ];
    environment = firstBootEnv;

    serviceConfig = {
      Type = "oneshot";
      ExecStart = firstBootScript;
      RemainAfterExit = true;
    };
  };
}
