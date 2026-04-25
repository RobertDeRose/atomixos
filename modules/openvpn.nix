# OpenVPN configuration for recovery management access.
# Included in the rootfs so it survives container-layer failures.
{
  config,
  lib,
  pkgs,
  ...
}:

{
  # ── OpenVPN ──────────────────────────────────────────────────────────────────
  #
  # OpenVPN is configured but the actual VPN config (server address, keys, certs)
  # is expected to be provisioned to /data/config/openvpn/ during device setup.
  # This module just ensures the OpenVPN package and service infrastructure is
  # available in the rootfs.

  environment.systemPackages = [ pkgs.openvpn ];

  # If a client config exists on /data, use it
  services.openvpn.servers.recovery = {
    config = ''
      config /data/config/openvpn/client.conf
    '';
    autoStart = false; # Only start when explicitly enabled or config exists
  };

  # Systemd override: only start if config file exists
  systemd.services.openvpn-recovery = {
    unitConfig = {
      ConditionPathExists = "/data/config/openvpn/client.conf";
    };
  };
}
