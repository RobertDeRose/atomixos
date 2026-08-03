# Verify boot artifacts use the NixOS device-tree package, including overlays.
{
  pkgs,
  ...
}:
pkgs.runCommand "test-device-tree-overlay" { } ''
  image_script=${../../scripts/build-image.sh}
  bundle_script=${../../scripts/build-rauc-bundle.sh}
  overlay=${../../dts/rock64-i2c-header.dts}
  internal_overlay=${../../dts/rock64-internal-watchdog.dts}
  hardware_module=${../../modules/hardware-rock64.nix}
  kernel_config=${../../modules/kernel-config.nix}
  watchdog_module=${../../modules/watchdog.nix}

  grep -F '"@deviceTree@/@dtbPath@"' "$image_script"
  grep -F '"@deviceTree@/@dtbPath@"' "$bundle_script"
  grep -F 'compatible = "pine64,rock64", "rockchip,rk3328";' "$overlay"
  grep -F 'compatible = "pine64,rock64", "rockchip,rk3328";' "$internal_overlay"
  grep -F '&wdt {' "$internal_overlay"
  grep -F 'snps,watchdog-tops = <' "$internal_overlay"
  grep -F '&{/} {' "$overlay"
  grep -F 'compatible = "ti,pca9536";' "$overlay"
  grep -F 'gpios = <&watchdog_gpio 1 0>;' "$overlay"
  grep -F 'hw_algo = "toggle";' "$overlay"
  grep -F 'always-running;' "$overlay"
  grep -F 'internal = "/dev/watchdog-internal";' "$hardware_module"
  grep -F 'dtsFile = ../dts/rock64-internal-watchdog.dts;' "$hardware_module"
  grep -F 'config.atomixos.watchdog.enableHardware' "$hardware_module"
  grep -F '&& config.atomixos.watchdog.backend == "external"' "$hardware_module"
  grep -F 'external = "/dev/watchdog-external";' "$hardware_module"
  grep -F 'atomixos.watchdog.device = watchdogDevice;' "$hardware_module"
  grep -F 'KERNELS=="ff1a0000.watchdog", SYMLINK+="watchdog-internal"' "$hardware_module"
  grep -F 'KERNELS=="watchdog-external", SYMLINK+="watchdog-external"' "$hardware_module"
  grep -F 'GPIO_PCA953X = lib.mkForce yes;' "$kernel_config"
  grep -F 'GPIO_WATCHDOG = lib.mkForce yes;' "$kernel_config"
  grep -F 'WatchdogDevice = lib.mkIf' "$watchdog_module"

  touch "$out"
''
