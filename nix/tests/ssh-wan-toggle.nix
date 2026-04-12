# NixOS test: verify SSH-on-WAN toggle via flag file.
#
# This test:
# 1. Boots gateway with firewall — SSH on WAN is blocked by default
# 2. Creates /persist/config/ssh-wan-enabled flag file
# 3. Runs ssh-wan-reload service, verifies SSH now reachable on WAN
# 4. Removes the flag file, reloads again, verifies SSH blocked again
#
# NixOS test VMs always have eth0 as a management backdoor.  VLAN 1 becomes
# eth1.  We therefore define test-local nftables rules and toggle scripts
# that reference eth1 (the "WAN" interface inside the test VM) rather than
# importing the production firewall.nix which hard-codes eth0/eth1 for
# WAN/LAN.
#
# Run:  nix build .#checks.aarch64-linux.ssh-wan-toggle
{
  pkgs,
  hostPkgs ? pkgs,
  self,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };

  # Test-local scripts that reference eth1 (the VLAN 1 / "WAN" interface
  # inside the test VM) instead of eth0 (production WAN interface).
  sshWanToggle = pkgs.writeShellScript "ssh-wan-toggle-test" ''
    set -euo pipefail
    if [ -f /persist/config/ssh-wan-enabled ]; then
      echo "SSH-on-WAN flag detected, adding firewall rule"
      nft add rule inet filter input iifname "eth1" tcp dport 22 accept comment \"SSH-WAN-dynamic\"
    else
      echo "SSH-on-WAN flag not present, SSH on WAN remains blocked"
    fi
  '';

  sshWanReload = pkgs.writeShellScript "ssh-wan-reload-test" ''
    set -euo pipefail
    # Remove any existing dynamic SSH rule (grep may find nothing — that's OK)
    HANDLE=$(nft -a list chain inet filter input 2>/dev/null \
      | grep 'SSH-WAN-dynamic' | awk '{print $NF}' || true)
    if [ -n "$HANDLE" ]; then
      nft delete rule inet filter input handle "$HANDLE"
    fi
    # Re-add if flag exists
    if [ -f /persist/config/ssh-wan-enabled ]; then
      echo "Re-adding SSH-on-WAN rule"
      nft add rule inet filter input iifname "eth1" tcp dport 22 accept comment \"SSH-WAN-dynamic\"
    else
      echo "SSH-on-WAN disabled"
    fi
  '';
in
nixos-lib.runTest {
  name = "ssh-wan-toggle";

  inherit hostPkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      virtualisation = {
        vlans = [ 1 ];
        memorySize = 512;
      };

      system.stateVersion = "25.11";

      # -- Networking: eth1 = VLAN 1 ("WAN" in test topology) ----------------
      networking.useDHCP = false;
      networking.interfaces.eth1.ipv4.addresses = [
        {
          address = "192.168.1.1";
          prefixLength = 24;
        }
      ];

      # -- Minimal nftables matching production firewall structure ------------
      # Uses eth1 as WAN (the VLAN interface in the test VM).
      networking.firewall.enable = false;
      networking.nftables.enable = true;
      networking.nftables.tables.filter = {
        family = "inet";
        content = ''
          chain input {
            type filter hook input priority 0; policy drop;
            iif "lo" accept
            ct state established,related accept

            # Allow the NixOS test driver backdoor on eth0
            iifname "eth0" accept

            # WAN (eth1 in test VM) — only HTTPS + OpenVPN
            iifname "eth1" tcp dport 443 accept   comment "HTTPS"
            iifname "eth1" udp dport 1194 accept  comment "OpenVPN"

            # SSH on WAN is NOT allowed by default — toggle adds it here
          }

          chain forward {
            type filter hook forward priority 0; policy drop;
          }

          chain output {
            type filter hook output priority 0; policy accept;
          }
        '';
      };

      # -- /persist for flag file --------------------------------------------
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
        "d /persist/config 0755 root root -"
      ];

      # -- SSH-WAN toggle services (test-local, using eth1) ------------------
      systemd.services.ssh-wan-toggle = {
        description = "Toggle SSH access on WAN based on flag file";
        after = [
          "nftables.service"
          "network-online.target"
        ];
        wants = [
          "nftables.service"
          "network-online.target"
        ];
        wantedBy = [ "multi-user.target" ];
        path = [ pkgs.nftables ];
        serviceConfig = {
          Type = "oneshot";
          RemainAfterExit = true;
          ExecStart = sshWanToggle;
        };
      };

      systemd.services.ssh-wan-reload = {
        description = "Reload SSH-on-WAN firewall rule";
        after = [ "ssh-wan-toggle.service" ];
        path = [
          pkgs.nftables
          pkgs.gawk
        ];
        serviceConfig = {
          Type = "oneshot";
          ExecStart = sshWanReload;
        };
      };

      environment.systemPackages = [
        pkgs.nftables
        pkgs.gawk
        pkgs.nmap
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
      environment.systemPackages = [ pkgs.netcat ];
    };

  testScript = ''
    gateway.start()
    wan.start()

    gateway.wait_for_unit("multi-user.target")
    wan.wait_for_unit("multi-user.target")

    gateway.wait_for_unit("nftables.service")
    gateway.wait_for_unit("ssh-wan-toggle.service")

    # Start a TCP listener on port 22 for probing
    # Use ncat from nmap which reliably supports -k (keep-alive) mode
    gateway.succeed("ncat -lk 22 >/dev/null 2>&1 &")
    import time
    time.sleep(2)
    # Verify the listener is actually running
    gateway.succeed("ss -tlnp | grep ':22'")

    # ── Phase 1: SSH blocked on WAN by default ──
    gateway.log("Phase 1: SSH should be BLOCKED on WAN (no flag file)")

    wan.fail("nc -z -w 3 192.168.1.1 22")

    # Verify no SSH-WAN-dynamic rule in nftables
    gateway.fail("nft list chain inet filter input | grep 'SSH-WAN-dynamic'")

    gateway.log("Phase 1 PASSED: SSH blocked on WAN")

    # ── Phase 2: Enable SSH on WAN ──
    gateway.log("Phase 2: Enabling SSH on WAN via flag file")

    gateway.succeed("touch /persist/config/ssh-wan-enabled")
    gateway.succeed("systemctl start ssh-wan-reload.service")

    # Verify the dynamic rule was added
    gateway.succeed("nft list chain inet filter input | grep 'SSH-WAN-dynamic'")

    # SSH should now be reachable from WAN
    wan.succeed("nc -z -w 5 192.168.1.1 22")

    gateway.log("Phase 2 PASSED: SSH reachable on WAN after flag enabled")

    # ── Phase 3: Disable SSH on WAN ──
    gateway.log("Phase 3: Disabling SSH on WAN by removing flag file")

    gateway.succeed("rm /persist/config/ssh-wan-enabled")
    gateway.succeed("systemctl start ssh-wan-reload.service")

    # Verify the dynamic rule was removed
    gateway.fail("nft list chain inet filter input | grep 'SSH-WAN-dynamic'")

    # SSH should be blocked again
    wan.fail("nc -z -w 3 192.168.1.1 22")

    gateway.log("Phase 3 PASSED: SSH blocked on WAN after flag removed")

    gateway.log("SSH-on-WAN toggle test passed — enable/disable cycle verified")
  '';
}
