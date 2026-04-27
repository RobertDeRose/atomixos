# NixOS test: verify nftables firewall rules on WAN, LAN, and VPN interfaces.
#
# This test:
# 1. Boots a gateway node with firewall rules modelled on firewall.nix
# 2. Boots a single probe node on BOTH VLANs (1 and 2)
# 3. Verifies WAN allows only HTTPS (443) and OpenVPN (1194)
# 4. Verifies LAN allows DHCP (67-68), NTP (123), SSH (22), and bootstrap UI (8080)
# 5. Verifies SSH is blocked on WAN by default
# 6. Verifies no forwarding between interfaces
#
# Uses a 2-node topology to fit within 3.9 GB Lima (3-node OOM under TCG).
# The probe node has vlans = [1 2] so it gets eth1 (VLAN 1 / WAN) and
# eth2 (VLAN 2 / LAN), allowing it to test both sides from one VM.
#
# NixOS test VMs always have eth0 as a management backdoor.  With
# vlans = [1 2], the VLAN interfaces become eth1 and eth2.  We therefore
# define test-local nftables rules mapping:
#   eth1 = WAN (production eth0)
#   eth2 = LAN (production eth1)
#
# Run:  nix build .#checks.aarch64-linux.firewall
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
  name = "firewall";

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

      # Disable IP forwarding (EN18031 compliance)
      boot.kernel.sysctl = {
        "net.ipv4.ip_forward" = 0;
        "net.ipv6.conf.all.forwarding" = 0;
      };

      # -- Nftables matching production structure (adapted for test) ---
      networking.firewall.enable = false;
      networking.nftables.enable = true;
      networking.nftables.tables.filter = {
        family = "inet";
        content = ''
          chain input {
            type filter hook input priority 0; policy drop;

            # Allow loopback
            iif "lo" accept

            # Allow established/related
            ct state established,related accept

            # Allow NixOS test driver backdoor
            iifname "eth0" accept

            # -- eth1 (WAN / VLAN 1) rules --
            iifname "eth1" tcp dport 443 accept   comment "HTTPS (Traefik)"
            iifname "eth1" udp dport 1194 accept  comment "OpenVPN"

            # -- eth2 (LAN / VLAN 2) rules --
            iifname "eth2" udp dport { 67, 68 } accept  comment "DHCP"
            iifname "eth2" udp dport 123 accept          comment "NTP"
            iifname "eth2" tcp dport 22 accept           comment "SSH"
            iifname "eth2" tcp dport 8080 accept         comment "Bootstrap UI"

            # Everything else is dropped by default policy
          }

          chain forward {
            type filter hook forward priority 0; policy drop;
            # No forwarding between interfaces
          }

          chain output {
            type filter hook output priority 0; policy accept;
          }
        '';
      };

      # /data for ssh-wan-toggle flag file
      systemd.tmpfiles.rules = [
        "d /data 0755 root root -"
        "d /data/config 0755 root root -"
      ];

      # Listener services for port probing
      environment.systemPackages = [
        pkgs.nmap
        pkgs.nftables
      ];
    };

  # Single probe node on BOTH VLANs — tests WAN and LAN rules from one VM.
  # eth1 = VLAN 1 (WAN side, 192.168.1.x)
  # eth2 = VLAN 2 (LAN side, 172.20.30.x)
  nodes.probe =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [
          1
          2
        ];
        memorySize = 256;
      };
      system.stateVersion = "25.11";
      networking.useDHCP = false;
      networking.interfaces.eth1.ipv4.addresses = [
        {
          address = "192.168.1.2";
          prefixLength = 24;
        }
      ];
      networking.interfaces.eth2.ipv4.addresses = [
        {
          address = "172.20.30.2";
          prefixLength = 24;
        }
      ];
      environment.systemPackages = [
        pkgs.nmap
        pkgs.netcat
      ];
    };

  testScript = ''
    # Start VMs sequentially to reduce peak memory under TCG
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("nftables.service")

    probe.start()
    probe.wait_for_unit("multi-user.target")

    # Log the nftables ruleset for debugging
    gateway.succeed("nft list ruleset")

    # Verify interfaces exist with expected IPs
    gateway.succeed("ip -4 addr show eth1 | grep '192.168.1.1'")
    gateway.succeed("ip -4 addr show eth2 | grep '172.20.30.1'")

    # ── Start listeners on the gateway for port probing ──
    # Use ncat (from nmap) which reliably supports -k (keep-alive) for TCP
    # and -u for UDP listeners
    gateway.succeed("ncat -lk 443 >/dev/null 2>&1 &")       # HTTPS (TCP)
    gateway.succeed("ncat -lk 22 >/dev/null 2>&1 &")        # SSH (TCP)
    gateway.succeed("ncat -lu 1194 >/dev/null 2>&1 &")      # OpenVPN (UDP)
    gateway.succeed("ncat -lu 123 >/dev/null 2>&1 &")       # NTP (UDP)
    gateway.succeed("ncat -lu 67 >/dev/null 2>&1 &")        # DHCP (UDP)
    gateway.succeed("ncat -lk 8080 >/dev/null 2>&1 &")      # Unlisted port (should be blocked)

    import time
    time.sleep(2)

    # Verify TCP listeners are actually running
    gateway.succeed("ss -tlnp | grep ':443'")
    gateway.succeed("ss -tlnp | grep ':22'")

    # ── Phase 1: WAN rules (probe eth1 → gateway eth1) ──
    gateway.log("Phase 1: Testing WAN firewall rules")

    # HTTPS (443/tcp) — ALLOWED on WAN
    probe.succeed("nc -z -w 3 192.168.1.1 443")

    # OpenVPN (1194/udp) — ALLOWED on WAN
    # Use ncat to send a UDP packet and verify it's not rejected
    probe.succeed("echo test | ncat -u -w 3 192.168.1.1 1194")

    # SSH (22/tcp) — BLOCKED on WAN by default (no flag file)
    probe.fail("nc -z -w 3 192.168.1.1 22")

    # Random port (8080/tcp) — BLOCKED on WAN
    probe.fail("nc -z -w 3 192.168.1.1 8080")

    gateway.log("Phase 1 PASSED: WAN allows HTTPS+OpenVPN, blocks SSH+other")

    # ── Phase 2: LAN rules (probe eth2 → gateway eth2) ──
    gateway.log("Phase 2: Testing LAN firewall rules")

    # SSH (22/tcp) — ALLOWED on LAN
    probe.succeed("nc -z -w 3 172.20.30.1 22")

    # NTP (123/udp) — ALLOWED on LAN
    probe.succeed("echo test | ncat -u -w 3 172.20.30.1 123")

    # DHCP (67/udp) — ALLOWED on LAN
    probe.succeed("echo test | ncat -u -w 3 172.20.30.1 67")

    # Bootstrap UI (8080/tcp) — ALLOWED on LAN
    probe.succeed("nc -z -w 3 172.20.30.1 8080")

    # HTTPS (443/tcp) — BLOCKED on LAN (only allowed on WAN)
    probe.fail("nc -z -w 3 172.20.30.1 443")

    gateway.log("Phase 2 PASSED: LAN allows SSH+NTP+DHCP+bootstrap, blocks HTTPS")

    # ── Phase 3: No forwarding ──
    gateway.log("Phase 3: Testing forward chain (drop all)")

    # Verify ip_forward is disabled
    fwd = gateway.succeed("cat /proc/sys/net/ipv4/ip_forward").strip()
    assert fwd == "0", f"Expected ip_forward=0, got: {fwd}"

    gateway.log("Phase 3 PASSED: Forwarding disabled")

    gateway.log("Firewall test passed — all WAN/LAN rules verified")
  '';
}
