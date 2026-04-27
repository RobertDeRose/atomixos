{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  provisionCli = pkgs.writeScriptBin "first-boot-provision" (
    builtins.readFile ../../scripts/first-boot-provision.py
  );
in
nixos-lib.runTest {
  name = "first-boot-provision";

  inherit hostPkgs;

  nodes.gateway =
    { ... }:
    {
      imports = [ qemuModule ];

      virtualisation.memorySize = 512;
      system.stateVersion = "25.11";

      environment.systemPackages = [
        pkgs.curl
        pkgs.python3Minimal
        provisionCli
      ];

      systemd.tmpfiles.rules = [
        "d /data 0755 root root -"
        "d /etc/containers/systemd 0755 root root -"
      ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    gateway.succeed("cat > /tmp/config.toml <<'EOF'\n[admin]\npassword_hash = \"$6$rounds=1000$example$abcdefghijklmnopqrstuv\"\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"]\n\n[health]\nrequired = [\"myapp\"]\n\n[quadlet.network.frontend.Network]\nLabel = [\"env=test\", \"tier=edge\"]\n\n[quadlet.container.myapp.Unit]\nDescription = \"My App\"\n\n[quadlet.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nNetwork = [\"frontend\", \"backend\"]\nEnvironment = [\"A=1\", \"B=2\"]\n\n[quadlet.container.myapp.Install]\nWantedBy = [\"multi-user.target\"]\nEOF")

    gateway.succeed("first-boot-provision validate /tmp/config.toml")
    gateway.succeed("first-boot-provision import /tmp/config.toml /data/config")
    gateway.succeed("first-boot-provision sync-quadlet /data/config /etc/containers/systemd")

    gateway.succeed("test -f /data/config/config.toml")
    gateway.succeed("test -f /data/config/admin-password-hash")
    gateway.succeed("test -f /data/config/ssh-authorized-keys/admin")
    gateway.succeed("test -f /data/config/health-required.json")
    gateway.succeed("test -f /data/config/quadlet/myapp.container")
    gateway.succeed("test -f /data/config/quadlet/frontend.network")
    gateway.succeed("test -f /etc/containers/systemd/myapp.container")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\nrequired = json.loads(Path('/data/config/health-required.json').read_text())\nassert required == ['myapp'], required\nPY")
    gateway.succeed("grep -c '^Network=' /data/config/quadlet/myapp.container | grep '^2$'")
    gateway.succeed("grep -c '^Environment=' /data/config/quadlet/myapp.container | grep '^2$'")

    gateway.succeed("rm -rf /tmp/bootstrap-root")
    gateway.succeed("mkdir -p /tmp/bootstrap-root")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root /tmp/bootstrap-output.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -F config_file=@/tmp/config.toml http://127.0.0.1:18080/apply >/tmp/bootstrap-response.html")
    gateway.succeed("test -f /tmp/bootstrap-root/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root/admin-password-hash")
    gateway.succeed("test -f /tmp/bootstrap-root/ssh-authorized-keys/admin")
    gateway.succeed("test -f /tmp/bootstrap-root/health-required.json")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-response.html")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.succeed("cat > /tmp/invalid-config.toml <<'EOF'\n[admin]\npassword_hash = \"$6$rounds=1000$example$abcdefghijklmnopqrstuv\"\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"]\n\n[health]\nrequired = [\"missing-service\"]\n\n[quadlet.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nEOF")
    gateway.fail("first-boot-provision validate /tmp/invalid-config.toml")

    gateway.log("first-boot-provision helper test passed")
  '';
}
