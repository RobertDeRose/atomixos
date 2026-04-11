# RAUC A/B update system configuration.
# Defines slot pairs and U-Boot bootloader backend.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── RAUC service ─────────────────────────────────────────────────────────────

  # Note: The RAUC NixOS module handles most of this, but we also need
  # to provide the system.conf for the slot definitions.

  environment.systemPackages = [ pkgs.rauc ];

  # RAUC system configuration
  # This defines the slot layout and bootloader integration
  environment.etc."rauc/system.conf".text = ''
    [system]
    compatible=rock64
    bootloader=uboot
    statusfile=/persist/rauc/status.raucs

    [keyring]
    path=/etc/rauc/ca.cert.pem

    [handlers]
    bootloader-custom-backend=noop

    [slot.boot.0]
    device=/dev/mmcblk1p1
    type=vfat
    bootname=A

    [slot.rootfs.0]
    device=/dev/mmcblk1p3
    type=raw
    bootname=A
    parent=boot.0

    [slot.boot.1]
    device=/dev/mmcblk1p2
    type=vfat
    bootname=B

    [slot.rootfs.1]
    device=/dev/mmcblk1p4
    type=raw
    bootname=B
    parent=boot.1
  '';

  # CA certificate for bundle verification
  # Uses the development CA by default. Production devices override this
  # with a production CA cert provisioned separately.
  environment.etc."rauc/ca.cert.pem".source = ../certs/dev.ca.cert.pem;
}
