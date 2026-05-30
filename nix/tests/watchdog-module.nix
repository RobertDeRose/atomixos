{
  pkgs,
  self,
  qemuModule,
  ...
}:

let
  system = "aarch64-linux";
  evalSystem =
    modules:
    self.inputs.nixpkgs.lib.nixosSystem {
      inherit system;
      modules = modules ++ [
        ../../modules/base.nix
        qemuModule
        (
          { lib, ... }:
          {
            atomixos.rauc.enable = lib.mkForce false;
          }
        )
      ];
      specialArgs = {
        inherit self;
        developmentMode = true;
        nixstasis = self.inputs.nixstasis;
      };
    };
  defaults = (evalSystem [ ]).config;
  enabled =
    (evalSystem [
      {
        atomixos.watchdog.enableHardware = true;
      }
    ]).config;
  custom =
    (evalSystem [
      {
        atomixos.watchdog = {
          enableHardware = true;
          runtimeWatchdogSec = "45s";
          rebootWatchdogSec = "5min";
        };
      }
    ]).config;
in
pkgs.runCommand "watchdog-module-check" { } ''
  set -euo pipefail

  test ${builtins.toJSON (defaults.atomixos.watchdog.enableHardware == false)} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.runtimeWatchdogSec == "30s")} = true
  test ${builtins.toJSON (defaults.atomixos.watchdog.rebootWatchdogSec == "10min")} = true
  test ${builtins.toJSON (!(defaults.systemd.settings.Manager ? RuntimeWatchdogSec))} = true
  test ${builtins.toJSON (!(defaults.systemd.settings.Manager ? RebootWatchdogSec))} = true

  test ${builtins.toJSON (enabled.systemd.settings.Manager.RuntimeWatchdogSec == "30s")} = true
  test ${builtins.toJSON (enabled.systemd.settings.Manager.RebootWatchdogSec == "10min")} = true

  test ${builtins.toJSON (custom.systemd.settings.Manager.RuntimeWatchdogSec == "45s")} = true
  test ${builtins.toJSON (custom.systemd.settings.Manager.RebootWatchdogSec == "5min")} = true

  mkdir -p "$out"
''
