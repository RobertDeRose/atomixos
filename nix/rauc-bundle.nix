# Build a signed RAUC bundle containing both boot partition image and rootfs.
# This is a multi-slot bundle that RAUC installs atomically to the inactive slot pair.
{
  lib,
  stdenv,
  rauc,
  dosfstools,
  mtools,
  squashfsTools,
  nixosConfig,
  squashfsImage,
  bootScript,
  signingCert,
  signingKeyPath,
  caCert,
}:

let
  # Extract kernel and DTB from the NixOS configuration
  kernel = nixosConfig.boot.kernelPackages.kernel;
  initrd = nixosConfig.system.build.initialRamdisk;
  dtbPath = "rockchip/rk3328-rock64.dtb";
  version = nixosConfig.system.nixos.version;

  buildScript = stdenv.mkDerivation {
    name = "build-rauc-bundle-script";
    src = ../scripts/build-rauc-bundle.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@kernel@" "${kernel}" \
        --replace-fail "@initrd@" "${initrd}" \
        --replace-fail "@dtbPath@" "${dtbPath}" \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@bootScript@" "${bootScript}" \
        --replace-fail "@signingCert@" "${signingCert}" \
        --replace-fail "@signingKey@" "${signingKeyPath}" \
        --replace-fail "@version@" "${version}"
      chmod +x $out
    '';
  };
in
stdenv.mkDerivation {
  name = "rock64-rauc-bundle";
  inherit version;

  nativeBuildInputs = [
    rauc
    dosfstools
    mtools
    squashfsTools # mksquashfs — required by rauc bundle
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
