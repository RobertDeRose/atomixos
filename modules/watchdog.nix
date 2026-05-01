# Systemd watchdog configuration.
# Integration is implemented but intentionally disabled during development
# until Rock64 boot reliability is fully validated.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

let
  watchdogBootCountCli = pkgs.writeShellScriptBin "watchdog-boot-count" (
    builtins.readFile ../scripts/watchdog-boot-count.sh
  );
in
{
  # ── Watchdog ─────────────────────────────────────────────────────────────────

  # systemd kicks the hardware watchdog every 30s.
  # If systemd hangs (kernel panic, deadlock, OOM), the hardware watchdog
  # fires and triggers a hard reboot. Combined with U-Boot boot-count,
  # this leads to automatic rollback if the system can't stay up.
  # TODO: Re-enable once boot completes reliably on hardware.
  # RuntimeWatchdogSec = "30s";
  # RebootWatchdogSec = "10min";
  systemd.settings.Manager = { };

  environment.systemPackages = [
    watchdogBootCountCli
  ];

  systemd.services.watchdog-boot-count = {
    description = "Record watchdog boot-count and rollback state";
    wantedBy = [ "multi-user.target" ];
    before = [ "rauc.service" ];
    after = [ "local-fs.target" ];
    path = [
      watchdogBootCountCli
    ]
    ++ lib.optionals (config.atomixos.rauc.bootloader == "uboot") [
      self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools
    ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${watchdogBootCountCli}/bin/watchdog-boot-count";
    };
    environment = {
      ATOMIXOS_RAUC_BOOTLOADER = config.atomixos.rauc.bootloader;
      ATOMIXOS_RAUC_STATE_DIR = "/var/lib/rauc";
    };
  };
}
