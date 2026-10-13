# Build the boot-slot filesystem for the selected board, shared by its
# factory image and RAUC update bundle.
{
  stdenvNoCC,
  dosfstools,
  mtools,
  nixosConfig,
  bootScript,
  partitionLayout,
  board ? "rock64",
}:

let
  kernel = nixosConfig.boot.kernelPackages.kernel;
  deviceTree = nixosConfig.hardware.deviceTree.package;
  initrd = nixosConfig.system.build.initialRamdisk;
  dtbPath = nixosConfig.hardware.deviceTree.name;
in
stdenvNoCC.mkDerivation {
  name = "${board}-boot-partition";
  version = "0.1.0";

  nativeBuildInputs = [
    dosfstools
    mtools
  ];

  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    mkdir -p "$out"
    dd if=/dev/zero of="$out/boot.vfat" bs=1M count=${toString partitionLayout.boot.sizeMiB} status=none
    mkfs.vfat -n BOOT "$out/boot.vfat"
    mmd -i "$out/boot.vfat" ::dtbs
    mmd -i "$out/boot.vfat" ::dtbs/rockchip
    mcopy -i "$out/boot.vfat" ${kernel}/Image ::Image
    mcopy -i "$out/boot.vfat" ${initrd}/initrd ::initrd
    mcopy -i "$out/boot.vfat" ${deviceTree}/${dtbPath} ::dtbs/${dtbPath}
    mcopy -i "$out/boot.vfat" ${bootScript}/boot.scr ::boot.scr
  '';

  passthru = { inherit partitionLayout; };
}
