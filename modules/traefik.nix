# Traefik reverse proxy — runs as a pod (docker.io/library/traefik).
# Terminates TLS on port 443 (WAN) and routes to backend services on localhost.
# Currently routes to Cockpit (127.0.0.1:9090).
#
# Uses a raw systemd unit calling podman directly (same pattern as cockpit.nix)
# to avoid pulling extra dependencies into the squashfs closure.
#
# TLS certificates are loaded from /persist/config/traefik/certs/. The
# provisioning task generates a self-signed certificate; ACME or a proper CA
# cert can be deployed later via Cockpit or the update pipeline.
#
# Forward-auth middleware for OIDC (Microsoft Entra) is configured but
# disabled by default. Enable it by placing the forwardAuth config in
# /persist/config/traefik/dynamic/oidc.yaml.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Traefik container via raw systemd + podman ─────────────────────────────
  # The container image is pulled during device provisioning (not baked into
  # the squashfs). It lives on /persist/containers via podman's graph root.

  systemd.services.traefik = {
    description = "Traefik reverse proxy (container)";
    after = [
      "network-online.target"
      "podman.socket"
      "cockpit-ws.service"
    ];
    wants = [ "network-online.target" ];
    requires = [ "cockpit-ws.service" ];
    wantedBy = [ "multi-user.target" ];

    path = [ config.virtualisation.podman.package ];

    serviceConfig = {
      Type = "simple";
      Restart = "on-failure";
      RestartSec = "10s";

      ExecStartPre = "-${config.virtualisation.podman.package}/bin/podman rm -f traefik";
      ExecStart = builtins.concatStringsSep " " [
        "${config.virtualisation.podman.package}/bin/podman"
        "run"
        "--rm"
        "--name=traefik"
        # Host networking — Traefik binds 0.0.0.0:443 (WAN-facing) and
        # connects to Cockpit on 127.0.0.1:9090 (loopback only).
        "--network=host"
        # Mount static config from /persist
        "--volume=/persist/config/traefik/traefik.yaml:/etc/traefik/traefik.yaml:ro"
        # Mount dynamic config directory (service routes, middleware, OIDC)
        "--volume=/persist/config/traefik/dynamic:/etc/traefik/dynamic:ro"
        # Mount TLS certificates
        "--volume=/persist/config/traefik/certs:/etc/traefik/certs:ro"
        "docker.io/library/traefik:v3"
      ];
      ExecStop = "${config.virtualisation.podman.package}/bin/podman stop traefik";

      # Sandboxing
      ProtectSystem = "strict";
      ReadWritePaths = [
        "/run/podman"
        "/var/lib/containers"
        "/tmp"
      ];
    };
  };

  # ── Traefik configuration directories ──────────────────────────────────────
  # Ensure the traefik config directories exist on /persist.
  # Provisioning creates the actual config files and TLS certs.
  systemd.tmpfiles.rules = [
    "d /persist/config/traefik 0755 root root -"
    "d /persist/config/traefik/dynamic 0755 root root -"
    "d /persist/config/traefik/certs 0700 root root -"
  ];
}
