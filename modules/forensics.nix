{
  config,
  lib,
  pkgs,
  ...
}:

let
  hasRaucSlots =
    config.atomixos.rauc.enable
    && config.atomixos.rauc.slots.boot0 != null
    && config.atomixos.rauc.slots.boot1 != null;
  forensicCli = pkgs.writeShellScriptBin "forensic-log" (
    builtins.readFile ../scripts/forensic-log.sh
  );
  initrdForensicCli = pkgs.writeShellScriptBin "forensics-initrd-log" (
    builtins.readFile ../scripts/forensics-initrd-log.sh
  );
  shutdownFlushScript = pkgs.writeShellScript "forensics-shutdown-flush" ''
    set -euo pipefail
    ${forensicCli}/bin/forensic-log --stage shutdown --event flush-begin --result start
    ${forensicCli}/bin/forensic-log --stage shutdown --event flush-end --result ok
  '';
  dataMountOutcomeScript = pkgs.writeShellScript "forensics-data-mount-outcome" ''
    set -euo pipefail
    if ${pkgs.util-linux}/bin/findmnt /data >/dev/null 2>&1; then
      ${forensicCli}/bin/forensic-log --stage boot --event data-mount-ok --device /data --result ok
    else
      ${forensicCli}/bin/forensic-log --stage boot --event data-mount-failed --device /data --result fail
    fi
  '';
  currentBootForensicsMount = pkgs.writeShellScript "current-boot-forensics-mount" ''
    set -euo pipefail

    slot="''${1:-}"
    if [ -z "$slot" ]; then
      for arg in $(</proc/cmdline); do
        case "$arg" in
          rauc.slot=boot.0)
            slot="boot.0"
            ;;
          rauc.slot=boot.1)
            slot="boot.1"
            ;;
        esac
      done
    fi

    case "$slot" in
      boot.0)
        if ${pkgs.util-linux}/bin/findmnt /run/forensics/boot.0 >/dev/null 2>&1; then
          printf '%s\n' /run/forensics/boot.0
        else
          printf '%s\n' /boot
        fi
        ;;
      boot.1)
        if ${pkgs.util-linux}/bin/findmnt /run/forensics/boot.1 >/dev/null 2>&1; then
          printf '%s\n' /run/forensics/boot.1
        else
          printf '%s\n' /boot
        fi
        ;;
      *)
        printf '%s\n' /boot
        ;;
    esac
  '';
in
{
  config = {
    environment.systemPackages = [ forensicCli ];

    systemd.tmpfiles.rules = [
      "d /run/forensics 0755 root root -"
      "d /run/forensics/boot.0 0755 root root -"
      "d /run/forensics/boot.1 0755 root root -"
    ];

    fileSystems."/run/forensics/boot.0" = lib.mkIf hasRaucSlots {
      device = lib.mkDefault config.atomixos.rauc.slots.boot0;
      fsType = "vfat";
      options = [
        "nofail"
        "x-systemd.device-timeout=10s"
        "uid=0"
        "gid=0"
        "fmask=0133"
        "dmask=0022"
      ];
    };

    fileSystems."/run/forensics/boot.1" = lib.mkIf hasRaucSlots {
      device = lib.mkDefault config.atomixos.rauc.slots.boot1;
      fsType = "vfat";
      options = [
        "nofail"
        "x-systemd.device-timeout=10s"
        "uid=0"
        "gid=0"
        "fmask=0133"
        "dmask=0022"
      ];
    };

    environment.etc."atomixos/current-boot-forensics-mount".source = currentBootForensicsMount;

    systemd.services.forensics-boot-start = {
      description = "Record boot forensic start marker";
      wantedBy = [ "multi-user.target" ];
      after = [ "local-fs.target" ];
      wants = [ "local-fs.target" ];
      path = [
        pkgs.coreutils
        forensicCli
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = ''
          ${forensicCli}/bin/forensic-log --stage boot --event userspace-start
        '';
      };
    };

    systemd.services.forensics-boot-complete = {
      description = "Record boot forensic completion marker";
      wantedBy = [ "multi-user.target" ];
      before = [ "multi-user.target" ];
      after = [
        "forensics-boot-start.service"
        "forensics-data-mount-outcome.service"
      ];
      wants = [ "forensics-data-mount-outcome.service" ];
      path = [
        pkgs.coreutils
        forensicCli
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = ''
          ${forensicCli}/bin/forensic-log --stage boot --event boot-complete
        '';
      };
    };

    systemd.services.forensics-data-mount-outcome = {
      description = "Record /data mount forensic marker";
      wantedBy = [ "multi-user.target" ];
      after = [
        "local-fs.target"
        "data.mount"
      ];
      wants = [ "data.mount" ];
      path = [
        pkgs.coreutils
        pkgs.util-linux
        forensicCli
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = dataMountOutcomeScript;
      };
    };

    systemd.services.forensics-shutdown-flush = {
      description = "Record shutdown forensic markers";
      before = [ "shutdown.target" ];
      conflicts = [ "shutdown.target" ];
      wantedBy = [
        "halt.target"
        "poweroff.target"
        "reboot.target"
      ];
      path = [
        pkgs.coreutils
        forensicCli
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = shutdownFlushScript;
        TimeoutStartSec = 15;
      };
    };

    services.journald.extraConfig = ''
      Storage=volatile
      RuntimeMaxUse=64M
    '';

    boot.initrd.systemd.services.forensics-initrd-start = lib.mkIf hasRaucSlots {
      description = "Record initrd forensic start marker";
      wantedBy = [ "initrd-prepare-overlay-lower.service" ];
      before = [ "initrd-prepare-overlay-lower.service" ];
      after = [ "initrd-root-device.target" ];
      wants = [ "initrd-root-device.target" ];
      unitConfig.DefaultDependencies = false;
      path = [
        pkgs.coreutils
        pkgs.util-linux
        forensicCli
        initrdForensicCli
      ];
      environment = {
        ATOMIXOS_FORENSICS_BOOT0 = config.atomixos.rauc.slots.boot0;
        ATOMIXOS_FORENSICS_BOOT1 = config.atomixos.rauc.slots.boot1;
      };
      serviceConfig = {
        Type = "oneshot";
        ExecStart = ''
          ${initrdForensicCli}/bin/forensics-initrd-log --event boot-start
        '';
      };
    };

    boot.initrd.systemd.services.forensics-initrd-rootfs-selected = lib.mkIf hasRaucSlots {
      description = "Record initrd rootfs selection marker";
      wantedBy = [ "sysroot.mount" ];
      before = [ "sysroot.mount" ];
      after = [ "initrd-prepare-overlay-lower.service" ];
      requires = [ "initrd-prepare-overlay-lower.service" ];
      unitConfig.DefaultDependencies = false;
      path = [
        pkgs.coreutils
        pkgs.util-linux
        forensicCli
        initrdForensicCli
      ];
      environment = {
        ATOMIXOS_FORENSICS_BOOT0 = config.atomixos.rauc.slots.boot0;
        ATOMIXOS_FORENSICS_BOOT1 = config.atomixos.rauc.slots.boot1;
      };
      serviceConfig = {
        Type = "oneshot";
        ExecStart = ''
          ${initrdForensicCli}/bin/forensics-initrd-log --event lowerdev-selected
        '';
      };
    };

    virtualisation.containers.containersConf.settings.containers.log_driver = "journald";
  };
}
