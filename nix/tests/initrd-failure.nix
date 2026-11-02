# NixOS test: a failed initrd panics, unless the `_RUT_OH_` serial debug flag
# (atomixos.initrd_shell) asked for an emergency shell instead.
#
# The test driver itself adds `panic=1 boot.panic_on_fail`, so the panic node
# shows the driver's panic delay, not the board's `panic=10`. What the test does
# prove is AtomixOS's own condition: atomixos.initrd_shell suppresses the panic.
{
  pkgs,
  self,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  failingInitrd =
    { lib, ... }:
    {
      imports = [
        ../../modules/base.nix
        qemuModule
      ];
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      # Hardware boards enable this through hardware-rockchip.nix.
      atomixos.serialRootDebug.enable = true;
      # Stand-in for a missing root slot: a required initrd unit that fails.
      boot.initrd.systemd.services.fail-initrd = {
        requiredBy = [ "initrd.target" ];
        before = [ "initrd.target" ];
        unitConfig.DefaultDependencies = false;
        serviceConfig = {
          Type = "oneshot";
          ExecStart = "/bin/false";
        };
      };
    };
in
nixos-lib.runTest {
  name = "initrd-failure";

  inherit hostPkgs;

  node.specialArgs = {
    inherit self;
    developmentMode = true;
    nixstasis = self.inputs.nixstasis;
  };

  nodes.panics = failingInitrd;

  nodes.shell =
    { ... }:
    {
      imports = [ failingInitrd ];
      boot.kernelParams = [ "atomixos.initrd_shell" ];
      # The shell opens on /dev/console, the last console= entry. Make that the
      # serial line the test reads, as console=ttyS2 is on a board.
      virtualisation.qemu.consoles = [ "ttyAMA0,115200n8" ];
    };

  testScript = ''
    panics.start()
    panics.wait_for_console_text("Kernel panic")
    panics.wait_for_shutdown()

    shell.start()
    shell.wait_for_console_text("You are in emergency mode")
    # Long past the driver's panic=1, the root shell still answers. (Machine
    # sleep() waits for a finished boot, which never comes here.)
    import time
    time.sleep(5)
    shell.wait_for_console_text("Press Enter for system maintenance")
    shell.send_console("\n")
    time.sleep(1)
    shell.send_console("echo initrd-shell-$((40 + 2))\n")
    shell.wait_for_console_text("initrd-shell-42")
  '';
}
