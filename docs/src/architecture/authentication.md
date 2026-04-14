# Authentication (EN18031)

AtomixOS ships with no embedded credentials. EN18031 compliance requires that each device has unique credentials
provisioned at factory time -- there are no default passwords or shared secrets.

## Credential Provisioning

During [eMMC provisioning](../provisioning/emmc-provisioning.md), the operator provides:

| Credential | Storage Path | Format |
|-----------|-------------|--------|
| Admin password | `/persist/config/admin-password-hash` | SHA-512 hash |
| SSH public key | `/persist/config/ssh-authorized-keys/admin` | OpenSSH format |
| TLS certificate | `/persist/config/traefik/certs/` | Self-signed EC P-256 |
| OIDC config | `/persist/config/traefik/dynamic/` | Traefik forward-auth middleware |

## Authentication Flows

### SSH Access

- **LAN (eth1)**: Key-only authentication via SSH public key
- **VPN (tun0)**: Key-only authentication via SSH public key
- **WAN (eth0)**: Disabled by default; enabled only when `/persist/config/ssh-wan-enabled` flag file exists
- **Localhost**: Password authentication allowed (required for Cockpit's SSH bridge)

### Web Management (Cockpit)

Cockpit runs as a container (`quay.io/cockpit/ws`) on the loopback interface (127.0.0.1:9090). Traefik terminates TLS on
port 443 and reverse-proxies to Cockpit.

Two authentication paths:

1. **OIDC (primary)**: Microsoft Entra via Traefik forward-auth middleware. Used when internet is available.
2. **Local password (fallback)**: The provisioned admin password. Used on the LAN or when internet is unavailable.

LAN clients (`172.20.30.0/24`) bypass OIDC and authenticate directly with the local password.

### Device Identity

Each device is identified by the MAC address of its onboard Ethernet (eth0). This MAC is used as the `X-Device-ID`
header when polling for updates.

## SSH Configuration

```nix
services.openssh = {
  enable = true;
  settings = {
    PermitRootLogin = "no";
    PasswordAuthentication = false;
  };
};

# Exception: allow password auth from localhost for Cockpit
services.openssh.extraConfig = ''
  Match Address 127.0.0.1,::1
    PasswordAuthentication yes
'';
```

The `admin` user's authorized keys are read from `/persist/config/ssh-authorized-keys/admin`, which is populated during
provisioning.
