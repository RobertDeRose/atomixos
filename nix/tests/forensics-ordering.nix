{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-ordering";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      boot.kernelParams = [ "rauc.slot=boot.0" ];
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          set -euo pipefail
          case "''${1:-boot.0}" in
            boot.0) printf '%s\n' /tmp/forensics/boot.0 ;;
            boot.1) printf '%s\n' /tmp/forensics/boot.1 ;;
            *) printf '%s\n' /tmp/forensics/boot.0 ;;
          esac
        '';
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "forensic-log" (builtins.readFile ../../scripts/forensic-log.sh))
      ];
      systemd.tmpfiles.rules = [
        "d /tmp/forensics 0755 root root -"
        "d /tmp/forensics/boot.0 0755 root root -"
        "d /tmp/forensics/boot.1 0755 root root -"
      ];
    };

  testScript = ''
    import re

    def parse_field(line, key):
        match = re.search(rf"(?:^| ){key}=([^ ]+)", line)
        assert match is not None, f"Missing {key} in: {line}"
        return match.group(1)

    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("forensic-log --stage boot --event userspace-start --detail boot0-first && sync")
    machine.succeed("forensic-log --stage verify --event complete --detail boot0-second && sync")

    boot0_first = machine.succeed("grep 'detail=boot0-first' /tmp/forensics/boot.0/forensics/segment-0.log").strip()
    boot0_second = machine.succeed("grep 'detail=boot0-second' /tmp/forensics/boot.0/forensics/segment-0.log").strip()
    boot0_first_id = parse_field(boot0_first, "boot_id")
    boot0_second_id = parse_field(boot0_second, "boot_id")
    assert boot0_first_id == boot0_second_id, "Expected boot.0 records in one boot to share boot_id"
    assert boot0_first_id.endswith("-A"), f"Expected boot.0 boot_id suffix -A, got {boot0_first_id}"
    assert parse_field(boot0_first, "seq") == "1", f"Expected first boot.0 seq=1, got: {boot0_first}"
    assert parse_field(boot0_second, "seq") == "2", f"Expected second boot.0 seq=2, got: {boot0_second}"

    machine.succeed("forensic-log --slot boot.1 --stage rauc --event install-complete --detail slot-switch && sync")
    boot1_line = machine.succeed("grep 'detail=slot-switch' /tmp/forensics/boot.1/forensics/segment-0.log").strip()
    boot1_id = parse_field(boot1_line, "boot_id")
    assert boot1_id.endswith("-B"), f"Expected boot.1 boot_id suffix -B, got {boot1_id}"
    assert boot1_id != boot0_first_id, "Expected boot.1 to use a distinct boot_id from boot.0"
    assert parse_field(boot1_line, "seq") == "1", f"Expected first boot.1 seq=1, got: {boot1_line}"

    machine.crash()
    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("forensic-log --stage rollback --event complete --detail rollback-to-a && sync")
    rollback_line = machine.succeed("grep 'detail=rollback-to-a' /tmp/forensics/boot.0/forensics/segment-0.log").strip()
    rollback_id = parse_field(rollback_line, "boot_id")
    assert rollback_id.endswith("-A"), f"Expected rollback boot_id suffix -A, got {rollback_id}"
    assert rollback_id != boot0_first_id, "Expected a new boot.0 boot_id after reboot/rollback"
    assert parse_field(rollback_line, "seq") == "1", f"Expected rollback boot.0 seq reset to 1, got: {rollback_line}"
  '';
}
