{
  pkgs,
  self,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
in
nixos-lib.runTest {
  name = "kernel-security";

  inherit hostPkgs;

  node.specialArgs = {
    inherit self;
    developmentMode = true;
    nixstasis = self.inputs.nixstasis;
  };

  nodes.gateway =
    { lib, ... }:
    {
      imports = [
        ../../modules/base.nix
        qemuModule
      ];
      system.stateVersion = "25.11";
      # This profile validates the stripped kernel only; RAUC and Rock64
      # boot-storage diagnostics are intentionally absent in QEMU.
      atomixos.rauc.enable = lib.mkForce false;
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.succeed("test -r /sys/kernel/security/lsm")
    gateway.succeed("grep -qw bpf /sys/kernel/security/lsm")
    gateway.succeed("test -r /sys/kernel/btf/vmlinux")
    gateway.succeed("grep -Eq '(^| )lsm=bpf($| )' /proc/cmdline")
    gateway.fail("journalctl -b --no-pager | grep -E 'BPF LSM hook not enabled|BPF LSM not supported|bpf-restrict-fs: Failed to link program'")
    gateway.fail("journalctl -b --no-pager | grep 'mtd_probe'")
    gateway.fail("journalctl -b --no-pager | grep 'boot-storage-debug'")
    gateway.succeed("systemctl is-active systemd-sysctl.service")
    gateway.fail("journalctl -b --no-pager | grep 'kernel/hung_task_timeout_secs'")
  '';
}
