# Build a squashfs image from the NixOS system closure.
# Includes a size check to ensure it fits within the A/B partition slot.
{
  lib,
  stdenv,
  squashfsTools,
  closureInfo,
  nixosConfig,
  maxSquashfsSize,
}:

let
  # Get the full system closure (everything needed to boot)
  systemClosure = nixosConfig.system.build.toplevel;

  # closureInfo computes all store paths reachable from the toplevel.
  # Without this, mksquashfs would only pack the immediate directory.
  closure = closureInfo { rootPaths = [ systemClosure ]; };

  buildScript = stdenv.mkDerivation {
    name = "build-squashfs-script";
    src = ../scripts/build-squashfs.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@systemClosure@" "${systemClosure}" \
        --replace-fail "@closureInfo@" "${closure}" \
        --replace-fail "@maxSize@" "${toString maxSquashfsSize}"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-squashfs";
  version = "0.1.0";

  nativeBuildInputs = [ squashfsTools ];

  # No source — we're packaging the NixOS closure
  dontUnpack = true;
  dontConfigure = true;
  dontBuild = true;

  # Ensure the closure is available in the sandbox
  disallowedReferences = [ ];

  installPhase = ''
    bash ${buildScript}
  '';
}
