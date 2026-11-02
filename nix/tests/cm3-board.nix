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
  # `_RUT_OH_` without a password, and with a required one, built in or missing.
  # Each fixture forces both options, so build.toml policy cannot change them.
  testPasswordHash = "$y$j9T$3b8cf4ea23612c5d1452$YA82C.PVPWBZHNWLz7qT2Tgc7tTlndR4p0AUEqUB0WA";
  cm3With =
    serialRootDebug:
    (self.nixosConfigurations.cm3.extendModules {
      modules = [ { atomixos.serialRootDebug = lib.mapAttrs (_: lib.mkForce) serialRootDebug; } ];
    }).config;
  cm3Open = cm3With {
    requirePassword = false;
    passwordHash = null;
  };
  cm3Password = cm3With {
    requirePassword = true;
    passwordHash = testPasswordHash;
  };
  cm3Locked = cm3With { requirePassword = true; };
  gateScript = config: config.systemd.services.serial-root-debug-gate.script;
  panicConditions =
    config: config.boot.initrd.systemd.services.panic-on-fail.unitConfig.ConditionKernelCommandLine;
in
# fw_env.config lists the primary copy first and the redundant copy second.
assert builtins.elemAt fwEnvLines 0 == "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET"} ${envSize}";
assert builtins.elemAt fwEnvLines 1 == "/dev/mmcblk0 ${ubootConfig "ENV_OFFSET_REDUND"} ${envSize}";
assert cm3.hardware.deviceTree.name == "rockchip/rk3566-radxa-cm3-io.dtb";
assert cm3.atomixos.rauc.compatible == "radxa-cm3-io";
assert cm3.boot.initrd.systemd.repart.device == "/dev/mmcblk0";
assert cm3.atomixos.board == "cm3";
# The onboard GMAC1 is renamed to wan by its platform path, whatever registers first.
assert cm3.systemd.network.links."10-wan".matchConfig == { Path = "platform-fe010000.ethernet"; };
assert cm3.systemd.network.links."10-wan".linkConfig.Name == "wan";
# PREBOOT and boot.cmd run `ums` for START_UMS recovery on every board.
assert ubootConfig "CMD_USB_MASS_STORAGE" == "y";
assert ubootConfig "USB_DWC3_GADGET" == "y";
assert ubootConfig "FAT_WRITE" == "y";
# A failed slot resets so the RAUC try counter can fall back.
assert lib.hasSuffix "; reset\"" (ubootConfig "BOOTCOMMAND");
# Only the eMMC is scanned, and only by the RAUC bootmeth.
assert lib.hasInfix "setenv boot_targets mmc0;" (ubootConfig "BOOTCOMMAND");
assert lib.hasInfix "bootmeth order rauc;" (ubootConfig "BOOTCOMMAND");
# With `bootmeth order` set, U-Boot refuses scans that skip global bootmeths
# (-G, a label, or a bootdev) and reports zero bootflows: scan boot_targets.
assert builtins.match ".*bootflow scan -[a-z]*G.*" (ubootConfig "BOOTCOMMAND") == null;
assert
  builtins.match ''.*bootflow scan( -[a-zA-Z]+)? [^-;"][^;"]*[;"].*'' (ubootConfig "BOOTCOMMAND")
  == null;
# A failed initrd panics, and a panic reboots, so each failure spends a boot try.
# VM tests cannot show this: the test driver adds both parameters itself.
assert builtins.elem "boot.panic_on_fail" cm3.boot.kernelParams;
assert builtins.elem "panic=10" cm3.boot.kernelParams;
# `_RUT_OH_` (atomixos.initrd_shell) is the only way to keep the initrd shell.
assert cm3Open.boot.initrd.systemd.emergencyAccess == true;
assert builtins.elem "!atomixos.initrd_shell" (panicConditions cm3Open);
# The squashfs slot can appear after initrd-root-device.target; wait for it.
assert lib.hasInfix ''until [ -b "$lower_device" ]''
  cm3.boot.initrd.systemd.services.initrd-prepare-overlay-lower.script;
# Every hardware board has the one-shot `_RUT_OH_` serial root recovery.
assert cm3.atomixos.serialRootDebug.enable;
assert cm3.systemd.services.serial-root-debug-gate.wantedBy == [ "multi-user.target" ];
assert lib.hasInfix "--autologin root"
  cm3.systemd.services."serial-root-debug@".serviceConfig.ExecStart;
# Without a required password, `_RUT_OH_` swaps the getty for the autologin.
assert lib.hasInfix "systemctl start serial-root-debug@ttyS2.service" (gateScript cm3Open);
# With one, both shells ask for it: sulogin in the initrd, the normal getty after boot.
assert cm3Password.boot.initrd.systemd.emergencyAccess == testPasswordHash;
assert builtins.elem "!atomixos.initrd_shell" (panicConditions cm3Password);
assert lib.hasInfix "usermod --password" (gateScript cm3Password);
assert !lib.hasInfix "serial-root-debug@ttyS2" (gateScript cm3Password);
# A required password that is missing disables both shells and warns.
assert cm3Locked.boot.initrd.systemd.emergencyAccess == false;
assert !builtins.elem "!atomixos.initrd_shell" (panicConditions cm3Locked);
assert lib.hasInfix "ignoring _RUT_OH_=1" (gateScript cm3Locked);
assert !lib.hasInfix "serial-root-debug@ttyS2" (gateScript cm3Locked);
assert builtins.any (lib.hasInfix "serial root shells are disabled") cm3Locked.warnings;
# RAUC refuses to install to a mounted slot, so boot slot A is never mounted at
# runtime, not even by an automount that any sandboxed service could trigger.
assert cm3.fileSystems."/boot".options == [ "noauto" ];
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
    grep -F 'dtbPath = nixosConfig.hardware.deviceTree.name;' ${../../nix/boot-partition.nix}
    grep -F 'atomixos.lowerdev=''${atomixos_lowerdev}' ${../../scripts/boot.cmd}
    grep -F '"@compatible@" "''${nixosConfig.atomixos.rauc.compatible}"' ${../../nix/rauc-bundle.nix}
    grep -F 'compatible=@compatible@' ${../../scripts/build-rauc-bundle.sh}
    touch "$out"
  ''
