{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-rollover";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      environment.variables = {
        ATOMIXOS_FORENSICS_SEGMENT_COUNT = "7";
        ATOMIXOS_FORENSICS_SEGMENT_SIZE = "1024";
      };
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          printf '%s\n' /tmp/forensics
        '';
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "forensic-log" (builtins.readFile ../../scripts/forensic-log.sh))
      ];
      systemd.tmpfiles.rules = [ "d /tmp/forensics 0755 root root -" ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.succeed("payload=$(printf 'x%.0s' $(seq 1 256)); for i in $(seq 1 200); do forensic-log --stage boot --event userspace-start --detail $payload-$i; done")
    machine.succeed("test -f /tmp/forensics/forensics/meta")
    machine.succeed("test $(ls /tmp/forensics/forensics/segment-*.log | wc -l) -eq 7")
    machine.succeed("grep '^active_segment=[1-6]$' /tmp/forensics/forensics/meta")
    machine.succeed("test $(grep -l . /tmp/forensics/forensics/segment-*.log | wc -l) -gt 1")
    machine.succeed("total=0; for file in /tmp/forensics/forensics/segment-*.log; do size=$(wc -c < \"$file\"); total=$((total + size)); done; test \"$total\" -le 7168")
  '';
}
