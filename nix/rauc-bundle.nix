# Build a signed RAUC bundle containing both boot partition image and rootfs.
# This is a multi-slot bundle that RAUC installs atomically to the inactive slot pair.
#
# signingKey is a path string (not a Nix store path) so it doesn't need to be
# in the git tree / flake source. Pass it at build time:
#   nix build .#rauc-bundle --override-input ... or via --arg
{
  lib,
  stdenv,
  rauc,
  dosfstools,
  mtools,
  nixosConfig,
  squashfsImage,
  signingCert,
  signingKeyPath ? "",
  caCert,
}:

let
  # Extract kernel and DTB from the NixOS configuration
  kernel = nixosConfig.boot.kernelPackages.kernel;
  dtbPath = "rockchip/rk3328-rock64.dtb";

  buildScript = stdenv.mkDerivation {
    name = "build-rauc-bundle-script";
    src = ../scripts/build-rauc-bundle.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@kernel@" "${kernel}" \
        --replace-fail "@dtbPath@" "${dtbPath}" \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@signingCert@" "${signingCert}" \
        --replace-fail "@signingKey@" "${signingKeyPath}" \
        --replace-fail "@version@" "0.1.0"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-rauc-bundle";
  version = "0.1.0";

  nativeBuildInputs = [
    rauc
    dosfstools
    mtools
  ];

  dontUnpack = true;
  dontConfigure = true;

  buildPhase = ''
    bash ${buildScript}
  '';

  installPhase = ''
    mkdir -p $out
    cp rock64.raucb $out/
    echo "RAUC bundle created: $out/rock64.raucb"
    ls -lh $out/rock64.raucb
  '';
}
