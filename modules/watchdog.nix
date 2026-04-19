# Systemd watchdog configuration.
# Integration is implemented but intentionally disabled during development
# until Rock64 boot reliability is fully validated.
{
  config,
  lib,
  pkgs,
  ...
}:

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
}
