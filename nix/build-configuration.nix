{ lib }:

let
  allowedTopLevel = [
    "version"
    "watchdog"
  ];
  allowedWatchdog = [
    "enable_hardware"
    "runtime_timeout"
    "reboot_timeout"
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
      ++ runtimeErrors
      ++ rebootErrors;

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
      in
      unknownFieldErrors name "" allowedTopLevel document ++ versionErrors ++ watchdogErrors;

  parseTOML = name: text: builtins.addErrorContext "while parsing ${name}" (builtins.fromTOML text);

  renderCanonical =
    document:
    builtins.concatStringsSep "\n" [
      "version = 1"
      ""
      "[watchdog]"
      "enable_hardware = ${if document.watchdog.enable_hardware then "true" else "false"}"
      ''runtime_timeout = "${document.watchdog.runtime_timeout}"''
      ''reboot_timeout = "${document.watchdog.reboot_timeout}"''
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
        });
    in
    if errors != [ ] then
      throw "invalid build configuration:\n- ${builtins.concatStringsSep "\n- " errors}"
    else
      let
        effectiveDocument = lib.recursiveUpdate baseDocument overlayDocument;
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
          runtimeTimeout = effectiveDocument.watchdog.runtime_timeout;
          rebootTimeout = effectiveDocument.watchdog.reboot_timeout;
        };
      };
}
