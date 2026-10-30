{
  pkgs,
  self,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };

  # A production certificate issued after the source commit: its validity start
  # must raise the floor.
  futureCert = pkgs.runCommand "future-cert.pem" { nativeBuildInputs = [ pkgs.openssl ]; } ''
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
      -keyout /dev/null -subj /CN=future -out "$out" \
      -not_before 20300101000000Z -not_after 20400101000000Z
  '';
in
nixos-lib.runTest {
  name = "clock";

  inherit hostPkgs;

  node.specialArgs = {
    inherit self;
    developmentMode = true;
    nixstasis = self.inputs.nixstasis;
  };

  nodes.gateway =
    { lib, ... }:
    {
      imports = [
        ../../modules/base.nix
        qemuModule
      ];
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      atomixos.clock.floorCertificates = [ futureCert ];
      virtualisation.memorySize = 1024;
    };

  # QEMU's /data is a tmpfs, so this restarts atomixos-clock.service (restore on
  # start, save on stop) instead of rebooting.
  testScript = ''
    past = 1000000000  # 2001, before any AtomixOS source date

    def now():
        return int(gateway.succeed("date +%s"))

    def saved():
        return int(gateway.succeed("cat /data/clock/last-known"))

    gateway.start()
    gateway.wait_for_unit("atomixos-clock.service")
    gateway.succeed("systemctl is-active atomixos-clock-save.timer")

    # The certificate starting 2030-01-01 sets the floor, and boot already moved
    # the clock there.
    floor = int(gateway.succeed("cat /etc/atomixos/clock-floor"))
    assert floor == 1893456000, floor
    assert floor > ${toString self.lastModified}
    assert now() >= floor, now()

    # Saving records the current time on /data.
    gateway.succeed("systemctl start atomixos-clock-save.service")
    assert saved() >= floor, saved()

    # A clock set back before the image source date moves forward to the last known time.
    gateway.succeed("systemctl stop atomixos-clock.service")
    last = saved()
    gateway.succeed(f"date -u -s @{past}")
    gateway.succeed("systemctl start atomixos-clock.service")
    assert now() >= last, (now(), last)

    # With no saved time, it moves forward to the image source date.
    gateway.succeed("systemctl stop atomixos-clock.service")
    gateway.succeed(f"rm /data/clock/last-known && date -u -s @{past}")
    gateway.succeed("systemctl start atomixos-clock.service")
    assert floor <= now() < floor + 600, (now(), floor)

    # A saved time ahead of the clock wins.
    gateway.succeed("systemctl stop atomixos-clock.service")
    ahead = now() + 30 * 86400
    gateway.succeed(f"echo {ahead} >/data/clock/last-known")
    gateway.succeed("systemctl start atomixos-clock.service")
    assert now() >= ahead, (now(), ahead)

    # A clock before the image source date is never saved.
    gateway.succeed(f"date -u -s @{past}")
    gateway.succeed("systemctl start atomixos-clock-save.service")
    assert saved() == ahead, saved()

    # chronyd keeps the RTC in sync through the kernel's 11-minute mode.
    gateway.succeed("grep -qx rtcsync $(systemctl cat chronyd | grep -o '/nix/store/[^ ]*chrony.conf' | head -1)")
  '';
}
