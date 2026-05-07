# First-boot initialization — runs once on initial device boot.
#
# Imports provisioning state and writes a sentinel file
# (/data/.completed_first_boot) so it never runs again. When RAUC is enabled,
# it also marks the current slot good because there is no health manifest or
# container image state yet on first boot.
#
# os-verification.service has the inverse condition — it only runs after
# the sentinel exists (i.e. on all boots AFTER the first) and only when RAUC
# confirmation is enabled.
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
  provisionCli = pkgs.runCommand "first-boot-provision" { } ''
    mkdir -p "$out/bin" "$out/share/atomixos"
    install -m0755 ${../scripts/first-boot-provision.py} "$out/bin/first-boot-provision"
    install -m0644 ${../docs/src/atomixos.png} "$out/share/atomixos/atomixos.png"
    install -m0644 ${../schemas/config.schema.json} "$out/share/atomixos/config.schema.json"
  '';
  ubootEnvTools = self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools;
  firstBootEnv = {
    ATOMIXOS_RAUC_ENABLE = if config.atomixos.rauc.enable then "1" else "0";
  };
in
{
  systemd.services.quadlet-sync = {
    description = "Sync provisioned Quadlet units";
    after = [
      "data.mount"
      "network-online.target"
      "chronyd.service"
    ];
    wants = [
      "data.mount"
      "network-online.target"
    ];
    wantedBy = [ "multi-user.target" ];

    unitConfig.ConditionPathExists = "/data/config/config.toml";
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.chrony
      pkgs.gzip
      pkgs.jq
      pkgs.podman
      pkgs.python3Minimal
      pkgs.util-linux
      pkgs.systemd
      pkgs.zstd
      provisionCli
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStartPre = "${pkgs.chrony}/bin/chronyc waitsync 0 1";
      ExecStart = quadletSyncScript;
      TimeoutStartSec = 300;
    };
  };

  systemd.services.first-boot = {
    description = "First-boot initialization (provision, confirm slot if enabled)";
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
    path =
      lib.optionals config.atomixos.rauc.enable [
        pkgs.rauc
        ubootEnvTools
      ]
      ++ [
        pkgs.coreutils
        pkgs.gzip
        pkgs.jq
        pkgs.systemd
        pkgs.python3Minimal
        pkgs.zstd
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
