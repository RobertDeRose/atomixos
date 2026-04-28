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
  ...
}:

let
  firstBootScript = pkgs.writeShellScript "first-boot" (builtins.readFile ../scripts/first-boot.sh);
  quadletSyncScript = pkgs.writeShellScript "quadlet-sync" (
    builtins.readFile ../scripts/quadlet-sync.sh
  );
  provisionCli = pkgs.writeScriptBin "first-boot-provision" (
    builtins.readFile ../scripts/first-boot-provision.py
  );
  ubootEnvTools = self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools;
  firstBootEnv = lib.optionalAttrs developmentMode {
    ATOMIXOS_DEV_ENABLE_SSH_WAN = "1";
  };
in
{
  systemd.services.quadlet-sync = {
    description = "Sync provisioned Quadlet units";
    after = [ "data.mount" ];
    wants = [ "data.mount" ];
    before = [ "multi-user.target" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig.ConditionPathExists = "/data/config/config.toml";
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.gzip
      pkgs.podman
      pkgs.python3Minimal
      pkgs.util-linux
      pkgs.systemd
      pkgs.zstd
      provisionCli
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = quadletSyncScript;
    };
  };

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
      pkgs.gzip
      pkgs.systemd
      pkgs.python3Minimal
      pkgs.zstd
      ubootEnvTools
      pkgs.util-linux
      provisionCli
    ];
    environment = firstBootEnv;

    serviceConfig = {
      Type = "oneshot";
      ExecStart = firstBootScript;
      RemainAfterExit = true;
    };
  };
}
