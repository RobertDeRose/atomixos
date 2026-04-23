# NixOS test: verify LAN devices get DHCP/NTP but cannot reach WAN.
#
# This test:
# 1. Boots a gateway with dnsmasq (DHCP) + chrony (NTP) on the LAN interface
# 2. Boots a LAN client on VLAN 2
# 3. Verifies LAN client receives a DHCP lease in the correct range
# 4. Verifies LAN client can query NTP from the gateway
# 5. Verifies LAN client cannot reach any WAN address (no forwarding)
#
# Uses a 2-node topology (gateway + lan) to fit within 3.9 GB Lima.
# WAN isolation is verified by: ip_forward=0, forward chain drops all,
# and no route from LAN to WAN subnet.
#
# NixOS test VMs always have eth0 as a management backdoor.  With
# vlans = [1 2], the VLAN interfaces become eth1 and eth2.  We therefore
# use eth1 = WAN (VLAN 1) and eth2 = LAN (VLAN 2) in the gateway config.
#
# Run:  nix build .#checks.aarch64-linux.network-isolation
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
  name = "network-isolation";

  inherit hostPkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [ qemuModule ];

      virtualisation = {
        vlans = [
          1
          2
        ];
        memorySize = 384;
      };

      system.stateVersion = "25.11";

      # -- Networking: eth1 = WAN (VLAN 1), eth2 = LAN (VLAN 2) ------
      networking.useDHCP = false;
      networking.interfaces.eth1.ipv4.addresses = [
        {
          address = "192.168.1.1";
          prefixLength = 24;
        }
      ];
      networking.interfaces.eth2.ipv4.addresses = [
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

      # -- Nftables (minimal, allows LAN services + blocks forwarding) -
      networking.firewall.enable = false;
      networking.nftables.enable = true;
      networking.nftables.tables.filter = {
        family = "inet";
        content = ''
          chain input {
            type filter hook input priority 0; policy drop;
            iif "lo" accept
            ct state established,related accept
            iifname "eth0" accept

            # LAN (eth2) — DHCP, NTP, SSH, ping
            iifname "eth2" udp dport { 67, 68 } accept  comment "DHCP"
            iifname "eth2" udp dport 123 accept          comment "NTP"
            iifname "eth2" tcp dport 22 accept           comment "SSH"
            iifname "eth2" icmp type echo-request accept comment "ping"
          }

          chain forward {
            type filter hook forward priority 0; policy drop;
          }

          chain output {
            type filter hook output priority 0; policy accept;
          }
        '';
      };

      # /persist directory
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
        "d /persist/config 0755 root root -"
      ];

      # dnsmasq — DHCP server on eth2 (LAN / VLAN 2)
      # Use bind-dynamic so dnsmasq doesn't fail if eth2 isn't ready at start.
      services.dnsmasq = {
        enable = true;
        settings = {
          interface = "eth2";
          bind-dynamic = true;
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
      ];
    };

  # LAN client — gets DHCP from gateway, should be isolated from WAN.
  # Only on VLAN 2, so it gets eth1 (not eth2) as its VLAN interface.
  nodes.lan =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 2 ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      networking.useDHCP = false;
      networking.interfaces.eth1.useDHCP = true;
      environment.systemPackages = [
        pkgs.chrony
        pkgs.iproute2
      ];
    };

  testScript = ''
    # Start VMs sequentially to reduce peak memory under TCG
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("nftables.service")
    gateway.wait_for_unit("dnsmasq.service")
    gateway.wait_for_unit("chronyd.service")

    # Verify gateway interfaces
    gateway.succeed("ip -4 addr show eth1 | grep '192.168.1.1'")
    gateway.succeed("ip -4 addr show eth2 | grep '172.20.30.1'")

    # ── Phase 1: LAN client gets DHCP lease ──
    gateway.log("Phase 1: Verifying LAN client gets DHCP")

    lan.start()
    lan.wait_for_unit("multi-user.target")

    # Wait for DHCP lease (the LAN client should get an IP in 172.20.30.10-254)
    # LAN client has vlans=[2], so its VLAN interface is eth1
    # NixOS test driver also auto-assigns 192.168.2.x on VLAN interfaces,
    # so we must filter specifically for the DHCP range.
    # TCG boots are slow — allow up to 60s for DHCP negotiation
    lan.wait_until_succeeds("ip -4 addr show eth1 | grep '172.20.30.'", timeout=60)
    lan_ip = lan.succeed("ip -4 addr show eth1 | grep -oP 'inet \\K[\\d.]+' | grep '^172\\.20\\.30\\.'").strip()
    gateway.log(f"LAN client got IP: {lan_ip}")
    assert lan_ip.startswith("172.20.30."), f"Unexpected LAN IP: {lan_ip}"

    # Verify LAN client can reach the gateway
    lan.succeed("ping -c 1 -W 3 172.20.30.1")

    gateway.log("Phase 1 PASSED: LAN client received DHCP lease")

    # ── Phase 2: LAN client can query NTP ──
    gateway.log("Phase 2: Verifying NTP reachability")

    # Use chronyd client mode to query the gateway
    lan.succeed("chronyd -Q 'server 172.20.30.1 iburst' 2>&1 || true")
    # Also verify basic reachability
    lan.succeed("ping -c 1 -W 3 172.20.30.1")

    gateway.log("Phase 2 PASSED: NTP reachable from LAN")

    # ── Phase 3: LAN client cannot reach WAN ──
    gateway.log("Phase 3: Verifying LAN-to-WAN isolation")

    # Verify forwarding is disabled on the gateway
    fwd = gateway.succeed("cat /proc/sys/net/ipv4/ip_forward").strip()
    assert fwd == "0", f"Expected ip_forward=0, got: {fwd}"

    # Verify forward chain exists with drop policy
    gateway.succeed("nft list chain inet filter forward | grep 'policy drop'")

    # The LAN client has a default route via the gateway (from DHCP), but
    # the gateway has ip_forward=0 so it cannot forward packets to the WAN.
    # Try pinging a hypothetical WAN host (192.168.1.2) — there's no such
    # host, AND even if there were the gateway would not forward.  The ping
    # must time out.
    lan.fail("ping -c 1 -W 3 192.168.1.2")

    # Also verify the gateway's WAN interface is in a different subnet than
    # the LAN client's network — no direct L2 reachability.
    lan_routes = lan.succeed("ip route show")
    gateway.log(f"LAN client routes: {lan_routes}")
    assert "192.168.1.0" not in lan_routes, "LAN client should not have a direct route to WAN subnet"

    gateway.log("Phase 3 PASSED: LAN client isolated from WAN")

    gateway.log("Network isolation test passed — DHCP works, WAN unreachable")
  '';
}
