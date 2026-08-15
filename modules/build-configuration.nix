# Apply validated immutable build policy to the NixOS system.
{
  lib,
  effectiveBuildConfig,
  ...
}:

{
  options.atomixos.provisioning.bootstrapTransport = lib.mkOption {
    type = lib.types.enum [
      "network"
      "nixstasis"
    ];
    default = "network";
    description = "Immutable transport used for the initial AtomixOS provisioning API.";
  };

  config = {
    assertions = [
      {
        assertion =
          effectiveBuildConfig.provisioning.bootstrapTransport != "nixstasis"
          || effectiveBuildConfig.nixstasis.enable;
        message = "provisioning.bootstrapTransport = nixstasis requires nixstasis.enable = true";
      }
    ];

    atomixos.provisioning.bootstrapTransport = effectiveBuildConfig.provisioning.bootstrapTransport;

    atomixos.watchdog = {
      enableHardware = effectiveBuildConfig.watchdog.enableHardware;
      backend = effectiveBuildConfig.watchdog.backend;
      runtimeWatchdogSec = effectiveBuildConfig.watchdog.runtimeTimeout;
      rebootWatchdogSec = effectiveBuildConfig.watchdog.rebootTimeout;
    };

    atomixos.nixstasis = {
      enable = effectiveBuildConfig.nixstasis.enable;
      apiUrl = effectiveBuildConfig.nixstasis.apiUrl;
      frp.serverAddr = effectiveBuildConfig.nixstasis.frpServerAddr;
      frp.serverPort = effectiveBuildConfig.nixstasis.frpServerPort;
    };

    environment.etc = {
      "atomixos/build.toml" = {
        source = effectiveBuildConfig.tomlFile;
        mode = "0444";
      };
      "atomixos/build-metadata.json" = {
        source = effectiveBuildConfig.metadataFile;
        mode = "0444";
      };
    };
  };
}
