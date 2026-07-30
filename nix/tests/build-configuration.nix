{
  pkgs,
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
    runtime_timeout = "30s"
    reboot_timeout = "10min"
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
      runtime_timeout = "45s"
    '';
  };
  expectedCanonical = builtins.concatStringsSep "\n" [
    "version = 1"
    ""
    "[watchdog]"
    "enable_hardware = false"
    ''runtime_timeout = "30s"''
    ''reboot_timeout = "10min"''
    ""
  ];
  expectedOverrideCanonical = builtins.concatStringsSep "\n" [
    "version = 1"
    ""
    "[watchdog]"
    "enable_hardware = true"
    ''runtime_timeout = "45s"''
    ''reboot_timeout = "10min"''
    ""
  ];
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
  test ${builtins.toJSON (defaults.watchdog.runtimeTimeout == "30s")} = true
  test ${builtins.toJSON (defaults.watchdog.rebootTimeout == "10min")} = true
  test ${builtins.toJSON (!defaults.localOverride)} = true
  test ${builtins.toJSON (defaults.canonicalTOML == expectedCanonical)} = true

  test ${builtins.toJSON overridden.watchdog.enableHardware} = true
  test ${builtins.toJSON (overridden.watchdog.runtimeTimeout == "45s")} = true
  test ${builtins.toJSON (overridden.watchdog.rebootTimeout == "10min")} = true
  test ${builtins.toJSON overridden.localOverride} = true
  test ${builtins.toJSON (overridden.canonicalTOML == expectedOverrideCanonical)} = true

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
    [watchdog]
    enable_hardware = "yes"
  '')} = true
  test ${builtins.toJSON schemaDiagnostic} = true
  test ${builtins.toJSON typeDiagnostic} = true

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
