# Build a signed RAUC bundle containing both boot partition image and rootfs.
# This is a multi-slot bundle that RAUC installs atomically to the inactive slot pair.
{
  stdenv,
  rauc,
  squashfsTools,
  buildConfiguration,
  nixosConfig,
  squashfsImage,
  bootPartition,
  signingCert,
  signingKeyPath,
}:

let
  version = nixosConfig.system.nixos.version;
  bundleName = "rock64${buildConfiguration.artifactSuffix}.raucb";

  buildScript = stdenv.mkDerivation {
    name = "build-rauc-bundle-script";
    src = ../scripts/build-rauc-bundle.sh;
    dontUnpack = true;
    dontBuild = true;
    installPhase = ''
      substitute $src $out \
        --replace-fail "@squashfs@" "${squashfsImage}" \
        --replace-fail "@bootPartition@" "${bootPartition}" \
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
