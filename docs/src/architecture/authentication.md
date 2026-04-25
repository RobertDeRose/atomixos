# Authentication (EN18031)

AtomixOS ships with no embedded credentials. EN18031 compliance requires that each device has unique credentials
provisioned at factory time -- there are no default passwords or shared secrets.

For local development, the build can opt into a dev-only path via `.env`
(`DEVELOPMENT=1`) that seeds a locally generated admin password hash on first
boot. This is intended only for test images and is not enabled by default.

## Provisioning State

Persisted device-local state lives on `/data`:

| Item                       | Storage Path                              | Notes                                             |
|----------------------------|-------------------------------------------|---------------------------------------------------|
| Admin password             | `/data/config/admin-password-hash`        | Optional local recovery credential                |
| SSH public key             | `/data/config/ssh-authorized-keys/admin`  | Local operator key for LAN/VPN access             |
| Nixstasis registration key | `/data/config/nixstasis/registration-key` | Planned persistent device enrollment credential   |
| Nixstasis agent state      | `/data/config/nixstasis/`                 | Planned client state, tunnel config, and metadata |

## Authentication Flows

### SSH Access

- **LAN (eth1)**: Key-only authentication via SSH public key
- **VPN (tun0)**: Key-only authentication via SSH public key
- **WAN (eth0)**: Disabled by default; enabled only when `/data/config/ssh-wan-enabled` flag file exists

When `DEVELOPMENT=1` is enabled at build time, the image also enables password
authentication for SSH and seeds `/data/config/ssh-wan-enabled` on first boot
to simplify recovery and SSH testing.

### Nixstasis Enrollment

The target remote-management model is Nixstasis-managed enrollment and access:

1. The device identifies itself to Nixstasis using the `eth0` MAC address.
2. Nixstasis checks that MAC against an approved inventory list.
3. Approved devices receive a registration key and persist it on `/data`.
4. Future device requests authenticate with that registration key.
5. Nixstasis issues short-lived SSH credentials and establishes remote sessions over the reverse tunnel managed by the
   Nixstasis client.

The MAC address is an eligibility identifier, not a secret. The registration key is the first durable credential in the
management flow.

### Remote Management

Remote Cockpit access is intended to run from the Nixstasis environment rather than from services hosted directly on the
device. The device remains responsible for SSH, LAN gateway services, update logic, and the Nixstasis client.

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
```

The `admin` user's authorized keys are read from `/data/config/ssh-authorized-keys/admin`, which is populated during
provisioning.
