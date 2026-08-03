# Build a signed RAUC bundle containing both boot partition image and rootfs.
# This is a multi-slot bundle that RAUC installs atomically to the inactive slot pair.
{
  stdenv,
  rauc,
  dosfstools,
  mtools,
  squashfsTools,
  buildConfiguration,
  nixosConfig,
  squashfsImage,
  bootScript,
  signingCert,
  signingKeyPath,
}:

let
  # Extract kernel and the overlaid DTB package from the NixOS configuration
  kernel = nixosConfig.boot.kernelPackages.kernel;
  deviceTree = nixosConfig.hardware.deviceTree.package;
  initrd = nixosConfig.system.build.initialRamdisk;
  dtbPath = "rockchip/rk3328-rock64.dtb";
  version = nixosConfig.system.nixos.version;
  bundleName = "rock64${buildConfiguration.artifactSuffix}.raucb";

  buildScript = stdenv.mkDerivation {
    name = "build-rauc-bundle-script";
    src = ../scripts/build-rauc-bundle.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@kernel@" "${kernel}" \
        --replace-fail "@deviceTree@" "${deviceTree}" \
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
    mkdir -p "$out"
    install -m 0444 rock64.raucb "$out/${bundleName}"
    install -m 0444 ${buildConfiguration.tomlFile} "$out/build.toml"
    install -m 0444 ${buildConfiguration.metadataFile} "$out/build-metadata.json"
    echo "RAUC bundle created: $out/${bundleName}"
    ls -lh "$out/${bundleName}"
  '';

  passthru = {
    artifactName = bundleName;
    inherit buildConfiguration;
  };
}
