# Build the boot-slot filesystem for the selected board, shared by its
# factory image and RAUC update bundle.
{
  stdenvNoCC,
  dosfstools,
  mtools,
  nixosConfig,
  bootScript,
  partitionLayout,
  board ? nixosConfig.atomixos.board,
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
    # Fail with the cause instead of mcopy's "Disk full" when a kernel or initrd
    # bump outgrows the slot. FAT tables, the root directory, and cluster
    # rounding need some room, so reserve 4 MiB of the partition for them.
    capacity=$((${toString partitionLayout.boot.sizeMiB} * 1024 * 1024))
    reserve=$((4 * 1024 * 1024))
    payload=0
    for file in ${kernel}/Image ${initrd}/initrd ${deviceTree}/${dtbPath} ${bootScript}/boot.scr; do
      payload=$((payload + $(stat -L -c %s "$file")))
    done
    if [ $((payload + reserve)) -gt "$capacity" ]; then
      echo "boot partition overflow: payload $((payload / 1048576)) MiB + $((reserve / 1048576)) MiB FAT reserve exceeds the ${toString partitionLayout.boot.sizeMiB} MiB boot slot" >&2
      ls -lL ${kernel}/Image ${initrd}/initrd ${deviceTree}/${dtbPath} ${bootScript}/boot.scr >&2
      echo "Trim the kernel or initrd, or grow boot.sizeMiB in nix/partition-layout.nix." >&2
      exit 1
    fi

    mkdir -p "$out"
    dd if=/dev/zero of="$out/boot.vfat" bs=1M count=${toString partitionLayout.boot.sizeMiB} status=none
    mkfs.vfat -n BOOT "$out/boot.vfat"
    mmd -i "$out/boot.vfat" ::dtbs
    mmd -i "$out/boot.vfat" ::dtbs/${dirOf dtbPath}
    mcopy -i "$out/boot.vfat" ${kernel}/Image ::Image
    mcopy -i "$out/boot.vfat" ${initrd}/initrd ::initrd
    mcopy -i "$out/boot.vfat" ${deviceTree}/${dtbPath} ::dtbs/${dtbPath}
    mcopy -i "$out/boot.vfat" ${bootScript}/boot.scr ::boot.scr
    free=$(mdir -i "$out/boot.vfat" :: | awk '/bytes free/ { gsub(/[^0-9]/, ""); print }')
    echo "boot.vfat: $((free / 1048576)) MiB free of ${toString partitionLayout.boot.sizeMiB} MiB"
  '';

  passthru = { inherit partitionLayout; };
}
