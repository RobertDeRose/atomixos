# Systemd watchdog configuration.
# Integration is implemented but intentionally disabled during development
# until Rock64 boot reliability is fully validated.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

let
  cfg = config.atomixos.watchdog;
  watchdogBootCountCli = pkgs.writeShellScriptBin "watchdog-boot-count" (
    builtins.readFile ../scripts/watchdog-boot-count.sh
  );
in
{
  options.atomixos.watchdog = {
    enableHardware = lib.mkEnableOption "systemd hardware watchdog enforcement";

    runtimeWatchdogSec = lib.mkOption {
      type = lib.types.str;
      default = "30s";
      description = "systemd RuntimeWatchdogSec value used when hardware watchdog enforcement is enabled.";
    };

    rebootWatchdogSec = lib.mkOption {
      type = lib.types.str;
      default = "10min";
      description = "systemd RebootWatchdogSec value used when hardware watchdog enforcement is enabled.";
    };
  };

  config = {
    # ── Watchdog ─────────────────────────────────────────────────────────────────

    systemd.settings.Manager = lib.mkIf cfg.enableHardware {
      RuntimeWatchdogSec = cfg.runtimeWatchdogSec;
      RebootWatchdogSec = cfg.rebootWatchdogSec;
    };

    environment.systemPackages = [
      watchdogBootCountCli
    ];

    systemd.services.watchdog-boot-count = {
      description = "Record watchdog boot-count and rollback state";
      wantedBy = [ "multi-user.target" ];
      before = [ "rauc.service" ];
      after = [ "local-fs.target" ];
      path = [
        watchdogBootCountCli
      ]
      ++ lib.optionals (config.atomixos.rauc.bootloader == "uboot") [
        self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = "${watchdogBootCountCli}/bin/watchdog-boot-count";
      };
      environment = {
        ATOMIXOS_RAUC_BOOTLOADER = config.atomixos.rauc.bootloader;
        ATOMIXOS_RAUC_STATE_DIR = "/var/lib/rauc";
      };
    };
  };
}
