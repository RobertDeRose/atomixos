{
  pkgs,
  hostPkgs ? pkgs,
  self,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  provisionCli = pkgs.runCommand "first-boot-provision" { } ''
    mkdir -p "$out/bin" "$out/share/atomixos"
    install -m0755 ${../../scripts/first-boot-provision.py} "$out/bin/first-boot-provision"
    install -m0644 ${../../docs/src/atomixos.png} "$out/share/atomixos/atomixos.png"
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
        pkgs.python3Minimal
        pkgs.gnutar
        provisionCli
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

    gateway.succeed("cat > /tmp/config.toml <<'EOF'\nversion = 1\n\n[admin]\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"]\n\n[firewall.inbound]\ntcp = [80, 443]\nudp = [1194]\n\n[lan]\ngateway_cidr = \"10.44.0.1/24\"\ndhcp_start = \"10.44.0.10\"\ndhcp_end = \"10.44.0.200\"\ndomain = \"lab\"\ngateway_aliases = [\"atomixos\", \"gateway.lab\"]\nhostname_pattern = \"gateway-{mac}\"\n\n[health]\nrequired = [\"traefik\", \"myapp\"]\n\n[container.traefik]\nprivileged = true\n\n[container.traefik.Unit]\nDescription = \"Traefik\"\n\n[container.traefik.Container]\nImage = \"docker.io/library/traefik:v3.1\"\nEnvironment = [\"A=1\", \"B=2\"]\nExec = [\"--serve\", \"--port=8080\"]\n\n[container.traefik.Install]\nWantedBy = [\"multi-user.target\"]\n\n[container.myapp]\nprivileged = false\n\n[container.myapp.Unit]\nDescription = \"My App\"\n\n[container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nNetwork = [\"frontend\"]\nPublishPort = [\"10080:80\", \"192.168.1.20:10081:81\"]\nVolume = [\"''${FILES_DIR}/app/config.yaml:/app/config.yaml:ro\", \"''${CONFIG_DIR}/local.env:/app/local.env:ro\"]\n\n[container.myapp.Install]\nWantedBy = [\"default.target\"]\nEOF")

    gateway.succeed("printf 'KEY=VALUE\n' >/tmp/local.env")
    gateway.succeed("cat > /tmp/invalid-config.toml <<'EOF'\nversion = 1\n\n[admin]\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example\"]\n\n[firewall.inbound]\ntcp = [443]\n\n[health]\nrequired = [\"missing-service\"]\n\n[container.myapp]\nprivileged = false\n\n[container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nEOF")

    gateway.succeed("first-boot-provision validate /tmp/config.toml")
    gateway.succeed("first-boot-provision import /tmp/config.toml /data/config")
    gateway.succeed("cp /tmp/local.env /data/config/local.env")
    gateway.succeed("mkdir -p /var/lib/appsvc/.config/containers/systemd")
    gateway.succeed("first-boot-provision sync-quadlet /data/config /etc/containers/systemd /var/lib/appsvc/.config/containers/systemd")

    gateway.succeed("test -f /data/config/config.toml")
    gateway.succeed("test -f /data/config/ssh-authorized-keys/admin")
    gateway.succeed("test -f /data/config/health-required.json")
    gateway.succeed("test -f /data/config/firewall-inbound.json")
    gateway.succeed("test -f /data/config/lan-settings.json")
    gateway.succeed("test -f /data/config/quadlet-runtime.json")
    gateway.succeed("test -f /data/config/quadlet/traefik.container")
    gateway.succeed("test -f /data/config/quadlet/myapp.container")
    gateway.succeed("test -f /etc/containers/systemd/traefik.container")
    gateway.succeed("test -f /var/lib/appsvc/.config/containers/systemd/myapp.container")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\nrequired = json.loads(Path('/data/config/health-required.json').read_text())\nassert required == ['traefik', 'myapp'], required\nfirewall = json.loads(Path('/data/config/firewall-inbound.json').read_text())\nassert firewall == {'tcp': [80, 443], 'udp': [1194]}, firewall\nlan = json.loads(Path('/data/config/lan-settings.json').read_text())\nassert lan == {\n    'gateway_cidr': '10.44.0.1/24',\n    'gateway_ip': '10.44.0.1',\n    'subnet_cidr': '10.44.0.0/24',\n    'netmask': '255.255.255.0',\n    'dhcp_start': '10.44.0.10',\n    'dhcp_end': '10.44.0.200',\n    'domain': 'lab',\n    'hostname_pattern': 'gateway-{mac}',\n    'gateway_aliases': ['atomixos', 'gateway.lab'],\n}, lan\nruntime = json.loads(Path('/data/config/quadlet-runtime.json').read_text())\nassert runtime['app_user'] == 'appsvc', runtime\nassert runtime['rootless_network'] == 'pasta', runtime\nassert runtime['units'] == [\n    {'name': 'traefik', 'filename': 'traefik.container', 'service': 'traefik.service', 'mode': 'rootful'},\n    {'name': 'myapp', 'filename': 'myapp.container', 'service': 'myapp.service', 'mode': 'rootless'},\n], runtime['units']\nPY")
    gateway.succeed("grep -c '^Environment=' /data/config/quadlet/traefik.container | grep '^2$'")
    gateway.succeed("grep -c '^Exec=' /data/config/quadlet/traefik.container | grep '^2$'")
    gateway.succeed("grep '^Network=host$' /data/config/quadlet/traefik.container")
    gateway.succeed("grep '^Exec=--serve$' /data/config/quadlet/traefik.container")
    gateway.succeed("grep '^Exec=--port=8080$' /data/config/quadlet/traefik.container")
    gateway.succeed("grep -c '^Network=' /data/config/quadlet/myapp.container | grep '^1$'")
    gateway.succeed("grep '^Network=pasta$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^PublishPort=127.0.0.1:10080:80$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^PublishPort=127.0.0.1:10081:81$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^Volume=/data/config/files/app/config.yaml:/app/config.yaml:ro$' /data/config/quadlet/myapp.container")
    gateway.succeed("grep '^Volume=/data/config/local.env:/app/local.env:ro$' /data/config/quadlet/myapp.container")

    gateway.succeed("mkdir -p /tmp/lan-apply/bin /tmp/lan-apply/etc/systemd/network/20-lan.network.d /tmp/lan-apply/sys/class/net/eth1")
    gateway.succeed("printf '00:11:22:33:44:55\n' >/tmp/lan-apply/sys/class/net/eth1/address")
    gateway.succeed("ln -s /tmp/lan-apply/store-network /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("ln -s /tmp/lan-apply/store-dnsmasq /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("ln -s /tmp/lan-apply/store-hosts /tmp/lan-apply/dnsmasq-hosts")
    gateway.succeed("ln -s /tmp/lan-apply/store-chrony /tmp/lan-apply/chrony-lan.conf")
    gateway.succeed("printf '127.0.0.1 localhost\n10.0.0.2 old # ATOMIXOS_LAN_GATEWAY\n' >/tmp/lan-apply/etc-hosts")
    gateway.succeed("cat > /tmp/lan-apply/bin/networkctl <<'EOF'\n#!/usr/bin/env bash\nprintf '%s\n' \"$*\" >>/tmp/lan-apply/networkctl.log\nEOF\nchmod +x /tmp/lan-apply/bin/networkctl")
    gateway.succeed("cat > /tmp/lan-apply/bin/systemctl <<'EOF'\n#!/usr/bin/env bash\nprintf '%s\n' \"$*\" >>/tmp/lan-apply/systemctl.log\nEOF\nchmod +x /tmp/lan-apply/bin/systemctl")
    gateway.succeed("PATH=/tmp/lan-apply/bin:$PATH ATOMIXOS_LAN_SETTINGS_FILE=/data/config/lan-settings.json ATOMIXOS_DNSMASQ_CONFIG_DIR=/tmp/lan-apply ATOMIXOS_DNSMASQ_HOSTS_FILE=/tmp/lan-apply/dnsmasq-hosts ATOMIXOS_CHRONY_LAN_FILE=/tmp/lan-apply/chrony-lan.conf ATOMIXOS_LAN_NETWORK_FILE=/tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf ATOMIXOS_ETC_HOSTS_FILE=/tmp/lan-apply/etc-hosts ATOMIXOS_SYS_CLASS_NET_DIR=/tmp/lan-apply/sys/class/net bash ${../../scripts/lan-gateway-apply.sh}")
    gateway.succeed("test ! -L /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("test ! -L /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^Address=10.44.0.1/24$' /tmp/lan-apply/etc/systemd/network/20-lan.network.d/50-atomixos.conf")
    gateway.succeed("grep '^dhcp-range=10.44.0.10,10.44.0.200,255.255.255.0,24h$' /tmp/lan-apply/atomixos-lan.conf")
    gateway.succeed("grep '^domain=lab$' /tmp/lan-apply/atomixos-lan.conf")
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

    gateway.succeed("rm -rf /tmp/bootstrap-root")
    gateway.succeed("mkdir -p /tmp/bootstrap-root")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root /tmp/bootstrap-output.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS http://127.0.0.1:18080/assets/atomixos.png >/tmp/bootstrap-logo.png")
    gateway.succeed("test -s /tmp/bootstrap-logo.png")
    gateway.succeed("curl -fsS -F config_file=@/tmp/config.toml http://127.0.0.1:18080/apply >/tmp/bootstrap-response.html")
    gateway.succeed("test -f /tmp/bootstrap-root/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root/ssh-authorized-keys/admin")
    gateway.succeed("test -f /tmp/bootstrap-root/health-required.json")
    gateway.succeed("grep 'src=\"/assets/atomixos.png\"' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'downloadAppliedConfig()' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'version = 1' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'docker.io/library/traefik:v3.1' /tmp/bootstrap-response.html")
    gateway.succeed("rm -rf /tmp/bootstrap-root-api && mkdir -p /tmp/bootstrap-root-api")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-api /tmp/bootstrap-output-api.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS -H 'Content-Type: text/plain; charset=utf-8' --data-binary @/tmp/config.toml http://127.0.0.1:18080/api/config >/tmp/bootstrap-api-response.json")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\n\npayload = json.loads(Path('/tmp/bootstrap-api-response.json').read_text())\nassert payload == {'ok': True, 'message': 'Configuration applied.'}, payload\nPY")
    gateway.succeed("test -f /tmp/bootstrap-root-api/config.toml")
    gateway.succeed("test -f /tmp/bootstrap-root-api/ssh-authorized-keys/admin")
    gateway.succeed("test -f /tmp/bootstrap-root-api/health-required.json")
    gateway.succeed("kill $(cat /tmp/bootstrap.pid)")

    gateway.succeed("rm -rf /tmp/bootstrap-root-generate && mkdir -p /tmp/bootstrap-root-generate")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root-generate /tmp/bootstrap-output-generate.toml --host 127.0.0.1 --port 18080 >/tmp/bootstrap.log 2>&1 & echo $! >/tmp/bootstrap.pid")
    gateway.wait_until_succeeds("ss -tln | grep ':18080'", timeout=30)
    gateway.succeed("curl -fsS --data-urlencode 'ssh_keys=ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBootstrapKey admin@example' --data-urlencode 'wan_tcp=443' --data-urlencode 'wan_udp=1194' --data-urlencode 'required=' --data-urlencode 'quadlet=[container.myapp]\nprivileged = false\n\n[container.myapp.Unit]\nDescription = \"My App\"\n\n[container.myapp.Container]\nImage = \"ghcr.io/example/myapp:latest\"\nPublishPort = [\"10080:8080\"]\n\n[container.myapp.Install]\nWantedBy = [\"default.target\"]' http://127.0.0.1:18080/generate >/tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'downloadAppliedConfig()' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'version = 1' /tmp/bootstrap-generate-response.html")
    gateway.succeed("grep 'ghcr.io/example/myapp:latest' /tmp/bootstrap-generate-response.html")
    gateway.succeed("python3 - <<'PY'\nimport json\nimport tomllib\nfrom pathlib import Path\n\nconfig = tomllib.loads(Path('/tmp/bootstrap-root-generate/config.toml').read_text())\nassert config['health']['required'] == ['myapp'], config['health']['required']\nrequired = json.loads(Path('/tmp/bootstrap-root-generate/health-required.json').read_text())\nassert required == ['myapp'], required\nPY")
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

    gateway.fail("first-boot-provision validate /tmp/invalid-config.toml")

    gateway.log("first-boot-provision helper test passed")
  '';
}
