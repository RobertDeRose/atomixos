# Build a flashable disk image for the Rock64 eMMC.
# Contains: GPT partition table, U-Boot, boot slot A (kernel + DTB + initrd +
# boot.scr), rootfs slot A (squashfs), and first-boot-created slot B + /data
# partitions.
{
  stdenv,
  dosfstools,
  f2fs-tools,
  mtools,
  util-linux,
  ubootRock64,
  nixosConfig,
  squashfsImage,
  bootScript,
}:

let
  kernel = nixosConfig.boot.kernelPackages.kernel;
  initrd = nixosConfig.system.build.initialRamdisk;
  dtbPath = "rockchip/rk3328-rock64.dtb";
  nixosVersion = nixosConfig.system.nixos.version;
  nixosSeries =
    let
      match = builtins.match "([0-9]+\\.[0-9]+).*" nixosVersion;
    in
    if match == null then nixosVersion else builtins.elemAt match 0;
  imageName = "atomixos-${nixosSeries}.img";

  buildScript = stdenv.mkDerivation {
    name = "build-image-script";
    src = ../scripts/build-image.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@kernel@" "${kernel}" \
        --replace-fail "@initrd@" "${initrd}" \
        --replace-fail "@dtbPath@" "${dtbPath}" \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@bootScript@" "${bootScript}" \
        --replace-fail "@uboot@" "${ubootRock64}" \
        --replace-fail "@imageName@" "${imageName}"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-image";
  version = "0.1.0";

  nativeBuildInputs = [
    dosfstools
    f2fs-tools
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
