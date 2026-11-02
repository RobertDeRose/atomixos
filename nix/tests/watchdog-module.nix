{
  pkgs,
  self,
  qemuModule,
  ...
}:

let
  system = "aarch64-linux";
  nixlib = self.inputs.nixpkgs.lib;
  evalSystem =
    modules:
    nixlib.nixosSystem {
      inherit system;
      modules = modules ++ [
        ../../modules/base.nix
        qemuModule
      ];
      specialArgs = {
        inherit self;
        developmentMode = true;
        nixstasis = self.inputs.nixstasis;
      };
    };
  nonRaucModule =
    { lib, ... }:
    {
      atomixos.rauc.enable = lib.mkForce false;
    };
  defaults = (evalSystem [ nonRaucModule ]).config;
  enabled =
    (evalSystem [
      nonRaucModule
      {
        atomixos.watchdog.enableHardware = true;
      }
    ]).config;
  custom =
    (evalSystem [
      nonRaucModule
      {
        atomixos.watchdog = {
          enableHardware = true;
          backend = "internal";
          runtimeWatchdogSec = "45s";
          rebootWatchdogSec = "5min";
        };
      }
    ]).config;
  external =
    (evalSystem [
      nonRaucModule
      {
        atomixos.watchdog = {
          enableHardware = true;
          device = "/dev/watchdog-external";
        };
      }
    ]).config;
  bootloaderStarted =
    (evalSystem [
      nonRaucModule
      {
        atomixos.watchdog = {
          bootloaderStarted = true;
          openTimeoutSec = 240;
        };
      }
    ]).config;
  # ROCK64's U-Boot does not start a watchdog, so it keeps the build policy default.
  rock64 = self.nixosConfigurations.rock64.config;
  hasOpenTimeout =
    evaluatedConfig:
    builtins.any (nixlib.hasPrefix "watchdog.open_timeout=") evaluatedConfig.boot.kernelParams;
  customRauc =
    (evalSystem [
      ./rauc-qemu-config.nix
    ]).config;
  ubootRauc =
    (evalSystem [
      ./rauc-qemu-config.nix
      (
        { lib, ... }:
        {
          atomixos.rauc.bootloader = lib.mkForce "uboot";
        }
      )
    ]).config;
  hasBootCountPackage =
    evaluatedConfig:
    builtins.any (
      package: nixlib.getName package == "watchdog-boot-count"
    ) evaluatedConfig.environment.systemPackages;
  ubootEnvTools = toString self.packages.${system}.rock64.uboot-env-tools;
  customService = customRauc.systemd.services.watchdog-boot-count;
  ubootService = ubootRauc.systemd.services.watchdog-boot-count;
  serviceContract =
    service:
    builtins.elem "multi-user.target" service.wantedBy
    && builtins.elem "rauc.service" service.before
    && builtins.elem "local-fs.target" service.after
    && builtins.any (package: nixlib.getName package == "watchdog-boot-count") service.path
    && nixlib.hasSuffix "/bin/watchdog-boot-count" service.serviceConfig.ExecStart
    && service.environment.ATOMIXOS_RAUC_STATE_DIR == "/var/lib/rauc";
in
pkgs.runCommand "watchdog-module-check" { } ''
  set -euo pipefail

  test ${builtins.toJSON (defaults.atomixos.watchdog.enableHardware == false)} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.backend == "external")} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.runtimeWatchdogSec == "30s")} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.rebootWatchdogSec == "10min")} = true
  test ${builtins.toJSON (!(defaults.systemd.settings.Manager ? RuntimeWatchdogSec))} = true
  test ${builtins.toJSON (!(defaults.systemd.settings.Manager ? RebootWatchdogSec))} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.device == null)} = true
  test ${builtins.toJSON (!(defaults.systemd.settings.Manager ? WatchdogDevice))} = true
  test ${builtins.toJSON (!builtins.hasAttr "watchdog-boot-count" defaults.systemd.services)} = true
  test ${builtins.toJSON (!hasBootCountPackage defaults)} = true

  test ${builtins.toJSON (defaults.atomixos.watchdog.bootloaderStarted == false)} = true
  test ${builtins.toJSON (!hasOpenTimeout defaults)} = true
  test ${builtins.toJSON (!hasOpenTimeout enabled)} = true

  # A bootloader-started watchdog turns on enforcement and bounds the kernel's
  # pre-userspace feeding, even though enableHardware stays false.
  test ${builtins.toJSON (bootloaderStarted.atomixos.watchdog.enableHardware == false)} = true
  test ${builtins.toJSON (builtins.elem "watchdog.open_timeout=240" bootloaderStarted.boot.kernelParams)} = true
  test ${
    builtins.toJSON (bootloaderStarted.systemd.settings.Manager.RuntimeWatchdogSec == "30s")
  } = true
  test ${
    builtins.toJSON (bootloaderStarted.systemd.settings.Manager.RebootWatchdogSec == "10min")
  } = true
  test ${builtins.toJSON (bootloaderStarted.systemd.services ? watchdog-device-check)} = true

  test ${builtins.toJSON (rock64.atomixos.watchdog.bootloaderStarted == false)} = true
  test ${builtins.toJSON (!hasOpenTimeout rock64)} = true
  test ${
    builtins.toJSON (
      !(nixlib.hasInfix "CONFIG_WATCHDOG_AUTOSTART=y" rock64.atomixos.ubootEnvTools.extraConfig)
    )
  } = true
  test ${
    builtins.toJSON (
      rock64.atomixos.watchdog.enableHardware == (rock64.systemd.settings.Manager ? RuntimeWatchdogSec)
    )
  } = true

  test ${builtins.toJSON (enabled.systemd.settings.Manager.RuntimeWatchdogSec == "30s")} = true
  test ${builtins.toJSON (enabled.systemd.settings.Manager.RebootWatchdogSec == "10min")} = true

  test ${builtins.toJSON (custom.atomixos.watchdog.backend == "internal")} = true
  test ${builtins.toJSON (custom.systemd.settings.Manager.RuntimeWatchdogSec == "45s")} = true
  test ${builtins.toJSON (custom.systemd.settings.Manager.RebootWatchdogSec == "5min")} = true

  test ${
    builtins.toJSON (external.systemd.settings.Manager.WatchdogDevice == "/dev/watchdog-external")
  } = true

  test ${builtins.toJSON (hasBootCountPackage customRauc)} = true
  test ${builtins.toJSON (serviceContract customService)} = true
  test ${builtins.toJSON (customService.environment.ATOMIXOS_RAUC_BOOTLOADER == "custom")} = true
  test ${builtins.toJSON (!(builtins.elem ubootEnvTools (map toString customService.path)))} = true

  test ${builtins.toJSON (hasBootCountPackage ubootRauc)} = true
  test ${builtins.toJSON (serviceContract ubootService)} = true
  test ${builtins.toJSON (ubootService.environment.ATOMIXOS_RAUC_BOOTLOADER == "uboot")} = true
  test ${builtins.toJSON (builtins.elem ubootEnvTools (map toString ubootService.path))} = true

  mkdir -p "$out"
''
