{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  firstBootScript = pkgs.writeScriptBin "first-boot" (builtins.readFile ../../scripts/first-boot.sh);
  provisionCli = pkgs.runCommand "first-boot-provision" { } ''
    mkdir -p "$out/bin" "$out/share/atomixos"
    install -m0755 ${../../scripts/first-boot-provision.py} "$out/bin/first-boot-provision"
    install -m0644 ${../../docs/src/atomixos.png} "$out/share/atomixos/atomixos.png"
    install -m0644 ${../../schemas/config.schema.json} "$out/share/atomixos/config.schema.json"
  '';
in
nixos-lib.runTest {
  name = "first-boot-source-discovery";

  inherit hostPkgs;

  nodes.gateway =
    { ... }:
    {
      imports = [ qemuModule ];

      virtualisation.memorySize = 512;
      system.stateVersion = "25.11";

      environment.systemPackages = [
        pkgs.gzip
        pkgs.jq
        pkgs.python3Minimal
        pkgs.util-linux
        pkgs.zstd
        provisionCli
        firstBootScript
      ];

      systemd.tmpfiles.rules = [
        "d /boot 0755 root root -"
        "d /data 0755 root root -"
        "d /data/config 0755 root root -"
        "d /etc/atomixos 0755 root root -"
        "d /testbin 0755 root root -"
        "d /test-state 0755 root root -"
      ];
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    gateway.succeed("cat > /tmp/config-template.toml <<'EOF'\nversion = 1\n\n[admin]\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey admin@example\"]\n\n[firewall.inbound]\n\n[firewall.inbound.wan]\ntcp = [443]\n\n[health]\nrequired = [\"demo\"]\n\n[container.demo]\nprivileged = true\n\n[container.demo.Container]\nImage = \"docker.io/library/nginx:latest\"\n\n[container.demo.Install]\nWantedBy = [\"multi-user.target\"]\nEOF")

    gateway.succeed("cat > /testbin/rauc <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\n' \"$*\" >>/test-state/rauc.log\nif [ \"$1\" = status ] && [ \"$2\" = mark-good ]; then\n  exit 0\nfi\necho unexpected rauc invocation >&2\nexit 1\nEOF\nchmod +x /testbin/rauc")
    gateway.succeed("cat > /testbin/fw_printenv <<'EOF'\n#!/usr/bin/env bash\nexit 0\nEOF\nchmod +x /testbin/fw_printenv")
    gateway.succeed("cat > /testbin/fw_setenv <<'EOF'\n#!/usr/bin/env bash\nprintf 'fw_setenv %s\n' \"$*\" >>/test-state/fw-setenv.log\nEOF\nchmod +x /testbin/fw_setenv")
    gateway.succeed("cat > /testbin/systemctl <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\n' \"$*\" >>/test-state/systemctl.log\ncase \"$1\" in\n  restart)\n    if [ \"''${ATOMIXOS_TEST_FAIL_SERVICE:-}\" = \"$2\" ]; then\n      exit 1\n    fi\n    exit 0\n    ;;&\n  try-restart)\n    exit 0\n    ;;&\n  list-unit-files)\n    if [ \"''${ATOMIXOS_TEST_LIST_APPLY_SERVICES:-0}\" = 1 ]; then\n      case \"$2\" in\n        lan-gateway-apply.service|provisioned-firewall-inbound.service) exit 0 ;;&\n      esac\n    fi\n    exit 1\n    ;;&\n  *) echo unexpected systemctl invocation >&2; exit 1 ;;&\nesac\nEOF\nchmod +x /testbin/systemctl")
    gateway.succeed("cat > /testbin/mount <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nargs=(\"$@\")\nargc=''${#args[@]}\nsource_path=''${args[$((argc-2))]}\ntarget=''${args[$((argc-1))]}\ncase \"$source_path\" in\n  /test-usb/*) cp -R \"$source_path/.\" \"$target/\" ;;\n  *) echo unexpected mount source: $source_path >&2; exit 1 ;;\nesac\nprintf '%s -> %s\n' \"$source_path\" \"$target\" >>/test-state/mount.log\nEOF\nchmod +x /testbin/mount")
    gateway.succeed("cat > /testbin/umount <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nrm -rf \"$1\"/*\nprintf '%s\n' \"$1\" >>/test-state/umount.log\nEOF\nchmod +x /testbin/umount")
    gateway.succeed("cat > /testbin/first-boot-provision <<'EOF'\n#!/usr/bin/env bash\nexec /run/current-system/sw/bin/first-boot-provision \"$@\"\nEOF\nchmod +x /testbin/first-boot-provision")

    gateway.succeed("mkdir -p /test-usb/usb-a /test-usb/usb-b /tmp/bootcases /tmp/config-roots")

    gateway.succeed("rm -rf /tmp/bootcases/fresh-boot-seed /tmp/config-roots/fresh-boot-seed /test-state && mkdir -p /tmp/bootcases/fresh-boot-seed /tmp/config-roots/fresh-boot-seed /test-state /etc/atomixos")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /data/.completed_first_boot")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("cp /tmp/config-template.toml /boot/config.toml && cp /tmp/config-template.toml /test-usb/usb-a/config.toml && : >/etc/atomixos/fresh-flash")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/config-roots/fresh-boot-seed ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootcases/fresh-boot-seed/sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_INITRD_MARKER=/etc/atomixos/fresh-flash ATOMIXOS_BOOT_CONFIG_PATH=/boot/config.toml first-boot")
    gateway.succeed("cmp /boot/config.toml /tmp/config-roots/fresh-boot-seed/config.toml")
    gateway.succeed("test -f /tmp/bootcases/fresh-boot-seed/sentinel")
    gateway.succeed("grep '^status mark-good boot.a$' /test-state/rauc.log")

    gateway.succeed("rm -rf /tmp/bootcases/fresh-usb-fallback /tmp/config-roots/fresh-usb-fallback /test-state && mkdir -p /tmp/bootcases/fresh-usb-fallback /tmp/config-roots/fresh-usb-fallback /test-state /etc/atomixos")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /data/.completed_first_boot")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("cp /tmp/config-template.toml /test-usb/usb-b/config.toml && : >/etc/atomixos/fresh-flash")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/config-roots/fresh-usb-fallback ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootcases/fresh-usb-fallback/sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_INITRD_MARKER=/etc/atomixos/fresh-flash ATOMIXOS_BOOT_CONFIG_PATH=/boot/config.toml first-boot")
    gateway.succeed("cmp /test-usb/usb-b/config.toml /tmp/config-roots/fresh-usb-fallback/config.toml")
    gateway.succeed("grep '/test-usb/usb-b' /test-state/mount.log")
    gateway.succeed("test -f /tmp/bootcases/fresh-usb-fallback/sentinel")

    gateway.succeed("rm -rf /tmp/bootcases/reprovision-skips-boot /tmp/config-roots/reprovision-skips-boot /test-state && mkdir -p /tmp/bootcases/reprovision-skips-boot /tmp/config-roots/reprovision-skips-boot /test-state /etc/atomixos")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /data/.completed_first_boot")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("cp /tmp/config-template.toml /boot/config.toml && cp /tmp/config-template.toml /test-usb/usb-a/config.toml")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/config-roots/reprovision-skips-boot ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootcases/reprovision-skips-boot/sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_INITRD_MARKER=/etc/atomixos/fresh-flash ATOMIXOS_BOOT_CONFIG_PATH=/boot/config.toml first-boot")
    gateway.succeed("cmp /test-usb/usb-a/config.toml /tmp/config-roots/reprovision-skips-boot/config.toml")
    gateway.succeed("grep '/test-usb/usb-a' /test-state/mount.log")
    gateway.succeed("test ! -f /etc/atomixos/fresh-flash")

    gateway.succeed("rm -rf /tmp/bootstrap-root && mkdir -p /tmp/bootstrap-root /test-state /etc/atomixos")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("ATOMIXOS_CONFIG_ROOT=/tmp/bootstrap-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootstrap-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_PORT=18080 PATH=/testbin:/run/current-system/sw/bin first-boot >/tmp/bootstrap-case.log 2>&1 & echo $! >/tmp/bootstrap-case.pid")
    gateway.succeed("ip addr add 172.20.30.1/24 dev eth1")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-root --host 172.20.30.1 --port 18080 >/tmp/bootstrap-web.log 2>&1 & echo $! >/tmp/bootstrap-web.pid")
    gateway.wait_until_succeeds("ss -tln | grep '172.20.30.1:18080'", timeout = 60)
    gateway.succeed("curl -fsS -F config_file=@/tmp/config-template.toml http://172.20.30.1:18080/apply >/tmp/bootstrap-response.html")
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-root/config.toml", timeout = 60)
    gateway.succeed("grep 'downloadAppliedConfig()' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'version = 1' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'docker.io/library/nginx:latest' /tmp/bootstrap-response.html")
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-sentinel", timeout = 60)
    gateway.wait_until_succeeds("test ! -e /proc/$(cat /tmp/bootstrap-case.pid)", timeout = 60)
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Waiting for provisioning via bootstrap web console' /tmp/bootstrap-case.log")
    gateway.succeed("kill $(cat /tmp/bootstrap-web.pid)")
    gateway.succeed("rm -rf /tmp/bootstrap-invalid-lan-root /test-state && mkdir -p /tmp/bootstrap-invalid-lan-root /test-state")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /tmp/bootstrap-invalid-lan-sentinel")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("printf '{\"gateway_ip\": true}\n' >/tmp/bootstrap-invalid-lan-root/lan-settings.json")
    gateway.succeed("ATOMIXOS_CONFIG_ROOT=/tmp/bootstrap-invalid-lan-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootstrap-invalid-lan-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18081 PATH=/testbin:/run/current-system/sw/bin first-boot >/tmp/bootstrap-invalid-lan.log 2>&1 & echo $! >/tmp/bootstrap-invalid-lan.pid")
    gateway.succeed("first-boot-provision serve /tmp/bootstrap-invalid-lan-root --host 127.0.0.1 --port 18081 >/tmp/bootstrap-invalid-lan-web.log 2>&1 & echo $! >/tmp/bootstrap-invalid-lan-web.pid")
    gateway.wait_until_succeeds("ss -tln | grep '127.0.0.1:18081'", timeout = 60)
    gateway.succeed("curl -fsS -F config_file=@/tmp/config-template.toml http://127.0.0.1:18081/apply >/tmp/bootstrap-invalid-lan-response.html")
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-invalid-lan-root/config.toml", timeout = 60)
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-invalid-lan-sentinel", timeout = 60)
    gateway.wait_until_succeeds("test ! -e /proc/$(cat /tmp/bootstrap-invalid-lan.pid)", timeout = 60)
    gateway.succeed("grep 'Waiting for provisioning via bootstrap web console' /tmp/bootstrap-invalid-lan.log")
    gateway.succeed("kill $(cat /tmp/bootstrap-invalid-lan-web.pid)")

    gateway.succeed("rm -rf /tmp/config-roots/reapply-runtime /test-state && mkdir -p /tmp/config-roots/reapply-runtime /test-state")
    gateway.succeed("cp /tmp/config-template.toml /tmp/config-roots/reapply-runtime/config.toml")
    gateway.succeed("printf '{}\n' >/tmp/config-roots/reapply-runtime/quadlet-runtime.json")
    gateway.succeed("printf '{\"gateway_cidr\":\"172.20.30.1/24\"}\n' >/tmp/config-roots/reapply-runtime/lan-settings.json")
    gateway.succeed("printf '{\"wan\":{},\"lan\":{}}\n' >/tmp/config-roots/reapply-runtime/firewall-inbound.json")
    gateway.succeed("cat >/tmp/bootstrap-post-response-test <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nsystemctl restart quadlet-sync.service\nif systemctl list-unit-files lan-gateway-apply.service >/dev/null 2>&1; then\n  systemctl restart lan-gateway-apply.service\nfi\nif systemctl list-unit-files provisioned-firewall-inbound.service >/dev/null 2>&1; then\n  systemctl restart provisioned-firewall-inbound.service\nfi\nsystemctl try-restart atomixos-bootstrap.service\nEOF\nchmod +x /tmp/bootstrap-post-response-test")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_TEST_LIST_APPLY_SERVICES=1 /tmp/bootstrap-post-response-test >/tmp/reapply-runtime.out 2>&1")
    gateway.succeed("grep '^restart quadlet-sync.service$' /test-state/systemctl.log")
    gateway.succeed("grep '^restart lan-gateway-apply.service$' /test-state/systemctl.log")
    gateway.succeed("grep '^restart provisioned-firewall-inbound.service$' /test-state/systemctl.log")
    gateway.succeed("grep '^try-restart atomixos-bootstrap.service$' /test-state/systemctl.log")

    gateway.succeed("rm -rf /tmp/prod-missing-root /test-state && mkdir -p /tmp/prod-missing-root /test-state")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /tmp/prod-missing-sentinel")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/prod-missing-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/prod-missing-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 first-boot >/tmp/prod-missing.log 2>&1 & echo $! >/tmp/prod-missing.pid")
    gateway.succeed("sleep 3")
    gateway.succeed("kill -0 $(cat /tmp/prod-missing.pid)")
    gateway.succeed("test ! -f /tmp/prod-missing-sentinel")
    gateway.succeed("test ! -f /test-state/rauc.log")
    gateway.succeed("grep 'Waiting for provisioning via bootstrap web console' /tmp/prod-missing.log")
    gateway.succeed("kill $(cat /tmp/prod-missing.pid)")

    gateway.succeed("rm -rf /tmp/no-dev-fallback-root /test-state && mkdir -p /tmp/no-dev-fallback-root /test-state")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash /tmp/no-dev-fallback-sentinel")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/no-dev-fallback-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/no-dev-fallback-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_DEV_ENABLE_SSH_WAN=1 first-boot >/tmp/no-dev-fallback.log 2>&1 & echo $! >/tmp/no-dev-fallback.pid")
    gateway.succeed("sleep 3")
    gateway.succeed("kill -0 $(cat /tmp/no-dev-fallback.pid)")
    gateway.succeed("test ! -f /tmp/no-dev-fallback-sentinel")
    gateway.succeed("test ! -f /tmp/no-dev-fallback-root/ssh-wan-enabled")
    gateway.succeed("test ! -f /tmp/no-dev-fallback-root/health-required.json")
    gateway.succeed("test ! -f /test-state/rauc.log")
    gateway.succeed("grep 'Waiting for provisioning via bootstrap web console' /tmp/no-dev-fallback.log")
    gateway.succeed("kill $(cat /tmp/no-dev-fallback.pid)")

    gateway.succeed("rm -rf /tmp/bootcases/lan-apply-fail /tmp/config-roots/lan-apply-fail /test-state && mkdir -p /tmp/bootcases/lan-apply-fail /tmp/config-roots/lan-apply-fail /test-state /etc/atomixos")
    gateway.succeed("cp /tmp/config-template.toml /boot/config.toml && : >/etc/atomixos/fresh-flash")
    gateway.fail("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/config-roots/lan-apply-fail ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootcases/lan-apply-fail/sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_INITRD_MARKER=/etc/atomixos/fresh-flash ATOMIXOS_BOOT_CONFIG_PATH=/boot/config.toml ATOMIXOS_TEST_LIST_APPLY_SERVICES=1 ATOMIXOS_TEST_FAIL_SERVICE=lan-gateway-apply.service first-boot >/tmp/lan-apply-fail.log 2>&1")
    gateway.succeed("test ! -f /tmp/bootcases/lan-apply-fail/sentinel")
    gateway.succeed("test ! -f /test-state/rauc.log")
    gateway.succeed("grep 'ERROR: lan-gateway-apply.service failed' /tmp/lan-apply-fail.log")

    gateway.log("first-boot source discovery test passed")
  '';
}
