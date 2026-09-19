{ lib }:

let
  inherit (lib) mkOption types;

  durationMillis =
    value:
    let
      matched = builtins.match "([1-9][0-9]*)(ms|s|min|h)" value;
    in
    if matched == null then
      null
    else
      let
        numberText = builtins.elemAt matched 0;
        unit = builtins.elemAt matched 1;
      in
      if builtins.stringLength numberText > 6 then
        null
      else
        builtins.fromJSON numberText
        * {
          ms = 1;
          s = 1000;
          min = 60 * 1000;
          h = 60 * 60 * 1000;
        }
        .${unit};

  durationType =
    minimumMillis: maximumMillis:
    types.addCheck types.str (
      value:
      let
        milliseconds = durationMillis value;
      in
      milliseconds != null && milliseconds >= minimumMillis && milliseconds <= maximumMillis
    );

  assertionType = types.submodule {
    options = {
      assertion = mkOption { type = types.bool; };
      message = mkOption { type = types.str; };
    };
  };

  policyModule =
    { config, sourceName, ... }:
    {
      options = {
        policy = {
          version = mkOption {
            type = types.addCheck types.int (value: value == 1);
            description = "AtomixOS immutable build-policy format version.";
          };

          watchdog = {
            enable_hardware = mkOption {
              type = types.bool;
              description = "Whether systemd enforces a hardware watchdog.";
            };
            backend = mkOption {
              type = types.enum [
                "internal"
                "external"
              ];
              description = "Hardware watchdog implementation.";
            };
            runtime_timeout = mkOption {
              type = durationType (10 * 1000) (5 * 60 * 1000);
              description = "Runtime watchdog timeout from 10 seconds through 5 minutes.";
            };
            reboot_timeout = mkOption {
              type = durationType (60 * 1000) (10 * 60 * 1000);
              description = "Reboot watchdog timeout from 1 through 10 minutes.";
            };
          };

          provisioning.bootstrap_transport = mkOption {
            type = types.enum [
              "network"
              "nixstasis"
            ];
            description = "Transport exposed for initial provisioning.";
          };

          nixstasis = {
            enable = mkOption {
              type = types.bool;
              description = "Whether the Nixstasis client is enabled.";
            };
            api_url = mkOption {
              type = types.str;
              description = "Public Nixstasis API URL.";
            };
            frp_server_addr = mkOption {
              type = types.str;
              description = "Public FRP server address.";
            };
            frp_server_port = mkOption {
              type = types.ints.between 1 65535;
              description = "Public FRP server port.";
            };
          };
        };

        assertions = mkOption {
          type = types.listOf assertionType;
          default = [ ];
          internal = true;
        };
      };

      config.assertions = [
        {
          assertion = !config.policy.nixstasis.enable || config.policy.nixstasis.api_url != "";
          message = "${sourceName}: nixstasis.api_url is required when Nixstasis is enabled";
        }
        {
          assertion = !config.policy.nixstasis.enable || config.policy.nixstasis.frp_server_addr != "";
          message = "${sourceName}: nixstasis.frp_server_addr is required when Nixstasis is enabled";
        }
        {
          assertion =
            config.policy.provisioning.bootstrap_transport != "nixstasis" || config.policy.nixstasis.enable;
          message = "${sourceName}: provisioning.bootstrap_transport = \"nixstasis\" requires nixstasis.enable = true";
        }
      ];
    };

  evaluatePolicy =
    name: document:
    let
      evaluated = lib.evalModules {
        modules = [
          policyModule
          { config.policy = document; }
        ];
        specialArgs.sourceName = name;
      };
      failedAssertions = builtins.filter (assertion: !assertion.assertion) evaluated.config.assertions;
    in
    if failedAssertions != [ ] then
      throw "invalid build configuration:\n- ${
        builtins.concatStringsSep "\n- " (map (assertion: assertion.message) failedAssertions)
      }"
    else
      builtins.addErrorContext "while validating ${name}" (
        builtins.deepSeq evaluated.config.policy evaluated.config.policy
      );

  parseTOML = name: text: builtins.addErrorContext "while parsing ${name}" (builtins.fromTOML text);

  renderCanonical =
    document:
    builtins.concatStringsSep "\n" [
      "version = 1"
      ""
      "[watchdog]"
      "enable_hardware = ${if document.watchdog.enable_hardware then "true" else "false"}"
      ''backend = "${document.watchdog.backend}"''
      ''runtime_timeout = "${document.watchdog.runtime_timeout}"''
      ''reboot_timeout = "${document.watchdog.reboot_timeout}"''
      ""
      "[provisioning]"
      "bootstrap_transport = ${builtins.toJSON document.provisioning.bootstrap_transport}"
      ""
      "[nixstasis]"
      "enable = ${if document.nixstasis.enable then "true" else "false"}"
      "api_url = ${builtins.toJSON document.nixstasis.api_url}"
      "frp_server_addr = ${builtins.toJSON document.nixstasis.frp_server_addr}"
      "frp_server_port = ${toString document.nixstasis.frp_server_port}"
      ""
    ];
in
{
  evaluate =
    {
      baseName,
      baseText,
      overlayName ? "build.dev.toml",
      overlayText ? null,
    }:
    let
      baseDocument = parseTOML baseName baseText;
      validatedBase = evaluatePolicy baseName baseDocument;
      overlayDocument = if overlayText == null then { } else parseTOML overlayName overlayText;
      effectiveName = if overlayText == null then baseName else overlayName;
      effectiveDocument = evaluatePolicy effectiveName (
        lib.recursiveUpdate validatedBase overlayDocument
      );
      canonicalTOML = renderCanonical effectiveDocument;
      localOverride = overlayText != null;
      policySHA256 = builtins.hashString "sha256" canonicalTOML;
      canonicalMetadataJSON = ''
        {"local_override":${if localOverride then "true" else "false"},"policy_sha256":"${policySHA256}"}
      '';
      tomlFile = builtins.toFile "atomixos-build.toml" canonicalTOML;
      metadataFile = builtins.toFile "atomixos-build-metadata.json" canonicalMetadataJSON;
    in
    {
      inherit
        canonicalMetadataJSON
        canonicalTOML
        effectiveDocument
        localOverride
        metadataFile
        policySHA256
        tomlFile
        ;
      artifactSuffix = if localOverride then "-dev" else "";
      watchdog = {
        enableHardware = effectiveDocument.watchdog.enable_hardware;
        backend = effectiveDocument.watchdog.backend;
        runtimeTimeout = effectiveDocument.watchdog.runtime_timeout;
        rebootTimeout = effectiveDocument.watchdog.reboot_timeout;
      };
      provisioning.bootstrapTransport = effectiveDocument.provisioning.bootstrap_transport;
      nixstasis = {
        enable = effectiveDocument.nixstasis.enable;
        apiUrl = effectiveDocument.nixstasis.api_url;
        frpServerAddr = effectiveDocument.nixstasis.frp_server_addr;
        frpServerPort = effectiveDocument.nixstasis.frp_server_port;
      };
    };
}
