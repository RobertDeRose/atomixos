# Build a flashable disk image for the Rock64 eMMC.
# Contains: GPT partition table, U-Boot, boot slot A (kernel + DTB + boot.scr),
# empty boot slot B, rootfs slot A (squashfs), empty rootfs slot B.
# The /persist partition is NOT included — systemd-repart creates and formats
# it as f2fs on first boot, filling remaining eMMC space.
{
  lib,
  stdenv,
  dosfstools,
  mtools,
  util-linux,
  ubootRock64,
  nixosConfig,
  squashfsImage,
  bootScript,
}:

let
  kernel = nixosConfig.boot.kernelPackages.kernel;
  dtbPath = "rockchip/rk3328-rock64.dtb";

  buildScript = stdenv.mkDerivation {
    name = "build-image-script";
    src = ../scripts/build-image.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@kernel@" "${kernel}" \
        --replace-fail "@dtbPath@" "${dtbPath}" \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@bootScript@" "${bootScript}" \
        --replace-fail "@uboot@" "${ubootRock64}"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-image";
  version = "0.1.0";

  nativeBuildInputs = [
    dosfstools
    mtools
    util-linux # sfdisk
  ];

  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    bash ${buildScript}
  '';
}
