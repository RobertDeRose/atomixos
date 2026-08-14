# Nixstasis Enrollment

AtomixOS supports Nixstasis enrollment as immutable base-system code. Standalone images keep the existing network
bootstrap by default; fleet images opt into a separate loopback-only transport at build time.

## Network Bootstrap Flow

The default `bootstrap_transport = "network"` policy preserves the existing local recovery path:

1. The device boots with no embedded remote-management credential.
2. The Nixstasis client identifies the device using the `eth0` MAC address.
3. Nixstasis checks that MAC against an approved inventory list.
4. If approved, Nixstasis returns a device UUID and runtime token.
5. The device persists that identity at `/data/nixstasis/id` for future authenticated requests.
6. Nixstasis can issue short-lived SSH credentials and establish remote sessions through the reverse tunnel managed by
   the device client.

This enrollment flow does not change the network bootstrap listener. The build policy must opt into the fleet transport
explicitly; enabling the Nixstasis client alone does not expose or restrict the provisioning API.

## Fleet Bootstrap Flow

Fleet images set `provisioning.bootstrap_transport = "nixstasis"` and bind the existing provisioning API only to
`127.0.0.1:8080`. The flow has separate authorization gates:

1. The immutable Nixstasis client registers and waits for device approval. Approval issues the normal runtime identity;
   it does not start FRPC.
2. The server issues a separate `remote_access_token` and the named `atomixos-bootstrap` profile. Only then does the
   client start FRPC.
3. The client-owned profile renders a bounded plain-HTTP route to `127.0.0.1:8080` and rewrites the downstream
   `Host` header to `localhost`. AtomixOS does not accept arbitrary FRPC TOML, plugins, targets, or credentials.
4. The Nixstasis server action submits the exact initial `config.toml` or bundle bytes to the existing programmatic
   `POST /api/config` route and polls the returned job resource. It does not use the browser Boot UI, `/apply`, or its
   CSRF token, and it never writes `/data/config` directly.
5. AtomixOS uses the normal asynchronous validation, staging, promotion, activation, health-check, rollback, and job
   reporting pipeline. The server records a terminal success or failure before withdrawing the route lease.
6. An indeterminate upload or polling result retains the lease for explicit reconciliation, withdrawal, or expiry; it
   is never silently reposted. After withdrawal, the client stops FRPC.

The fleet socket remains loopback-only after provisioning. Later re-apply requests use the existing SSH-signature
boundary, not the first-boot exception. Fleet mode does not install the pending WAN bootstrap rule or rebind the socket
to the provisioned LAN gateway.

The AtomixOS image consumes the published Nixstasis capability pinned at `6afcb7641b3cd4ed3db467df26b1b8ffc780f863`.
The named route profile, fixed Host rewrite, and server delivery action are owned by upstream tasks `nixstasis-255`,
`nixstasis-fss`, and `nixstasis-4gg`.

## Trust Model

- The MAC address is an identifier, not a secret.
- Inventory approval determines whether a device is eligible to enroll.
- The runtime token in `/data/nixstasis/id` is the first durable management credential.
- A separate remote-access lease authorizes the temporary FRP route.
- FRP credentials are runtime state only and do not enter `build.toml`, derivation metadata, or rendered route files.
- Short-lived SSH credentials are issued dynamically by Nixstasis and expire automatically.
- Nixstasis-managed SSH keys are stored separately from provisioned operator keys at
  `/data/nixstasis/.ssh/authorized_keys`.

## Device Responsibilities

AtomixOS remains responsible for:

- local LAN gateway services (`dnsmasq`, `chrony`, firewall)
- SSH access for LAN/VPN recovery
- RAUC update and rollback flow
- the loopback provisioning API and its complete config/bundle pipeline
- persistent storage of enrollment state under `/data/nixstasis`

Nixstasis remains responsible for inventory approval, remote-access authorization, bounded route selection, server-side
artifact delivery, job polling, audit state, and route-lease withdrawal. Public FRPS/Caddy deployment and public
end-to-end transport validation remain outside the AtomixOS repository boundary.
