{
  config,
  lib,
  nixstasis,
  pkgs,
  ...
}:

let
  cfg = config.atomixos.nixstasis;
  clientPackage = cfg.package;
  settings = {
    api.url = cfg.apiUrl;
    poll.interval = cfg.pollInterval;
    scripts.dir = cfg.scriptsDir;
    frp = {
      auth_token = "";
      name = cfg.frp.name;
      server_addr = cfg.frp.serverAddr;
      server_port = cfg.frp.serverPort;
      web_server_addr = cfg.frp.webServerAddr;
      web_server_port = cfg.frp.webServerPort;
      http_local_addr = cfg.frp.httpLocalAddr;
      ssh_local_port = cfg.frp.sshLocalPort;
    };
    runtime = {
      mqtt_broker = cfg.runtime.mqttBroker;
      authorized_keys_path = cfg.runtime.authorizedKeysPath;
      exec_work_dir = cfg.runtime.execWorkDir;
      exec_env = cfg.runtime.execEnv;
      exec_commands = cfg.runtime.execCommands;
      mqtt_publish_topics = cfg.runtime.mqttPublishTopics;
      mqtt_subscribe_topics = cfg.runtime.mqttSubscribeTopics;
    };
    log = {
      level = cfg.log.level;
      format = cfg.log.format;
    };
  };
  configFile = (pkgs.formats.yaml { }).generate "nixstasis-config.yaml" settings;
  pathComponents = lib.splitString "/" cfg.runtime.authorizedKeysPath;
  commonEnvironment = {
    NIXSTASIS_CONFIG_FILE = "/etc/nixstasis/config.yaml";
    NIXSTASIS_IDENTITY_PATH = "${toString cfg.stateDir}/id";
    NIXSTASIS_FRPC_BINARY_PATH = "${clientPackage}/libexec/nixstasis/frpc";
    NIXSTASIS_FRPC_CONFIG_PATH = "${clientPackage}/share/nixstasis/frpc.toml";
  };
  commonServiceConfig = {
    DynamicUser = false;
    LockPersonality = true;
    MemoryDenyWriteExecute = true;
    NoNewPrivileges = true;
    PrivateTmp = true;
    ProtectClock = true;
    ProtectControlGroups = true;
    ProtectHome = true;
    ProtectHostname = true;
    ProtectKernelLogs = true;
    ProtectKernelModules = true;
    ProtectKernelTunables = true;
    ProtectSystem = "strict";
    ReadWritePaths = [ (toString cfg.stateDir) ];
    Restart = "always";
    RestartSec = "120s";
    RestrictAddressFamilies = [
      "AF_INET"
      "AF_INET6"
      "AF_NETLINK"
      "AF_UNIX"
    ];
    RestrictNamespaces = true;
    RestrictRealtime = true;
    SystemCallArchitectures = "native";
    UMask = "0077";
  };
  pollStateDir = "${toString cfg.stateDir}/poll";
in
{
  options.atomixos.nixstasis = {
    enable = lib.mkEnableOption "the Nixstasis client";

    package = lib.mkOption {
      type = lib.types.package;
      default = nixstasis.packages.${pkgs.stdenv.hostPlatform.system}.client;
      defaultText = lib.literalExpression "nixstasis.packages.\${pkgs.stdenv.hostPlatform.system}.client";
      description = "Nixstasis client package to install.";
    };

    apiUrl = lib.mkOption {
      type = lib.types.str;
      example = "https://nixstasis.example.com";
      description = "Base URL for the Nixstasis API.";
    };

    pollInterval = lib.mkOption {
      type = lib.types.str;
      default = "30s";
      description = "Polling interval passed to the Nixstasis client config.";
    };

    stateDir = lib.mkOption {
      type = lib.types.path;
      default = "/data/nixstasis";
      description = "Persistent Nixstasis state directory.";
    };

    scriptsDir = lib.mkOption {
      type = lib.types.str;
      default = "/usr/libexec/nixstasis/scripts";
      description = "Directory where Nixstasis runtime scripts are discovered.";
    };

    frp = {
      name = lib.mkOption {
        type = lib.types.str;
        default = "";
        description = "Optional FRP proxy name override.";
      };

      serverAddr = lib.mkOption {
        type = lib.types.str;
        example = "nixstasis.example.com";
        description = "FRP server address.";
      };

      serverPort = lib.mkOption {
        type = lib.types.port;
        default = 7000;
        description = "FRP server port.";
      };

      webServerAddr = lib.mkOption {
        type = lib.types.str;
        default = "127.0.0.1";
        description = "Loopback address for the local FRP admin endpoint.";
      };

      webServerPort = lib.mkOption {
        type = lib.types.port;
        default = 7400;
        description = "Local FRP admin endpoint port.";
      };

      httpLocalAddr = lib.mkOption {
        type = lib.types.str;
        default = "127.0.0.1:443";
        description = "Local HTTPS endpoint exposed through Nixstasis FRP.";
      };

      sshLocalPort = lib.mkOption {
        type = lib.types.port;
        default = 22;
        description = "Local SSH port exposed through Nixstasis FRP.";
      };
    };

    runtime = {
      authorizedKeysPath = lib.mkOption {
        type = lib.types.str;
        default = "/data/nixstasis/.ssh/authorized_keys";
        description = "Authorized keys file managed by Nixstasis remote-access commands.";
      };

      execWorkDir = lib.mkOption {
        type = lib.types.str;
        default = "/";
        description = "Working directory for allowlisted Nixstasis runtime commands.";
      };

      execEnv = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "LANG=C" ];
        description = "Environment entries available to allowlisted runtime commands.";
      };

      execCommands = lib.mkOption {
        type = lib.types.attrsOf lib.types.str;
        default = { };
        description = "Deny-by-default command allowlist for Nixstasis runtime scripts.";
      };

      mqttBroker = lib.mkOption {
        type = lib.types.str;
        default = "tcp://localhost:1883";
        description = "MQTT broker URL used by Nixstasis runtime scripts.";
      };

      mqttPublishTopics = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "nixstasis/+/request" ];
        description = "MQTT publish topics allowed for runtime scripts.";
      };

      mqttSubscribeTopics = lib.mkOption {
        type = lib.types.listOf lib.types.str;
        default = [ "nixstasis/+/response" ];
        description = "MQTT subscribe topics allowed for runtime scripts.";
      };
    };

    log = {
      level = lib.mkOption {
        type = lib.types.enum [
          "debug"
          "info"
          "warn"
          "error"
        ];
        default = "info";
        description = "Nixstasis client log level.";
      };

      format = lib.mkOption {
        type = lib.types.enum [
          "json"
          "text"
        ];
        default = "text";
        description = "Nixstasis client log format.";
      };
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = cfg.apiUrl != "";
        message = "atomixos.nixstasis.apiUrl must be set when Nixstasis is enabled";
      }
      {
        assertion = cfg.frp.serverAddr != "";
        message = "atomixos.nixstasis.frp.serverAddr must be set when Nixstasis is enabled";
      }
      {
        assertion =
          lib.hasPrefix "${toString cfg.stateDir}/" cfg.runtime.authorizedKeysPath
          && !(builtins.elem ".." pathComponents);
        message = "atomixos.nixstasis.runtime.authorizedKeysPath must live under atomixos.nixstasis.stateDir";
      }
    ];

    environment.systemPackages = [ clientPackage ];
    environment.etc."nixstasis/config.yaml".source = configFile;

    services.openssh.authorizedKeysFiles = lib.mkAfter [ cfg.runtime.authorizedKeysPath ];

    systemd.tmpfiles.rules = [
      "d ${toString cfg.stateDir} 0700 root root - -"
      "d ${toString cfg.stateDir}/.ssh 0700 root root - -"
      "d ${pollStateDir} 0700 root root - -"
      "d ${pollStateDir}/tmp 0700 root root - -"
    ];

    systemd.services.nixstasis-registration = {
      description = "Nixstasis Registration";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];
      unitConfig.ConditionPathExists = "!${toString cfg.stateDir}/id";
      path = [ pkgs.systemd ];
      environment = commonEnvironment;
      serviceConfig = commonServiceConfig // {
        Type = "simple";
        ExecStart = "${clientPackage}/bin/nixstasis register";
      };
    };

    systemd.services.nixstasis-poll = {
      description = "Poll Nixstasis with device details";
      after = [
        "network-online.target"
        "nixstasis-registration.service"
      ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];
      unitConfig = {
        ConditionPathExists = "${toString cfg.stateDir}/id";
        StartLimitIntervalSec = 600;
        StartLimitBurst = 5;
      };
      path = [
        pkgs.systemd
        pkgs.coreutils
      ];
      environment = commonEnvironment;
      serviceConfig = commonServiceConfig // {
        Type = "simple";
        ExecStart = "${clientPackage}/bin/nixstasis poll";
        Environment = "TMPDIR=${pollStateDir}/tmp";
        ReadWritePaths = [
          (toString cfg.stateDir)
          pollStateDir
        ];
      };
    };
  };
}
