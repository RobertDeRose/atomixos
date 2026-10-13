# CM3 hardware output wiring, including U-Boot/fw_env.config environment agreement
# and ROCK64 U-Boot feature parity (UMS recovery, FAT write).
{
  pkgs,
  self,
  ...
}:
let
  inherit (pkgs) lib;
  cm3 = self.nixosConfigurations.cm3.config;
  ubootConfigLines = map lib.trim (lib.splitString "\n" cm3.atomixos.ubootEnvTools.extraConfig);
  ubootConfig =
    name:
    lib.removePrefix "CONFIG_${name}=" (
      lib.findFirst (
        line: lib.hasPrefix "CONFIG_${name}=" line
      ) (throw "uboot-cm3 extraConfig lacks CONFIG_${name}") ubootConfigLines
    );
  fwEnvConfig = cm3.environment.etc."fw_env.config".text;
  envSize = ubootConfig "ENV_SIZE";
in
assert lib.hasInfix "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET"} ${envSize}" fwEnvConfig;
assert lib.hasInfix "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET_REDUND"} ${envSize}" fwEnvConfig;
assert cm3.hardware.deviceTree.name == "rockchip/rk3566-radxa-cm3-io.dtb";
assert cm3.atomixos.rauc.compatible == "radxa-cm3-io";
assert cm3.boot.initrd.systemd.repart.device == "/dev/mmcblk0";
assert cm3.atomixos.board == "cm3";
# boot.cmd runs `ums` for START_UMS recovery on every board.
assert ubootConfig "CMD_USB_MASS_STORAGE" == "y";
assert ubootConfig "USB_DWC3_GADGET" == "y";
assert ubootConfig "FAT_WRITE" == "y";
# A failed slot resets so the RAUC try counter can fall back.
assert lib.hasSuffix "; reset\"" (ubootConfig "BOOTCOMMAND");
# RAUC refuses to install to a mounted slot, so boot slot A is not kept mounted.
assert builtins.elem "x-systemd.automount" cm3.fileSystems."/boot".options;
assert builtins.elem "noauto" cm3.fileSystems."/boot".options;
pkgs.runCommand "test-cm3-board" { } ''
  grep -F 'defconfig = "radxa-cm3-io-rk3566_defconfig";' ${../../nix/uboot-cm3.nix}
  grep -F 'CONFIG_ENV_IS_IN_MMC=y' ${../../nix/uboot-cm3.nix}
  grep -F 'CONFIG_ENV_REDUNDANT=y' ${../../nix/uboot-cm3.nix}
  grep -F 'CONFIG_BOOTCOMMAND="bootmeth order rauc; bootflow scan -lb mmc0; reset"' ${../../nix/uboot-cm3.nix}
  grep -F 'dtbPath = nixosConfig.hardware.deviceTree.name;' ${../../nix/boot-partition.nix}
  grep -F 'atomixos.lowerdev=''${atomixos_lowerdev}' ${../../scripts/boot.cmd}
  grep -F '"@compatible@" "''${nixosConfig.atomixos.rauc.compatible}"' ${../../nix/rauc-bundle.nix}
  grep -F 'compatible=@compatible@' ${../../scripts/build-rauc-bundle.sh}
  touch "$out"
''
