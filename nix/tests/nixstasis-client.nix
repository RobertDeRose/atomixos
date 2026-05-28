{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  mockApi = pkgs.writeText "nixstasis-mock-api.py" ''
    import json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from pathlib import Path
    from urllib.parse import urlparse

    STATE = Path("/tmp/nixstasis-mock")
    STATE.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("content-length", "0"))
            body = self.rfile.read(length)
            path = urlparse(self.path).path
            if path == "/api/v1/devices/register":
                count_path = STATE / "register.count"
                count = int(count_path.read_text() or "0") if count_path.exists() else 0
                count_path.write_text(str(count + 1))
                (STATE / "register.json").write_bytes(body)
                self.reply(201, {"data": {"id": "11111111-1111-4111-8111-111111111111", "api_token": "runtime-token"}})
                return
            if path.startswith("/api/v1/devices/") and path.endswith("/heartbeat"):
                (STATE / "heartbeat.json").write_bytes(body)
                self.reply(200, {"data": {"remote_access_token": "frp-token", "commands": []}})
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
in
nixos-lib.runTest {
  name = "nixstasis-client";

  inherit hostPkgs;

  nodes.gateway =
    { lib, pkgs, ... }:
    {
      _module.args = {
        inherit self;
        developmentMode = false;
        nixstasis = self.inputs.nixstasis;
      };

      imports = [
        ../../modules/base.nix
        qemuModule
      ];

      virtualisation.memorySize = 768;
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      atomixos.nixstasis = {
        enable = true;
        apiUrl = "http://127.0.0.1:4000";
        pollInterval = "1s";
        frp = {
          name = "atom-test";
          serverAddr = "127.0.0.1";
        };
        runtime.execCommands.uname = "/run/current-system/sw/bin/uname";
      };

      systemd.services.nixstasis-mock-api = {
        description = "Mock Nixstasis API";
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
    gateway.wait_for_unit("nixstasis-mock-api.service")
    gateway.wait_for_open_port(4000)

    gateway.wait_until_succeeds("test -s /data/nixstasis/id", timeout=120)
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\ncreds = json.loads(Path('/data/nixstasis/id').read_text())\nassert creds['uuid'] == '11111111-1111-4111-8111-111111111111', creds\nassert creds['token'] == 'runtime-token', creds\nPY")
    gateway.succeed("test -s /tmp/nixstasis-mock/register.json")
    gateway.succeed("test \"$(cat /tmp/nixstasis-mock/register.count)\" = 1")
    gateway.succeed("systemctl restart nixstasis-registration.service")
    gateway.succeed("test \"$(cat /tmp/nixstasis-mock/register.count)\" = 1")

    gateway.wait_until_succeeds("test -s /tmp/nixstasis-mock/heartbeat.json", timeout=120)
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nheartbeat = json.loads(Path('/tmp/nixstasis-mock/heartbeat.json').read_text())\nassert 'telemetry' in heartbeat, heartbeat\nassert 'connection_status' in heartbeat, heartbeat\nPY")

    gateway.wait_until_succeeds("journalctl -u nixstasis-poll -b --no-pager | grep 'Server requested remote access'", timeout=120)
    gateway.wait_until_succeeds("systemctl list-units --all 'nixstasis-frpc.service' --no-legend | grep nixstasis-frpc", timeout=120)
    gateway.fail("systemctl show nixstasis-frpc.service -p Environment --value | grep 'FRPS_AUTH_TOKEN=frp-token'")
    gateway.fail("journalctl -u nixstasis-frpc -b --no-pager | grep 'frp-token'")

    gateway.succeed("systemctl stop nixstasis-mock-api.service")
    gateway.succeed("systemctl is-active multi-user.target")
    gateway.succeed("systemctl is-active nixstasis-poll.service")
  '';
}
