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

  # Custom bootloader backend script for QEMU/test environments.
  # Simulates U-Boot boot selection using plain files instead of
  # fw_setenv/fw_printenv. Modelled after the upstream NixOS RAUC test.
  #
  # RAUC calls this with: get-primary, set-primary <bootname>,
  # get-state <bootname>, set-state <bootname> <state>, get-current.
  # Bootnames are "A" and "B" (matching bootname= in system.conf).
  customBackendScript = pkgs.writeShellScript "rauc-custom-backend" ''
    STATE_DIR="/var/lib/rauc"
    mkdir -p "$STATE_DIR"

    case "$1" in
      get-primary)
        cat "$STATE_DIR/primary" 2>/dev/null || echo "A"
        ;;
      set-primary)
        echo "$2" > "$STATE_DIR/primary"
        ;;
      get-state)
        cat "$STATE_DIR/state.$2" 2>/dev/null || echo "good"
        ;;
      set-state)
        echo "$3" > "$STATE_DIR/state.$2"
        ;;
      get-current)
        cat "$STATE_DIR/booted" 2>/dev/null || echo "A"
        ;;
      *)
        exit 1
        ;;
    esac
  '';

  # Build the optional [handlers] section
  handlersSection = lib.optionalString (cfg.bootloader == "custom") ''

    [handlers]
    bootloader-custom-backend=${customBackendScript}
  '';
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
      ${handlersSection}
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
