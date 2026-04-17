# Compile the U-Boot boot script for Rock64 A/B slot selection.
# buildId is substituted into boot.cmd so it's visible in serial output.
{
  stdenv,
  ubootTools,
  buildId ? "unknown",
}:

stdenv.mkDerivation {
  name = "rock64-boot-script";
  version = "0.1.0";

  src = ../scripts/boot.cmd;

  nativeBuildInputs = [ ubootTools ];

  dontUnpack = true;
  dontConfigure = true;

  buildPhase = ''
    substitute ${../scripts/boot.cmd} boot.cmd \
      --replace-fail "@buildId@" "${buildId}"
    mkimage -C none -A arm64 -T script -d boot.cmd boot.scr
  '';

  installPhase = ''
    mkdir -p $out
    cp boot.scr $out/
    cp boot.cmd $out/boot.cmd
  '';
}
