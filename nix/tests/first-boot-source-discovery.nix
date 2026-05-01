{
  pkgs,
  hostPkgs ? pkgs,
  qemuModule,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  firstBootScript = pkgs.writeScriptBin "first-boot" (builtins.readFile ../../scripts/first-boot.sh);
  provisionCli = pkgs.writeScriptBin "first-boot-provision" (
    builtins.readFile ../../scripts/first-boot-provision.py
  );
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

    gateway.succeed("cat > /tmp/config-template.toml <<'EOF'\nversion = 1\n\n[admin]\nssh_keys = [\"ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITestKey admin@example\"]\n\n[firewall.inbound]\ntcp = [443]\n\n[health]\nrequired = [\"demo\"]\n\n[container.demo]\nprivileged = true\n\n[container.demo.Container]\nImage = \"docker.io/library/nginx:latest\"\n\n[container.demo.Install]\nWantedBy = [\"multi-user.target\"]\nEOF")

    gateway.succeed("cat > /testbin/rauc <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\n' \"$*\" >>/test-state/rauc.log\nif [ \"$1\" = status ] && [ \"$2\" = mark-good ]; then\n  exit 0\nfi\necho unexpected rauc invocation >&2\nexit 1\nEOF\nchmod +x /testbin/rauc")
    gateway.succeed("cat > /testbin/fw_printenv <<'EOF'\n#!/usr/bin/env bash\nexit 0\nEOF\nchmod +x /testbin/fw_printenv")
    gateway.succeed("cat > /testbin/fw_setenv <<'EOF'\n#!/usr/bin/env bash\nprintf 'fw_setenv %s\n' \"$*\" >>/test-state/fw-setenv.log\nEOF\nchmod +x /testbin/fw_setenv")
    gateway.succeed("cat > /testbin/systemctl <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nprintf '%s\n' \"$*\" >>/test-state/systemctl.log\ncase \"$1\" in\n  restart) exit 0 ;;&\n  list-unit-files) exit 1 ;;&\n  *) echo unexpected systemctl invocation >&2; exit 1 ;;&\nesac\nEOF\nchmod +x /testbin/systemctl")
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
    gateway.succeed("ATOMIXOS_CONFIG_ROOT=/tmp/bootstrap-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/bootstrap-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_BOOTSTRAP_DOWNLOAD_GRACE_SECONDS=3 PATH=/testbin:/run/current-system/sw/bin first-boot >/tmp/bootstrap-case.log 2>&1 & echo $! >/tmp/bootstrap-case.pid")
    gateway.succeed("sleep 2 && ip addr add 172.20.30.1/24 dev eth1 >/tmp/bootstrap-ip.log 2>&1 &")
    gateway.wait_until_succeeds("ss -tln | grep '172.20.30.1:18080'", timeout = 60)
    gateway.succeed("curl -fsS -F config_file=@/tmp/config-template.toml http://172.20.30.1:18080/apply >/tmp/bootstrap-response.html")
    gateway.wait_until_succeeds("test -f /tmp/bootstrap-root/config.toml", timeout = 60)
    gateway.succeed("download_path=$(python3 - <<'PY'\nimport re\nfrom pathlib import Path\nhtml = Path('/tmp/bootstrap-response.html').read_text()\nmatch = re.search(r'href=\"([^\"]*/download/config\.toml\?token=[^\"]+)\"', html)\nassert match, html\nprint(match.group(1))\nPY\n) && printf '%s' \"$download_path\" >/tmp/bootstrap-download.path && curl -fsS \"http://172.20.30.1:18080$download_path\" >/tmp/bootstrap-download.toml")
    gateway.succeed("cmp /tmp/bootstrap-root/config.toml /tmp/bootstrap-download.toml")
    gateway.fail("download_path=$(cat /tmp/bootstrap-download.path) && curl -fsS \"http://172.20.30.1:18080$download_path\" >/tmp/bootstrap-download-reuse.toml")
    gateway.succeed("for _ in $(seq 1 60); do if test -f /tmp/bootstrap-sentinel; then exit 0; fi; if ! kill -0 $(cat /tmp/bootstrap-case.pid) 2>/dev/null; then echo 'bootstrap process exited unexpectedly' >&2; test -f /tmp/bootstrap-case.log && cat /tmp/bootstrap-case.log >&2; exit 1; fi; sleep 1; done; echo 'bootstrap sentinel did not appear' >&2; test -f /tmp/bootstrap-case.log && cat /tmp/bootstrap-case.log >&2; exit 1")
    gateway.wait_until_succeeds("test ! -e /proc/$(cat /tmp/bootstrap-case.pid)", timeout = 60)
    gateway.succeed("grep 'Configuration applied' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'Download applied config.toml' /tmp/bootstrap-response.html")
    gateway.succeed("grep 'waiting for bootstrap address 172.20.30.1' /tmp/bootstrap-case.log")
    gateway.fail("grep 'token=' /tmp/bootstrap-case.log")
    gateway.succeed("cat > /testbin/first-boot-provision-prodfail <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nif [ \"$1\" = serve ]; then\n  exit 1\nfi\nexec /run/current-system/sw/bin/first-boot-provision \"$@\"\nEOF\nchmod +x /testbin/first-boot-provision-prodfail")
    gateway.succeed("rm -rf /tmp/prod-missing-root /test-state && mkdir -p /tmp/prod-missing-root /test-state")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("cat > /testbin/first-boot-provision <<'EOF'\n#!/usr/bin/env bash\nexec /testbin/first-boot-provision-prodfail \"$@\"\nEOF\nchmod +x /testbin/first-boot-provision")
    gateway.fail("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/prod-missing-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/prod-missing-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 first-boot >/tmp/prod-missing.log 2>&1")
    gateway.succeed("test ! -f /tmp/prod-missing-sentinel")
    gateway.succeed("test ! -f /test-state/rauc.log")
    gateway.succeed("grep 'ERROR: provisioning seed not found' /tmp/prod-missing.log")

    gateway.succeed("cat > /testbin/first-boot-provision-dev <<'EOF'\n#!/usr/bin/env bash\nset -euo pipefail\nif [ \"$1\" = serve ]; then\n  exit 1\nfi\nexec /run/current-system/sw/bin/first-boot-provision \"$@\"\nEOF\nchmod +x /testbin/first-boot-provision-dev")
    gateway.succeed("rm -rf /tmp/dev-fallback-root /test-state && mkdir -p /tmp/dev-fallback-root /test-state")
    gateway.succeed("rm -f /boot/config.toml /etc/atomixos/fresh-flash")
    gateway.succeed("rm -rf /test-usb/usb-a/* /test-usb/usb-b/*")
    gateway.succeed("cat > /testbin/first-boot-provision <<'EOF'\n#!/usr/bin/env bash\nexec /testbin/first-boot-provision-dev \"$@\"\nEOF\nchmod +x /testbin/first-boot-provision")
    gateway.succeed("env PATH=/testbin:/run/current-system/sw/bin ATOMIXOS_CONFIG_ROOT=/tmp/dev-fallback-root ATOMIXOS_FIRST_BOOT_SENTINEL=/tmp/dev-fallback-sentinel ATOMIXOS_BOOT_SLOT=boot.a ATOMIXOS_USB_SEARCH_DIRS='/test-usb' ATOMIXOS_BOOTSTRAP_HOST=127.0.0.1 ATOMIXOS_BOOTSTRAP_PORT=18080 ATOMIXOS_DEV_ENABLE_SSH_WAN=1 first-boot")
    gateway.succeed("test -f /tmp/dev-fallback-root/ssh-wan-enabled")
    gateway.succeed("python3 - <<'PY'\nimport json\nfrom pathlib import Path\nassert json.loads(Path('/tmp/dev-fallback-root/health-required.json').read_text()) == []\nPY")
    gateway.succeed("test -f /tmp/dev-fallback-sentinel")

    gateway.log("first-boot source discovery test passed")
  '';
}
