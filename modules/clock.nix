# Keep the system clock from starting in the past.
#
# Boards without a battery-backed RTC, or without NTP yet, boot with the clock at
# systemd's compiled-in epoch, which can predate the RAUC signing certificate. RAUC
# then rejects every bundle as "not yet valid". At boot the clock is moved forward
# to the later of the image's source date and the last time saved on /data; the
# time is saved again every 15 minutes and at shutdown, so it never runs backwards
# across a power loss.
{
  pkgs,
  self,
  ...
}:
let
  # The commit time of the AtomixOS source: fixed for a given image, and never
  # earlier than the certificates committed with it.
  floor = toString self.lastModified;
  stateFile = "/data/clock/last-known";

  clockScript = pkgs.writeShellScript "atomixos-clock" ''
    set -euo pipefail
    floor=${floor}
    state=${stateFile}
    now=$(date +%s)

    case "''${1:-}" in
    restore)
      target=$floor
      saved=$(cat "$state" 2>/dev/null || true)
      case "$saved" in
      "" | *[!0-9]*) ;;
      *) [ "$saved" -le "$target" ] || target=$saved ;;
      esac
      if [ "$now" -lt "$target" ]; then
        echo "clock $(date -u -d "@$now" +%FT%TZ) is behind $(date -u -d "@$target" +%FT%TZ); moving it forward"
        date -u -s "@$target" >/dev/null
      fi
      ;;
    save)
      if [ "$now" -lt "$floor" ]; then
        echo "clock is before the image source date; not saving it"
        exit 0
      fi
      mkdir -p "''${state%/*}"
      printf '%s\n' "$now" >"$state.tmp"
      mv "$state.tmp" "$state"
      ;;
    *)
      echo "usage: $0 restore|save" >&2
      exit 2
      ;;
    esac
  '';
in
{
  # Restore at boot, before anything that checks certificate dates; save when
  # stopped at shutdown, before /data is unmounted.
  systemd.services.atomixos-clock = {
    description = "Keep the clock at or after the last known time";
    unitConfig.DefaultDependencies = false;
    after = [
      "local-fs.target"
      "data.mount"
    ];
    wants = [ "time-set.target" ];
    before = [
      "time-set.target"
      "sysinit.target"
      "shutdown.target"
    ];
    conflicts = [ "shutdown.target" ];
    wantedBy = [ "sysinit.target" ];
    path = [ pkgs.coreutils ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = "${clockScript} restore";
      ExecStop = "${clockScript} save";
    };
  };

  systemd.services.atomixos-clock-save = {
    description = "Save the current time as the last known time";
    after = [ "atomixos-clock.service" ];
    unitConfig.RequiresMountsFor = [ "/data" ];
    path = [ pkgs.coreutils ];
    serviceConfig = {
      Type = "oneshot";
      ExecStart = "${clockScript} save";
    };
  };

  systemd.timers.atomixos-clock-save = {
    description = "Save the current time every 15 minutes";
    wantedBy = [ "timers.target" ];
    timerConfig = {
      OnBootSec = "5min";
      OnUnitActiveSec = "15min";
    };
  };
}
