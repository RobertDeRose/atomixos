# Keep the system clock from starting in the past.
#
# Boards without a battery-backed RTC, or without NTP yet, boot with the clock at
# systemd's compiled-in epoch, which can predate the RAUC certificates. RAUC then
# rejects every bundle as "not yet valid". At boot the clock is moved forward to
# the later of a build-time floor and the last time saved on /data; the time is
# saved again every 15 minutes and at shutdown, so it never runs backwards across
# a power loss.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:
let
  cfg = config.atomixos.clock;
  stateFile = "/data/clock/last-known";

  # The floor is the latest of the AtomixOS source commit time and the start of
  # every listed certificate's validity, computed when the image is built.
  floorFile = pkgs.runCommand "atomixos-clock-floor" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    floor=${toString self.lastModified}
    for cert in ${lib.escapeShellArgs (map (cert: "${cert}") cfg.floorCertificates)}; do
      start=$(openssl x509 -in "$cert" -noout -dateopt iso_8601 -startdate)
      start=$(date -u -d "''${start#notBefore=}" +%s)
      [ "$start" -le "$floor" ] || floor=$start
    done
    echo "$floor" >"$out"
  '';

  clockScript = pkgs.writeShellScript "atomixos-clock" ''
    set -euo pipefail
    floor=$(cat /etc/atomixos/clock-floor)
    state=${stateFile}
    dir=''${state%/*}
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
      # /data is a nofail mount: never write the state onto the overlay root.
      if ! mountpoint -q "''${dir%/*}"; then
        echo "''${dir%/*} is not mounted; not saving the time"
        exit 0
      fi
      if [ "$now" -lt "$floor" ]; then
        echo "clock is before the build-time floor; not saving it"
        exit 0
      fi
      # Flush the new value, then the rename and the directory entry, so a power
      # loss right after a save keeps either the old or the new time.
      mkdir -p "$dir"
      printf '%s\n' "$now" >"$state.tmp"
      sync "$state.tmp"
      mv "$state.tmp" "$state"
      sync "$dir" "''${dir%/*}"
      ;;
    *)
      echo "usage: $0 restore|save" >&2
      exit 2
      ;;
    esac
  '';
in
{
  options.atomixos.clock.floorCertificates = lib.mkOption {
    type = lib.types.listOf lib.types.path;
    default =
      if config.atomixos.rauc.keyringCert != null then
        [ config.atomixos.rauc.keyringCert ]
      else
        [
          ../certs/dev.ca.cert.pem
          ../certs/dev.signing.cert.pem
        ];
    defaultText = lib.literalExpression ''
      if atomixos.rauc.keyringCert != null then [ atomixos.rauc.keyringCert ]
      else [ ./certs/dev.ca.cert.pem ./certs/dev.signing.cert.pem ]
    '';
    description = ''
      Certificates whose validity start raises the boot-time clock floor. The
      floor is the latest of these and the AtomixOS source commit time. Add the
      production RAUC signing certificate when it is not the repository one.
    '';
  };

  config = {
    environment.etc."atomixos/clock-floor".source = floorFile;

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
      path = [
        pkgs.coreutils
        pkgs.util-linux
      ];
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
      path = [
        pkgs.coreutils
        pkgs.util-linux
      ];
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
  };
}
