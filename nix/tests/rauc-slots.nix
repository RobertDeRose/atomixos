# NixOS test: verify RAUC slot logic with virtual block devices in QEMU.
#
# This test boots a minimal QEMU VM with four extra virtio-blk disks
# representing the A/B slot pairs (boot-a, boot-b, rootfs-a, rootfs-b),
# then verifies that RAUC sees all four slots with the correct device paths.
#
# Only imports rauc.nix + hardware-qemu.nix — no podman/cockpit/traefik.
#
# Run:  nix build .#checks.aarch64-linux.rauc-slots
{
  pkgs,
  self,
  raucModule,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "rauc-slot-logic";

  hostPkgs = pkgs;

  nodes.gateway =
    { config, lib, ... }:
    {
      imports = [
        raucModule
        qemuModule
      ];

      virtualisation = {
        # Four extra virtio-blk disks for A/B slot pairs.
        # NixOS test infra creates these as qcow2 images automatically.
        emptyDiskImages = [
          128 # vdb — boot slot A (128 MB)
          128 # vdc — boot slot B (128 MB)
          1024 # vdd — rootfs slot A (1 GB)
          1024 # vde — rootfs slot B (1 GB)
        ];
        memorySize = 1024;
        diskSize = 2048;
      };

      # Minimal system — just enough for RAUC to work
      system.stateVersion = "25.11";
      environment.systemPackages = [ pkgs.rauc ];

      # Tell RAUC which slot is currently booted via kernel cmdline.
      # Without this, `rauc service` cannot determine slot states.
      boot.kernelParams = [ "rauc.slot=boot.0" ];

      # Status file directory — the default /persist doesn't exist in
      # the test VM, so override to a path that does.
      atomixos.rauc.statusFile = "/tmp/rauc.status";

      # RAUC D-Bus service — needed so `rauc status` can query slot info.
      # The upstream NixOS module (services.rauc) pulls in more than we need,
      # so we define a minimal systemd unit directly.
      systemd.services.rauc = {
        description = "RAUC slot management service";
        after = [ "dbus.service" ];
        wantedBy = [ "multi-user.target" ];
        serviceConfig = {
          Type = "dbus";
          BusName = "de.pengutronix.rauc";
          ExecStart = "${pkgs.rauc}/bin/rauc service --conf=/etc/rauc/system.conf";
        };
      };

      # D-Bus policy so RAUC can register on the system bus
      services.dbus.packages = [ pkgs.rauc ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    # Verify the four virtio block devices exist
    gateway.succeed("test -b /dev/vdb")  # boot slot A
    gateway.succeed("test -b /dev/vdc")  # boot slot B
    gateway.succeed("test -b /dev/vdd")  # rootfs slot A
    gateway.succeed("test -b /dev/vde")  # rootfs slot B

    # Verify RAUC system.conf is deployed
    gateway.succeed("test -f /etc/rauc/system.conf")

    # Check system.conf references our virtio devices
    conf = gateway.succeed("cat /etc/rauc/system.conf")
    assert "/dev/vdb" in conf, f"boot slot A device not in system.conf: {conf}"
    assert "/dev/vdc" in conf, f"boot slot B device not in system.conf: {conf}"
    assert "/dev/vdd" in conf, f"rootfs slot A device not in system.conf: {conf}"
    assert "/dev/vde" in conf, f"rootfs slot B device not in system.conf: {conf}"
    assert "compatible=rock64" in conf, f"compatible string missing: {conf}"
    assert "bootloader=custom" in conf, f"bootloader setting missing: {conf}"

    # Verify custom bootloader backend is configured
    assert "bootloader-custom-backend=" in conf, f"custom backend handler missing: {conf}"

    # Verify bootname labels and parent relationships
    assert "bootname=A" in conf, f"bootname A missing: {conf}"
    assert "bootname=B" in conf, f"bootname B missing: {conf}"
    assert "parent=boot.0" in conf, f"rootfs.0 parent missing: {conf}"
    assert "parent=boot.1" in conf, f"rootfs.1 parent missing: {conf}"

    # Verify RAUC CA certificate is deployed
    gateway.succeed("test -f /etc/rauc/ca.cert.pem")

    # Wait for the RAUC D-Bus service to be ready
    gateway.wait_for_unit("rauc.service")

    # Verify RAUC can parse system.conf and list slot information.
    # Disks are empty (no filesystems) so slots show as inactive — that's
    # expected. The point is RAUC recognizes the slot structure.
    status = gateway.succeed("rauc status 2>&1")

    assert "boot.0" in status, f"boot.0 slot not in rauc status: {status}"
    assert "boot.1" in status, f"boot.1 slot not in rauc status: {status}"
    assert "rootfs.0" in status, f"rootfs.0 slot not in rauc status: {status}"
    assert "rootfs.1" in status, f"rootfs.1 slot not in rauc status: {status}"

    assert "/dev/vdb" in status, f"vdb not in rauc status: {status}"
    assert "/dev/vdc" in status, f"vdc not in rauc status: {status}"
    assert "/dev/vdd" in status, f"vdd not in rauc status: {status}"
    assert "/dev/vde" in status, f"vde not in rauc status: {status}"

    # Verify custom bootloader backend works — mark-good should succeed
    # (this would fail with bootloader=uboot since fw_setenv is missing)
    gateway.succeed("rauc status mark-good")

    # Verify the slot was actually marked good via the custom backend
    slot_state = gateway.succeed("cat /var/lib/rauc/state.A 2>/dev/null || echo missing")
    assert "good" in slot_state, f"Slot A not marked good: {slot_state}"

    gateway.log("RAUC slot logic verification passed — all 4 slots detected with correct device paths")
  '';
}
