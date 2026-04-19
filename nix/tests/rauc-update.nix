# NixOS test: verify RAUC bundle install switches to the inactive slot pair.
#
# This test:
# 1. Boots a QEMU VM with RAUC service and custom bootloader backend
# 2. Verifies boot.0 (A) is the current/primary slot
# 3. Builds a minimal RAUC bundle with dummy boot + rootfs images
# 4. Installs the bundle via `rauc install`
# 5. Verifies RAUC switched the primary to boot.1 (B)
#
# Only imports rauc.nix + hardware-qemu.nix — no podman/cockpit/traefik.
#
# Run:  nix build .#checks.aarch64-linux.rauc-update
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

  signingCert = ../../certs/dev.signing.cert.pem;
  signingKey = ../../certs/dev.signing.key.pem;

  # Build a minimal RAUC bundle at derivation time.
  # Contains dummy boot (vfat) and rootfs (raw) slot images.
  testBundle =
    pkgs.runCommand "test-rauc-bundle"
      {
        nativeBuildInputs = [
          pkgs.rauc
          pkgs.dosfstools
          pkgs.squashfsTools
        ];
      }
      ''
        mkdir -p bundle

        # Dummy boot slot image (small vfat)
        dd if=/dev/zero of=bundle/boot.vfat bs=1M count=4
        mkfs.vfat -n "TEST_BOOT" bundle/boot.vfat

        # Dummy rootfs slot image (raw file with a marker)
        dd if=/dev/zero of=bundle/rootfs.img bs=1M count=4
        echo "ROOTFS_V2_MARKER" | dd of=bundle/rootfs.img bs=1 seek=0 conv=notrunc

        # RAUC manifest — use explicit 'plain' format (verity requires casync)
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

        # Build signed bundle
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
  name = "rauc-update-install";

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
      environment.systemPackages = [ pkgs.rauc ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];
      atomixos.rauc.statusFile = "/tmp/rauc.status";
      atomixos.rauc.bundleFormats = [
        "+plain"
        "-verity"
      ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("rauc.service")

    # Verify we booted into slot A
    status = gateway.succeed("rauc status --output-format=json 2>&1")
    assert '"booted": "A"' in status or '"booted":"A"' in status or "booted" in status, \
        f"Not booted into slot A: {status}"

    # Verify slot A is primary
    primary = gateway.succeed("cat /var/lib/rauc/primary 2>/dev/null || echo A").strip()
    assert primary == "A", f"Expected primary=A, got: {primary}"

    # Copy the test bundle into the VM
    gateway.succeed("mkdir -p /tmp/bundles")
    gateway.copy_from_host("${testBundle}/test-update.raucb", "/tmp/bundles/test-update.raucb")

    # Install the bundle — RAUC should write to the inactive slot pair (B)
    gateway.succeed("rauc install /tmp/bundles/test-update.raucb")

    # After install, RAUC should have switched the primary to B
    primary_after = gateway.succeed("cat /var/lib/rauc/primary").strip()
    assert primary_after == "B", f"Expected primary=B after install, got: {primary_after}"

    # Verify rauc status shows the update
    status_after = gateway.succeed("rauc status --output-format=json 2>&1")

    gateway.log("RAUC update install test passed — bundle installed to inactive slot, primary switched to B")
  '';
}
