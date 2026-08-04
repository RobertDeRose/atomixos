# NixOS test: enabled watchdog policy fails open when no device exists.
{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "watchdog-missing-device";

  inherit hostPkgs;

  nodes.gateway =
    { pkgs, ... }:
    {
      _module.args = {
        inherit self;
        developmentMode = true;
        nixstasis = self.inputs.nixstasis;
      };

      imports = [
        ../../modules/base.nix
        qemuModule
        ./rauc-qemu-config.nix
      ];

      virtualisation = {
        emptyDiskImages = [
          128 # vdb — boot slot A
          128 # vdc — boot slot B
          1024 # vdd — rootfs slot A
          1024 # vde — rootfs slot B
        ];
        memorySize = 768;
      };
      system.stateVersion = "25.11";

      boot.kernelParams = [ "rauc.slot=boot.0" ];
      atomixos.rauc.statusFile = "/tmp/rauc.status";
      atomixos.rauc.bundleFormats = [
        "+plain"
        "-verity"
      ];
      atomixos.watchdog.enableHardware = true;

      systemd.services.watchdog-test-rauc-state = {
        description = "Seed RAUC state before the missing-device check";
        wantedBy = [ "multi-user.target" ];
        before = [ "watchdog-device-check.service" ];
        after = [ "watchdog-boot-count.service" ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
        };
        script = ''
          install -d /var/lib/rauc
          printf '%s\n' A > /var/lib/rauc/primary
          printf '%s\n' good > /var/lib/rauc/state.A
          printf '%s\n' bad > /var/lib/rauc/state.B
          ${pkgs.coreutils}/bin/sha256sum \
            /var/lib/rauc/primary \
            /var/lib/rauc/state.A \
            /var/lib/rauc/state.B \
            > /run/watchdog-rauc-state.before
        '';
      };

      systemd.services.watchdog-device-check = {
        requires = [ "watchdog-test-rauc-state.service" ];
        after = [ "watchdog-test-rauc-state.service" ];
      };
    };

  testScript = ''
    import json

    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.fail("journalctl -b -u networkd-dispatcher --no-pager | grep -F 'No valid path found for iwconfig'")
    gateway.wait_for_unit("rauc.service")
    gateway.wait_for_unit("watchdog-test-rauc-state.service")
    gateway.wait_for_unit("watchdog-device-check.service")

    gateway.fail("test -e /dev/watchdog")
    gateway.fail("test -e /dev/watchdog0")
    gateway.succeed("systemctl show -p RuntimeWatchdogUSec --value | grep -qx 30s")
    gateway.succeed("systemctl show -p RebootWatchdogUSec --value | grep -qx 10min")

    # Missing watchdog hardware must not fail boot or the loaded verification unit.
    gateway.succeed("systemctl is-active --quiet multi-user.target")
    gateway.succeed("systemctl show -p LoadState --value os-verification.service | grep -qx loaded")
    gateway.fail("systemctl is-failed --quiet os-verification.service")

    # The missing-device check must not mutate existing simulated RAUC state.
    gateway.succeed("${pkgs.coreutils}/bin/sha256sum /var/lib/rauc/primary /var/lib/rauc/state.A /var/lib/rauc/state.B | diff -u /run/watchdog-rauc-state.before -")

    # systemd owns device acquisition; AtomixOS reports unavailability at warning priority.
    gateway.succeed("systemctl show -p Result --value watchdog-device-check.service | grep -qx success")
    warning_entries = [
        json.loads(line)
        for line in gateway.succeed(
            "journalctl -b -u watchdog-device-check.service --no-pager -o json"
        ).splitlines()
    ]
    assert any(
        entry.get("PRIORITY") == "4"
        and "hardware watchdog enforcement is unavailable: no watchdog character device exists"
        in entry.get("MESSAGE", "")
        for entry in warning_entries
    ), warning_entries
  '';
}
