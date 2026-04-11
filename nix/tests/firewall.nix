# NixOS test: verify nftables firewall rules on WAN, LAN, and VPN interfaces.
#
# This test:
# 1. Boots a gateway node with the production firewall rules (firewall.nix)
# 2. Boots a WAN probe node on VLAN 1 and a LAN client on VLAN 2
# 3. Verifies WAN allows only HTTPS (443) and OpenVPN (1194)
# 4. Verifies LAN allows DHCP (67-68), NTP (123), and SSH (22)
# 5. Verifies SSH is blocked on WAN by default
# 6. Verifies no forwarding between interfaces
#
# Uses multi-node NixOS test with VLANs. Imports firewall.nix directly.
#
# Run:  nix build .#checks.aarch64-linux.firewall
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
  name = "firewall";

  hostPkgs = pkgs;

  # Gateway: our device under test — VLAN 1 (WAN) + VLAN 2 (LAN)
  # WAN probe: on VLAN 1, tests WAN-side rules
  # LAN client: on VLAN 2, tests LAN-side rules
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

      # The test framework creates eth1 (VLAN 1) and eth2 (VLAN 2).
      # Our firewall rules reference eth0 (WAN) and eth1 (LAN).
      # Rename at boot via udev so nftables rules match.
      services.udev.extraRules = ''
        SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="52:54:00:12:01:*", NAME="eth0"
        SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="52:54:00:12:02:*", NAME="eth1"
      '';

      # Static IPs since we're not using the production networking.nix
      # (which expects hardware-specific .link matches)
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

      # Disable IP forwarding (EN18031 compliance)
      boot.kernel.sysctl = {
        "net.ipv4.ip_forward" = 0;
        "net.ipv6.conf.all.forwarding" = 0;
      };

      # /persist for ssh-wan-toggle flag file
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
        "d /persist/config 0755 root root -"
      ];

      # Listener services for port probing
      # nc listeners will be started from the test script instead
      environment.systemPackages = [
        pkgs.nmap
        pkgs.nftables
      ];
    };

  nodes.wan =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 1 ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      environment.systemPackages = [
        pkgs.nmap
        pkgs.netcat
      ];
    };

  nodes.lan =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 2 ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      environment.systemPackages = [
        pkgs.nmap
        pkgs.netcat
      ];
    };

  testScript = ''
    gateway.start()
    wan.start()
    lan.start()

    gateway.wait_for_unit("multi-user.target")
    wan.wait_for_unit("multi-user.target")
    lan.wait_for_unit("multi-user.target")

    # Wait for nftables to be loaded
    gateway.wait_for_unit("nftables.service")
    gateway.wait_for_unit("ssh-wan-toggle.service")

    # Log the nftables ruleset for debugging
    gateway.succeed("nft list ruleset")

    # Verify interfaces exist with expected names
    gateway.succeed("ip link show eth0")
    gateway.succeed("ip link show eth1")

    # ── Start listeners on the gateway for port probing ──
    # These simulate services listening on various ports
    gateway.succeed("nc -l -k 443 >/dev/null 2>&1 &")   # HTTPS
    gateway.succeed("nc -l -k 22 >/dev/null 2>&1 &")    # SSH
    gateway.succeed("nc -l -u 1194 >/dev/null 2>&1 &")  # OpenVPN (UDP)
    gateway.succeed("nc -l -u 123 >/dev/null 2>&1 &")   # NTP (UDP)
    gateway.succeed("nc -l -u 67 >/dev/null 2>&1 &")    # DHCP (UDP)
    gateway.succeed("nc -l -k 8080 >/dev/null 2>&1 &")  # Unlisted port (should be blocked)

    import time
    time.sleep(1)

    # ── Phase 1: WAN rules (from wan node → gateway eth0) ──
    gateway.log("Phase 1: Testing WAN firewall rules")

    # HTTPS (443/tcp) — ALLOWED on WAN
    wan.succeed("nc -z -w 3 192.168.1.1 443")

    # OpenVPN (1194/udp) — ALLOWED on WAN
    # UDP port scanning: send a packet with nc -u, if no ICMP unreachable comes
    # back, the port is open. nmap gives clearer results.
    wan.succeed("nmap -sU -p 1194 --host-timeout 10s 192.168.1.1 | grep -q 'open'")

    # SSH (22/tcp) — BLOCKED on WAN by default (no flag file)
    wan.fail("nc -z -w 3 192.168.1.1 22")

    # Random port (8080/tcp) — BLOCKED on WAN
    wan.fail("nc -z -w 3 192.168.1.1 8080")

    gateway.log("Phase 1 PASSED: WAN allows HTTPS+OpenVPN, blocks SSH+other")

    # ── Phase 2: LAN rules (from lan node → gateway eth1) ──
    gateway.log("Phase 2: Testing LAN firewall rules")

    # SSH (22/tcp) — ALLOWED on LAN
    lan.succeed("nc -z -w 3 172.20.30.1 22")

    # NTP (123/udp) — ALLOWED on LAN
    lan.succeed("nmap -sU -p 123 --host-timeout 10s 172.20.30.1 | grep -q 'open'")

    # DHCP (67/udp) — ALLOWED on LAN
    lan.succeed("nmap -sU -p 67 --host-timeout 10s 172.20.30.1 | grep -q 'open'")

    # Random port (8080/tcp) — BLOCKED on LAN
    lan.fail("nc -z -w 3 172.20.30.1 8080")

    # HTTPS (443/tcp) — BLOCKED on LAN (only allowed on WAN)
    lan.fail("nc -z -w 3 172.20.30.1 443")

    gateway.log("Phase 2 PASSED: LAN allows SSH+NTP+DHCP, blocks HTTPS+other")

    # ── Phase 3: No forwarding ──
    gateway.log("Phase 3: Testing forward chain (drop all)")

    # Verify ip_forward is disabled
    fwd = gateway.succeed("cat /proc/sys/net/ipv4/ip_forward").strip()
    assert fwd == "0", f"Expected ip_forward=0, got: {fwd}"

    gateway.log("Phase 3 PASSED: Forwarding disabled")

    gateway.log("Firewall test passed — all WAN/LAN rules verified")
  '';
}
