{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  self,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  mockApi = pkgs.writeText "fleet-bootstrap-mock-api.py" ''
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path
    from urllib.parse import urlparse

    STATE = Path("/tmp/nixstasis-fleet")
    STATE.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length)
            path = urlparse(self.path).path

            if path == "/api/v1/devices/register":
                (STATE / "register.json").write_bytes(body)
                response = {
                    "data": {
                        "id": "22222222-2222-4222-8222-222222222222",
                    }
                }
                if (STATE / "approve").exists():
                    (STATE / "registration-approved").write_text("approved\n")
                    response["data"]["api_token"] = "fleet-runtime-token"
                else:
                    (STATE / "registration-pending").write_text("pending\n")
                self.reply(201, response)
                return

            if path.startswith("/api/v1/devices/") and path.endswith("/heartbeat"):
                (STATE / "heartbeat.json").write_bytes(body)
                if (STATE / "withdraw").exists():
                    self.reply(200, {"data": {"commands": []}})
                elif (STATE / "grant").exists():
                    (STATE / "profile").write_text("atomixos-bootstrap:1\n")
                    self.reply(
                        200,
                        {
                            "data": {
                                "remote_access_token": "fleet-frp-token",
                                "remote_access_profile": {
                                    "name": "atomixos-bootstrap",
                                    "version": 1,
                                },
                                "commands": [],
                            }
                        },
                    )
                else:
                    (STATE / "heartbeat-no-lease").write_bytes(body)
                    self.reply(200, {"data": {"commands": []}})
                return

            if path == "/mock/frpc":
                if body == b"started":
                    (STATE / "frpc.started").write_bytes(body)
                self.reply(200, {"ok": True})
                return

            self.reply(404, {"error": "not found"})

        def log_message(self, *_args):
            return

        def reply(self, status, payload):
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    HTTPServer(("127.0.0.1", 4000), Handler).serve_forever()
  '';
  mockFrpc = pkgs.writeShellScriptBin "nixstasis-fleet-test-frpc" ''
    set -eu

    config=/run/nixstasis/frpc.toml
    upload=/data/fleet-bootstrap-test-config.toml
    test -s "$config"
    test -s "$upload"
    test -n "''${FRPS_AUTH_TOKEN:-}"
    ${pkgs.gnugrep}/bin/grep -F 'type = "http"' "$config"
    ${pkgs.gnugrep}/bin/grep -F 'subdomain = "fleet-test-provisioning"' "$config"
    ${pkgs.gnugrep}/bin/grep -F 'localIP = "127.0.0.1"' "$config"
    ${pkgs.gnugrep}/bin/grep -F 'localPort = 8080' "$config"
    ${pkgs.gnugrep}/bin/grep -F 'hostHeaderRewrite = "localhost"' "$config"
    ! ${pkgs.gnugrep}/bin/grep -F 'http2https' "$config"
    ! ${pkgs.gnugrep}/bin/grep -F 'localPort = 22' "$config"
    ! ${pkgs.gnugrep}/bin/grep -F 'localPort = 44321' "$config"
    ! ${pkgs.gnugrep}/bin/grep -F 'fleet-frp-token' "$config"

    ${pkgs.curl}/bin/curl -fsS -X POST http://127.0.0.1:4000/mock/frpc --data-binary started >/dev/null

    upload_response=$(${pkgs.curl}/bin/curl -fsS -H 'Host: localhost' -H 'Content-Type: application/octet-stream' --data-binary @"$upload" http://127.0.0.1:8080/api/config)
    printf '%s' "$upload_response" > /data/fleet-bootstrap-upload-response.json
    job_url=$(${pkgs.jq}/bin/jq -r .job_url /data/fleet-bootstrap-upload-response.json)
    for _ in $(${pkgs.coreutils}/bin/seq 1 120); do
      ${pkgs.curl}/bin/curl -fsS "http://127.0.0.1:8080$job_url" > /data/fleet-bootstrap-upload-job.json
      state=$(${pkgs.jq}/bin/jq -r .state /data/fleet-bootstrap-upload-job.json)
      if [ "$state" = succeeded ]; then
        : > /data/fleet-bootstrap-upload-succeeded
        break
      fi
      if [ "$state" = failed ]; then
        ${pkgs.coreutils}/bin/cat /data/fleet-bootstrap-upload-job.json >&2
        exit 1
      fi
      ${pkgs.coreutils}/bin/sleep 1
    done
    test -e /tmp/nixstasis-fleet/upload-succeeded

    while true; do
      ${pkgs.coreutils}/bin/sleep 1
    done
  '';
  testConfig = pkgs.writeText "fleet-bootstrap-test-config.toml" ''
    version = 1

    [users.fleetadmin]
    isAdmin = true
    ssh_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey fleetadmin@example"

    [activation]
    required = ["fleet-test"]

    [containers.container.fleet-test]
    privileged = true

    [containers.container.fleet-test.Container]
    Image = "fleet-bootstrap-test:latest"

    [containers.container.fleet-test.Install]
    WantedBy = ["multi-user.target"]
  '';
  testImage = pkgs.dockerTools.buildImage {
    name = "fleet-bootstrap-test";
    tag = "latest";
    copyToRoot = pkgs.buildEnv {
      name = "fleet-bootstrap-test-root";
      paths = [ pkgs.busybox ];
      pathsToLink = [ "/bin" ];
    };
    config = {
      Cmd = [
        "/bin/sh"
        "-c"
        "sleep 3600"
      ];
    };
  };
in
nixos-lib.runTest {
  name = "fleet-bootstrap";

  inherit hostPkgs;

  nodes.gateway =
    { lib, ... }:
    {
      _module.args = {
        inherit self;
        developmentMode = false;
        effectiveBuildConfig = self.lib.effectiveBuildConfiguration;
        nixstasis = self.inputs.nixstasis;
      };

      imports = [
        ../../modules/base.nix
        ../../modules/build-configuration.nix
        qemuModule
      ];

      virtualisation.memorySize = 768;
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      atomixos.provisioning.bootstrapTransport = lib.mkForce "nixstasis";
      atomixos.nixstasis = {
        enable = lib.mkForce true;
        apiUrl = lib.mkForce "http://127.0.0.1:4000";
        pollInterval = "1s";
        frp = {
          name = "fleet-test";
          serverAddr = lib.mkForce "frps.example.test";
          serverPort = lib.mkForce 7000;
        };
        runtime.execCommands.uname = "/run/current-system/sw/bin/uname";
      };

      environment.systemPackages = [
        pkgs.curl
        pkgs.iproute2
        pkgs.jq
      ];
      systemd.services.nixstasis-poll.environment.NIXSTASIS_FRPC_BINARY_PATH =
        lib.mkForce "${mockFrpc}/bin/nixstasis-fleet-test-frpc";

      systemd.services.nixstasis-fleet-mock-api = {
        description = "Fleet bootstrap Nixstasis mock API";
        wantedBy = [ "multi-user.target" ];
        after = [ "network.target" ];
        serviceConfig = {
          Type = "simple";
          ExecStart = "${pkgs.python3}/bin/python3 ${mockApi}";
          Restart = "on-failure";
        };
      };
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")
    gateway.wait_for_unit("nixstasis-fleet-mock-api.service")
    gateway.wait_for_open_port(4000)

    gateway.wait_until_succeeds("ss -tln | grep '127.0.0.1:8080'", timeout=120)
    gateway.fail("ss -tln | grep '0.0.0.0:8080'")
    gateway.succeed("curl -fsS -H 'Host: localhost' http://127.0.0.1:8080/api/health | grep -F 'status'")
    gateway.succeed("test \"$(curl -sS -o /tmp/fleet-config-submit.json -w '%{http_code}' -X POST -H 'Host: localhost' -H 'Content-Type: application/octet-stream' --data-binary @/dev/null http://127.0.0.1:8080/api/config)\" = 202")
    gateway.succeed("jq -e '(.job_id | type == \"string\" and length > 0) and (.job_url == (\"/api/jobs/\" + .job_id))' /tmp/fleet-config-submit.json")
    gateway.wait_until_succeeds("job_url=$(jq -r .job_url /tmp/fleet-config-submit.json); curl -fsS \"http://127.0.0.1:8080$job_url\" > /tmp/fleet-config-job.json; test \"$(jq -r .state /tmp/fleet-config-job.json)\" = failed", timeout=120)
    gateway.succeed("jq -e '.state == \"failed\" and (.error | type == \"string\" and length > 0)' /tmp/fleet-config-job.json")
    gateway.succeed("test ! -e /data/config/config.toml")

    gateway.wait_until_succeeds("test -s /tmp/nixstasis-fleet/registration-pending", timeout=120)
    gateway.succeed("test ! -e /data/nixstasis/id")
    gateway.succeed("! systemctl is-active --quiet nixstasis-frpc.service")
    gateway.fail("test -e /tmp/nixstasis-fleet/frpc.started")

    gateway.succeed("touch /tmp/nixstasis-fleet/approve")
    gateway.wait_until_succeeds("test -s /tmp/nixstasis-fleet/registration-approved", timeout=120)
    gateway.wait_until_succeeds("test -s /data/nixstasis/id", timeout=120)
    gateway.wait_until_succeeds("test -s /tmp/nixstasis-fleet/heartbeat-no-lease", timeout=120)
    gateway.succeed("! systemctl is-active --quiet nixstasis-frpc.service")
    gateway.fail("test -e /tmp/nixstasis-fleet/frpc.started")

    gateway.copy_from_host("${testConfig}", "/data/fleet-bootstrap-test-config.toml")
    gateway.copy_from_host("${testImage}", "/tmp/fleet-bootstrap-test.tar.gz")
    gateway.succeed("podman load -i /tmp/fleet-bootstrap-test.tar.gz")
    gateway.succeed("touch /tmp/nixstasis-fleet/grant")
    gateway.wait_until_succeeds("test -s /tmp/nixstasis-fleet/profile", timeout=120)
    gateway.wait_until_succeeds("test -s /tmp/nixstasis-fleet/frpc.started", timeout=120)
    gateway.wait_until_succeeds("systemctl is-active --quiet nixstasis-frpc.service", timeout=120)
    gateway.wait_until_succeeds("test -e /data/fleet-bootstrap-upload-succeeded", timeout=600)
    gateway.succeed("grep -F 'version = 1' /data/config/config.toml")

    gateway.succeed("test \"$(cat /tmp/nixstasis-fleet/profile)\" = 'atomixos-bootstrap:1'")
    gateway.succeed("grep -F 'type = \"http\"' /run/nixstasis/frpc.toml")
    gateway.succeed("grep -F 'subdomain = \"fleet-test-provisioning\"' /run/nixstasis/frpc.toml")
    gateway.succeed("grep -F 'localIP = \"127.0.0.1\"' /run/nixstasis/frpc.toml")
    gateway.succeed("grep -F 'localPort = 8080' /run/nixstasis/frpc.toml")
    gateway.succeed("grep -F 'hostHeaderRewrite = \"localhost\"' /run/nixstasis/frpc.toml")
    gateway.fail("grep -F 'fleet-frp-token' /run/nixstasis/frpc.toml")
    gateway.fail("systemctl show nixstasis-frpc.service -p Environment --value | grep 'FRPS_AUTH_TOKEN=fleet-frp-token'")
    gateway.fail("journalctl -b --no-pager | grep 'fleet-frp-token'")
    gateway.fail("grep -R -F 'fleet-frp-token' /data/nixstasis /tmp/nixstasis-fleet")

    gateway.succeed("touch /tmp/nixstasis-fleet/withdraw")
    gateway.wait_until_succeeds("! systemctl is-active --quiet nixstasis-frpc.service", timeout=120)
    gateway.succeed("test ! -e /run/nixstasis/frpc.env")
    gateway.succeed("systemctl is-active --quiet multi-user.target")
  '';
}
