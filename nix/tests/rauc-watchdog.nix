# NixOS test: verify watchdog + boot-count rollback mechanism.
#
# This test verifies:
# 1. i6300esb watchdog device is present and systemd is kicking it
# 2. Boot-count decrement service correctly counts down on each boot
# 3. When boot count exhausts, primary rolls back and failed slot is marked bad
#
# The crash()/start() pattern simulates what happens after a watchdog reset:
# the VM loses power and reboots. The qcow2 overlay persists across restarts,
# so /var/lib/rauc state is preserved (just like real eMMC storage).
#
# We verify the watchdog infrastructure is armed (device present, systemd
# kicking) but use crash() to simulate the reboot rather than waiting for
# the actual watchdog to fire — this keeps the test fast and deterministic.
#
# A boot-count-decrement systemd service runs on each boot to simulate
# the U-Boot boot-count mechanism that the real hardware uses.
#
# Only imports rauc.nix + hardware-qemu.nix — no podman/cockpit/traefik.
#
# Run:  nix build .#checks.aarch64-linux.rauc-watchdog
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
  forensicStub = pkgs.writeShellScriptBin "forensic-log" ''
    set -euo pipefail
    segment_dir=/boot/forensics
    mkdir -p "$segment_dir"
    if [ ! -f "$segment_dir/meta" ]; then
      printf '%s\n' "format=v1" > "$segment_dir/meta"
    fi
    if [ ! -f "$segment_dir/segment-0.log" ]; then
      : > "$segment_dir/segment-0.log"
    fi

    record=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --stage|--event|--slot|--result|--reason|--target-slot|--version|--device|--service|--attempt|--detail)
          key=$(printf '%s' "$1" | sed 's/^--//' | tr '-' '_')
          value="$2"
          if [ -n "$record" ]; then
            record="$record "
          fi
          record="$record$key=$value"
          shift 2
          ;;
        *)
          shift
          ;;
      esac
    done

    printf '%s\n' "$record" >> "$segment_dir/segment-0.log"
  '';

  signingCert = ../../certs/dev.signing.cert.pem;
  signingKey = ../../certs/dev.signing.key.pem;

  # Small test bundle — just needs to be installable, size doesn't matter here
  testBundle =
    pkgs.runCommand "test-rauc-bundle-watchdog"
      {
        nativeBuildInputs = [
          pkgs.rauc
          pkgs.dosfstools
          pkgs.squashfsTools
        ];
      }
      ''
        mkdir -p bundle

        # Minimal dummy boot slot (4 MB vfat)
        dd if=/dev/zero of=bundle/boot.vfat bs=1M count=4
        mkfs.vfat -n "TEST_BOOT" bundle/boot.vfat

        # Minimal dummy rootfs (4 MB raw)
        dd if=/dev/zero of=bundle/rootfs.img bs=1M count=4

        cat > bundle/manifest.raucm <<'EOF'
        [update]
        compatible=rock64
        version=2.0.0

        [bundle]
        format=plain

        [image.boot]
        filename=boot.vfat

        [image.rootfs]
        filename=rootfs.img
        EOF

        rauc bundle \
          --cert=${signingCert} \
          --key=${signingKey} \
          bundle/ \
          test-watchdog.raucb

        mkdir -p $out
        cp test-watchdog.raucb $out/
      '';
in
nixos-lib.runTest {
  name = "rauc-watchdog-rollback";

  inherit hostPkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [
        raucModule
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
        memorySize = 1024;
        diskSize = 2048;
        qemu.options = [
          "-device"
          "i6300esb"
        ];
      };

      system.stateVersion = "25.11";
      environment.systemPackages = [
        pkgs.rauc
        forensicStub
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];
      boot.kernelModules = [ "i6300esb" ];
      atomixos.rauc.statusFile = "/tmp/rauc.status";
      atomixos.rauc.bundleFormats = [
        "+plain"
        "-verity"
      ];

      systemd.tmpfiles.rules = [ "d /boot/forensics 0755 root root -" ];

      # Use a short watchdog timeout to speed up the test.
      # 10s runtime means systemd kicks every ~5s; if frozen, the
      # hardware watchdog fires after 10s and QEMU resets the VM.
      systemd.settings.Manager = {
        RuntimeWatchdogSec = lib.mkForce "10s";
        RebootWatchdogSec = lib.mkForce "1min";
      };

      # Boot-count decrement service — simulates U-Boot's BOOT_B_LEFT logic.
      # On each boot: if a boot-count file exists for the current primary,
      # decrement it. If it reaches 0, roll back to the other slot and mark
      # the failed slot as bad.
      systemd.services.boot-count-decrement = {
        description = "Decrement RAUC boot count (simulates U-Boot)";
        wantedBy = [ "multi-user.target" ];
        before = [ "rauc.service" ];
        path = [
          pkgs.coreutils
          forensicStub
        ];
        serviceConfig.Type = "oneshot";
        script = ''
          STATE_DIR="/var/lib/rauc"
          mkdir -p "$STATE_DIR"

          PRIMARY=$(cat "$STATE_DIR/primary" 2>/dev/null || echo "A")
          COUNT_FILE="$STATE_DIR/boot-count.$PRIMARY"

          if [ ! -f "$COUNT_FILE" ]; then
            echo "boot-count-decrement: no boot count for $PRIMARY, skipping"
            exit 0
          fi

          COUNT=$(cat "$COUNT_FILE")
          echo "boot-count-decrement: $PRIMARY count=$COUNT"

          NEW_COUNT=$((COUNT - 1))
          forensic-log --stage watchdog --event boot-count-decrement --detail "$PRIMARY:$NEW_COUNT"

          if [ "$NEW_COUNT" -le 0 ]; then
            echo "boot-count-decrement: count exhausted, rolling back from $PRIMARY"
            if [ "$PRIMARY" = "B" ]; then
              FAILED_SLOT="boot.1"
              TARGET_SLOT="boot.0"
            else
              FAILED_SLOT="boot.0"
              TARGET_SLOT="boot.1"
            fi
            forensic-log --stage watchdog --event rollback-triggered --slot "$FAILED_SLOT" --target-slot "$TARGET_SLOT" --reason boot-count-exhausted
            # Roll back to the other slot
            if [ "$PRIMARY" = "B" ]; then
              echo "A" > "$STATE_DIR/primary"
            else
              echo "B" > "$STATE_DIR/primary"
            fi
            echo "bad" > "$STATE_DIR/state.$PRIMARY"
            rm -f "$COUNT_FILE"
            forensic-log --stage rauc --event rollback-complete --slot "$FAILED_SLOT" --target-slot "$TARGET_SLOT" --result ok
            echo "boot-count-decrement: rollback complete"
          else
            echo "$NEW_COUNT" > "$COUNT_FILE"
            echo "boot-count-decrement: decremented to $NEW_COUNT"
          fi
        '';
      };
    };

  testScript = ''
    # Phase 1: Boot and verify watchdog infrastructure.
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("rauc.service")

    # Verify i6300esb watchdog device is present and the kernel module loaded
    gateway.succeed("test -c /dev/watchdog")
    gateway.succeed("lsmod | grep i6300esb")
    gateway.log("Watchdog device /dev/watchdog confirmed present (i6300esb)")

    # Verify systemd is actively kicking the watchdog
    gateway.succeed("systemctl show -p RuntimeWatchdogUSec | grep -q 10s")
    gateway.log("Confirmed: systemd RuntimeWatchdogUSec=10s")

    gateway.succeed("rauc status mark-good")
    primary = gateway.succeed("cat /var/lib/rauc/primary 2>/dev/null || echo A").strip()
    assert primary == "A", f"Expected primary=A, got: {primary}"
    gateway.log("Phase 1: Watchdog armed, A is primary and good")

    # Phase 2: Install bundle to slot B, set B as primary with boot count
    gateway.succeed("mkdir -p /tmp/bundles")
    gateway.copy_from_host(
        "${testBundle}/test-watchdog.raucb",
        "/tmp/bundles/test-watchdog.raucb",
    )
    gateway.succeed("forensic-log --stage rauc --event install-start --target-slot boot.1 --version 2.0.0")
    gateway.succeed("rauc install /tmp/bundles/test-watchdog.raucb")
    gateway.succeed("forensic-log --stage rauc --event install-complete --slot boot.1 --version 2.0.0 --result ok")

    primary = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary == "B", f"Expected primary=B after install, got: {primary}"

    # Set boot count — the decrement service will count down from 2.
    # After 2 reboots (2 -> 1, 1 -> 0), the rollback triggers.
    gateway.succeed("echo 2 > /var/lib/rauc/boot-count.B")
    gateway.log("Phase 2: Bundle installed, B is primary, boot-count.B=2")

    # Phase 3: First simulated watchdog reboot.
    # crash() simulates what happens when the watchdog fires: sudden power
    # loss followed by restart. The qcow2 overlay persists, preserving
    # /var/lib/rauc state across the restart (same as real eMMC).
    # Sync first — crash() sends QEMU 'quit' which may lose unflushed
    # writeback cache. On real hardware the boot-count is in U-Boot env
    # at a raw eMMC offset (not in a filesystem cache), so this is fine.
    gateway.log("Phase 3: Simulating watchdog reboot 1")
    gateway.succeed("sync")
    gateway.crash()
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.log("VM restarted after simulated watchdog reboot 1")

    # Boot-count should have decremented from 2 to 1
    count = gateway.succeed("cat /var/lib/rauc/boot-count.B").strip()
    assert count == "1", f"Expected boot-count.B=1 after first reboot, got: {count}"
    primary = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary == "B", f"Expected primary still B after first reboot, got: {primary}"
    gateway.succeed("grep 'stage=watchdog event=boot-count-decrement detail=B:1' /boot/forensics/segment-0.log")
    gateway.log(f"After reboot 1: primary={primary}, boot-count.B={count}")

    # Phase 4: Second simulated watchdog reboot — this exhausts the count.
    gateway.log("Phase 4: Simulating watchdog reboot 2 (count will exhaust)")
    gateway.succeed("sync")
    gateway.crash()
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.log("VM restarted after simulated watchdog reboot 2")

    # Boot-count file should be gone (removed after rollback)
    gateway.fail("test -f /var/lib/rauc/boot-count.B")

    # Primary should have rolled back to A
    primary = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary == "A", f"Expected rollback to A, got: {primary}"

    # Slot B should be marked bad
    state_b = gateway.succeed("cat /var/lib/rauc/state.B").strip()
    assert state_b == "bad", f"Expected state.B=bad, got: {state_b}"

    # Slot A should still be good
    state_a = gateway.succeed("cat /var/lib/rauc/state.A").strip()
    assert state_a == "good", f"Expected state.A=good, got: {state_a}"

    gateway.succeed("grep 'stage=watchdog event=rollback-triggered slot=boot.1 target_slot=boot.0 reason=boot-count-exhausted' /boot/forensics/segment-0.log")
    gateway.succeed("grep 'stage=rauc event=rollback-complete slot=boot.1 target_slot=boot.0 result=ok' /boot/forensics/segment-0.log")

    gateway.log("Watchdog rollback test passed — B exhausted boot count, rolled back to A")
  '';
}
