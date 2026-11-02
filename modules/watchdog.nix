# Systemd watchdog configuration.
# Enforcement is opt-in through build policy, except on boards whose U-Boot
# starts the watchdog before the kernel (bootloaderStarted): there systemd
# always holds it, and the kernel feeds it only until openTimeoutSec, so a boot
# that stalls before systemd resets the board and spends a RAUC boot try.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.atomixos.watchdog;
  # A bootloader-started watchdog must be held by systemd: once the kernel's
  # open timeout passes, nothing else feeds it.
  enforced = cfg.enableHardware || cfg.bootloaderStarted;
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

    backend = lib.mkOption {
      type = lib.types.enum [
        "internal"
        "external"
      ];
      default = "external";
      description = "Watchdog implementation selected by immutable build policy on hardware-specific systems.";
    };

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

    device = lib.mkOption {
      type = lib.types.nullOr lib.types.str;
      default = null;
      description = "Stable watchdog device path selected by systemd when hardware enforcement is enabled.";
    };

    bootloaderStarted = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Whether the board's U-Boot starts the hardware watchdog before booting the kernel. Board modules set
        this to match their U-Boot build. It turns on systemd enforcement whatever enableHardware says, and
        adds watchdog.open_timeout so a boot that stalls before systemd opens the watchdog resets the board.
      '';
    };

    openTimeoutSec = lib.mkOption {
      type = lib.types.ints.positive;
      default = 180;
      description = ''
        Seconds after the kernel's watchdog driver registers during which the kernel feeds a
        bootloader-started watchdog before systemd opens it (watchdog.open_timeout). It must cover the kernel
        and the initrd on a slow first boot, which creates slot B and formats /data.
      '';
    };
  };

  config = {
    # ── Watchdog ─────────────────────────────────────────────────────────────────

    boot.kernelParams = lib.optional cfg.bootloaderStarted "watchdog.open_timeout=${toString cfg.openTimeoutSec}";

    systemd.settings.Manager = lib.mkIf enforced {
      RuntimeWatchdogSec = cfg.runtimeWatchdogSec;
      RebootWatchdogSec = cfg.rebootWatchdogSec;
      WatchdogDevice = lib.mkIf (cfg.device != null) cfg.device;
    };

    environment.systemPackages = lib.optionals config.atomixos.rauc.enable [
      watchdogBootCountCli
    ];

    systemd.services.watchdog-device-check = lib.mkIf enforced {
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

    systemd.services.watchdog-boot-count = lib.mkIf config.atomixos.rauc.enable {
      description = "Record watchdog boot-count and rollback state";
      wantedBy = [ "multi-user.target" ];
      before = [ "rauc.service" ];
      after = [ "local-fs.target" ];
      path = [
        watchdogBootCountCli
      ]
      ++ lib.optionals (config.atomixos.rauc.bootloader == "uboot") [
        config.atomixos.ubootEnvTools
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
