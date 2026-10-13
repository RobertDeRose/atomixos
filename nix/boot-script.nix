# Compile the U-Boot boot script for board-specific RAUC A/B slot selection.
# buildId is substituted into boot.cmd so it's visible in serial output.
{
  stdenv,
  ubootTools,
  nixosConfig,
  buildId ? "unknown",
  board ? nixosConfig.atomixos.board,
  systemClosure ? nixosConfig.system.build.toplevel,
  # Keep boot.scr on the same DTB path boot-partition.nix installs.
  dtbPath ? nixosConfig.hardware.deviceTree.name,
  # Derived from the board's RAUC rootfs slots so boot.scr cannot drift from them.
  rootfsPathA ? nixosConfig.atomixos.rauc.slots.rootfs0,
  rootfsPathB ? nixosConfig.atomixos.rauc.slots.rootfs1,
  bootargsBase,
  # Empty disables the hold-button UMS trigger.
  recoveryButtonPin,
  # Empty keeps the U-Boot default ramdisk_addr_r.
  ramdiskAddr,
}:

stdenv.mkDerivation {
  name = "${board}-boot-script";
  version = "0.1.0";

  src = ../scripts/boot.cmd;

  nativeBuildInputs = [ ubootTools ];

  dontUnpack = true;
  dontConfigure = true;

  buildPhase = ''
    substitute ${../scripts/boot.cmd} boot.cmd \
      --replace-fail "@buildId@" "${buildId}" \
      --replace-fail "@systemClosure@" "${systemClosure}" \
      --replace-fail "@dtbPath@" "${dtbPath}" \
      --replace-fail "@bootargsBase@" "${bootargsBase}" \
      --replace-fail "@rootfsPathA@" "${rootfsPathA}" \
      --replace-fail "@rootfsPathB@" "${rootfsPathB}" \
      --replace-fail "@recoveryButtonPin@" "${recoveryButtonPin}" \
      --replace-fail "@ramdiskAddr@" "${ramdiskAddr}"
    mkimage -C none -A arm64 -T script -d boot.cmd boot.scr
  '';

  installPhase = ''
    mkdir -p $out
    cp boot.scr $out/
    cp boot.cmd $out/boot.cmd
  '';
}
