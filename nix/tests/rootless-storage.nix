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
  name = "rootless-storage";

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

  # The rootless application store must live on /data, not in the appsvc home
  # on the overlay root, which every boot resets. QEMU's /data is a tmpfs, so
  # this checks where images land rather than a reboot.
  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.succeed("test \"$(stat -c %U:%a /data/containers/rootless/appsvc)\" = appsvc:700")

    gateway.succeed("loginctl enable-linger appsvc")
    gateway.wait_until_succeeds("systemctl is-active user@$(id -u appsvc).service")
    as_appsvc = "cd /tmp && runuser -u appsvc -- env HOME=/var/lib/appsvc XDG_RUNTIME_DIR=/run/user/$(id -u appsvc) "

    graph_root = gateway.succeed(as_appsvc + "podman info --format '{{.Store.GraphRoot}}'").strip()
    assert graph_root == "/data/containers/rootless/appsvc", graph_root

    # Import an image offline and confirm its layers are stored on /data.
    gateway.succeed("mkdir -p /tmp/rootfs && printf 'hello\\n' >/tmp/rootfs/hello && tar -C /tmp/rootfs -cf /tmp/rootfs.tar . && chmod 0644 /tmp/rootfs.tar")
    gateway.succeed(as_appsvc + "podman import /tmp/rootfs.tar localhost/probe:1")
    gateway.succeed(as_appsvc + "podman images --format '{{.Repository}}:{{.Tag}}' | grep -x localhost/probe:1")
    gateway.succeed("test -d /data/containers/rootless/appsvc/overlay-images")
    gateway.fail("test -e /var/lib/appsvc/.local/share/containers/storage/overlay-images")
  '';
}
