# RAUC A/B update system configuration.
# Defines slot pairs and U-Boot bootloader backend.
# Slot device paths are configurable via options — each hardware module
# (Rock64, QEMU) provides its own device paths.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  cfg = config.atomixos.rauc;
in
{
  # ── Options ─────────────────────────────────────────────────────────────────

  options.atomixos.rauc = {
    compatible = lib.mkOption {
      type = lib.types.str;
      default = "rock64";
      description = "RAUC compatible string — must match the bundle manifest.";
    };

    bootloader = lib.mkOption {
      type = lib.types.str;
      default = "uboot";
      description = "RAUC bootloader backend (uboot, custom, etc).";
    };

    statusFile = lib.mkOption {
      type = lib.types.str;
      default = "/persist/rauc/status.raucs";
      description = "Path to the RAUC status file.";
    };

    slots = {
      boot0 = lib.mkOption {
        type = lib.types.str;
        description = "Block device for boot slot A.";
      };
      boot1 = lib.mkOption {
        type = lib.types.str;
        description = "Block device for boot slot B.";
      };
      rootfs0 = lib.mkOption {
        type = lib.types.str;
        description = "Block device for rootfs slot A.";
      };
      rootfs1 = lib.mkOption {
        type = lib.types.str;
        description = "Block device for rootfs slot B.";
      };
    };
  };

  # ── Configuration ───────────────────────────────────────────────────────────

  config = {
    environment.systemPackages = [ pkgs.rauc ];

    # RAUC system configuration
    # This defines the slot layout and bootloader integration
    environment.etc."rauc/system.conf".text = ''
      [system]
      compatible=${cfg.compatible}
      bootloader=${cfg.bootloader}
      statusfile=${cfg.statusFile}

      [keyring]
      path=/etc/rauc/ca.cert.pem

      [slot.boot.0]
      device=${cfg.slots.boot0}
      type=vfat
      bootname=A

      [slot.rootfs.0]
      device=${cfg.slots.rootfs0}
      type=raw
      parent=boot.0

      [slot.boot.1]
      device=${cfg.slots.boot1}
      type=vfat
      bootname=B

      [slot.rootfs.1]
      device=${cfg.slots.rootfs1}
      type=raw
      parent=boot.1
    '';

    # CA certificate for bundle verification
    # Uses the development CA by default. Production devices override this
    # with a production CA cert provisioned separately.
    environment.etc."rauc/ca.cert.pem".source = ../certs/dev.ca.cert.pem;
  };
}
