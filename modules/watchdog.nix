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
  watchdogDeviceCheck = pkgs.writeShellScript "watchdog-device-check" ''
    set -eu

    device_present=false
    for attempt in 1 2 3 4 5; do
      device_present=false
      for device in /dev/watchdog /dev/watchdog0; do
        if [ -c "$device" ]; then
          device_present=true
          break
        fi
      done

      if [ "$device_present" = true ]; then
        for fd in /proc/1/fd/*; do
          target="$(${pkgs.coreutils}/bin/readlink "$fd" 2>/dev/null || true)"
          case "$target" in
            /dev/watchdog*) exit 0 ;;
          esac
        done
      fi

      [ "$attempt" -eq 5 ] || ${pkgs.coreutils}/bin/sleep 1
    done

    if [ "$device_present" = false ]; then
      message="hardware watchdog enforcement is unavailable: no watchdog character device exists"
    else
      message="hardware watchdog enforcement is unavailable: systemd does not hold a watchdog device"
    fi

    printf '%s\n' "$message" | ${pkgs.systemd}/bin/systemd-cat \
      --identifier=watchdog-device-check \
      --priority=warning
  '';
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

    systemd.services.watchdog-device-check = lib.mkIf cfg.enableHardware {
      description = "Report unavailable hardware watchdog enforcement";
      wantedBy = [ "multi-user.target" ];
      after = [
        "multi-user.target"
        "systemd-modules-load.service"
        "systemd-udevd.service"
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = watchdogDeviceCheck;
        RemainAfterExit = true;
      };
    };

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
