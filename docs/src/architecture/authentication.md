# Authentication

AtomixOS images contain no credentials. There are no default passwords and no shared keys; each device gets its own
credentials when it is provisioned. This is what the EN 18031 requirements for connected devices ask for, and it means
one leaked image never unlocks a fleet.

## Credential Storage

Device credentials live on `/data`, so they survive updates and rollbacks:

| Item                      | Path                                      | Purpose                                           |
|---------------------------|-------------------------------------------|---------------------------------------------------|
| Admin signer keys         | `/data/config/admin-signers`              | SSH keys allowed to sign configuration re-applies |
| User SSH public keys      | `/data/config/ssh-authorized-keys/<user>` | Per-user SSH login                                |
| SSH host key              | `/data/ssh/ssh_host_ed25519_key`          | The device's own SSH identity                     |
| Nixstasis identity        | `/data/nixstasis/id`                      | Device UUID and runtime token issued by Nixstasis |
| Nixstasis SSH public keys | `/data/nixstasis/.ssh/authorized_keys`    | Remote-access keys for the Nixstasis SSH user     |

The local `root` password is locked, and the image has no built-in operator account. Accounts come from the `[users]`
section of the provisioned `config.toml`; see [Data Flow](../data-flow.md#managed-users-flow).

## SSH Access

SSH accepts keys only. Root login and password authentication are off:

```nix
services.openssh = {
  enable = true;
  settings = {
    PermitRootLogin = "no";
    PasswordAuthentication = false;
  };
};
```

Where you can connect from:

- **LAN (`lan`):** always, with a provisioned key.
- **WAN (`wan`):** only while the flag file `/data/config/ssh-wan-enabled` exists. Nothing creates it automatically.

The device presents one Ed25519 host key, generated on the first boot after `/data` is created and kept at
`/data/ssh/ssh_host_ed25519_key`. It stays the same across reboots, updates, and rollbacks, so a changed host key
means the device was reflashed with a new `/data` or something else is answering. Reprovisioning does not replace it,
because the key lives outside `/data/config`.

User keys are read from `/data/config/ssh-authorized-keys/<user>`. Admin signer keys are kept separately in
`/data/config/admin-signers`, so being able to log in does not by itself allow re-applying configuration. How signed
re-applies work is described in [Data Flow](../data-flow.md#re-apply-flow).

When the Nixstasis client is enabled, `modules/nixstasis.nix` adds a `Match User` block for its SSH user (`admin` by
default) that points `AuthorizedKeysFile` at `/data/nixstasis/.ssh/authorized_keys`. Nixstasis-managed keys are kept
apart from provisioned operator keys and are never copied into `/data/config`.

## Physical Recovery

Every hardware board keeps a separate break-glass path for someone with the board in hand. If the U-Boot variable
`_RUT_OH_` is set to `1`, the next boot starts a serial-only root login on `ttyS2` and clears the variable. This is a
local recovery tool, not part of network authentication.

To set the variable:

- **From a running system:** run `fw_setenv _RUT_OH_ 1`.
- **With no login available:** on the serial console, interrupt autoboot, then run `setenv _RUT_OH_ 1; saveenv; reset`
  at the U-Boot prompt.

## Device Identity

A device is identified by the MAC address of its onboard Ethernet (the [`wan` interface](network-topology.md#nic-naming)),
written as 12 lowercase hex digits with no separators: `aa:bb:cc:dd:ee:ff` becomes `aabbccddeeff`. The update client
sends it in the `X-Device-ID` header, or `unknown` when it cannot read the address, and the Nixstasis client uses it to
enroll.

A MAC address is an identifier, not a secret. Nixstasis enrollment, described in
[Nixstasis Enrollment](nixstasis-enrollment.md), issues the device's first real credential.

## Remote Management

The device hosts no web management interface. Remote management runs in Nixstasis, which reaches the device through a
tunnel opened by the Nixstasis client. The device itself is responsible for SSH, its LAN gateway services, updates, and
the client.
