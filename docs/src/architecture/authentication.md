# Authentication (EN18031)

AtomixOS ships with no embedded credentials. EN18031 compliance requires that each device has unique credentials
provisioned at factory time -- there are no default passwords or shared secrets.

## Provisioning State

Persisted device-local state lives on `/data`:

| Item                       | Storage Path                              | Notes                                             |
|----------------------------|-------------------------------------------|---------------------------------------------------|
| Admin signer keys          | `/data/config/admin-signers`              | Admin SSH keys trusted for config re-apply        |
| User SSH public keys       | `/data/config/ssh-authorized-keys/<user>` | Per-user LAN/VPN SSH access                       |
| Nixstasis identity         | `/data/nixstasis/id`                      | Device UUID and runtime token issued by Nixstasis |
| Nixstasis SSH public keys  | `/data/nixstasis/.ssh/authorized_keys`    | Remote-access keys managed by Nixstasis commands  |

## Authentication Flows

### SSH Access

- **LAN (eth1)**: Key-only authentication via SSH public key
- **VPN (tun0)**: Key-only authentication via SSH public key
- **WAN (eth0)**: Disabled by default; enabled only when `/data/config/ssh-wan-enabled` flag file exists

### Physical Recovery

Rock64 keeps a separate physical break-glass path. If `_RUT_OH_=1` is set in
U-Boot, the next boot starts a serial-only root autologin on `ttyS2` and clears
that flag after use. This is a local recovery mechanism, not part of normal
network authentication.

### Nixstasis Enrollment

The target remote-management model is Nixstasis-managed enrollment and access:

1. The device identifies itself to Nixstasis using the `eth0` MAC address.
2. Nixstasis checks that MAC against an approved inventory list.
3. Approved devices receive a device UUID and runtime token, persisted as `/data/nixstasis/id`.
4. Future device requests authenticate with that runtime identity.
5. Nixstasis issues short-lived SSH credentials and establishes remote sessions over the reverse tunnel managed by the
    Nixstasis client.

The MAC address is an eligibility identifier, not a secret. The runtime token is the first durable credential in the
management flow.

### Remote Management

Remote web access is intended to run from the Nixstasis environment rather than from services hosted directly on the
device. The device remains responsible for SSH, LAN gateway services, update logic, and the Nixstasis client.

### Device Identity

Each device is identified by the compact lowercase 12-hex MAC address of its onboard Ethernet (eth0). For example,
`aa:bb:cc:dd:ee:ff` becomes `aabbccddeeff` in the `X-Device-ID` header when polling for updates.

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

User authorized keys are read from `/data/config/ssh-authorized-keys/<user>`, which is populated during provisioning.
Admin re-apply signer keys are stored separately in `/data/config/admin-signers`.
When Nixstasis is enabled, OpenSSH also reads `/data/nixstasis/.ssh/authorized_keys` as a separate remote-access key
source. Nixstasis-managed keys do not replace provisioned operator keys and are not copied into `/data/config`.
