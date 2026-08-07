# First-boot initialization — runs once on initial device boot.
#
# Imports provisioning state and writes a sentinel file
# (/data/.completed_first_boot) so it never runs again. When RAUC is enabled,
# it also marks the current slot good because there is no health manifest or
# container image state yet on first boot.
#
# os-verification.service has the inverse condition — it only runs after
# the sentinel exists (i.e. on all boots AFTER the first) and only when RAUC
# confirmation is enabled.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

let
  bootstrapTransport = lib.attrByPath [
    "atomixos"
    "provisioning"
    "bootstrapTransport"
  ] "network" config;
  bootstrapListenAddress = if bootstrapTransport == "nixstasis" then "127.0.0.1" else "0.0.0.0";
  firstBootScript = pkgs.writeShellScript "first-boot" (builtins.readFile ../scripts/first-boot.sh);
  applyUsersScript = pkgs.writeShellScript "apply-users" ''
    set -euo pipefail
    export ATOMIXOS_ADMIN_SHELL=/run/current-system/sw/bin/zsh
    export ATOMIXOS_SYSTEM_SHELL=/run/current-system/sw/bin/bash
    exec ${pkgs.python3Minimal}/bin/python3 ${../scripts/apply-users.py}
  '';
  bootstrapActivationScript = pkgs.writeShellScript "bootstrap-activation" ''
    set -euo pipefail
    ${pkgs.systemd}/bin/systemctl restart atomixos-apply-users.service
    ${pkgs.systemd}/bin/systemctl restart quadlet-sync.service
    if ${pkgs.systemd}/bin/systemctl cat lan-gateway-apply.service >/dev/null 2>&1; then
      ${pkgs.systemd}/bin/systemctl restart lan-gateway-apply.service
    fi
    if ${pkgs.systemd}/bin/systemctl cat provisioned-firewall-inbound.service >/dev/null 2>&1; then
      ${pkgs.systemd}/bin/systemctl restart provisioned-firewall-inbound.service
    fi
  '';
  quadletSyncScript = pkgs.writeShellScript "quadlet-sync" (
    builtins.readFile ../scripts/quadlet-sync.sh
  );
  provisionCli = pkgs.python3Packages.buildPythonApplication {
    pname = "atomixos-provision";
    version = "0.1.0";
    pyproject = true;

    src = ../scripts/atomixos_provision;

    build-system = [ pkgs.python3Packages.hatchling ];
    dependencies = [
      pkgs.python3Packages.click
      pkgs.python3Packages.litestar
      pkgs.python3Packages.uvicorn
    ];

    postInstall = ''
      mkdir -p "$out/share/atomixos"
      install -m0644 ${../docs/src/atomixos.png} "$out/share/atomixos/atomixos.png"
      install -m0644 ${../docs/src/config_dropzone.png} "$out/share/atomixos/config_dropzone.png"
      install -m0644 ${../schemas/config.schema.json} "$out/share/atomixos/config.schema.json"
    '';

    # Tests require NixOS VM environment
    doCheck = false;
  };
  configRecoveryScript = pkgs.writeShellScript "atomixos-config-recover" ''
    set -euo pipefail
    export ATOMIXOS_PROVISION_WORKER_ACTIVE=1
    exec ${provisionCli}/bin/atomixos-provision recover /data/config
  '';
  provisionApplyScript = pkgs.writeShellScript "atomixos-provision-apply" ''
    set -euo pipefail
    export ATOMIXOS_BOOTSTRAP_ACTIVATION=${bootstrapActivationScript}
    export ATOMIXOS_PROVISION_WORKER_ACTIVE=1
    export ATOMIXOS_PROVISION_RESULT_TIMEOUT_SECONDS=3900
    ${provisionCli}/bin/atomixos-provision finalize-staged --runtime-root /run/atomixos-provision
    exec ${provisionCli}/bin/atomixos-provision apply-staged /data/config --runtime-root /run/atomixos-provision --drain
  '';
  provisionApplyFinalizeScript = pkgs.writeShellScript "atomixos-provision-apply-finalize" ''
    set -euo pipefail
    exec ${provisionCli}/bin/atomixos-provision finalize-staged --runtime-root /run/atomixos-provision
  '';
  ubootEnvTools = self.packages.${pkgs.stdenv.hostPlatform.system}.uboot-env-tools;
  firstBootEnv = {
    ATOMIXOS_RAUC_ENABLE = if config.atomixos.rauc.enable then "1" else "0";
    ATOMIXOS_APPLY_USERS_SCRIPT = "${applyUsersScript}";
    ATOMIXOS_BOOTSTRAP_TRANSPORT = bootstrapTransport;
  };
in
{
  systemd.tmpfiles.rules = [
    "d /run/atomixos-provision 0755 root root -"
    "d /run/atomixos-provision/queue 2770 root atomixos-provision -"
    "d /run/atomixos-provision/results 2750 root atomixos-provision -"
    "d /run/atomixos-provision/boot-ui-jobs 0700 atomixos-provision atomixos-provision -"
    "d /run/atomixos-provision/active 2750 root atomixos-provision -"
    "f /run/atomixos-provision/config.lock 0660 root atomixos-provision -"
    "f /run/atomixos-provision/queue.lock 0660 root atomixos-provision -"
  ];

  users.users.atomixos-provision = {
    description = "AtomixOS provisioning API service user";
    group = "atomixos-provision";
    isSystemUser = true;
  };

  users.groups.atomixos-provision = { };

  systemd.services.atomixos-config-recover = {
    description = "Recover interrupted AtomixOS config promotion";
    after = [ "data.mount" ];
    wants = [ "data.mount" ];
    before = [
      "atomixos-apply-users.service"
      "atomixos-bootstrap-rebind.service"
      "atomixos-bootstrap.service"
      "bootstrap-wan-toggle.service"
      "first-boot.service"
      "lan-gateway-apply.service"
      "provisioned-firewall-inbound.service"
      "quadlet-sync.service"
    ];
    wantedBy = [ "multi-user.target" ];

    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.python3Minimal
      provisionCli
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = configRecoveryScript;
      RemainAfterExit = true;
    };
  };

  systemd.paths.atomixos-provision-apply = {
    description = "Watch for staged AtomixOS provisioning jobs";
    wantedBy = [ "multi-user.target" ];
    pathConfig = {
      PathExistsGlob = "/run/atomixos-provision/queue/*.ready";
      Unit = "atomixos-provision-apply.service";
    };
  };

  systemd.services.atomixos-provision-apply = {
    description = "Apply staged AtomixOS provisioning job";
    after = [
      "atomixos-config-recover.service"
      "data.mount"
    ];
    requires = [ "atomixos-config-recover.service" ];
    wants = [ "data.mount" ];

    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.gzip
      pkgs.jq
      pkgs.procps
      pkgs.python3Minimal
      pkgs.systemd
      pkgs.util-linux
      pkgs.zstd
      provisionCli
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = provisionApplyScript;
      ExecStopPost = provisionApplyFinalizeScript;
      TimeoutStartSec = 7500;
      PrivateTmp = true;
      NoNewPrivileges = true;
      ProtectSystem = "strict";
      ProtectHome = true;
      ReadWritePaths = [
        "/data"
        "/run/atomixos-provision"
      ];
    };
  };

  systemd.services.quadlet-sync = {
    description = "Sync provisioned Quadlet units";
    after = [
      "atomixos-config-recover.service"
      "data.mount"
      "network-online.target"
      "chronyd.service"
    ];
    requires = [ "atomixos-config-recover.service" ];
    wants = [
      "data.mount"
      "network-online.target"
    ];
    wantedBy = [ "multi-user.target" ];

    unitConfig.ConditionPathExists = "/data/config/config.toml";
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.chrony
      pkgs.findutils
      pkgs.gzip
      pkgs.gnugrep
      pkgs.jq
      pkgs.podman
      pkgs.python3Minimal
      pkgs.util-linux
      pkgs.systemd
      pkgs.zstd
      provisionCli
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = quadletSyncScript;
      TimeoutStartSec = 300;
    };
  };

  systemd.services.first-boot = {
    description = "First-boot initialization (provision, confirm slot if enabled)";
    after = [
      "atomixos-config-recover.service"
      "data.mount"
      "multi-user.target"
    ];
    requires = [ "atomixos-config-recover.service" ];
    wants = [
      "data.mount"
    ];
    wantedBy = [ "multi-user.target" ];

    # Only run if the sentinel does NOT exist (first boot only)
    unitConfig.ConditionPathExists = "!/data/.completed_first_boot";
    unitConfig.RequiresMountsFor = [ "/data" ];

    # RAUC needs to be on PATH to call `rauc status mark-good`
    path =
      lib.optionals config.atomixos.rauc.enable [
        pkgs.rauc
        ubootEnvTools
      ]
      ++ [
        pkgs.coreutils
        pkgs.gzip
        pkgs.jq
        pkgs.procps
        pkgs.systemd
        pkgs.python3Minimal
        pkgs.zstd
        pkgs.util-linux
        provisionCli
      ];
    environment = firstBootEnv;

    serviceConfig = {
      Type = "oneshot";
      ExecStart = firstBootScript;
      RemainAfterExit = true;
      TimeoutStartSec = "infinity";
    };
  };

  systemd.services.atomixos-apply-users = {
    description = "Materialize managed users from provisioned config";
    after = [
      "atomixos-config-recover.service"
      "data.mount"
      "nss-user-lookup.target"
    ];
    requires = [ "atomixos-config-recover.service" ];
    wants = [
      "data.mount"
      "nss-user-lookup.target"
    ];
    before = [ "sshd.service" ];
    wantedBy = [ "multi-user.target" ];

    unitConfig.ConditionPathExists = "/data/config/users.json";
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.bashInteractive
      pkgs.python3Minimal
      pkgs.shadow
      pkgs.zsh
      pkgs.util-linux
    ];

    serviceConfig = {
      Type = "oneshot";
      Environment = "ATOMIXOS_PROVISION_WORKER_ACTIVE=1";
      ExecStart = applyUsersScript;
      RemainAfterExit = true;
    };
  };

  systemd.sockets.atomixos-bootstrap = {
    description = "AtomixOS bootstrap web console socket";
    after = [
      "data.mount"
      "network-online.target"
    ];
    wants = [
      "data.mount"
      "network-online.target"
    ];
    wantedBy = [ "sockets.target" ];

    unitConfig.RequiresMountsFor = [ "/data" ];

    socketConfig = {
      ListenStream = "${bootstrapListenAddress}:8080";
      FreeBind = true;
      Accept = false;
    };
  };

  systemd.services.atomixos-bootstrap = {
    description = "AtomixOS bootstrap web console";
    after = [
      "atomixos-config-recover.service"
      "data.mount"
      "network-online.target"
    ];
    requires = [ "atomixos-config-recover.service" ];
    wants = [
      "data.mount"
      "network-online.target"
    ];
    unitConfig.RequiresMountsFor = [ "/data" ];

    path = [
      pkgs.coreutils
      pkgs.gzip
      pkgs.jq
      pkgs.openssh
      pkgs.python3Minimal
      pkgs.systemd
      pkgs.util-linux
      pkgs.zstd
      provisionCli
    ];

    serviceConfig = {
      Type = "simple";
      Restart = "always";
      RestartSec = 2;
      Environment = [
        "ATOMIXOS_PROVISION_RESULT_TIMEOUT_SECONDS=3900"
      ];
      ExecStart = "${provisionCli}/bin/atomixos-provision serve /data/config";
      User = "atomixos-provision";
      Group = "atomixos-provision";
      NoNewPrivileges = true;
      PrivateTmp = true;
      ProtectHome = true;
      ProtectSystem = "strict";
      ReadOnlyPaths = [
        "-/data/config"
      ];
      ReadWritePaths = [
        "/run/atomixos-provision"
      ];
    };
  };
}
