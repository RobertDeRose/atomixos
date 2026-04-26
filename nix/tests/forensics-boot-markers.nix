{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-boot-markers";

  inherit hostPkgs;

  nodes.machine =
    {
      ...
    }:
    {
      boot.kernelParams = [
        "rauc.slot=boot.0"
        "atomixos.lowerdev=/dev/disk/by-partlabel/rootfs-a"
      ];
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          printf '%s\n' /tmp/forensics/boot.0
        '';
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "forensic-log" (builtins.readFile ../../scripts/forensic-log.sh))
        (pkgs.writeShellScriptBin "forensics-initrd-log" (
          builtins.readFile ../../scripts/forensics-initrd-log.sh
        ))
      ];
      systemd.tmpfiles.rules = [
        "d /tmp/forensics 0755 root root -"
        "d /tmp/forensics/boot.0 0755 root root -"
        "d /tmp/initrd-boot 0755 root root -"
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

    env = (
        "ATOMIXOS_FORENSICS_BOOT0=/dev/null "
        "ATOMIXOS_FORENSICS_MOUNT=/tmp/initrd-boot "
        "ATOMIXOS_FORENSICS_SLOT=boot.0 "
        "ATOMIXOS_FORENSICS_LOWERDEV=/dev/disk/by-partlabel/rootfs-a"
    )
    machine.succeed(f"{env} forensics-initrd-log --event boot-start")
    machine.succeed(f"{env} forensics-initrd-log --event lowerdev-selected")
    machine.succeed("forensic-log --mount /tmp/initrd-boot --slot boot.0 --stage boot --event userspace-start")
    machine.succeed("forensic-log --mount /tmp/initrd-boot --slot boot.0 --stage boot --event boot-complete")

    readback = machine.succeed("forensic-log --mount /tmp/initrd-boot --slot boot.0 read")
    lines = [line.strip() for line in readback.splitlines() if line.strip()]

    expected = [
        ("initrd", "boot-start", "/dev/disk/by-partlabel/rootfs-a", "1"),
        ("initrd", "lowerdev-selected", "/dev/disk/by-partlabel/rootfs-a", "2"),
        ("boot", "userspace-start", None, "3"),
        ("boot", "boot-complete", None, "4"),
    ]

    assert len(lines) == len(expected), f"Expected {len(expected)} records, got {len(lines)}: {lines}"
    for line, (stage, event, device, seq) in zip(lines, expected):
        assert parse_field(line, "stage") == stage, f"Expected stage={stage}, got: {line}"
        assert parse_field(line, "event") == event, f"Expected event={event}, got: {line}"
        assert parse_field(line, "seq") == seq, f"Expected seq={seq}, got: {line}"
        if device is not None:
            assert parse_field(line, "device") == device, f"Expected device={device}, got: {line}"
  '';
}
