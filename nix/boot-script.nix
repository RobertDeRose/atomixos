# Compile the U-Boot boot script for board-specific RAUC A/B slot selection.
# buildId is substituted into boot.cmd so it's visible in serial output.
{
  stdenv,
  ubootTools,
  buildId ? "unknown",
  systemClosure,
  board ? "rock64",
  dtbPath ? "rockchip/rk3328-rock64.dtb",
  bootargsBase ? "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xff130000 loglevel=7 rootwait",
  # Pass the board's RAUC rootfs slot devices so boot.scr cannot drift from them.
  rootfsPathA,
  rootfsPathB,
  recoveryButtonPin ? "100",
  # Empty keeps the U-Boot default ramdisk_addr_r.
  ramdiskAddr ? "0x08000000",
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
