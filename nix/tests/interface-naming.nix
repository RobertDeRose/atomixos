{
  pkgs,
  self,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  # The NixOS test driver gives node 1's NIC on VLAN n the MAC 52:54:00:12:0n:01.
  vlan1Mac = "52:54:00:12:01:01";
  vlan2Mac = "52:54:00:12:02:01";
in
nixos-lib.runTest {
  name = "interface-naming";

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
      virtualisation.vlans = [
        1
        2
      ];
      # Match by MAC the opposite way to kernel registration order: VLAN 1
      # registers first (eth1) but is LAN, VLAN 2 registers second (eth2) but
      # is WAN. Hardware matches the onboard NIC by platform path instead.
      atomixos.network = {
        wanInterface = "wan";
        lanInterface = "lan";
        wanLinkMatch.MACAddress = vlan2Mac;
        lanLinkMatch.MACAddress = vlan1Mac;
      };
    };

  # WAN and LAN names must follow the hardware, not which NIC registers first.
  testScript = ''
    def assert_names():
        gateway.wait_until_succeeds("test -e /sys/class/net/wan && test -e /sys/class/net/lan")
        assert gateway.succeed("cat /sys/class/net/wan/address").strip() == "${vlan2Mac}"
        assert gateway.succeed("cat /sys/class/net/lan/address").strip() == "${vlan1Mac}"

    gateway.start()
    gateway.wait_for_unit("systemd-networkd.service")
    assert_names()
    gateway.wait_until_succeeds("networkctl status lan --no-pager | grep -E 'State: .*(configured|configuring)'")

    # Re-register both NICs in the reverse order: WAN first, then LAN.
    wan_dev = gateway.succeed("basename $(readlink -f /sys/class/net/wan/device)").strip()
    lan_dev = gateway.succeed("basename $(readlink -f /sys/class/net/lan/device)").strip()
    driver = "/sys/bus/virtio/drivers/virtio_net"
    gateway.succeed(f"echo {wan_dev} > {driver}/unbind && echo {lan_dev} > {driver}/unbind")
    gateway.succeed(f"echo {wan_dev} > {driver}/bind")
    gateway.wait_until_succeeds("test -e /sys/class/net/wan")
    gateway.succeed(f"echo {lan_dev} > {driver}/bind")
    assert_names()
  '';
}
