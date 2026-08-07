{ lib }:

let
  allowedTopLevel = [
    "version"
    "watchdog"
    "provisioning"
    "nixstasis"
  ];
  allowedWatchdog = [
    "enable_hardware"
    "backend"
    "runtime_timeout"
    "reboot_timeout"
  ];
  allowedProvisioning = [ "bootstrap_transport" ];
  allowedNixstasis = [
    "enable"
    "api_url"
    "frp_server_addr"
    "frp_server_port"
  ];

  unknownFieldErrors =
    name: prefix: allowed: value:
    if !builtins.isAttrs value then
      [ ]
    else
      map (field: "${name}: ${prefix}${field}: unknown field") (
        builtins.filter (field: !(builtins.elem field allowed)) (builtins.attrNames value)
      );

  requiredFieldError =
    name: path: value: field:
    lib.optional (
      !(builtins.hasAttr field value)
    ) "${name}: ${path}${field}: required field is missing";

  durationErrors =
    {
      name,
      field,
      value,
      minimumMillis,
      maximumMillis,
      rangeDescription,
    }:
    if !builtins.isString value then
      [ "${name}: watchdog.${field}: expected a duration string" ]
    else
      let
        matched = builtins.match "([1-9][0-9]*)(ms|s|min|h)" value;
      in
      if matched == null then
        [ "${name}: watchdog.${field}: expected a positive integer followed by ms, s, min, or h" ]
      else
        let
          numberText = builtins.elemAt matched 0;
          unit = builtins.elemAt matched 1;
        in
        if builtins.stringLength numberText > 6 then
          [ "${name}: watchdog.${field}: duration is outside ${rangeDescription}" ]
        else
          let
            number = builtins.fromJSON numberText;
            multiplier =
              {
                ms = 1;
                s = 1000;
                min = 60 * 1000;
                h = 60 * 60 * 1000;
              }
              .${unit};
            milliseconds = number * multiplier;
          in
          lib.optional (
            milliseconds < minimumMillis || milliseconds > maximumMillis
          ) "${name}: watchdog.${field}: duration is outside ${rangeDescription}";

  validateWatchdog =
    {
      name,
      kind,
      value,
    }:
    if !builtins.isAttrs value then
      [ "${name}: watchdog: expected a table" ]
    else
      let
        requiredErrors = lib.optionals (kind == "base") (
          lib.concatMap (requiredFieldError name "watchdog." value) allowedWatchdog
        );
        boolErrors =
          if !(builtins.hasAttr "enable_hardware" value) || builtins.isBool value.enable_hardware then
            [ ]
          else
            [ "${name}: watchdog.enable_hardware: expected a boolean" ];
        backendErrors =
          if !(builtins.hasAttr "backend" value) then
            [ ]
          else if !builtins.isString value.backend then
            [ "${name}: watchdog.backend: expected \"internal\" or \"external\"" ]
          else
            lib.optional (
              !(builtins.elem value.backend [
                "internal"
                "external"
              ])
            ) "${name}: watchdog.backend: expected \"internal\" or \"external\"";
        runtimeErrors = lib.optionals (builtins.hasAttr "runtime_timeout" value) (durationErrors {
          inherit name;
          field = "runtime_timeout";
          value = value.runtime_timeout;
          minimumMillis = 10 * 1000;
          maximumMillis = 5 * 60 * 1000;
          rangeDescription = "the inclusive 10s–5min range";
        });
        rebootErrors = lib.optionals (builtins.hasAttr "reboot_timeout" value) (durationErrors {
          inherit name;
          field = "reboot_timeout";
          value = value.reboot_timeout;
          minimumMillis = 60 * 1000;
          maximumMillis = 10 * 60 * 1000;
          rangeDescription = "the inclusive 1min–10min range";
        });
      in
      unknownFieldErrors name "watchdog." allowedWatchdog value
      ++ requiredErrors
      ++ boolErrors
      ++ backendErrors
      ++ runtimeErrors
      ++ rebootErrors;

  validateProvisioning =
    {
      name,
      kind,
      value,
    }:
    if !builtins.isAttrs value then
      [ "${name}: provisioning: expected a table" ]
    else
      let
        requiredErrors = lib.optionals (kind == "base") (
          lib.concatMap (requiredFieldError name "provisioning." value) allowedProvisioning
        );
        transportErrors =
          if !(builtins.hasAttr "bootstrap_transport" value) then
            [ ]
          else if !builtins.isString value.bootstrap_transport then
            [ "${name}: provisioning.bootstrap_transport: expected \"network\" or \"nixstasis\"" ]
          else
            lib.optional (
              !(builtins.elem value.bootstrap_transport [
                "network"
                "nixstasis"
              ])
            ) "${name}: provisioning.bootstrap_transport: expected \"network\" or \"nixstasis\"";
      in
      unknownFieldErrors name "provisioning." allowedProvisioning value
      ++ requiredErrors
      ++ transportErrors;

  validatePort =
    name: field: value:
    if !builtins.isInt value then
      [ "${name}: nixstasis.${field}: expected an integer between 1 and 65535" ]
    else
      lib.optional (
        value < 1 || value > 65535
      ) "${name}: nixstasis.${field}: expected an integer between 1 and 65535";

  validateNixstasis =
    {
      name,
      kind,
      value,
    }:
    if !builtins.isAttrs value then
      [ "${name}: nixstasis: expected a table" ]
    else
      let
        requiredErrors = lib.optionals (kind == "base") (
          lib.concatMap (requiredFieldError name "nixstasis." value) allowedNixstasis
        );
        enableErrors =
          if !(builtins.hasAttr "enable" value) then
            [ ]
          else
            lib.optional (!(builtins.isBool value.enable)) "${name}: nixstasis.enable: expected a boolean";
        apiUrlErrors =
          if !(builtins.hasAttr "api_url" value) then
            [ ]
          else
            lib.optional (!(builtins.isString value.api_url)) "${name}: nixstasis.api_url: expected a string";
        serverAddrErrors =
          if !(builtins.hasAttr "frp_server_addr" value) then
            [ ]
          else
            lib.optional (
              !(builtins.isString value.frp_server_addr)
            ) "${name}: nixstasis.frp_server_addr: expected a string";
        serverPortErrors =
          if !(builtins.hasAttr "frp_server_port" value) then
            [ ]
          else
            validatePort name "frp_server_port" value.frp_server_port;
      in
      unknownFieldErrors name "nixstasis." allowedNixstasis value
      ++ requiredErrors
      ++ enableErrors
      ++ apiUrlErrors
      ++ serverAddrErrors
      ++ serverPortErrors;

  enabledNixstasisErrors =
    name: document:
    if !builtins.isAttrs document then
      [ ]
    else if !(builtins.hasAttr "nixstasis" document) then
      [ ]
    else if !builtins.isAttrs document.nixstasis then
      [ ]
    else if !(builtins.hasAttr "enable" document.nixstasis) then
      [ ]
    else if !(builtins.isBool document.nixstasis.enable) || !document.nixstasis.enable then
      [ ]
    else
      let
        apiUrlErrors = lib.optional (
          !(builtins.hasAttr "api_url" document.nixstasis)
          || !(builtins.isString document.nixstasis.api_url)
          || document.nixstasis.api_url == ""
        ) "${name}: nixstasis.api_url: required when Nixstasis is enabled";
        serverAddrErrors = lib.optional (
          !(builtins.hasAttr "frp_server_addr" document.nixstasis)
          || !(builtins.isString document.nixstasis.frp_server_addr)
          || document.nixstasis.frp_server_addr == ""
        ) "${name}: nixstasis.frp_server_addr: required when Nixstasis is enabled";
      in
      apiUrlErrors ++ serverAddrErrors;

  validationErrors =
    {
      name,
      kind,
      document,
    }:
    if !builtins.isAttrs document then
      [ "${name}: expected a TOML document" ]
    else
      let
        versionRequired = kind == "base" && !(builtins.hasAttr "version" document);
        versionErrors =
          lib.optional versionRequired "${name}: version: required field is missing"
          ++ lib.optionals (builtins.hasAttr "version" document) (
            if !builtins.isInt document.version then
              [ "${name}: version: expected integer 1" ]
            else
              lib.optional (
                document.version != 1
              ) "${name}: version: unsupported version ${toString document.version}"
          );
        watchdogRequired = kind == "base" && !(builtins.hasAttr "watchdog" document);
        watchdogErrors =
          lib.optional watchdogRequired "${name}: watchdog: required table is missing"
          ++ lib.optionals (builtins.hasAttr "watchdog" document) (validateWatchdog {
            inherit name kind;
            value = document.watchdog;
          });
        provisioningRequired = kind == "base" && !(builtins.hasAttr "provisioning" document);
        provisioningErrors =
          lib.optional provisioningRequired "${name}: provisioning: required table is missing"
          ++ lib.optionals (builtins.hasAttr "provisioning" document) (validateProvisioning {
            inherit name kind;
            value = document.provisioning;
          });
        nixstasisRequired = kind == "base" && !(builtins.hasAttr "nixstasis" document);
        nixstasisErrors =
          lib.optional nixstasisRequired "${name}: nixstasis: required table is missing"
          ++ lib.optionals (builtins.hasAttr "nixstasis" document) (validateNixstasis {
            inherit name kind;
            value = document.nixstasis;
          });
      in
      unknownFieldErrors name "" allowedTopLevel document
      ++ versionErrors
      ++ watchdogErrors
      ++ provisioningErrors
      ++ nixstasisErrors;

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
  inherit validationErrors;

  evaluate =
    {
      baseName,
      baseText,
      overlayName ? "build.dev.toml",
      overlayText ? null,
    }:
    let
      baseDocument = parseTOML baseName baseText;
      overlayDocument = if overlayText == null then { } else parseTOML overlayName overlayText;
      effectiveDocument = lib.recursiveUpdate baseDocument overlayDocument;
      effectiveName = if overlayText == null then baseName else overlayName;
      errors =
        validationErrors {
          name = baseName;
          kind = "base";
          document = baseDocument;
        }
        ++ lib.optionals (overlayText != null) (validationErrors {
          name = overlayName;
          kind = "overlay";
          document = overlayDocument;
        })
        ++ enabledNixstasisErrors effectiveName effectiveDocument;
    in
    if errors != [ ] then
      throw "invalid build configuration:\n- ${builtins.concatStringsSep "\n- " errors}"
    else
      let
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
        provisioning = {
          bootstrapTransport = effectiveDocument.provisioning.bootstrap_transport;
        };
        nixstasis = {
          enable = effectiveDocument.nixstasis.enable;
          apiUrl = effectiveDocument.nixstasis.api_url;
          frpServerAddr = effectiveDocument.nixstasis.frp_server_addr;
          frpServerPort = effectiveDocument.nixstasis.frp_server_port;
        };
      };
}
