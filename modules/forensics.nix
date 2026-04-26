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
  slotTransitionCli = pkgs.writeShellScriptBin "forensics-slot-transition" (
    builtins.readFile ../scripts/forensics-slot-transition.sh
  );
  shutdownFlushScript = pkgs.writeShellScript "forensics-shutdown-flush" ''
    set -euo pipefail
    ${forensicCli}/bin/forensic-log --stage shutdown --event flush-begin --result start
    if [ -x ${pkgs.systemd}/bin/journalctl ]; then
      ${pkgs.systemd}/bin/journalctl --sync >/dev/null 2>&1 || true
    fi
    if [ -x ${pkgs.systemd}/bin/systemctl ]; then
      ${pkgs.systemd}/bin/systemctl kill -s HUP syslog.service >/dev/null 2>&1 || true
    fi
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

    services.rsyslogd = {
      enable = true;
      defaultConfig = "";
      extraConfig = ''
        $WorkDirectory /run/rsyslog

        main_queue(
          queue.type="LinkedList"
          queue.size="50000"
          queue.dequeuebatchsize="1000"
          queue.saveonshutdown="on"
        )

        $ActionFileDefaultTemplate RSYSLOG_TraditionalFileFormat

        *.info;auth,authpriv.none action(
          type="omfile"
          file="/data/logs/messages.log"
          asyncWriting="on"
          sync="off"
          flushOnTXEnd="off"
          ioBufferSize="1m"
          flushInterval="3600"
        )

        auth,authpriv.* action(
          type="omfile"
          file="/data/logs/auth.log"
          asyncWriting="on"
          sync="off"
          flushOnTXEnd="off"
          ioBufferSize="1m"
          flushInterval="3600"
        )
      '';
    };

    services.logrotate = {
      settings = {
        header.dateext = true;
        dataLogs = {
          files = [
            "/data/logs/messages.log"
            "/data/logs/auth.log"
          ];
          frequency = "weekly";
          rotate = 8;
          compress = true;
          delaycompress = true;
          missingok = true;
          notifempty = true;
          create = "0640 root root";
          sharedscripts = true;
          postrotate = "${pkgs.systemd}/bin/systemctl kill -s HUP syslog.service >/dev/null 2>&1 || true";
        };
      };
    };

    systemd.tmpfiles.rules = [
      "d /run/forensics 0755 root root -"
      "d /run/forensics/boot.0 0755 root root -"
      "d /run/forensics/boot.1 0755 root root -"
      "d /run/rsyslog 0755 root root -"
      "d /data/logs 0755 root root -"
      "d /data/rauc/forensics 0755 root root -"
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

    systemd.services.forensics-slot-transition = {
      description = "Record RAUC slot transition forensic markers";
      wantedBy = [ "multi-user.target" ];
      after = [
        "local-fs.target"
        "data.mount"
        "forensics-boot-start.service"
      ];
      wants = [ "data.mount" ];
      unitConfig.RequiresMountsFor = [ "/data" ];
      path = [
        pkgs.coreutils
        forensicCli
        slotTransitionCli
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = ''
          ${slotTransitionCli}/bin/forensics-slot-transition
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
        pkgs.systemd
      ];
      serviceConfig = {
        Type = "oneshot";
        ExecStart = shutdownFlushScript;
        TimeoutStartSec = 15;
      };
    };

    services.journald.extraConfig = ''
      Storage=volatile
      RuntimeMaxUse=32M
      MaxLevelStore=info
      MaxLevelSyslog=info
      RateLimitIntervalSec=30s
      RateLimitBurst=500
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

    systemd.services.syslog.unitConfig.RequiresMountsFor = [ "/data" ];
    systemd.services.syslog.after = [ "data.mount" ];
    systemd.services.syslog.wants = [ "data.mount" ];
    systemd.services.syslog.serviceConfig.ExecStartPre = [
      "${pkgs.coreutils}/bin/mkdir -p /run/rsyslog"
      "${pkgs.coreutils}/bin/mkdir -p /data/logs"
      "${pkgs.coreutils}/bin/mkdir -p /var/spool/rsyslog"
    ];
  };
}
