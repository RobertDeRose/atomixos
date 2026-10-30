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
  name = "ssh-host-keys";

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
      atomixos.rauc.enable = lib.mkForce false;
      virtualisation.memorySize = 1024;
    };

  # The SSH host key must live on /data, not in /etc/ssh on the overlay root,
  # which every boot resets. QEMU's /data is a tmpfs, so this checks where the
  # key lands and that sshd serves it, rather than a reboot.
  testScript = ''
    gateway.start()
    gateway.wait_for_unit("sshd.service")

    key = "/data/ssh/ssh_host_ed25519_key"
    gateway.succeed(f"test \"$(stat -c %U:%a {key})\" = root:600")
    gateway.fail("ls /etc/ssh/ssh_host_*")

    # sshd presents exactly the key stored on /data.
    stored = gateway.succeed(f"cut -d' ' -f2 {key}.pub").strip()
    served = gateway.wait_until_succeeds("ssh-keyscan -t ed25519 127.0.0.1 2>/dev/null | grep ssh-ed25519 | cut -d' ' -f3").strip()
    assert served == stored, (served, stored)
    # It is the only host key: no RSA, ECDSA, or other type is served.
    scanned = gateway.succeed("ssh-keyscan -t rsa,ecdsa,ed25519 127.0.0.1 2>/dev/null | grep -v '^#' | cut -d' ' -f2").split()
    assert scanned == ["ssh-ed25519"], scanned

    # Restarting key generation and sshd keeps the same key.
    gateway.succeed("systemctl restart sshd-keygen.service sshd.service")
    gateway.wait_for_unit("sshd.service")
    again = gateway.wait_until_succeeds("ssh-keyscan -t ed25519 127.0.0.1 2>/dev/null | grep ssh-ed25519 | cut -d' ' -f3").strip()
    assert again == stored, (again, stored)
  '';
}
