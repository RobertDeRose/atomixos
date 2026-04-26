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
  name = "forensics-shutdown-flush";

  inherit hostPkgs;

  nodes.machine =
    { lib, ... }:
    {
      imports = [
        ../../modules/rauc.nix
        ../../modules/forensics.nix
        qemuModule
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];

      environment.etc."atomixos/current-boot-forensics-mount".source = lib.mkForce (
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          printf '%s\n' /boot
        ''
      );

      environment.systemPackages = [ pkgs.logger ];

      systemd.tmpfiles.rules = [ "d /boot/forensics 0755 root root -" ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("syslog.service")

    machine.succeed("logger -t forensics-shutdown-flush 'shutdown-flush-check'")
    machine.succeed("systemctl start forensics-shutdown-flush.service")

    machine.wait_until_succeeds("grep 'shutdown-flush-check' /data/logs/messages.log")
    machine.succeed("grep 'slot=boot.0 stage=shutdown event=flush-begin result=start' /boot/forensics/segment-0.log")
    machine.succeed("grep 'slot=boot.0 stage=shutdown event=flush-end result=ok' /boot/forensics/segment-0.log")
  '';
}
