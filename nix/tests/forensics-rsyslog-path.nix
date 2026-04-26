{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-rsyslog-path";

  inherit hostPkgs;

  nodes.machine =
    { ... }:
    {
      imports = [ qemuModule ];

      environment.systemPackages = [ pkgs.logger ];

      systemd.tmpfiles.rules = [
        "d /data 0755 root root -"
        "d /data/logs 0755 root root -"
        "d /run/rsyslog 0755 root root -"
      ];

      services.journald.extraConfig = ''
        Storage=volatile
        RuntimeMaxUse=32M
      '';

      services.rsyslogd = {
        enable = true;
        defaultConfig = "";
        extraConfig = ''
          $WorkDirectory /run/rsyslog

          main_queue(
            queue.type="LinkedList"
            queue.size="10000"
            queue.dequeuebatchsize="100"
            queue.saveonshutdown="on"
          )

          *.* action(
            type="omfile"
            file="/data/logs/messages.log"
            sync="off"
            flushOnTXEnd="off"
            ioBufferSize="64k"
          )
        '';
      };

      systemd.services.syslog.unitConfig.RequiresMountsFor = [ "/data" ];
      systemd.services.syslog.after = [ "data.mount" ];
      systemd.services.syslog.wants = [ "data.mount" ];
      systemd.services.syslog.serviceConfig.ExecStartPre = [
        "${pkgs.coreutils}/bin/mkdir -p /run/rsyslog"
        "${pkgs.coreutils}/bin/mkdir -p /data/logs"
        "${pkgs.coreutils}/bin/mkdir -p /var/spool/rsyslog"
      ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("syslog.service")

    machine.succeed("logger -t forensics-rsyslog-path 'batched-path-check'")
    machine.succeed("systemctl kill -s HUP syslog.service")
    machine.wait_until_succeeds("grep 'batched-path-check' /data/logs/messages.log")

    machine.succeed("test -s /data/logs/messages.log")
  '';
}
