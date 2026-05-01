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
        ../../modules/logging.nix
        qemuModule
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];

      environment.systemPackages = [ pkgs.logger ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("syslog.service")

    machine.succeed("logger -t forensics-shutdown-flush 'shutdown-flush-check'")
    machine.succeed("systemctl start logging-shutdown-flush.service")

    machine.wait_until_succeeds("grep 'shutdown-flush-check' /data/logs/messages.log")
  '';
}
