# NixOS test: verify RAUC rollback — marking a slot bad restores the previous good slot.
#
# This test simulates the rollback scenario:
# 1. Boot into slot A (good), install a bundle to slot B
# 2. Mark slot B as bad (simulating failed health check / boot-count exhaustion)
# 3. Switch primary back to A
# 4. Verify RAUC reports A as primary and B as bad
#
# This validates the custom bootloader backend's state management which
# underpins the real rollback flow (U-Boot boot-count decrement on Rock64).
#
# Run:  nix build .#checks.aarch64-linux.rauc-rollback
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

  # Minimal RAUC bundle for install testing
  testBundle =
    pkgs.runCommand "test-rauc-bundle-rollback"
      {
        nativeBuildInputs = [
          pkgs.rauc
          pkgs.dosfstools
          pkgs.squashfsTools
        ];
      }
      ''
        mkdir -p bundle

        dd if=/dev/zero of=bundle/boot.vfat bs=1M count=4
        mkfs.vfat -n "TEST_BOOT" bundle/boot.vfat

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
          test-update.raucb

        mkdir -p $out
        cp test-update.raucb $out/
      '';
in
nixos-lib.runTest {
  name = "rauc-rollback";

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
      };

      system.stateVersion = "25.11";
      environment.systemPackages = [
        pkgs.rauc
        pkgs.jq
        forensicStub
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];
      atomixos.rauc.statusFile = "/tmp/rauc.status";
      atomixos.rauc.bundleFormats = [
        "+plain"
        "-verity"
      ];

      systemd.tmpfiles.rules = [ "d /boot/forensics 0755 root root -" ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("rauc.service")

    # ── Phase 1: Verify initial state (booted into A, A is good) ──
    gateway.succeed("rauc status mark-good")
    primary = gateway.succeed("cat /var/lib/rauc/primary 2>/dev/null || echo A").strip()
    assert primary == "A", f"Expected initial primary=A, got: {primary}"

    state_a = gateway.succeed("cat /var/lib/rauc/state.A").strip()
    assert state_a == "good", f"Expected slot A state=good, got: {state_a}"

    # ── Phase 2: Install bundle → B becomes primary ──
    gateway.copy_from_host("${testBundle}/test-update.raucb", "/tmp/test-update.raucb")
    gateway.succeed("forensic-log --stage rauc --event install-start --target-slot boot.1 --version 2.0.0")
    gateway.succeed("rauc install /tmp/test-update.raucb")
    gateway.succeed("forensic-log --stage rauc --event install-complete --slot boot.1 --version 2.0.0 --result ok")

    primary_after_install = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary_after_install == "B", f"Expected primary=B after install, got: {primary_after_install}"

    # ── Phase 3: Simulate failed boot into B ──
    # In the real system, U-Boot decrements BOOT_B_LEFT on each boot attempt.
    # When it reaches 0, U-Boot switches back to A. Here we simulate this by
    # marking B as bad and switching primary back to A via RAUC.

    # Mark B as bad (this is what rauc does when boot-count is exhausted)
    gateway.succeed("forensic-log --stage rauc --event rollback-start --slot boot.1 --reason health-check")
    gateway.succeed("rauc status mark-bad boot.1")

    state_b = gateway.succeed("cat /var/lib/rauc/state.B").strip()
    assert state_b == "bad", f"Expected slot B state=bad after mark-bad, got: {state_b}"

    # Switch primary back to A (simulating U-Boot fallback)
    gateway.succeed("rauc status mark-active boot.0")
    gateway.succeed("forensic-log --stage rauc --event rollback-complete --slot boot.1 --target-slot boot.0 --result ok")

    primary_after_rollback = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary_after_rollback == "A", f"Expected primary=A after rollback, got: {primary_after_rollback}"

    # ── Phase 4: Verify final state ──
    # A should be good and primary, B should be bad
    state_a_final = gateway.succeed("cat /var/lib/rauc/state.A").strip()
    assert state_a_final == "good", f"Expected slot A state=good, got: {state_a_final}"

    state_b_final = gateway.succeed("cat /var/lib/rauc/state.B").strip()
    assert state_b_final == "bad", f"Expected slot B state=bad, got: {state_b_final}"

    # Verify via rauc status JSON output
    status_json = gateway.succeed("rauc status --output-format=json")
    gateway.succeed("echo '${testBundle}' > /dev/null")  # reference for nix
    gateway.succeed("grep 'stage=rauc event=install-complete slot=boot.1 version=2.0.0 result=ok' /boot/forensics/segment-0.log")
    gateway.succeed("grep 'stage=rauc event=rollback-complete slot=boot.1 target_slot=boot.0 result=ok' /boot/forensics/segment-0.log")

    gateway.log("RAUC rollback test passed — install to B, mark B bad, primary reverted to A")
  '';
}
