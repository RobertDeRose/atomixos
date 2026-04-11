# Cockpit web management — runs as a pod (quay.io/cockpit/ws).
# The pod SSHes into the host on localhost:22 and spawns a Python bridge
# via python3Minimal in the rootfs. Accessed through Traefik reverse proxy.
#
# Uses a raw systemd unit calling podman directly rather than the NixOS
# oci-containers module, to avoid pulling extra dependencies (openssl, krb5)
# into the squashfs closure.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── Cockpit container via raw systemd + podman ─────────────────────────────
  # The container image lives on /persist/containers via podman's graph root.
  # On first boot, ExecStartPre pulls the image if not already present.

  systemd.services.cockpit-ws = {
    description = "Cockpit web management (container)";
    after = [
      "network-online.target"
      "podman.socket"
    ];
    wants = [ "network-online.target" ];
    wantedBy = [ "multi-user.target" ];

    # Use the NixOS-wrapped podman from the podman module
    path = [ config.virtualisation.podman.package ];

    serviceConfig = {
      Type = "simple";
      Restart = "on-failure";
      RestartSec = "10s";

      ExecStartPre = [
        # Pull the image if not already present (first boot).
        # Subsequent boots use the cached image — pull is a no-op.
        "${config.virtualisation.podman.package}/bin/podman pull --quiet quay.io/cockpit/ws"
        # Remove any existing container from a previous failed start.
        "-${config.virtualisation.podman.package}/bin/podman rm -f cockpit-ws"
      ];
      ExecStart = builtins.concatStringsSep " " [
        "${config.virtualisation.podman.package}/bin/podman"
        "run"
        "--rm"
        "--name=cockpit-ws"
        # Host networking — Cockpit SSHes to localhost:22 to reach the host
        # sshd, which allows password auth from 127.0.0.1 only.
        "--network=host"
        # Cockpit listens on 127.0.0.1:9090 — only Traefik can reach it.
        # Port 443 on WAN is handled by Traefik reverse proxy.
        "--env=COCKPIT_WS_ARGS=--address=127.0.0.1 --port=9090 --no-tls"
        # Mount cockpit configuration from /persist (if present).
        "--volume=/persist/config/cockpit:/etc/cockpit:ro"
        "quay.io/cockpit/ws"
      ];
      ExecStop = "${config.virtualisation.podman.package}/bin/podman stop cockpit-ws";

      # Sandboxing
      ProtectSystem = "strict";
      ReadWritePaths = [
        "/run/podman"
        "/var/lib/containers"
        "/tmp"
      ];
    };
  };

  # ── Cockpit configuration directory ────────────────────────────────────────
  # Ensure the cockpit config directory exists on /persist.
  # The actual cockpit.conf is created during provisioning or manually.
  systemd.tmpfiles.rules = [
    "d /persist/config/cockpit 0755 root root -"
  ];
}
