# NixOS test: verify SSH-on-WAN toggle via flag file.
#
# This test:
# 1. Boots gateway with firewall — SSH on WAN is blocked by default
# 2. Creates /persist/config/ssh-wan-enabled flag file
# 3. Runs ssh-wan-reload service, verifies SSH now reachable on WAN
# 4. Removes the flag file, reloads again, verifies SSH blocked again
#
# Uses multi-node NixOS test with WAN probe on VLAN 1.
#
# Run:  nix build .#checks.aarch64-linux.ssh-wan-toggle
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
  name = "ssh-wan-toggle";

  hostPkgs = pkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [ firewallModule ];

      virtualisation = {
        vlans = [ 1 ];
        memorySize = 512;
      };

      system.stateVersion = "25.11";

      # Rename test interface to eth0 (WAN) to match firewall rules
      services.udev.extraRules = ''
        SUBSYSTEM=="net", ACTION=="add", ATTR{address}=="52:54:00:12:01:*", NAME="eth0"
      '';

      networking.useDHCP = false;
      networking.interfaces.eth0.ipv4.addresses = [
        {
          address = "192.168.1.1";
          prefixLength = 24;
        }
      ];

      # /persist for ssh-wan-toggle flag file
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
        "d /persist/config 0755 root root -"
      ];

      environment.systemPackages = [
        pkgs.nftables
        pkgs.gawk
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

    # Start an SSH listener on the gateway for probing
    gateway.succeed("nc -l -k 22 >/dev/null 2>&1 &")

    import time
    time.sleep(1)

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
    wan.succeed("nc -z -w 3 192.168.1.1 22")

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
