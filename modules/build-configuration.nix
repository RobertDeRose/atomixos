# Apply validated immutable build policy to the NixOS system.
{
  effectiveBuildConfig,
  ...
}:

{
  atomixos.watchdog = {
    enableHardware = effectiveBuildConfig.watchdog.enableHardware;
    runtimeWatchdogSec = effectiveBuildConfig.watchdog.runtimeTimeout;
    rebootWatchdogSec = effectiveBuildConfig.watchdog.rebootTimeout;
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
}
