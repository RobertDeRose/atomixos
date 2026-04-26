{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-persistence";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      boot.kernelParams = [ "rauc.slot=boot.0" ];
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          printf '%s\n' /boot
        '';
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "forensic-log" (builtins.readFile ../../scripts/forensic-log.sh))
      ];
      systemd.tmpfiles.rules = [
        "d /boot 0755 root root -"
        "d /boot/forensics 0755 root root -"
      ];
    };

  testScript = ''
    import re

    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("forensic-log --stage boot --event userspace-start --detail first_boot && sync")
    first_line = machine.succeed("grep 'detail=first_boot' /boot/forensics/segment-0.log").strip()
    first_match = re.search(r'boot_id=([^ ]+)', first_line)
    assert first_match is not None, f"Missing boot_id in first forensic record: {first_line}"
    first_boot_id = first_match.group(1)

    machine.crash()
    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("forensic-log --stage boot --event userspace-start --detail second_boot && sync")
    machine.succeed("grep 'detail=first_boot' /boot/forensics/segment-0.log")
    second_line = machine.succeed("grep 'detail=second_boot' /boot/forensics/segment-0.log").strip()
    second_match = re.search(r'boot_id=([^ ]+)', second_line)
    assert second_match is not None, f"Missing boot_id in second forensic record: {second_line}"
    second_boot_id = second_match.group(1)

    assert first_boot_id != second_boot_id, "Expected a new boot_id after restart"
    machine.succeed("grep '^next_seq=2$' /boot/forensics/meta")
    machine.succeed("test $(grep -c 'stage=boot event=userspace-start' /boot/forensics/segment-0.log) -eq 2")
  '';
}
