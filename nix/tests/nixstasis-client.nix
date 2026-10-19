{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  # The NixOS test driver gives node 1's NIC on VLAN n the MAC 52:54:00:12:0n:01.
  lanMac = "52:54:00:12:01:01";
  wanMac = "52:54:00:12:02:01";
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
                self.reply(200, {"data": {"remote_access_token": "frp-token", "remote_access_profile": {"name": "default", "version": 1}, "commands": []}})
                return
            if path == "/mock/frpc":
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
  # Runtime scripts: one passes an allowlisted argument vector, one does not.
  unameScript =
    name: arg:
    pkgs.writeText "${name}.stary" ''
      ---
      name: ${name}
      version: "1"
      schema:
        type: object
        required:
          - out
        properties:
          out:
            type: string
      ---

      def main():
          return {"out": exec_cmd("uname", ["${arg}"])}
    '';
  allowedScript = unameScript "uname-allowed" "-s";
  deniedScript = unameScript "uname-denied" "-r";
  mockFrpc = pkgs.writeShellScriptBin "nixstasis-test-frpc" ''
    set -eu
    test -n "''${FRPS_AUTH_TOKEN:-}"
    ${pkgs.curl}/bin/curl -fsS -X POST http://127.0.0.1:4000/mock/frpc --data-binary started >/dev/null
    while true; do
      ${pkgs.coreutils}/bin/sleep 1
    done
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
      # LAN registers before WAN, and the driver's own eth0 stays up with a MAC,
      # so identity must come from the configured wan interface, not probe order.
      virtualisation.vlans = [
        1
        2
      ];
      atomixos.network = {
        wanInterface = "wan";
        lanInterface = "lan";
        wanLinkMatch.MACAddress = wanMac;
        lanLinkMatch.MACAddress = lanMac;
      };
      system.stateVersion = "25.11";
      atomixos.rauc.enable = lib.mkForce false;
      atomixos.nixstasis = {
        enable = true;
        apiUrl = "http://127.0.0.1:4000";
        allowLoopbackHttp = true;
        pollInterval = "1s";
        frp = {
          serverAddr = "127.0.0.1";
        };
        runtime = {
          execCommands.uname = "/run/current-system/sw/bin/uname";
          execCommandArgs."/run/current-system/sw/bin/uname" = [ [ "-s" ] ];
        };
      };

      environment.systemPackages = [ mockFrpc ];
      systemd.tmpfiles.rules = [
        "d /var/lib/nixstasis/scripts 0755 root root - -"
        "C /var/lib/nixstasis/scripts/uname-allowed.stary 0644 root root - ${allowedScript}"
        "C /var/lib/nixstasis/scripts/uname-denied.stary 0644 root root - ${deniedScript}"
      ];
      systemd.services.nixstasis-poll.environment.NIXSTASIS_FRPC_BINARY_PATH =
        lib.mkForce "${mockFrpc}/bin/nixstasis-test-frpc";

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
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nregister = json.loads(Path('/tmp/nixstasis-mock/register.json').read_text())\nassert register['mac_address'] == '${wanMac}', register\ncreds = json.loads(Path('/data/nixstasis/id').read_text())\nassert creds['mac_address'] == '${wanMac}', creds\nPY")
    gateway.succeed("test \"$(cat /tmp/nixstasis-mock/register.count)\" = 1")
    gateway.succeed("systemctl restart nixstasis-registration.service")
    gateway.succeed("test \"$(cat /tmp/nixstasis-mock/register.count)\" = 1")

    gateway.wait_until_succeeds("test -s /tmp/nixstasis-mock/heartbeat.json", timeout=120)
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nheartbeat = json.loads(Path('/tmp/nixstasis-mock/heartbeat.json').read_text())\nassert 'telemetry' in heartbeat, heartbeat\nassert 'connection_status' in heartbeat, heartbeat\nPY")
    # Only the exact allowlisted argument vector may run.
    gateway.wait_until_succeeds("grep -q '\"Linux\"' /tmp/nixstasis-mock/heartbeat.json", timeout=60)
    gateway.succeed("grep -q 'uname-denied: arguments are not allowlisted' /tmp/nixstasis-mock/heartbeat.json")

    gateway.wait_until_succeeds("journalctl -u nixstasis-poll -b --no-pager | grep 'Server requested remote access'", timeout=120)
    gateway.wait_until_succeeds("systemctl is-active --quiet nixstasis-frpc.service", timeout=120)
    gateway.wait_until_succeeds("test -s /tmp/nixstasis-mock/frpc.started", timeout=120)
    gateway.succeed("systemctl cat nixstasis-frpc.service | grep -E '^EnvironmentFile=.*frpc.env'")
    gateway.succeed("systemctl show nixstasis-frpc.service -p Result --value | grep '^success$'")
    gateway.succeed("systemctl show nixstasis-frpc.service -p ExecMainStatus --value | grep '^0$'")
    gateway.fail("systemctl show nixstasis-frpc.service -p Environment --value | grep 'FRPS_AUTH_TOKEN=frp-token'")
    gateway.fail("journalctl -b --no-pager | grep -E '243/CREDENTIALS|Failed at step CREDENTIALS|start-limit-hit|already loaded or has a fragment file'")
    gateway.fail("journalctl -u nixstasis-frpc -b --no-pager | grep 'frp-token'")

    gateway.succeed("systemctl stop nixstasis-poll.service")
    gateway.succeed("systemctl stop nixstasis-frpc.service")
    gateway.succeed("systemctl show nixstasis-frpc.service -p Result --value | grep '^success$'")
    gateway.succeed("systemctl show nixstasis-frpc.service -p ExecMainStatus --value | grep '^0$'")
    gateway.succeed("systemctl stop nixstasis-mock-api.service")
    gateway.succeed("systemctl is-active multi-user.target")
    gateway.fail("systemctl is-active --quiet nixstasis-poll.service")
  '';
}
