{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  testImage = pkgs.dockerTools.buildImage {
    name = "podman-log-test";
    tag = "latest";
    copyToRoot = pkgs.buildEnv {
      name = "podman-log-test-root";
      paths = [ pkgs.busybox ];
      pathsToLink = [ "/bin" ];
    };
    config = {
      Cmd = [
        "/bin/sh"
        "-c"
        "echo podman-log-check"
      ];
    };
  };
in
nixos-lib.runTest {
  name = "forensics-podman-log-path";

  inherit hostPkgs;

  nodes.machine =
    { lib, ... }:
    {
      imports = [
        ../../modules/rauc.nix
        ../../modules/logging.nix
        qemuModule
      ];

      boot.kernelParams = [ "rauc.slot=boot.0" ];

      virtualisation.podman = {
        enable = true;
        dockerCompat = true;
        defaultNetwork.settings.dns_enabled = true;
      };

      virtualisation.containers.storage.settings = {
        storage = {
          graphroot = "/data/containers/storage";
          runroot = "/run/containers/storage";
        };
      };
    };

  testScript = ''
    machine.start()
    machine.wait_for_unit("multi-user.target")
    machine.wait_for_unit("syslog.service")

    machine.succeed("grep 'log_driver = \"journald\"' /etc/containers/containers.conf")

    machine.copy_from_host("${testImage}", "/tmp/podman-log-test.tar.gz")
    machine.succeed("podman load -i /tmp/podman-log-test.tar.gz")
    machine.succeed("podman run --rm --network=none --name podman-log-test localhost/podman-log-test:latest")

    machine.wait_until_succeeds("journalctl --since '1 minute ago' -o cat | grep '^podman-log-check$'")

    machine.succeed("systemctl kill -s HUP syslog.service")
    machine.wait_until_succeeds("grep 'podman-log-check' /data/logs/messages.log")
  '';
}
