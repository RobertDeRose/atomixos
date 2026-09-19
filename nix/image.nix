# Build a flashable disk image for the Rock64 eMMC.
# Contains: GPT partition table, U-Boot, boot slot A (kernel + DTB + initrd +
# boot.scr), rootfs slot A (squashfs), and first-boot-created slot B + /data
# partitions.
{
  stdenv,
  util-linux,
  ubootRock64,
  buildConfiguration,
  nixosConfig,
  squashfsImage,
  bootPartition,
  partitionLayout,
}:

let
  nixosVersion = nixosConfig.system.nixos.version;
  nixosSeries =
    let
      match = builtins.match "([0-9]+\\.[0-9]+).*" nixosVersion;
    in
    if match == null then nixosVersion else builtins.elemAt match 0;
  imageName = "atomixos-${nixosSeries}${buildConfiguration.artifactSuffix}.img";

  buildScript = stdenv.mkDerivation {
    name = "build-image-script";
    src = ../scripts/build-image.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@bootPartition@" "${bootPartition}" \
        --replace-fail "@uboot@" "${ubootRock64}" \
        --replace-fail "@imageName@" "${imageName}" \
        --replace-fail "@bootStartMiB@" "${toString partitionLayout.boot.startMiB}" \
        --replace-fail "@bootSizeMiB@" "${toString partitionLayout.boot.sizeMiB}" \
        --replace-fail "@bootTypeGuid@" "${partitionLayout.boot.typeGuid}" \
        --replace-fail "@bootLabelA@" "${partitionLayout.boot.labels.a}" \
        --replace-fail "@rootfsStartMiB@" "${toString partitionLayout.rootfs.startMiB}" \
        --replace-fail "@rootfsSizeMiB@" "${toString partitionLayout.rootfs.sizeMiB}" \
        --replace-fail "@rootfsTypeGuid@" "${partitionLayout.rootfs.typeGuid}" \
        --replace-fail "@rootfsLabelA@" "${partitionLayout.rootfs.labels.a}" \
        --replace-fail "@bootLabelB@" "${partitionLayout.boot.labels.b}" \
        --replace-fail "@rootfsLabelB@" "${partitionLayout.rootfs.labels.b}" \
        --replace-fail "@gptTailSlackMiB@" "${toString partitionLayout.gptTailSlackMiB}"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-image";
  version = "0.1.0";

  nativeBuildInputs = [
    util-linux # sfdisk
  ];

  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    bash ${buildScript}
    install -m 0444 ${buildConfiguration.tomlFile} "$out/build.toml"
    install -m 0444 ${buildConfiguration.metadataFile} "$out/build-metadata.json"
  '';

  passthru = {
    artifactName = imageName;
    inherit buildConfiguration;
  };
}
