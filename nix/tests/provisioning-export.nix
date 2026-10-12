{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  self,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  client = pkgs.writeText "export-client.py" ''
    import base64
    import hashlib
    import io
    import json
    import subprocess
    import tarfile
    import urllib.error
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import Path
    import sys

    base = "http://127.0.0.1:8080"

    def export():
        with urllib.request.urlopen(base + "/api/nonce") as response:
            nonce = json.load(response)["nonce"]
        message = (
            f"atomixos-reapply-v2\nnonce:{nonce}\nmethod:GET\n"
            f"path:/api/config/export\nsha256:{hashlib.sha256(bytes()).hexdigest()}\n"
        ).encode()
        signature = subprocess.run(
            ["ssh-keygen", "-Y", "sign", "-f", "/tmp/admin-key", "-n", "atomixos-reapply"],
            input=message, capture_output=True, check=True,
        ).stdout
        request = urllib.request.Request(base + "/api/config/export", headers={
            "x-atomixos-nonce": nonce,
            "x-atomixos-signature": base64.b64encode(signature).decode(),
        })
        try:
            with urllib.request.urlopen(request, timeout=140) as response:
                assert response.status == 200
                archive = response.read()
        except urllib.error.HTTPError as error:
            assert sys.argv[1:] == ["failure"]
            assert error.code == 500, error.code
            assert "export failed" in json.load(error)["error"]
            return
        assert sys.argv[1:] != ["failure"]
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as bundle:
            assert bundle.getnames() == ["config.toml", "files", "files/private.txt"]
            assert bundle.extractfile("files/private.txt").read() == b"workload-owned private data\n"
            assert bundle.getmember("files/private.txt").mode == 0o644
            assert bundle.getmember("files/private.txt").uid == 0
        Path("/tmp/export.tar.gz").write_bytes(archive)

    if sys.argv[1:] == ["parallel"]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: export(), range(2)))
    else:
        export()
  '';
in
nixos-lib.runTest {
  name = "provisioning-export";
  inherit hostPkgs;

  nodes.gateway =
    { lib, ... }:
    {
      imports = [
        qemuModule
        ../../modules/first-boot.nix
      ];
      options.atomixos.rauc.enable = lib.mkEnableOption "RAUC";
      config = {
        _module.args = { inherit self; };
        virtualisation.memorySize = 768;
        system.stateVersion = "25.11";
        # Match the appliance's networkd/resolved stack; the default test
        # resolvconf unit otherwise cycles with the network-ordered API socket.
        networking.useNetworkd = true;
        services.resolved.enable = true;
        environment.systemPackages = [
          pkgs.curl
          pkgs.python3
          pkgs.openssh
          pkgs.shadow
          pkgs.gnutar
          pkgs.gzip
        ];
        # Exercise the real export and API units without starting unrelated apply work.
        systemd.services.first-boot.enable = false;
        systemd.services.quadlet-sync.enable = false;
        systemd.services.atomixos-apply-users.enable = false;
      };
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("atomixos-config-recover.service")
    gateway.wait_for_unit("atomixos-provision-export.path")
    gateway.succeed("mkdir -p /data/config/files; printf 'version = 1\\n' > /data/config/config.toml")
    gateway.succeed("ssh-keygen -q -t ed25519 -N \"\" -f /tmp/admin-key; cp /tmp/admin-key.pub /data/config/admin-signers")
    gateway.succeed("printf 'workload-owned private data\\n' > /data/config/files/private.txt; chmod 700 /data/config/files; chmod 600 /data/config/files/private.txt; chown 12345:12345 /data/config/files/private.txt")
    gateway.fail("runuser -u atomixos-provision -- cat /data/config/files/private.txt")
    gateway.fail("runuser -u atomixos-provision -- touch /run/atomixos-provision/export/results/forged.tar.gz")
    gateway.wait_for_unit("atomixos-bootstrap.socket")
    gateway.wait_until_succeeds("curl -fsS http://127.0.0.1:8080/api/health")
    gateway.succeed("test $(curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/config/export) = 401")
    gateway.succeed("python3 ${client} parallel")
    gateway.succeed("test $(stat -c %u:%g:%a /data/config/files/private.txt) = 12345:12345:600")
    gateway.succeed("test $(stat -c %a /data/config/files) = 700")
    gateway.wait_until_succeeds("test -z \"$(ls -A /run/atomixos-provision/export/results)\"")
    gateway.succeed("mkdir /tmp/unpacked; tar -xzf /tmp/export.tar.gz -C /tmp/unpacked; cmp /tmp/unpacked/files/private.txt /data/config/files/private.txt")

    # Links cannot turn the privileged exporter into a reader of unrelated state.
    gateway.succeed("ln -s /etc/shadow /data/config/files/escape")
    gateway.succeed("python3 ${client} failure")
    gateway.succeed("rm /data/config/files/escape; ln /data/config/admin-signers /data/config/files/escape")
    gateway.succeed("python3 ${client} failure")
    gateway.succeed("rm /data/config/files/escape")
    gateway.wait_until_succeeds("test -z \"$(ls -A /run/atomixos-provision/export/results)\"")
  '';
}
