# Configures runtime logging through volatile journald plus buffered rsyslog
# writes to /data/logs.
{
  pkgs,
  ...
}:

let
  shutdownFlushScript = pkgs.writeShellScript "logging-shutdown-flush" ''
    set -euo pipefail
    if [ -x ${pkgs.systemd}/bin/journalctl ]; then
      ${pkgs.systemd}/bin/journalctl --sync >/dev/null 2>&1 || true
    fi
    if [ -x ${pkgs.systemd}/bin/systemctl ]; then
      ${pkgs.systemd}/bin/systemctl kill -s HUP syslog.service >/dev/null 2>&1 || true
    fi
  '';
in
{
  config = {
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
      "d /run/rsyslog 0755 root root -"
      "d /data/logs 0755 root root -"
    ];

    systemd.services.logging-shutdown-flush = {
      description = "Flush buffered logs during shutdown";
      before = [ "shutdown.target" ];
      conflicts = [ "shutdown.target" ];
      wantedBy = [
        "halt.target"
        "poweroff.target"
        "reboot.target"
      ];
      path = [ pkgs.systemd ];
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
