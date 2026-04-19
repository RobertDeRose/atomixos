# NixOS test: verify os-verification service confirms a RAUC slot after
# successful health checks.
#
# This test:
# 1. Boots a QEMU VM with RAUC + dnsmasq + chronyd + two network interfaces
# 2. Creates /persist/.completed_first_boot so the service condition is met
# 3. Starts the os-verification service (slot is pending on fresh boot)
# 4. Verifies the slot transitions to "good" after health checks pass
#
# No health manifest is provided, so container checks are skipped.
# Only imports rauc.nix + hardware-qemu.nix — no podman/cockpit/traefik.
#
# Run:  nix build .#checks.aarch64-linux.rauc-confirm
{
  pkgs,
  hostPkgs ? pkgs,
  self,
  raucModule,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };

  # The os-verification script — same source as modules/os-verification.nix
  verificationScript = pkgs.writeShellScript "os-verification" (
    builtins.readFile ../../scripts/os-verification.sh
  );
in
nixos-lib.runTest {
  name = "rauc-confirm";

  inherit hostPkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [
        raucModule
        qemuModule
      ];

      virtualisation = {
        emptyDiskImages = [
          128 # vdb — boot slot A
          128 # vdc — boot slot B
          1024 # vdd — rootfs slot A
          1024 # vde — rootfs slot B
        ];
        memorySize = 1024;
        diskSize = 2048;
      };

      system.stateVersion = "25.11";
      environment.systemPackages = [
        pkgs.rauc
        pkgs.jq
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];
      atomixos.rauc.statusFile = "/tmp/rauc.status";

      # ── Network: eth1 dummy created at test time ──
      # eth0 is provided by the NixOS test VLAN (gets DHCP automatically).
      # eth1 is created as a dummy in the test script with the static LAN IP.
      # This avoids race conditions between netdev creation and dnsmasq startup.

      # ── dnsmasq ──
      # The os-verification script checks `systemctl is-active dnsmasq.service`.
      # Bind to loopback so it starts reliably. eth1 is created later in test.
      services.dnsmasq = {
        enable = true;
        settings = {
          listen-address = "127.0.0.1";
          bind-interfaces = true;
          no-resolv = true;
          no-dhcp-interface = "lo";
        };
      };

      # ── Chrony ──
      # The os-verification script checks `systemctl is-active chronyd.service`.
      services.chrony = {
        enable = true;
        extraConfig = ''
          local stratum 10
        '';
      };

      # ── os-verification service ──
      # Replicated from modules/os-verification.nix but without podman
      # dependency (no health manifest → podman is never called).
      systemd.services.os-verification = {
        description = "OS update verification - local health check";
        after = [
          "multi-user.target"
          "network-online.target"
          "dnsmasq.service"
          "chronyd.service"
        ];
        wants = [ "network-online.target" ];
        # Do NOT add wantedBy — we start it manually in the test script
        # so we can set up preconditions first.

        unitConfig.ConditionPathExists = "/persist/.completed_first_boot";

        path = [
          pkgs.rauc
          pkgs.jq
          pkgs.systemd
          pkgs.iproute2
          pkgs.gnugrep
        ];

        serviceConfig = {
          Type = "oneshot";
          ExecStart = verificationScript;
          RemainAfterExit = true;
          TimeoutStartSec = 600;
        };
      };

      # ── /persist tmpfs ──
      # The real device has /persist on f2fs. For the test, a tmpfs suffices.
      systemd.tmpfiles.rules = [
        "d /persist 0755 root root -"
      ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("rauc.service")

    # ── Preconditions ──

    # 1. Create the first-boot sentinel so os-verification's condition passes
    gateway.succeed("date -Iseconds > /persist/.completed_first_boot")

    # 2. Set up eth1 with the LAN IP the os-verification script expects.
    #    eth1 exists from the NixOS test infra but has no IP.
    #    If it doesn't exist, create a dummy (e.g., single-VLAN setup).
    gateway.succeed("ip link add eth1 type dummy 2>/dev/null || true")
    gateway.succeed("ip addr flush dev eth1")
    gateway.succeed("ip addr add 172.20.30.1/24 dev eth1")
    gateway.succeed("ip link set eth1 up")

    # 3. Verify dnsmasq and chronyd are running
    gateway.wait_for_unit("dnsmasq.service")
    gateway.wait_for_unit("chronyd.service")

    # 4. Verify network interfaces have correct IPs
    #    eth0 gets DHCP from test VLAN; eth1 has static 172.20.30.1
    gateway.succeed("ip -4 addr show eth0 | grep 'inet '")
    gateway.succeed("ip -4 addr show eth1 | grep '172.20.30.1'")

    # 5. Inspect initial RAUC state — fresh boot, no statusfile.
    status_json = gateway.succeed("rauc status --output-format=json 2>&1")
    gateway.log(f"Initial RAUC status: {status_json[:2000]}")

    # ── Run os-verification ──
    gateway.log("Starting os-verification service...")
    gateway.succeed("systemctl start os-verification.service")

    # ── Verify outcome ──
    # The script should have run health checks and called `rauc status mark-good`.
    state_after = gateway.succeed("cat /var/lib/rauc/state.A").strip()
    assert state_after == "good", f"Expected state=good after verification, got: {state_after}"

    # Verify the service completed successfully (RemainAfterExit=true)
    gateway.succeed("systemctl is-active os-verification.service")

    # Verify RAUC now reports the slot as good
    status_after = gateway.succeed("rauc status --output-format=json 2>&1")
    gateway.log(f"Final RAUC status: {status_after[:2000]}")

    gateway.log("os-verification confirmation test passed — slot marked good after health checks")
  '';
}
