{
  pkgs,
  qemuModule,
  self,
  ...
}:

let
  evaluator = import ../build-configuration.nix {
    lib = self.inputs.nixpkgs.lib;
  };
  baseText = ''
    version = 1

    [watchdog]
    enable_hardware = false
    backend = "external"
    runtime_timeout = "30s"
    reboot_timeout = "10min"

    [provisioning]
    bootstrap_transport = "network"

    [nixstasis]
    enable = false
    api_url = ""
    frp_server_addr = ""
    frp_server_port = 7000
  '';
  evaluate =
    args:
    evaluator.evaluate (
      {
        baseName = "build.toml";
        inherit baseText;
      }
      // args
    );
  defaults = evaluate { };
  overridden = evaluate {
    overlayName = "build.dev.toml";
    overlayText = ''
      [watchdog]
      enable_hardware = true
      backend = "internal"
      runtime_timeout = "45s"
    '';
  };
  fleet = evaluate {
    overlayName = "build.fleet.toml";
    overlayText = ''
      [provisioning]
      bootstrap_transport = "nixstasis"

      [nixstasis]
      enable = true
      api_url = "https://nixstasis.example.test"
      frp_server_addr = "frps.example.test"
      frp_server_port = 7001
    '';
  };
  networkWithNixstasis = evaluate {
    overlayName = "build.nixstasis.toml";
    overlayText = ''
      [nixstasis]
      enable = true
      api_url = "https://nixstasis.example.test"
      frp_server_addr = "frps.example.test"
    '';
  };
  expectedCanonical = builtins.concatStringsSep "\n" [
    "version = 1"
    ""
    "[watchdog]"
    "enable_hardware = false"
    ''backend = "external"''
    ''runtime_timeout = "30s"''
    ''reboot_timeout = "10min"''
    ""
    "[provisioning]"
    ''bootstrap_transport = "network"''
    ""
    "[nixstasis]"
    "enable = false"
    ''api_url = ""''
    ''frp_server_addr = ""''
    "frp_server_port = 7000"
    ""
  ];
  expectedOverrideCanonical = builtins.concatStringsSep "\n" [
    "version = 1"
    ""
    "[watchdog]"
    "enable_hardware = true"
    ''backend = "internal"''
    ''runtime_timeout = "45s"''
    ''reboot_timeout = "10min"''
    ""
    "[provisioning]"
    ''bootstrap_transport = "network"''
    ""
    "[nixstasis]"
    "enable = false"
    ''api_url = ""''
    ''frp_server_addr = ""''
    "frp_server_port = 7000"
    ""
  ];
  expectedFleetCanonical = builtins.concatStringsSep "\n" [
    "version = 1"
    ""
    "[watchdog]"
    "enable_hardware = false"
    ''backend = "external"''
    ''runtime_timeout = "30s"''
    ''reboot_timeout = "10min"''
    ""
    "[provisioning]"
    ''bootstrap_transport = "nixstasis"''
    ""
    "[nixstasis]"
    "enable = true"
    ''api_url = "https://nixstasis.example.test"''
    ''frp_server_addr = "frps.example.test"''
    "frp_server_port = 7001"
    ""
  ];
  expectedMetadata = canonicalTOML: localOverride: ''
    {"local_override":${
      if localOverride then "true" else "false"
    },"policy_sha256":"${builtins.hashString "sha256" canonicalTOML}"}
  '';
  evalSystem =
    effectiveBuildConfig:
    self.inputs.nixpkgs.lib.nixosSystem {
      system = "aarch64-linux";
      modules = [
        ../../modules/base.nix
        ../../modules/build-configuration.nix
        qemuModule
      ];
      specialArgs = {
        inherit self effectiveBuildConfig;
        developmentMode = true;
        nixstasis = self.inputs.nixstasis;
      };
    };
  committedSystem = (evalSystem defaults).config;
  overriddenSystem = (evalSystem overridden).config;
  fleetSystem = (evalSystem fleet).config;
  networkWithNixstasisSystem = (evalSystem networkWithNixstasis).config;
  effective = self.lib.effectiveBuildConfiguration;
  imagePackage = self.packages.aarch64-linux.image;
  raucBundlePackage = self.packages.aarch64-linux.rauc-bundle;
  evaluationFails = args: !(builtins.tryEval (builtins.deepSeq (evaluate args) true)).success;
  baseFails = text: evaluationFails { baseText = text; };
  overlayFails =
    text:
    evaluationFails {
      overlayName = "build.dev.toml";
      overlayText = text;
    };
  validationErrors =
    kind: document:
    evaluator.validationErrors {
      name = if kind == "base" then "build.toml" else "build.dev.toml";
      inherit kind document;
    };
  schemaDiagnostic = builtins.elem "build.dev.toml: watchdog.extra: unknown field" (
    validationErrors "overlay" {
      watchdog.extra = true;
    }
  );
  typeDiagnostic = builtins.elem "build.toml: watchdog.enable_hardware: expected a boolean" (
    validationErrors "base" {
      version = 1;
      watchdog = {
        enable_hardware = "yes";
        runtime_timeout = "30s";
        reboot_timeout = "10min";
      };
    }
  );
in
pkgs.runCommand "build-configuration-check" { } ''
  set -euo pipefail

  test ${builtins.toJSON (defaults.watchdog.enableHardware == false)} = true
  test ${builtins.toJSON (defaults.watchdog.backend == "external")} = true
  test ${builtins.toJSON (defaults.watchdog.runtimeTimeout == "30s")} = true
  test ${builtins.toJSON (defaults.watchdog.rebootTimeout == "10min")} = true
  test ${builtins.toJSON (defaults.provisioning.bootstrapTransport == "network")} = true
  test ${builtins.toJSON (!defaults.nixstasis.enable)} = true
  test ${builtins.toJSON (defaults.nixstasis.apiUrl == "")} = true
  test ${builtins.toJSON (defaults.nixstasis.frpServerAddr == "")} = true
  test ${builtins.toJSON (defaults.nixstasis.frpServerPort == 7000)} = true
  test ${builtins.toJSON (!defaults.localOverride)} = true
  test ${builtins.toJSON (defaults.canonicalTOML == expectedCanonical)} = true
  test ${
    builtins.toJSON (defaults.policySHA256 == builtins.hashString "sha256" expectedCanonical)
  } = true
  test ${
    builtins.toJSON (defaults.canonicalMetadataJSON == expectedMetadata expectedCanonical false)
  } = true
  test ${builtins.toJSON (builtins.readFile defaults.tomlFile == expectedCanonical)} = true
  test ${
    builtins.toJSON (
      builtins.readFile defaults.metadataFile == expectedMetadata expectedCanonical false
    )
  } = true
  test ${builtins.toJSON (defaults.artifactSuffix == "")} = true

  test ${builtins.toJSON overridden.watchdog.enableHardware} = true
  test ${builtins.toJSON (overridden.watchdog.backend == "internal")} = true
  test ${builtins.toJSON (overridden.watchdog.runtimeTimeout == "45s")} = true
  test ${builtins.toJSON (overridden.watchdog.rebootTimeout == "10min")} = true
  test ${builtins.toJSON (overridden.provisioning.bootstrapTransport == "network")} = true
  test ${builtins.toJSON (!overridden.nixstasis.enable)} = true
  test ${builtins.toJSON overridden.localOverride} = true
  test ${builtins.toJSON (overridden.canonicalTOML == expectedOverrideCanonical)} = true
  test ${
    builtins.toJSON (
      overridden.canonicalMetadataJSON == expectedMetadata expectedOverrideCanonical true
    )
  } = true
  test ${builtins.toJSON (builtins.readFile overridden.tomlFile == expectedOverrideCanonical)} = true
  test ${
    builtins.toJSON (
      builtins.readFile overridden.metadataFile == expectedMetadata expectedOverrideCanonical true
    )
  } = true
  test ${builtins.toJSON (overridden.artifactSuffix == "-dev")} = true

  test ${builtins.toJSON (fleet.provisioning.bootstrapTransport == "nixstasis")} = true
  test ${builtins.toJSON fleet.nixstasis.enable} = true
  test ${builtins.toJSON (fleet.nixstasis.apiUrl == "https://nixstasis.example.test")} = true
  test ${builtins.toJSON (fleet.nixstasis.frpServerAddr == "frps.example.test")} = true
  test ${builtins.toJSON (fleet.nixstasis.frpServerPort == 7001)} = true
  test ${builtins.toJSON (fleet.canonicalTOML == expectedFleetCanonical)} = true
  test ${builtins.toJSON fleet.localOverride} = true
  test ${builtins.toJSON (networkWithNixstasis.provisioning.bootstrapTransport == "network")} = true
  test ${builtins.toJSON networkWithNixstasis.nixstasis.enable} = true

  # Effective policy maps to immutable NixOS options and audit files.
  test ${builtins.toJSON (!committedSystem.atomixos.watchdog.enableHardware)} = true
  test ${builtins.toJSON (committedSystem.atomixos.watchdog.backend == "external")} = true
  test ${
    builtins.toJSON (committedSystem.atomixos.provisioning.bootstrapTransport == "network")
  } = true
  test ${builtins.toJSON (!committedSystem.atomixos.nixstasis.enable)} = true
  test ${builtins.toJSON (committedSystem.atomixos.watchdog.runtimeWatchdogSec == "30s")} = true
  test ${builtins.toJSON (committedSystem.atomixos.watchdog.rebootWatchdogSec == "10min")} = true
  test ${
    builtins.toJSON (committedSystem.environment.etc."atomixos/build.toml".source == defaults.tomlFile)
  } = true
  test ${
    builtins.toJSON (
      committedSystem.environment.etc."atomixos/build-metadata.json".source == defaults.metadataFile
    )
  } = true
  test ${builtins.toJSON overriddenSystem.atomixos.watchdog.enableHardware} = true
  test ${builtins.toJSON (overriddenSystem.atomixos.watchdog.backend == "internal")} = true
  test ${builtins.toJSON (fleetSystem.atomixos.provisioning.bootstrapTransport == "nixstasis")} = true
  test ${builtins.toJSON fleetSystem.atomixos.nixstasis.enable} = true
  test ${
    builtins.toJSON (fleetSystem.atomixos.nixstasis.apiUrl == "https://nixstasis.example.test")
  } = true
  test ${
    builtins.toJSON (fleetSystem.atomixos.nixstasis.frp.serverAddr == "frps.example.test")
  } = true
  test ${builtins.toJSON (fleetSystem.atomixos.nixstasis.frp.serverPort == 7001)} = true
  test ${
    builtins.toJSON (networkWithNixstasisSystem.atomixos.provisioning.bootstrapTransport == "network")
  } = true
  test ${builtins.toJSON networkWithNixstasisSystem.atomixos.nixstasis.enable} = true
  test ${
    builtins.toJSON (
      committedSystem.systemd.sockets.atomixos-bootstrap.socketConfig.ListenStream == "0.0.0.0:8080"
    )
  } = true
  test ${
    builtins.toJSON (
      fleetSystem.systemd.sockets.atomixos-bootstrap.socketConfig.ListenStream == "127.0.0.1:8080"
    )
  } = true
  test ${builtins.toJSON (builtins.hasAttr "bootstrap-wan-toggle" committedSystem.systemd.services)} = true
  test ${
    builtins.toJSON (!(builtins.hasAttr "bootstrap-wan-toggle" fleetSystem.systemd.services))
  } = true
  test ${builtins.toJSON (builtins.hasAttr "atomixos-bootstrap-rebind" committedSystem.systemd.services)} = true
  test ${
    builtins.toJSON (!(builtins.hasAttr "atomixos-bootstrap-rebind" fleetSystem.systemd.services))
  } = true
  test ${
    builtins.toJSON (
      committedSystem.systemd.services.lan-gateway-apply.environment.ATOMIXOS_BOOTSTRAP_TRANSPORT
      == "network"
    )
  } = true
  test ${
    builtins.toJSON (
      fleetSystem.systemd.services.lan-gateway-apply.environment.ATOMIXOS_BOOTSTRAP_TRANSPORT
      == "nixstasis"
    )
  } = true
  test ${
    builtins.toJSON (
      committedSystem.systemd.services.first-boot.environment.ATOMIXOS_BOOTSTRAP_TRANSPORT == "network"
    )
  } = true
  test ${
    builtins.toJSON (
      fleetSystem.systemd.services.first-boot.environment.ATOMIXOS_BOOTSTRAP_TRANSPORT == "nixstasis"
    )
  } = true
  test ${builtins.toJSON (overriddenSystem.atomixos.watchdog.runtimeWatchdogSec == "45s")} = true
  test ${
    builtins.toJSON (overriddenSystem.systemd.settings.Manager.RuntimeWatchdogSec == "45s")
  } = true
  test ${
    builtins.toJSON (
      overriddenSystem.environment.etc."atomixos/build.toml".source == overridden.tomlFile
    )
  } = true

  # Image and update derivations consume the flake's effective immutable sidecar sources.
  # The standalone defaults and overridden fixtures above retain committed-policy coverage.
  test ${builtins.toJSON (imagePackage.buildConfiguration.tomlFile == effective.tomlFile)} = true
  test ${
    builtins.toJSON (imagePackage.buildConfiguration.metadataFile == effective.metadataFile)
  } = true
  test ${
    builtins.toJSON (imagePackage.buildConfiguration.localOverride == effective.localOverride)
  } = true
  test ${builtins.toJSON (raucBundlePackage.buildConfiguration.tomlFile == effective.tomlFile)} = true
  test ${
    builtins.toJSON (raucBundlePackage.buildConfiguration.metadataFile == effective.metadataFile)
  } = true
  test ${
    builtins.toJSON (raucBundlePackage.buildConfiguration.localOverride == effective.localOverride)
  } = true

  # Committed documents are complete and versioned.
  test ${builtins.toJSON (baseFails ''
    [watchdog]
    enable_hardware = false
    runtime_timeout = "30s"
    reboot_timeout = "10min"
  '')} = true
  test ${builtins.toJSON (baseFails ''
    version = 1
    [watchdog]
    enable_hardware = false
    runtime_timeout = "30s"
  '')} = true

  # Overlays may omit version, but an explicit incompatible version fails.
  test ${builtins.toJSON (overlayFails ''
    version = 2
  '')} = true

  # Unknown fields and wrong types fail closed.
  test ${builtins.toJSON (overlayFails "unknown = true")} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    extra = true
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [provisioning]
    extra = true
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    extra = true
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [provisioning]
    bootstrap_transport = "lan"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [provisioning]
    bootstrap_transport = true
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    frp_server_port = 0
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    frp_server_port = 65536
  '')} = true
  test ${
    builtins.toJSON (
      !(overlayFails ''
        [nixstasis]
        frp_server_port = 1
      '')
    )
  } = true
  test ${
    builtins.toJSON (
      !(overlayFails ''
        [nixstasis]
        frp_server_port = 65535
      '')
    )
  } = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    frp_server_port = "7000"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    enable = "yes"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    api_url = 7
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    frp_server_addr = 7
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    enable = true
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [nixstasis]
    enable = true
    api_url = ""
    frp_server_addr = "frps.example.test"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    enable_hardware = "yes"
  '')} = true
  test ${builtins.toJSON schemaDiagnostic} = true
  test ${builtins.toJSON typeDiagnostic} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    backend = "sidecar"
  '')} = true

  # Durations use the restricted grammar and converted policy bounds.
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    runtime_timeout = "9s"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    runtime_timeout = "301s"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    reboot_timeout = "59s"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    reboot_timeout = "11min"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    runtime_timeout = "1.5min"
  '')} = true
  test ${builtins.toJSON (overlayFails ''
    [watchdog]
    runtime_timeout = "999999999999999999999999999999999999999999ms"
  '')} = true

  # Inclusive boundaries and each accepted unit remain valid.
  test ${
    builtins.toJSON (
      !(overlayFails ''
        [watchdog]
        runtime_timeout = "10000ms"
        reboot_timeout = "60000ms"
      '')
    )
  } = true
  test ${
    builtins.toJSON (
      !(overlayFails ''
        [watchdog]
        runtime_timeout = "5min"
        reboot_timeout = "600s"
      '')
    )
  } = true

  # Native TOML parser diagnostics retain the input filename and location context.
  cat > invalid-syntax.nix <<'EOF'
  let
    evaluator = import ${../build-configuration.nix} {
      lib = import ${self.inputs.nixpkgs}/lib;
    };
  in
  evaluator.evaluate {
    baseName = "invalid-build.toml";
    baseText = "version = [";
  }
  EOF
  if ${pkgs.nix}/bin/nix-instantiate --eval --strict invalid-syntax.nix 2>syntax-error.log; then
    echo "invalid TOML unexpectedly evaluated" >&2
    exit 1
  fi
  grep -F "while parsing invalid-build.toml" syntax-error.log
  grep -F "missing closing bracket" syntax-error.log
  grep -F "1 | version = [" syntax-error.log

  mkdir -p "$out"
''
