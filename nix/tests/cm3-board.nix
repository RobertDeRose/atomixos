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
  fwEnvLines = builtins.filter (line: line != "") (map lib.trim (lib.splitString "\n" fwEnvConfig));
  uboot = self.packages.${pkgs.stdenv.hostPlatform.system}.cm3.uboot;
  # Settings the resolved .config must carry verbatim (=n may also be absent).
  enabledSettings = builtins.filter (
    line: lib.hasPrefix "CONFIG_" line && !(lib.hasSuffix "=n" line)
  ) ubootConfigLines;
  envSize = ubootConfig "ENV_SIZE";
in
# fw_env.config lists the primary copy first and the redundant copy second.
assert builtins.elemAt fwEnvLines 0 == "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET"} ${envSize}";
assert builtins.elemAt fwEnvLines 1 == "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET_REDUND"} ${envSize}";
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
# The squashfs slot can appear after initrd-root-device.target; wait for it.
assert lib.hasInfix ''until [ -b "$lower_device" ]''
  cm3.boot.initrd.systemd.services.initrd-prepare-overlay-lower.script;
# RAUC refuses to install to a mounted slot, so boot slot A is not kept mounted.
assert builtins.elem "x-systemd.automount" cm3.fileSystems."/boot".options;
assert builtins.elem "noauto" cm3.fileSystems."/boot".options;
pkgs.runCommand "test-cm3-board"
  {
    passAsFile = [ "enabledSettings" ];
    enabledSettings = lib.concatLines enabledSettings;
  }
  ''
    # Every enabled extraConfig line must survive into U-Boot's resolved .config;
    # Kconfig drops unknown or renamed symbols without an error.
    missing=0
    while IFS= read -r setting; do
      if ! grep -qxF -- "$setting" ${uboot}/u-boot.config; then
        echo "uboot-cm3 .config lacks: $setting" >&2
        missing=1
      fi
    done <"$enabledSettingsPath"
    test "$missing" -eq 0
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
