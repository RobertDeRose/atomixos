# RAUC A/B update system configuration.
# Uses the upstream NixOS RAUC module (`services.rauc`) and keeps
# project-specific options under `atomixos.rauc`.
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
  # fw_setenv/fw_printenv.
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
in
{
  options.atomixos.rauc = {
    compatible = lib.mkOption {
      type = lib.types.str;
      default = "rock64";
      description = "RAUC compatible string. Must match the bundle manifest.";
    };

    bootloader = lib.mkOption {
      type = lib.types.enum [
        "barebox"
        "grub"
        "uboot"
        "efi"
        "custom"
        "noop"
      ];
      default = "uboot";
      description = "RAUC bootloader backend.";
    };

    # Keep this as a string because tests override it with /tmp paths.
    statusFile = lib.mkOption {
      type = lib.types.str;
      default = "/persist/rauc/status.raucs";
      description = "Path to the RAUC status file.";
    };

    bundleFormats = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [
        "-plain"
        "+verity"
      ];
      description = "Allowed RAUC bundle formats.";
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

  config = {
    services.rauc = {
      enable = true;
      client.enable = true;
      compatible = cfg.compatible;
      bootloader = cfg.bootloader;
      bundleFormats = cfg.bundleFormats;

      slots = {
        boot = [
          {
            enable = true;
            device = cfg.slots.boot0;
            type = "vfat";
            settings.bootname = "A";
          }
          {
            enable = true;
            device = cfg.slots.boot1;
            type = "vfat";
            settings.bootname = "B";
          }
        ];

        rootfs = [
          {
            enable = true;
            device = cfg.slots.rootfs0;
            type = "raw";
            settings.parent = "boot.0";
          }
          {
            enable = true;
            device = cfg.slots.rootfs1;
            type = "raw";
            settings.parent = "boot.1";
          }
        ];
      };

      settings = {
        system.statusfile = cfg.statusFile;
        keyring.path = "/etc/rauc/ca.cert.pem";
      }
      // lib.optionalAttrs (cfg.bootloader == "custom") {
        handlers.bootloader-custom-backend = toString customBackendScript;
      };
    };

    systemd.services.rauc = {
      path = lib.optionals (cfg.bootloader == "uboot") [ pkgs.ubootTools ];
      after = [ "persist.mount" ];
      unitConfig.RequiresMountsFor = [ "/persist" ];
      serviceConfig.ExecStartPre = [ "${pkgs.coreutils}/bin/mkdir -p /persist/rauc" ];
    };

    # CA certificate for bundle verification.
    # Uses the development CA by default. Production devices override this
    # with a production CA cert provisioned separately.
    environment.etc."rauc/ca.cert.pem".source = ../certs/dev.ca.cert.pem;
  };
}
