{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-readback";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      environment.variables = {
        ATOMIXOS_FORENSICS_SEGMENT_COUNT = "3";
        ATOMIXOS_FORENSICS_SEGMENT_SIZE = "128";
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

    machine.succeed("forensic-log --stage boot --event userspace-start --detail one && sync")
    machine.succeed("forensic-log --stage verify --event complete --detail two && sync")
    machine.succeed("forensic-log --stage rollback --event detected --detail three && sync")

    machine.succeed("printf 'boot_id=torn seq=999 ts=broken slot=boot.0 stage=boot event=partial' >> /tmp/forensics/forensics/segment-0.log")

    readback = machine.succeed("forensic-log read")
    lines = [line.strip() for line in readback.splitlines() if line.strip()]

    expected = ["detail=one", "detail=two", "detail=three"]
    assert len(lines) == len(expected), f"Expected {len(expected)} complete records, got {len(lines)}: {lines}"
    for line, marker, seq in zip(lines, expected, ["1", "2", "3"]):
        assert marker in line, f"Missing {marker} in readback line: {line}"
        assert f"seq={seq}" in line, f"Expected seq={seq} in readback line: {line}"

    assert all("seq=999" not in line for line in lines), f"Readback included torn record: {lines}"
  '';
}
