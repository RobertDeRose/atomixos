# OS upgrade service — polls for RAUC bundle updates.
# Designed to be swappable with rauc-hawkbit-updater via config flag.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.os-upgrade;

  upgradeScript = pkgs.writeShellScript "os-upgrade" (builtins.readFile ../scripts/os-upgrade.sh);
in
{
  # ── Configuration options ────────────────────────────────────────────────────

  options.os-upgrade = {
    useHawkbit = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = "Use rauc-hawkbit-updater instead of simple polling service";
    };

    pollingInterval = lib.mkOption {
      type = lib.types.str;
      default = "1h";
      description = "How often to poll for updates (systemd timer format)";
    };

    serverUrl = lib.mkOption {
      type = lib.types.str;
      default = "http://localhost/updates";
      description = "URL of the update server";
    };
  };

  config = {
    # ── Simple polling service (default) ─────────────────────────────────────

    systemd.services.os-upgrade = lib.mkIf (!cfg.useHawkbit) {
      description = "OS upgrade polling service";
      after = [
        "network-online.target"
        "os-verification.service"
      ];
      wants = [ "network-online.target" ];

      path = [
        pkgs.rauc
        pkgs.curl
        pkgs.jq
        pkgs.systemd
        pkgs.coreutils
      ];

      environment = {
        OS_UPGRADE_URL = cfg.serverUrl;
      };

      serviceConfig = {
        Type = "oneshot";
        ExecStart = upgradeScript;
        TimeoutStartSec = 900; # 15 minutes (download can be slow)

        # Don't restart on failure — the timer will trigger the next run
        Restart = "no";
      };
    };

    systemd.timers.os-upgrade = lib.mkIf (!cfg.useHawkbit) {
      description = "OS upgrade polling timer";
      wantedBy = [ "timers.target" ];

      timerConfig = {
        OnBootSec = "5min"; # First check 5 minutes after boot
        OnUnitActiveSec = cfg.pollingInterval;
        RandomizedDelaySec = "10min"; # Jitter to avoid thundering herd
      };
    };

    # ── hawkBit client (optional) ────────────────────────────────────────────

    # rauc-hawkbit-updater is available as a package but only enabled when
    # useHawkbit is true. Configuration is expected at /data/config/hawkbit/
    environment.systemPackages = lib.mkIf cfg.useHawkbit [
      pkgs.rauc-hawkbit-updater
    ];

    # Note: rauc-hawkbit-updater systemd service configuration would go here
    # when hawkBit is enabled. The exact config depends on the hawkBit server
    # setup and will be defined when hawkBit is deployed.
  };
}
