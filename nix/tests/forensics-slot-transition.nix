{
  pkgs,
  hostPkgs ? pkgs,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "forensics-slot-transition";

  inherit hostPkgs;

  nodes.machine =
    { ... }:
    {
      boot.kernelParams = [ "rauc.slot=boot.0" ];
      environment.etc."atomixos/current-boot-forensics-mount".source =
        pkgs.writeShellScript "current-boot-forensics-mount" ''
          case "''${1:-boot.0}" in
            boot.0) printf '%s\n' /tmp/forensics/boot.0 ;;
            boot.1) printf '%s\n' /tmp/forensics/boot.1 ;;
            *) printf '%s\n' /tmp/forensics/boot.0 ;;
          esac
        '';
      environment.systemPackages = [
        (pkgs.writeShellScriptBin "forensic-log" (builtins.readFile ../../scripts/forensic-log.sh))
        (pkgs.writeShellScriptBin "forensics-slot-transition" (
          builtins.readFile ../../scripts/forensics-slot-transition.sh
        ))
      ];
      systemd.tmpfiles.rules = [
        "d /tmp/forensics 0755 root root -"
        "d /tmp/forensics/boot.0 0755 root root -"
        "d /tmp/forensics/boot.1 0755 root root -"
        "d /data 0755 root root -"
        "d /data/rauc 0755 root root -"
        "d /data/rauc/forensics 0755 root root -"
      ];
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")

    machine.succeed("printf 'boot.0\n' > /data/rauc/forensics/pending-source-slot")
    machine.succeed("printf 'boot.1\n' > /data/rauc/forensics/pending-target-slot")
    machine.succeed("printf '2.0.0\n' > /data/rauc/forensics/pending-target-version")

    machine.succeed("ATOMIXOS_FORENSICS_SLOT=boot.1 forensics-slot-transition")
    machine.succeed("grep 'slot=boot.1 stage=rauc event=slot-switch result=ok target_slot=boot.1 version=2.0.0' /tmp/forensics/boot.1/forensics/segment-0.log")

    machine.succeed("ATOMIXOS_FORENSICS_SLOT=boot.0 forensics-slot-transition")
    machine.succeed("grep 'slot=boot.1 stage=rollback event=detected target_slot=boot.0 reason=slot-fallback version=2.0.0' /tmp/forensics/boot.1/forensics/segment-0.log")
    machine.succeed("grep 'slot=boot.1 stage=rollback event=slot-fallback result=ok target_slot=boot.0 version=2.0.0' /tmp/forensics/boot.1/forensics/segment-0.log")
    machine.fail("test -e /data/rauc/forensics/pending-target-slot")
  '';
}
