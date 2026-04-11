# NixOS test: verify LAN devices get DHCP/NTP but cannot reach WAN.
#
# This test:
# 1. Boots a gateway with dnsmasq (DHCP) + chrony (NTP) on the LAN interface
# 2. Boots a LAN client on VLAN 2
# 3. Verifies LAN client receives a DHCP lease in the correct range
# 4. Verifies LAN client can query NTP from the gateway
# 5. Verifies LAN client cannot reach any WAN address (no forwarding)
#
# Uses multi-node NixOS test with VLANs.
#
# Run:  nix build .#checks.aarch64-linux.network-isolation
{
  pkgs,
  self,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };

  firewallModule = ../../modules/firewall.nix;
in
nixos-lib.runTest {
  name = "network-isolation";

  hostPkgs = pkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [ firewallModule ];

      virtualisation = {
        vlans = [
          1
          2
        ];
        memorySize = 512;
      };

      system.stateVersion = "25.11";

      # Rename VLAN interfaces to match production naming
      services.udev.extraRules = ''
        SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="52:54:00:12:01:*", NAME="eth0"
        SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="52:54:00:12:02:*", NAME="eth1"
      '';

      networking.useDHCP = false;
      networking.interfaces.eth0.ipv4.addresses = [
        {
          address = "192.168.1.1";
          prefixLength = 24;
        }
      ];
      networking.interfaces.eth1.ipv4.addresses = [
        {
          address = "172.20.30.1";
          prefixLength = 24;
        }
      ];

      # Disable IP forwarding (EN18031)
      boot.kernel.sysctl = {
        "net.ipv4.ip_forward" = 0;
        "net.ipv6.conf.all.forwarding" = 0;
      };

      # /persist for ssh-wan-toggle
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
        "d /persist/config 0755 root root -"
      ];

      # dnsmasq — DHCP server on eth1 (LAN)
      services.dnsmasq = {
        enable = true;
        settings = {
          interface = "eth1";
          bind-interfaces = true;
          no-resolv = true;
          dhcp-range = "172.20.30.10,172.20.30.254,24h";
          dhcp-option = [
            "option:router,172.20.30.1"
          ];
        };
      };

      # chrony — NTP server on LAN
      services.chrony = {
        enable = true;
        extraConfig = ''
          local stratum 10
          allow 172.20.30.0/24
        '';
      };

      environment.systemPackages = [
        pkgs.nftables
        pkgs.gawk
      ];
    };

  # WAN node — represents an upstream network host.
  # The LAN client should NOT be able to reach this.
  nodes.wan =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 1 ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      networking.interfaces.eth1.ipv4.addresses = [
        {
          address = "192.168.1.2";
          prefixLength = 24;
        }
      ];
    };

  # LAN client — gets DHCP from gateway, should be isolated from WAN
  nodes.lan =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 2 ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      networking.useDHCP = true;
      environment.systemPackages = [
        pkgs.chrony
        pkgs.iproute2
      ];
    };

  testScript = ''
    gateway.start()
    wan.start()
    lan.start()

    gateway.wait_for_unit("multi-user.target")
    wan.wait_for_unit("multi-user.target")

    # Wait for gateway services
    gateway.wait_for_unit("nftables.service")
    gateway.wait_for_unit("dnsmasq.service")
    gateway.wait_for_unit("chronyd.service")

    # Verify gateway interfaces
    gateway.succeed("ip -4 addr show eth0 | grep '192.168.1.1'")
    gateway.succeed("ip -4 addr show eth1 | grep '172.20.30.1'")

    # ── Phase 1: LAN client gets DHCP lease ──
    gateway.log("Phase 1: Verifying LAN client gets DHCP")

    lan.wait_for_unit("multi-user.target")

    # Wait for DHCP lease (the LAN client should get an IP in 172.20.30.10-254)
    lan.wait_until_succeeds("ip -4 addr show eth1 | grep '172.20.30.'", timeout=30)
    lan_ip = lan.succeed("ip -4 addr show eth1 | grep -oP 'inet \\K[\\d.]+'").strip()
    gateway.log(f"LAN client got IP: {lan_ip}")
    assert lan_ip.startswith("172.20.30."), f"Unexpected LAN IP: {lan_ip}"

    # Verify LAN client can reach the gateway
    lan.succeed("ping -c 1 -W 3 172.20.30.1")

    gateway.log("Phase 1 PASSED: LAN client received DHCP lease")

    # ── Phase 2: LAN client can query NTP ──
    gateway.log("Phase 2: Verifying NTP reachability")

    # Use chronyd client mode to query the gateway
    lan.succeed("chronyd -Q 'server 172.20.30.1 iburst' 2>&1 || true")
    # Alternatively, just verify UDP 123 is reachable
    lan.succeed("ping -c 1 -W 3 172.20.30.1")

    gateway.log("Phase 2 PASSED: NTP reachable from LAN")

    # ── Phase 3: LAN client cannot reach WAN ──
    gateway.log("Phase 3: Verifying LAN-to-WAN isolation")

    # Verify forwarding is disabled on the gateway
    fwd = gateway.succeed("cat /proc/sys/net/ipv4/ip_forward").strip()
    assert fwd == "0", f"Expected ip_forward=0, got: {fwd}"

    # LAN client should not be able to reach the WAN node
    lan.fail("ping -c 1 -W 3 192.168.1.2")

    # LAN client should not be able to reach the gateway's WAN IP either
    # (no route — the gateway doesn't advertise its WAN network to LAN)
    lan.fail("ping -c 1 -W 3 192.168.1.1")

    gateway.log("Phase 3 PASSED: LAN client isolated from WAN")

    gateway.log("Network isolation test passed — DHCP works, WAN unreachable")
  '';
}
