{
  pkgs,
  self,
  qemuModule,
  ...
}:

let
  system = "aarch64-linux";
  evaluated = self.inputs.nixpkgs.lib.nixosSystem {
    inherit system;
    modules = [
      ../../modules/base.nix
      qemuModule
      (
        { lib, ... }:
        {
          atomixos.nixstasis = {
            enable = true;
            apiUrl = "https://nixstasis.example.test";
            frp.serverAddr = "frp.example.test";
            runtime.execCommands.uname = "/run/current-system/sw/bin/uname";
          };
          atomixos.rauc.enable = lib.mkForce false;
        }
      )
    ];
    specialArgs = {
      inherit self;
      developmentMode = true;
      nixstasis = self.inputs.nixstasis;
    };
  };
  rejectedTraversal = builtins.tryEval (self.inputs.nixpkgs.lib.nixosSystem {
    inherit system;
    modules = [
      ../../modules/base.nix
      qemuModule
      (
        { lib, ... }:
        {
          atomixos.nixstasis = {
            enable = true;
            apiUrl = "https://nixstasis.example.test";
            frp.serverAddr = "frp.example.test";
            runtime.authorizedKeysPath = "/data/nixstasis/../config/ssh-authorized-keys/admin";
          };
          atomixos.rauc.enable = lib.mkForce false;
        }
      )
    ];
    specialArgs = {
      inherit self;
      developmentMode = true;
      nixstasis = self.inputs.nixstasis;
    };
  }).config.system.build.toplevel;
  cfg = evaluated.config;
  configYaml = builtins.readFile cfg.environment.etc."nixstasis/config.yaml".source;
in
pkgs.runCommand "nixstasis-module-check" { } ''
  set -euo pipefail

  grep -q 'url: https://nixstasis.example.test' ${cfg.environment.etc."nixstasis/config.yaml".source}
  grep -q 'server_addr: frp.example.test' ${cfg.environment.etc."nixstasis/config.yaml".source}
  grep -q 'authorized_keys_path: /data/nixstasis/.ssh/authorized_keys' ${cfg.environment.etc."nixstasis/config.yaml".source}

  test ${builtins.toJSON (builtins.elem "/data/nixstasis/.ssh/authorized_keys" cfg.services.openssh.authorizedKeysFiles)} = true
  test ${builtins.toJSON (builtins.elem "d /data/nixstasis 0700 root root - -" cfg.systemd.tmpfiles.rules)} = true
  test ${builtins.toJSON (builtins.elem "d /data/nixstasis/.ssh 0700 root root - -" cfg.systemd.tmpfiles.rules)} = true
  test ${builtins.toJSON (builtins.elem "d /data/nixstasis/poll/tmp 0700 root root - -" cfg.systemd.tmpfiles.rules)} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.environment.NIXSTASIS_IDENTITY_PATH == "/data/nixstasis/id")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.environment.NIXSTASIS_FRPC_BINARY_PATH == "${cfg.atomixos.nixstasis.package}/libexec/nixstasis/frpc")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.environment.NIXSTASIS_FRPC_CONFIG_PATH == "${cfg.atomixos.nixstasis.package}/share/nixstasis/frpc.toml")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.environment.NIXSTASIS_CONFIG_FILE == "/etc/nixstasis/config.yaml")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.environment.NIXSTASIS_FRPC_BINARY_PATH == "${cfg.atomixos.nixstasis.package}/libexec/nixstasis/frpc")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.environment.NIXSTASIS_FRPC_CONFIG_PATH == "${cfg.atomixos.nixstasis.package}/share/nixstasis/frpc.toml")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.serviceConfig.ExecStart == "${cfg.atomixos.nixstasis.package}/bin/nixstasis register")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.serviceConfig.ExecStart == "${cfg.atomixos.nixstasis.package}/bin/nixstasis poll")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.serviceConfig.NoNewPrivileges == true)} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-registration.serviceConfig.ProtectSystem == "strict")} = true
  test ${builtins.toJSON (builtins.elem "/data/nixstasis" cfg.systemd.services.nixstasis-poll.serviceConfig.ReadWritePaths)} = true
  test ${builtins.toJSON (builtins.elem "/data/nixstasis/poll" cfg.systemd.services.nixstasis-poll.serviceConfig.ReadWritePaths)} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.serviceConfig.Environment == "TMPDIR=/data/nixstasis/poll/tmp")} = true
  test ${builtins.toJSON (cfg.systemd.services.nixstasis-poll.unitConfig.StartLimitBurst == 5)} = true
  test ${builtins.toJSON (builtins.elem "AF_INET" cfg.systemd.services.nixstasis-poll.serviceConfig.RestrictAddressFamilies)} = true
  test ${builtins.toJSON (!rejectedTraversal.success)} = true

  mkdir -p "$out"
  cp ${cfg.environment.etc."nixstasis/config.yaml".source} "$out/config.yaml"
''
