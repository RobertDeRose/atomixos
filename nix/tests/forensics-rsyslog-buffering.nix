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
  name = "forensics-rsyslog-buffering";

  inherit hostPkgs;

  nodes.machine =
    { lib, ... }:
    {
      imports = [
        ../../modules/rauc.nix
        ../../modules/logging.nix
        qemuModule
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];

      environment.systemPackages = [
        pkgs.gawk
        pkgs.gnugrep
        pkgs.logger
        pkgs.procps
        pkgs.strace
      ];
      services.rsyslogd.extraConfig = lib.mkForce ''
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
          ioBufferSize="64k"
          flushInterval="5"
        )

        auth,authpriv.* action(
          type="omfile"
          file="/data/logs/auth.log"
          asyncWriting="on"
          sync="off"
          flushOnTXEnd="off"
          ioBufferSize="64k"
          flushInterval="5"
        )
      '';
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("syslog.service")

    machine.succeed("sh -eu -c ': > /data/logs/messages.log; rm -f /tmp/rsyslog-batch-trace.* /tmp/rsyslog-batch-attach.log /tmp/rsyslog-batch-strace.pid'")
    machine.succeed("sh -eu -c 'main_pid=$(systemctl show -p MainPID --value syslog.service); strace -ff -tt -yy -s 0 -e trace=write,writev,pwrite64,pwritev -p \"$main_pid\" -o /tmp/rsyslog-batch-trace >/tmp/rsyslog-batch-attach.log 2>&1 & echo $! >/tmp/rsyslog-batch-strace.pid'")

    machine.succeed("sh -eu -c 'payload=$(printf %0810d 0); for i in $(seq 1 200); do logger -t forensics-rsyslog-buffering \"buffering-check-$i $payload\"; done'")
    machine.wait_until_succeeds("grep 'buffering-check-200' /data/logs/messages.log")
    machine.succeed("test $(grep -c 'buffering-check-' /data/logs/messages.log) -ge 200")

    machine.succeed("kill $(cat /tmp/rsyslog-batch-strace.pid) || true")
    machine.wait_until_succeeds("ls /tmp/rsyslog-batch-trace.*")
    machine.succeed("sh -eu -c 'trace_matches=$(grep -h \"/data/logs/messages.log\" /tmp/rsyslog-batch-trace.* || true); test -n \"$trace_matches\"; write_count=$(printf \"%s\\n\" \"$trace_matches\" | wc -l); [ \"$write_count\" -lt 80 ]; max_write=$(printf \"%s\\n\" \"$trace_matches\" | grep -oE \"= [0-9]+$\" | grep -oE \"[0-9]+\" | sort -n | tail -n 1); [ \"''${max_write:-0}\" -gt 32768 ]'")
  '';
}
