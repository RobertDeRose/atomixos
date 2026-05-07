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
  name = "chrony-wan-recovery";

  inherit hostPkgs;

  nodes.gateway =
    { lib, ... }:
    {
      _module.args = {
        inherit self;
        developmentMode = false;
      };

      imports = [
        ../../modules/base.nix
        qemuModule
      ];

      virtualisation.memorySize = 512;
      system.stateVersion = "25.11";

      networking.useDHCP = false;

      systemd.network.networks."10-wan" = lib.mkForce {
        matchConfig.Name = "eth0";
        linkConfig = {
          ActivationPolicy = "manual";
        };
        networkConfig = {
          Address = [ "10.0.2.15/24" ];
          Gateway = [ "10.0.2.2" ];
          DNS = [ "10.0.2.3" ];
          IPv6AcceptRA = false;
          ConfigureWithoutCarrier = false;
        };
      };

      systemd.services.chrony-waitsync-probe = {
        description = "Probe chrony waitsync after delayed WAN";
        after = [ "chronyd.service" ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "${pkgs.chrony}/bin/chronyc waitsync 0 1";
          TimeoutStartSec = 180;
        };
      };
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("networkd-dispatcher.service")
    gateway.wait_for_unit("chronyd.service")

    gateway.wait_until_succeeds("chronyc activity | grep '^0 sources online$'", timeout=60)
    gateway.succeed("chronyc activity | grep 'sources with unknown address'")
    gateway.fail("chronyc waitsync 1 0 1 1")

    gateway.succeed("sh -c '(systemctl start chrony-waitsync-probe.service; echo $? >/tmp/chrony-waitsync-probe.exit) >/tmp/chrony-waitsync-probe.log 2>&1 &'")
    gateway.wait_until_succeeds("systemctl show -P ActiveState chrony-waitsync-probe.service | grep '^activating$'", timeout=30)

    gateway.succeed("networkctl up eth0")
    gateway.wait_until_succeeds("networkctl status eth0 --no-pager | grep 'State: routable'", timeout=60)
    gateway.wait_until_succeeds("journalctl -u networkd-dispatcher -b --no-pager | grep '\[chrony-wan-online\] bringing chrony online for eth0'", timeout=60)
    gateway.wait_until_succeeds("chronyc activity | grep -E '^[1-9][0-9]* sources online$'", timeout=60)
    gateway.wait_until_succeeds("chronyc tracking | grep '^Reference ID' | grep -v '7F7F0101'", timeout=120)
    gateway.wait_until_succeeds("test -f /tmp/chrony-waitsync-probe.exit", timeout=120)
    gateway.succeed("test \"$(cat /tmp/chrony-waitsync-probe.exit)\" = 0")
    gateway.succeed("systemctl show -P Result chrony-waitsync-probe.service | grep '^success$'")
  '';
}
