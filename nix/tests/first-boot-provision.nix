{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  quadletSyncScript = pkgs.writeShellScriptBin "quadlet-sync" (
    builtins.readFile ../../scripts/quadlet-sync.sh
  );
  provisionCli = pkgs.runCommand "first-boot-provision" { } ''
    mkdir -p "$out/bin" "$out/share/atomixos"
    install -m0755 ${../../scripts/first-boot-provision.py} "$out/bin/first-boot-provision"
    install -m0644 ${../../docs/src/atomixos.png} "$out/share/atomixos/atomixos.png"
    install -m0644 ${../../schemas/config.schema.json} "$out/share/atomixos/config.schema.json"
  '';
  applyUsersScript = pkgs.writeShellScriptBin "apply-users" ''
    set -euo pipefail
    exec ${pkgs.python3Minimal}/bin/python3 ${../../scripts/apply-users.py} "$@"
  '';
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
        pkgs.gzip
        pkgs.jq
        pkgs.python3Minimal
        pkgs.gnutar
        pkgs.shadow
        pkgs.openssh
        provisionCli
        applyUsersScript
        quadletSyncScript
        pkgs.zstd
      ];

      systemd.tmpfiles.rules = [
        "d /data 0755 root root -"
        "d /etc/containers/systemd 0755 root root -"
      ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    gateway.succeed("cat > /tmp/config.toml <<'EOF'\nversion = 1\n\n[users.admin]\nisAdmin = true\nssh_key = \"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"\n\n[users.guest]\n\n[network.firewall.inbound.wan]\ntcp = [80, 443]\nudp = [1194]\n\n[network.firewall.inbound.lan]\ntcp = [443]\n\n[network.dnsmasq]\ngateway_cidr = \"10.44.0.1/24\"\ndhcp_start = \"10.44.0.10\"\ndhcp_end = \"10.44.0.200\"\ndomain = \"lab\"\ngateway_aliases = [\"atomixos\", \"gateway.lab\"]\nhostname_pattern = \"gateway-{mac}\"\n\n[os_upgrade]\nserver_url = \"https://updates.example.test\"\n\n[health]\nrequired = [\"edgeproxy\", \"myapp\"]\n\n[containers.network.frontend]\n[containers.network.frontend.Network]\nSubnet = \"10.89.0.0/24\"\nGateway = \"10.89.0.1\"\n\n[containers.volume.app-data]\n[containers.volume.app-data.Volume]\nDriver = \"local\"\n\n[containers.build.custom-ws]\n[containers.build.custom-ws.Build]\nFile = \"''${FILES_DIR}/cockpit/Containerfile\"\nImageTag = \"localhost/custom-ws:latest\"\n\n[containers.container.edgeproxy]\nprivileged = true\n\n[containers.container.edgeproxy.Unit]\nDescription = \"Edge Proxy\"\n\n[containers.container.edgeproxy.Container]\nImage = \"ghcr.io/example/edgeproxy:latest\"\nEnvironment = [\"A=1\", \"B=2\"]\nExec = [\"--serve\", \"--port=8080\"]\n\n[containers.container.edgeproxy.Install]\nWantedBy = [\"multi-user.target\"]\n\n[containers.container.myapp]\nprivileged = false\n\n[containers.container.myapp.Unit]\nDescription = \"My App\"\n\n[containers.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nNetwork = [\"frontend\"]\nPublishPort = [\"10080:80\", \"192.168.1.20:10081:81\"]\nVolume = [\"''${FILES_DIR}/app/config.yaml:/app/config.yaml:ro\", \"''${CONFIG_DIR}/local.env:/app/local.env:ro\"]\n\n[containers.container.myapp.Install]\nWantedBy = [\"default.target\"]\nEOF")

    gateway.succeed("printf 'KEY=VALUE\n' >/tmp/local.env")
    gateway.succeed("cat > /tmp/invalid-config.toml <<'EOF'\nversion = 1\n\n[users.admin]\nisAdmin = true\nssh_key = \"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"\n\n[network.firewall.inbound.wan]\ntcp = [443]\n\n[health]\nrequired = [\"missing-service\"]\n\n[containers.container.myapp]\nprivileged = false\n\n[containers.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nEOF")
    gateway.succeed("cat > /tmp/gateway-contained-config.toml <<'EOF'\nversion = 1\n\n[users.admin]\nisAdmin = true\nssh_key = \"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"\n\n[network.firewall.inbound.wan]\ntcp = [443]\n\n[network.dnsmasq]\ngateway_cidr = \"10.44.0.50/24\"\ndhcp_start = \"10.44.0.10\"\ndhcp_end = \"10.44.0.200\"\n\n[health]\nrequired = [\"myapp\"]\n\n[containers.container.myapp]\nprivileged = false\n\n[containers.container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nEOF")

    gateway.succeed("first-boot-provision validate /tmp/config.toml")
    gateway.succeed("first-boot-provision import /tmp/config.toml /data/config")
    gateway.succeed("cp /tmp/local.env /data/config/local.env")
    gateway.succeed("mkdir -p /var/lib/appsvc/.config/containers/systemd")
    gateway.succeed("first-boot-provision sync-quadlet /data/config /etc/containers/systemd /var/lib/appsvc/.config/containers/systemd")

    gateway.succeed("test -f /data/config/config.toml")
    gateway.succeed("test -f /data/config/ssh-authorized-keys/admin")
    gateway.succeed("test -f /data/config/users.json")
    gateway.succeed("test -f /data/config/health-required.json")
    gateway.succeed("test -f /data/config/firewall-inbound.json")
    gateway.succeed("test -f /data/config/lan-settings.json")
    gateway.succeed("test -f /data/config/os-upgrade.json")
    gateway.succeed("test -f /data/config/quadlet-runtime.json")
    gateway.succeed("test -f /data/config/quadlet/edgeproxy.container")
    gateway.succeed("test -f /data/config/quadlet/myapp.container")
    gateway.succeed("test -f /data/config/quadlet/frontend.network")
    gateway.succeed("test -f /data/config/quadlet/app-data.volume")
    gateway.succeed("test -f /data/config/quadlet/custom-ws.build")
    gateway.succeed("test -f /etc/containers/systemd/edgeproxy.container")
    gateway.succeed("test -f /etc/containers/systemd/frontend.network")
    gateway.succeed("test -f /etc/containers/systemd/app-data.volume")
    gateway.succeed("test -f /etc/containers/systemd/custom-ws.build")
    gateway.succeed("test -f /var/lib/appsvc/.config/containers/systemd/myapp.container")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\nrequired = json.loads(Path('/data/config/health-required.json').read_text())\nassert required == ['edgeproxy', 'myapp'], required\nusers = json.loads(Path('/data/config/users.json').read_text())\nassert users['admin']['isAdmin'] is True, users\nassert users['admin']['ssh_key'] == 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example', users\nassert users['guest']['isAdmin'] is False, users\nassert not users['guest']['ssh_key'], users\nfirewall = json.loads(Path('/data/config/firewall-inbound.json').read_text())\nassert firewall == {\n    'wan': {'tcp': [80, 443], 'udp': [1194]},\n    'lan': {'tcp': [443]},\n}, firewall\nos_upgrade = json.loads(Path('/data/config/os-upgrade.json').read_text())\nassert os_upgrade == {'server_url': 'https://updates.example.test'}, os_upgrade\nlan = json.loads(Path('/data/config/lan-settings.json').read_text())\nassert lan == {\n    'gateway_cidr': '10.44.0.1/24',\n    'gateway_ip': '10.44.0.1',\n    'subnet_cidr': '10.44.0.0/24',\n    'netmask': '255.255.255.0',\n    'dhcp_start': '10.44.0.10',\n    'dhcp_end': '10.44.0.200',\n    'domain': 'lab',\n    'hostname_pattern': 'gateway-{mac}',\n    'gateway_aliases': ['atomixos', 'gateway.lab'],\n}, lan\nruntime = json.loads(Path('/data/config/quadlet-runtime.json').read_text())\nassert runtime['app_user'] == 'appsvc', runtime\nassert runtime['rootless_network'] == 'pasta', runtime\nassert runtime['units'] == [\n    {'name': 'edgeproxy', 'filename': 'edgeproxy.container', 'service': 'edgeproxy.service', 'mode': 'rootful'},\n    {'name': 'myapp', 'filename': 'myapp.container', 'service': 'myapp.service', 'mode': 'rootless'},\n    {'name': 'frontend', 'filename': 'frontend.network', 'service': 'frontend-network.service', 'mode': 'rootful'},\n    {'name': 'app-data', 'filename': 'app-data.volume', 'service': 'app-data-volume.service', 'mode': 'rootful'},\n    {'name': 'custom-ws', 'filename': 'custom-ws.build', 'service': 'custom-ws-build.service', 'mode': 'rootful'},\n], runtime['units']\nPY")
    gateway.succeed("grep -c '^Environment=' /data/config/quadlet/edgeproxy.container | grep '^2$'")
    gateway.succeed("grep -c '^Exec=' /data/config/quadlet/edgeproxy.container | grep '^2$'")
    gateway.succeed("grep '^Network=host$' /data/config/quadlet/edgeproxy.container")
    gateway.succeed("grep '^Exec=--serve$' /data/config/quadlet/edgeproxy.container")
    gateway.succeed("grep '^Exec=--port=8080$' /data/config/quadlet/edgeproxy.container")
    gateway.succeed("grep -c '^Network=' /data/config/quadlet/myapp.container | grep '^1$'")
    gateway.succeed("grep '^Network=pasta$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^PublishPort=127.0.0.1:10080:80$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^PublishPort=127.0.0.1:10081:81$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^Volume=/data/config/files/app/config.yaml:/app/config.yaml:ro$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^Volume=/data/config/local.env:/app/local.env:ro$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^Subnet=10.89.0.0/24$' /data/config/quadlet/frontend.network")
    gateway.succeed("grep '^Gateway=10.89.0.1$' /data/config/quadlet/frontend.network")
    gateway.succeed("grep '^\[Network\]$' /data/config/quadlet/frontend.network")
    gateway.succeed("grep '^Driver=local$' /data/config/quadlet/app-data.volume")
    gateway.succeed("grep '^\[Volume\]$' /data/config/quadlet/app-data.volume")
    gateway.succeed("grep '^\[Build\]$' /data/config/quadlet/custom-ws.build")
    gateway.succeed("grep '^File=/data/config/files/cockpit/Containerfile$' /data/config/quadlet/custom-ws.build")
    gateway.succeed("grep '^ImageTag=localhost/custom-ws:latest$' /data/config/quadlet/custom-ws.build")

    gateway.succeed("mkdir -p /tmp/lan-apply/bin /tmp/lan-apply/etc/systemd/network/20-lan.network.d /tmp/lan-apply/sys/class/net/eth1")
    gateway.succeed("printf '00:11:22:33:44:55\n' >/tmp/lan-apply/sys/class/net/eth1/address")
    gateway.succeed("ln -s /tmp/lan-apply/store-network /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("ln -s /tmp/lan-apply/store-dnsmasq /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("ln -s /tmp/lan-apply/store-hosts /tmp/lan-apply/dnsmasq-hosts")
    gateway.succeed("ln -s /tmp/lan-apply/store-chrony /tmp/lan-apply/chrony-lan.conf")
    gateway.succeed("printf '127.0.0.1 localhost\n10.0.0.2 old # ATOMIXOS_LAN_GATEWAY\n' >/tmp/lan-apply/etc-hosts")
    gateway.succeed("cat > /tmp/lan-apply/bin/networkctl <<'EOF'\n#!/usr/bin/env bash\nprintf '%s\n' \"$*\" >>/tmp/lan-apply/networkctl.log\nEOF\nchmod +x /tmp/lan-apply/bin/networkctl")
    gateway.succeed("cat > /tmp/lan-apply/bin/systemctl <<'EOF'\n#!/usr/bin/env bash\nprintf '%s\n' \"$*\" >>/tmp/lan-apply/systemctl.log\nEOF\nchmod +x /tmp/lan-apply/bin/systemctl")
    gateway.succeed("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/data/config/lan-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py}")
    gateway.succeed("test ! -L /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("test ! -L /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^Address=10.44.0.1/24$' /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("grep '^dhcp-range=10.44.0.10,10.44.0.200,255.255.255.0,24h$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^domain=lab$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^local=/lab/$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.fail("grep '^interface=' /tmp/lan-apply/atomixos-lan.conf")
    gateway.fail("grep '^bind-dynamic$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.fail("grep '^local-service$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.fail("grep '^no-resolv$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.fail("grep '^port=53$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^10.44.0.1 gateway-001122334455 gateway-001122334455.lab$' /tmp/lan-apply/dnsmasq-hosts")
    gateway.succeed("grep '^10.44.0.1 atomixos atomixos.lab$' /tmp/lan-apply/dnsmasq-hosts")
    gateway.succeed("grep '^10.44.0.1 gateway.lab$' /tmp/lan-apply/dnsmasq-hosts")
    gateway.succeed("grep '^allow 10.44.0.0/24$' /tmp/lan-apply/chrony-lan.conf")
    gateway.succeed("grep '^127.0.0.1 localhost$' /tmp/lan-apply/etc-hosts")
    gateway.succeed("grep '^10.44.0.1 gateway-001122334455 gateway-001122334455.lab # ATOMIXOS_LAN_GATEWAY$' /tmp/lan-apply/etc-hosts")
    gateway.succeed("grep '^10.44.0.1 atomixos atomixos.lab # ATOMIXOS_LAN_GATEWAY$' /tmp/lan-apply/etc-hosts")
    gateway.succeed("grep '^10.44.0.1 gateway.lab # ATOMIXOS_LAN_GATEWAY$' /tmp/lan-apply/etc-hosts")
    gateway.succeed("grep '^reload$' /tmp/lan-apply/networkctl.log")
    gateway.succeed("grep '^try-restart systemd-networkd.service$' /tmp/lan-apply/systemctl.log")
    gateway.succeed("grep '^try-restart dnsmasq.service$' /tmp/lan-apply/systemctl.log")
    gateway.succeed("grep '^try-restart chronyd.service$' /tmp/lan-apply/systemctl.log")
    gateway.succeed("rm -f /tmp/lan-apply/networkctl.log /tmp/lan-apply/systemctl.log")
    gateway.succeed("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/data/config/lan-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py}")
    gateway.succeed("test ! -e /tmp/lan-apply/networkctl.log")
    gateway.succeed("test ! -e /tmp/lan-apply/systemctl.log")
    gateway.succeed("cat > /tmp/lan-apply/bin/networkctl <<'EOF'\n#!/usr/bin/env bash\necho reload failed >&2\nexit 1\nEOF\nchmod +x /tmp/lan-apply/bin/networkctl")
    gateway.succeed("printf '{\"gateway_cidr\":\"10.44.1.1/24\",\"gateway_ip\":\"10.44.1.1\",\"subnet_cidr\":\"10.44.1.0/24\",\"netmask\":\"255.255.255.0\",\"dhcp_start\":\"10.44.1.10\",\"dhcp_end\":\"10.44.1.200\",\"domain\":\"lab\",\"hostname_pattern\":\"gateway-{mac}\",\"gateway_aliases\":[\"atomixos\"]}\n' >/tmp/lan-apply/restart-fail-settings.json")
    gateway.fail("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/tmp/lan-apply/restart-fail-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py} >/tmp/lan-apply/restart-fail.out 2>/tmp/lan-apply/restart-fail.err")
    gateway.succeed("grep -F '[lan-gateway-apply] command failed: networkctl reload: reload failed' /tmp/lan-apply/restart-fail.err")

    gateway.succeed("rm -rf /tmp/quadlet-sync && mkdir -p /tmp/quadlet-sync/bin /var/lib/appsvc/.config/containers/systemd /var/lib/appsvc")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/chronyc <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >>/tmp/quadlet-sync/chronyc.log\ncase \"$*\" in\n  tracking) printf 'Reference ID    : 7F7F0101 ()\\nLeap status     : Not synchronised\\n'; exit 0 ;;&\n  'waitsync 1 1') exit 1 ;;&\n  *) echo unexpected chronyc invocation >&2; exit 1 ;;&\nesac\nEOF\nchmod +x /tmp/quadlet-sync/bin/chronyc")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/id <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nif [ \"$#\" -eq 2 ] && [ \"$1\" = \"-u\" ] && [ \"$2\" = \"appsvc\" ]; then\n  echo 999\n  exit 0\nfi\necho unexpected id invocation >&2\nexit 1\nEOF\nchmod +x /tmp/quadlet-sync/bin/id")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/chown <<'EOF'\n#!/usr/bin/env bash\nexit 0\nEOF\nchmod +x /tmp/quadlet-sync/bin/chown")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/loginctl <<'EOF'\n#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >>/tmp/quadlet-sync/loginctl.log\nEOF\nchmod +x /tmp/quadlet-sync/bin/loginctl")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/runuser <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >>/tmp/quadlet-sync/runuser.log\nwhile [ \"$1\" != \"--\" ]; do\n  shift\ndone\nshift\nif [ \"$1\" = \"env\" ]; then\n  shift\n  while [ \"$#\" -gt 0 ] && [[ \"$1\" == *=* ]]; do\n    export \"$1\"\n    shift\n  done\nfi\nif [ \"$1\" = \"systemctl\" ]; then\n  shift\n  exec /tmp/quadlet-sync/bin/systemctl \"$@\"\nfi\nexec \"$@\"\nEOF\nchmod +x /tmp/quadlet-sync/bin/runuser")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/systemctl <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >>/tmp/quadlet-sync/systemctl.log\ncase \"$*\" in\n  'start user@999.service'|'daemon-reload'|'--user daemon-reload') exit 0 ;;&\n  'restart custom-ws-build.service'|'restart edgeproxy.service'|'--user restart myapp.service'|'restart frontend-network.service'|'restart app-data-volume.service') exit 1 ;;&\n  *) echo unexpected systemctl invocation >&2; exit 1 ;;&\nesac\nEOF\nchmod +x /tmp/quadlet-sync/bin/systemctl")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/first-boot-provision <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\\n' \"$*\" >>/tmp/quadlet-sync/provision.log\nif [ \"$1\" = \"sync-quadlet\" ]; then\n  exit 0\nfi\necho unexpected first-boot-provision invocation >&2\nexit 1\nEOF\nchmod +x /tmp/quadlet-sync/bin/first-boot-provision")
    gateway.succeed("ATOMIXOS_CHRONY_WAIT_TIMEOUT_SECONDS=1 ATOMIXOS_CHRONY_WAIT_ATTEMPTS=2 ATOMIXOS_ALLOW_UNSAFE_PATH=1 PATH=/tmp/quadlet-sync/bin:$PATH quadlet-sync >/tmp/quadlet-sync/output.log 2>&1 || (cat /tmp/quadlet-sync/output.log >&2; false)")
    gateway.succeed("grep -c '^waitsync 1 1$' /tmp/quadlet-sync/chronyc.log | grep '^2$'")
    gateway.succeed("grep 'WARNING: clock did not synchronize after bounded wait; continuing' /tmp/quadlet-sync/output.log")
    gateway.succeed("grep '^sync-quadlet /data/config /etc/containers/systemd /var/lib/appsvc/.config/containers/systemd$' /tmp/quadlet-sync/provision.log")
    gateway.succeed("grep '^enable-linger appsvc$' /tmp/quadlet-sync/loginctl.log")
    gateway.succeed("grep '^start user@999.service$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("grep '^daemon-reload$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("grep '^--user daemon-reload$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("python3 - <<'PY'\nfrom pathlib import Path\nlines = Path('/tmp/quadlet-sync/systemctl.log').read_text().splitlines()\nbuild = lines.index('restart custom-ws-build.service')\nedge = lines.index('restart edgeproxy.service')\nassert build < edge, lines\nPY")
    gateway.succeed("grep '^restart edgeproxy.service$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("grep '^--user restart myapp.service$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("grep 'PATH=/run/wrappers/bin:/run/current-system/sw/bin:/tmp/quadlet-sync/bin:' /tmp/quadlet-sync/runuser.log")
    gateway.succeed("grep 'WARNING: units failed to start after sync: custom-ws-build.service edgeproxy.service frontend-network.service app-data-volume.service myapp.service' /tmp/quadlet-sync/output.log")
    gateway.succeed("grep 'continuing so the provisioned system remains debuggable' /tmp/quadlet-sync/output.log")
    gateway.succeed("rm -f /tmp/quadlet-sync/chronyc.log /tmp/quadlet-sync/loginctl.log /tmp/quadlet-sync/runuser.log /tmp/quadlet-sync/systemctl.log /tmp/quadlet-sync/provision.log")
    gateway.succeed("cat > /data/config/quadlet-runtime.json <<'EOF'\n{\"app_user\":\"appsvc\",\"rootless_network\":\"pasta\",\"units\":[{\"name\":\"edgeproxy\",\"filename\":\"edgeproxy.container\",\"service\":\"edgeproxy.service\",\"mode\":\"rootful\"}]}\nEOF")
    gateway.succeed("ATOMIXOS_CHRONY_WAIT_TIMEOUT_SECONDS=1 ATOMIXOS_CHRONY_WAIT_ATTEMPTS=1 ATOMIXOS_ALLOW_UNSAFE_PATH=1 PATH=/tmp/quadlet-sync/bin:$PATH quadlet-sync >/tmp/quadlet-sync/rootful-only.log 2>&1 || (cat /tmp/quadlet-sync/rootful-only.log >&2; false)")
    gateway.succeed("grep '^sync-quadlet /data/config /etc/containers/systemd /var/lib/appsvc/.config/containers/systemd$' /tmp/quadlet-sync/provision.log")
    gateway.succeed("grep '^daemon-reload$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("grep '^restart edgeproxy.service$' /tmp/quadlet-sync/systemctl.log")
    gateway.succeed("test ! -e /tmp/quadlet-sync/loginctl.log")
    gateway.succeed("test ! -e /tmp/quadlet-sync/runuser.log")
    gateway.succeed("cat > /tmp/quadlet-sync/bin/first-boot-provision <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nif [ \"$1\" = \"sync-quadlet\" ]; then\n  exit 1\nfi\necho unexpected first-boot-provision invocation >&2\nexit 1\nEOF\nchmod +x /tmp/quadlet-sync/bin/first-boot-provision")
    gateway.fail("ATOMIXOS_ALLOW_UNSAFE_PATH=1 PATH=/tmp/quadlet-sync/bin:$PATH quadlet-sync >/tmp/quadlet-sync/fatal.log 2>&1")
    gateway.succeed("printf '{bad json\n' >/data/config/quadlet-runtime.json")
    gateway.fail("quadlet-sync >/tmp/quadlet-sync/invalid-runtime.log 2>&1")
    gateway.succeed("grep 'Invalid runtime metadata: /data/config/quadlet-runtime.json' /tmp/quadlet-sync/invalid-runtime.log")

    gateway.succeed("rm -rf /tmp/bootstrap-root")
    gateway.succeed("printf '{bad json\n' >/tmp/lan-apply/bad-lan-settings.json")
    gateway.fail("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/tmp/lan-apply/bad-lan-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py} >/tmp/lan-apply/bad-json.out 2>/tmp/lan-apply/bad-json.err")
    gateway.succeed("grep -F '[lan-gateway-apply] invalid JSON in /tmp/lan-apply/bad-lan-settings.json:' /tmp/lan-apply/bad-json.err")
    gateway.succeed("printf '{\"gateway_ip\":\"10.44.0.1\"}\n' >/tmp/lan-apply/missing-lan-settings.json")
    gateway.fail("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/tmp/lan-apply/missing-lan-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py} >/tmp/lan-apply/missing-key.out 2>/tmp/lan-apply/missing-key.err")
    gateway.succeed("grep -F \"[lan-gateway-apply] missing required key 'gateway_cidr' in /tmp/lan-apply/missing-lan-settings.json\" /tmp/lan-apply/missing-key.err")
    gateway.succeed("printf '{\"gateway_cidr\":\"10.44.0.1/24\",\"gateway_ip\":\"10.44.0.1\",\"subnet_cidr\":\"10.44.0.0/24\",\"netmask\":\"255.255.255.0\",\"dhcp_start\":\"10.44.0.10\",\"dhcp_end\":\"10.44.0.200\",\"domain\":\"lab bad\",\"gateway_aliases\":[\"atomixos\"]}\n' >/tmp/lan-apply/invalid-domain-settings.json")
    gateway.fail("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/tmp/lan-apply/invalid-domain-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py} >/tmp/lan-apply/invalid-domain.out 2>/tmp/lan-apply/invalid-domain.err")
    gateway.succeed("grep -F \"[lan-gateway-apply] domain must be a valid DNS name in /tmp/lan-apply/invalid-domain-settings.json: 'lab bad'\" /tmp/lan-apply/invalid-domain.err")
    gateway.succeed("printf '{\"gateway_cidr\":\"10.44.0.1/24\",\"gateway_ip\":\"10.44.0.1\",\"subnet_cidr\":\"10.44.0.0/24\",\"netmask\":\"255.255.255.0\",\"dhcp_start\":\"10.44.0.1\",\"dhcp_end\":\"10.44.0.200\",\"domain\":\"lab\",\"gateway_aliases\":[\"atomixos\"]}\n' >/tmp/lan-apply/gateway-dhcp-settings.json")
    gateway.fail("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/tmp/lan-apply/gateway-dhcp-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net python3 ${../../scripts/lan-gateway-apply.py} >/tmp/lan-apply/gateway-dhcp.out 2>/tmp/lan-apply/gateway-dhcp.err")
    gateway.succeed("grep -F \"[lan-gateway-apply] dhcp_start and dhcp_end must not include gateway_ip in /tmp/lan-apply/gateway-dhcp-settings.json\" /tmp/lan-apply/gateway-dhcp.err")

    # ── apply-users: create managed users from users.json ──
    gateway.succeed("mkdir -p /tmp/apply-users-test")
    gateway.succeed("cat > /tmp/apply-users-test/users.json <<'EOF'\n{\"admin\": {\"isAdmin\": true, \"ssh_key\": \"ssh-ed25519 AAAAC3test admin@test\"}, \"operator\": {\"isAdmin\": true, \"ssh_key\": \"ssh-ed25519 AAAAC3op op@test\"}, \"viewer\": {\"isAdmin\": false, \"ssh_key\": \"\"}}\nEOF")
    gateway.succeed("ATOMIXOS_USERS_JSON=/tmp/apply-users-test/users.json ATOMIXOS_MANAGED_STATE=/tmp/apply-users-test/managed-users.json python3 ${../../scripts/apply-users.py}")
    gateway.succeed("id operator")
    gateway.succeed("id viewer")
    gateway.succeed("id -nG operator | grep -w wheel")
    gateway.fail("id -nG viewer | grep -w wheel")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nmanaged = json.loads(Path('/tmp/apply-users-test/managed-users.json').read_text())\nassert sorted(managed) == ['operator', 'viewer'], managed\nPY")

    # ── apply-users: lock removed users ──
    gateway.succeed("cat > /tmp/apply-users-test/users.json <<'EOF'\n{\"admin\": {\"isAdmin\": true, \"ssh_key\": \"ssh-ed25519 AAAAC3test admin@test\"}, \"viewer\": {\"isAdmin\": false, \"ssh_key\": \"\"}}\nEOF")
    gateway.succeed("ATOMIXOS_USERS_JSON=/tmp/apply-users-test/users.json ATOMIXOS_MANAGED_STATE=/tmp/apply-users-test/managed-users.json python3 ${../../scripts/apply-users.py}")
    gateway.succeed("getent shadow operator | grep -F '!'")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nmanaged = json.loads(Path('/tmp/apply-users-test/managed-users.json').read_text())\nassert sorted(managed) == ['viewer'], managed\nPY")

    # ── apply-users: idempotent re-run does not fail ──
    gateway.succeed("ATOMIXOS_USERS_JSON=/tmp/apply-users-test/users.json ATOMIXOS_MANAGED_STATE=/tmp/apply-users-test/managed-users.json python3 ${../../scripts/apply-users.py}")

    # ── apply-users: skips gracefully when no users.json ──
    gateway.succeed("ATOMIXOS_USERS_JSON=/tmp/apply-users-test/nonexistent.json ATOMIXOS_MANAGED_STATE=/tmp/apply-users-test/managed-users.json python3 ${../../scripts/apply-users.py}")

    # ── apply-users: refuses to touch protected users ──
    gateway.succeed("cat > /tmp/apply-users-test/users-root.json <<'EOF'\n{\"admin\": {\"isAdmin\": true, \"ssh_key\": \"ssh-ed25519 AAAAC3test admin@test\"}, \"root\": {\"isAdmin\": true, \"ssh_key\": \"ssh-ed25519 AAAAC3root root@test\"}}\nEOF")
    gateway.succeed("ATOMIXOS_USERS_JSON=/tmp/apply-users-test/users-root.json ATOMIXOS_MANAGED_STATE=/tmp/apply-users-test/managed-users-root.json python3 ${../../scripts/apply-users.py}")
    gateway.fail("grep '^root:.*:/bin/sh$' /etc/passwd")
    gateway.succeed("rm -rf /tmp/bootstrap-root")
    gateway.succeed("mkdir -p /tmp/bootstrap-root")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root /tmp/bootstrap-output.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS http://127.0.0.1:18080/assets/atomixos.png >/tmp/bootstrap-logo.png")
    gateway.succeed("curl -fsS http://127.0.0.1:18080/ >/tmp/bootstrap-index.html")
    gateway.succeed("test -s /tmp/bootstrap-logo.png")
    gateway.fail("grep 'accept=' /tmp/bootstrap-index.html")
    gateway.succeed("curl -fsS -F config_file=@/tmp/config.toml http://127.0.0.1:18080/apply >/tmp/bootstrap-response.html")
    gateway.succeed("test -f /tmp/bootstrap-root/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root/ssh-authorized-keys/admin")
    gateway.succeed("test -f /tmp/bootstrap-root/health-required.json")
    gateway.succeed("grep 'src=\"/assets/atomixos.png\"' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'downloadAppliedConfig()' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'version = 1' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'ghcr.io/example/edgeproxy:latest' /tmp/bootstrap-response.html")
    gateway.succeed("kill -0 $(cat /tmp/bootstrap.pid)")
    gateway.succeed("rm -rf /tmp/bootstrap-root-api && mkdir -p /tmp/bootstrap-root-api")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-api /tmp/bootstrap-output-api.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain; charset=utf-8' --data-binary @/tmp/config.toml http://127.0.0.1:18080/api/config >/tmp/bootstrap-api-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\npayload = json.loads(Path('/tmp/bootstrap-api-response.json').read_text())\nassert payload == {'ok': True, 'message': 'Configuration applied.'}, payload\nPY")
    gateway.succeed("test -f /tmp/bootstrap-root-api/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root-api/ssh-authorized-keys/admin")
    gateway.succeed("test -f /tmp/bootstrap-root-api/health-required.json")
    gateway.succeed("kill -0 $(cat /tmp/bootstrap.pid)")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.succeed("rm -rf /tmp/bootstrap-root-api-hook && mkdir -p /tmp/bootstrap-root-api-hook")
    gateway.succeed("cat > /tmp/bootstrap-post-response-hook <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\ntouch /tmp/bootstrap-post-response-hook-ran\nkill -TERM \"$(cat /tmp/bootstrap.pid)\"\nEOF\nchmod +x /tmp/bootstrap-post-response-hook")
    gateway.succeed("ATOMIXOS_BOOTSTRAP_POST_RESPONSE=/tmp/bootstrap-post-response-hook first-boot-provision serve /tmp/bootstrap-root-api-hook /tmp/bootstrap-output-api-hook.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain; charset=utf-8' --data-binary @/tmp/config.toml http://127.0.0.1:18080/api/config >/tmp/bootstrap-api-hook-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\npayload = json.loads(Path('/tmp/bootstrap-api-hook-response.json').read_text())\nassert payload == {'ok': True, 'message': 'Configuration applied.'}, payload\nPY")
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-post-response-hook-ran", timeout=30)
    gateway.wait_until_fails("kill -0 $(cat /tmp/bootstrap.pid)", timeout=30)

    gateway.succeed("rm -rf /tmp/bootstrap-root-generate && mkdir -p /tmp/bootstrap-root-generate")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-generate /tmp/bootstrap-output-generate.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS --data-urlencode 'ssh_keys=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example' --data-urlencode 'wan_tcp=443' --data-urlencode 'wan_udp=1194' --data-urlencode 'required=' --data-urlencode 'quadlet=[container.myapp]\nprivileged = false\n\n[container.myapp.Unit]\nDescription = \"My App\"\n\n[container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nPublishPort = [\"10080:8080\"]\n\n[container.myapp.Install]\nWantedBy = [\"default.target\"]' http://127.0.0.1:18080/generate >/tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'downloadAppliedConfig()' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'version = 1' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'ghcr.io/example/myapp:latest' /tmp/bootstrap-generate-response.html")
    gateway.succeed("python3 - <<'PY'\nimport json\nimport tomllib\nfrom pathlib import Path\n\nconfig = tomllib.loads(Path('/tmp/bootstrap-root-generate/config.toml').read_text())\nassert config['health']['required'] == ['myapp'], config['health']['required']\nassert 'os_upgrade' not in config, config\nrequired = json.loads(Path('/tmp/bootstrap-root-generate/health-required.json').read_text())\nassert required == ['myapp'], required\nPY")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.succeed("rm -rf /tmp/bootstrap-root-invalid && mkdir -p /tmp/bootstrap-root-invalid")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-invalid /tmp/bootstrap-output-invalid.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -F config_file=@/tmp/invalid-config.toml http://127.0.0.1:18080/apply >/tmp/bootstrap-invalid-response.html")
    gateway.succeed("grep 'missing-service' /tmp/bootstrap-invalid-response.html")
    gateway.succeed("grep 'container.myapp' /tmp/bootstrap-invalid-response.html")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.succeed("rm -rf /tmp/bundle-root && mkdir -p /tmp/bundle-root/files/app")
    gateway.succeed("cp /tmp/config.toml /tmp/bundle-root/config.toml")
    gateway.succeed("printf 'hello: world\n' >/tmp/bundle-root/files/app/config.yaml")
    gateway.succeed("tar -C /tmp/bundle-root -czf /tmp/config.tar.gz config.toml files")
    gateway.succeed("first-boot-provision validate /tmp/config.tar.gz")
    gateway.succeed("rm -rf /tmp/import-bundle-gz && mkdir -p /tmp/import-bundle-gz")
    gateway.succeed("first-boot-provision import /tmp/config.tar.gz /tmp/import-bundle-gz")
    gateway.succeed("test -f /tmp/import-bundle-gz/config.toml")
    gateway.succeed("test -f /tmp/import-bundle-gz/files/app/config.yaml")

    gateway.succeed("tar -C /tmp/bundle-root -cf /tmp/config.tar config.toml files")
    gateway.succeed("zstd -q -f /tmp/config.tar -o /tmp/config.tar.zst")
    gateway.succeed("first-boot-provision validate /tmp/config.tar.zst")
    gateway.succeed("rm -rf /tmp/import-bundle-zst && mkdir -p /tmp/import-bundle-zst")
    gateway.succeed("first-boot-provision import /tmp/config.tar.zst /tmp/import-bundle-zst")
    gateway.succeed("test -f /tmp/import-bundle-zst/config.toml")
    gateway.succeed("test -f /tmp/import-bundle-zst/files/app/config.yaml")

    gateway.succeed("tar --zstd -cf /tmp/config-dot.tar.zstd -C /tmp/bundle-root .")
    gateway.succeed("first-boot-provision validate /tmp/config-dot.tar.zstd")
    gateway.succeed("rm -rf /tmp/import-bundle-dot-zstd && mkdir -p /tmp/import-bundle-dot-zstd")
    gateway.succeed("first-boot-provision import /tmp/config-dot.tar.zstd /tmp/import-bundle-dot-zstd")
    gateway.succeed("test -f /tmp/import-bundle-dot-zstd/config.toml")
    gateway.succeed("test -f /tmp/import-bundle-dot-zstd/files/app/config.yaml")

    gateway.succeed("rm -rf /tmp/bootstrap-root-zstd-upload && mkdir -p /tmp/bootstrap-root-zstd-upload")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-zstd-upload /tmp/bootstrap-output-zstd-upload.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -F config_file=@/tmp/config-dot.tar.zstd http://127.0.0.1:18080/apply >/tmp/bootstrap-zstd-upload-response.html")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-zstd-upload-response.html")
    gateway.succeed("test -f /tmp/bootstrap-root-zstd-upload/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root-zstd-upload/files/app/config.yaml")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.fail("first-boot-provision validate /tmp/invalid-config.toml")
    gateway.fail("first-boot-provision validate /tmp/gateway-contained-config.toml >/tmp/gateway-contained.out 2>/tmp/gateway-contained.err")
    gateway.succeed("grep 'network.dnsmasq.dhcp_start and network.dnsmasq.dhcp_end must not include the gateway IP' /tmp/gateway-contained.err")

    # ── T030: re-apply authentication ──
    # Set up a provisioned config root with known admin key
    gateway.succeed("rm -rf /tmp/auth-root && mkdir -p /tmp/auth-root")
    gateway.succeed("ssh-keygen -t ed25519 -N \"\" -f /tmp/auth-test-key -q")
    gateway.succeed("first-boot-provision import /tmp/config.toml /tmp/auth-root")

    # Overwrite admin authorized key with our test key
    gateway.succeed("cat /tmp/auth-test-key.pub > /tmp/auth-root/ssh-authorized-keys/admin")

    # Start bootstrap server pointing at provisioned root
    gateway.succeed("first-boot-provision serve /tmp/auth-root --host 127.0.0.1 --port 18081 >/tmp/auth-bootstrap.log 2>&1 & echo $! >/tmp/auth-bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18081'", timeout=30)

    # Unauthenticated POST to provisioned device must be rejected (401)
    gateway.succeed("curl -s -o /tmp/auth-unauth-response.json -w '%{http_code}' -H 'Content-Type: text/plain' --data-binary @/tmp/config.toml http://127.0.0.1:18081/api/config > /tmp/auth-unauth-code")
    gateway.succeed("grep '^401$' /tmp/auth-unauth-code")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-unauth-response.json').read_text())\nassert resp['ok'] is False, resp\nassert 'authentication required' in resp['error'], resp\nPY")

    # GET /api/nonce on provisioned device returns a nonce
    gateway.succeed("curl -fsS http://127.0.0.1:18081/api/nonce > /tmp/auth-nonce-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-nonce-response.json').read_text())\nassert resp['ok'] is True, resp\nassert len(resp['nonce']) > 20, resp\nPath('/tmp/auth-nonce.txt').write_text(resp['nonce'])\nPY")

    # Sign the nonce with our test key
    gateway.succeed("cat /tmp/auth-nonce.txt | ssh-keygen -Y sign -f /tmp/auth-test-key -n atomixos-reapply > /tmp/auth-signature.pem")
    gateway.succeed("python3 - <<'PY'\nimport base64\nfrom pathlib import Path\nsig = Path('/tmp/auth-signature.pem').read_bytes()\nPath('/tmp/auth-signature-b64.txt').write_text(base64.b64encode(sig).decode())\nnonce = Path('/tmp/auth-nonce.txt').read_text().strip()\nPath('/tmp/auth-nonce-clean.txt').write_text(nonce)\nPY")

    # Authenticated POST should succeed
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain' -H \"X-Atomicnix-Nonce: $(cat /tmp/auth-nonce-clean.txt)\" -H \"X-Atomicnix-Signature: $(cat /tmp/auth-signature-b64.txt)\" --data-binary @/tmp/config.toml http://127.0.0.1:18081/api/config > /tmp/auth-success-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-success-response.json').read_text())\nassert resp['ok'] is True, resp\nassert resp['message'] == 'Configuration applied.', resp\nPY")

    # Nonce replay must fail (nonce was consumed)
    gateway.succeed("curl -s -o /tmp/auth-replay-response.json -w '%{http_code}' -H 'Content-Type: text/plain' -H \"X-Atomicnix-Nonce: $(cat /tmp/auth-nonce-clean.txt)\" -H \"X-Atomicnix-Signature: $(cat /tmp/auth-signature-b64.txt)\" --data-binary @/tmp/config.toml http://127.0.0.1:18081/api/config > /tmp/auth-replay-code")
    gateway.succeed("grep '^401$' /tmp/auth-replay-code")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-replay-response.json').read_text())\nassert 'expired' in resp['error'], resp\nPY")

    # GET /api/nonce on UNPROVISIONED device returns empty nonce
    gateway.succeed("kill $(cat /tmp/auth-bootstrap.pid)")
    gateway.succeed("rm -rf /tmp/auth-root-empty && mkdir -p /tmp/auth-root-empty")
    gateway.succeed("first-boot-provision serve /tmp/auth-root-empty --host 127.0.0.1 --port 18081 >/tmp/auth-bootstrap2.log 2>&1 & echo $! >/tmp/auth-bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18081'", timeout=30)
    gateway.succeed("curl -fsS http://127.0.0.1:18081/api/nonce > /tmp/auth-nonce-empty.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-nonce-empty.json').read_text())\nassert resp['ok'] is True, resp\nassert resp['nonce'] == \"\", resp\nassert 'unprovisioned' in resp.get('message', \"\"), resp\nPY")

    # Unauthenticated POST to unprovisioned device should succeed
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain' --data-binary @/tmp/config.toml http://127.0.0.1:18081/api/config > /tmp/auth-fresh-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/auth-fresh-response.json').read_text())\nassert resp['ok'] is True, resp\nPY")
    gateway.succeed("kill $(cat /tmp/auth-bootstrap.pid)")

    # ── T040: atomic candidate apply ──
    # Start with a provisioned root
    gateway.succeed("rm -rf /tmp/atomic-root /tmp/atomic-root-candidate /tmp/atomic-root-rollback && mkdir -p /tmp/atomic-root")
    gateway.succeed("first-boot-provision import /tmp/config.toml /tmp/atomic-root")
    gateway.succeed("test -f /tmp/atomic-root/config.toml")

    # Re-import via bootstrap server should create rollback
    gateway.succeed("ssh-keygen -t ed25519 -N \"\" -f /tmp/atomic-key -q")
    gateway.succeed("cat /tmp/atomic-key.pub > /tmp/atomic-root/ssh-authorized-keys/admin")
    gateway.succeed("first-boot-provision serve /tmp/atomic-root --host 127.0.0.1 --port 18082 >/tmp/atomic-bootstrap.log 2>&1 & echo $! >/tmp/atomic-bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18082'", timeout=30)

    # Get nonce and sign
    gateway.succeed("curl -fsS http://127.0.0.1:18082/api/nonce > /tmp/atomic-nonce.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nnonce = json.loads(Path('/tmp/atomic-nonce.json').read_text())['nonce']\nPath('/tmp/atomic-nonce.txt').write_text(nonce)\nPY")
    gateway.succeed("cat /tmp/atomic-nonce.txt | ssh-keygen -Y sign -f /tmp/atomic-key -n atomixos-reapply > /tmp/atomic-sig.pem")
    gateway.succeed("python3 - <<'PY'\nimport base64\nfrom pathlib import Path\nsig = Path('/tmp/atomic-sig.pem').read_bytes()\nPath('/tmp/atomic-sig-b64.txt').write_text(base64.b64encode(sig).decode())\nPY")

    # Authenticated re-apply: rollback is cleaned after successful activation
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain' -H \"X-Atomicnix-Nonce: $(cat /tmp/atomic-nonce.txt)\" -H \"X-Atomicnix-Signature: $(cat /tmp/atomic-sig-b64.txt)\" --data-binary @/tmp/config.toml http://127.0.0.1:18082/api/config > /tmp/atomic-apply-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nresp = json.loads(Path('/tmp/atomic-apply-response.json').read_text())\nassert resp['ok'] is True, resp\nPY")
    # Rollback was created then cleaned after successful activation
    gateway.succeed("test ! -d /tmp/atomic-root-rollback")
    gateway.succeed("test -f /tmp/atomic-root/config.toml")
    gateway.succeed("test ! -d /tmp/atomic-root-candidate")
    gateway.succeed("kill $(cat /tmp/atomic-bootstrap.pid)")

    # Test restore_rollback (create a fake rollback first)
    gateway.succeed("mkdir -p /tmp/atomic-root-rollback && cp /tmp/config.toml /tmp/atomic-root-rollback/config.toml")
    gateway.succeed("python3 - <<'PY'\nimport sys, os, importlib.util\nfrom pathlib import Path\nos.environ['ATOMIXOS_CONFIG_SCHEMA'] = '${provisionCli}/share/atomixos/config.schema.json'\nspec = importlib.util.spec_from_file_location('fbp', '${../../scripts/first-boot-provision.py}')\nmod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\nassert mod.restore_rollback(Path('/tmp/atomic-root')) is True\nassert Path('/tmp/atomic-root/config.toml').exists()\nassert not Path('/tmp/atomic-root-rollback').exists()\nPY")

    # Test cleanup_rollback
    gateway.succeed("first-boot-provision import /tmp/config.toml /tmp/atomic-root")
    gateway.succeed("mkdir -p /tmp/atomic-root-rollback && touch /tmp/atomic-root-rollback/config.toml")
    gateway.succeed("python3 - <<'PY'\nimport sys, os, importlib.util\nfrom pathlib import Path\nos.environ['ATOMIXOS_CONFIG_SCHEMA'] = '${provisionCli}/share/atomixos/config.schema.json'\nspec = importlib.util.spec_from_file_location('fbp', '${../../scripts/first-boot-provision.py}')\nmod = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(mod)\nmod.cleanup_rollback(Path('/tmp/atomic-root'))\nassert not Path('/tmp/atomic-root-rollback').exists()\nPY")

    gateway.log("first-boot-provision helper test passed")
  '';
}
