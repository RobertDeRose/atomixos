# Compile the U-Boot boot script for Rock64 A/B slot selection.
{ stdenv, ubootTools }:

stdenv.mkDerivation {
  name = "rock64-boot-script";
  version = "0.1.0";

  src = ../scripts/boot.cmd;

  nativeBuildInputs = [ ubootTools ];

  dontUnpack = true;
  dontConfigure = true;

  buildPhase = ''
    mkimage -C none -A arm64 -T script -d ${../scripts/boot.cmd} boot.scr
  '';

  installPhase = ''
    mkdir -p $out
    cp boot.scr $out/
    # Also keep the source for reference
    cp ${../scripts/boot.cmd} $out/boot.cmd
  '';
}
