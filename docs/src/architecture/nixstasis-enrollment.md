# Nixstasis Enrollment

Nixstasis is an optional fleet service that approves devices, grants remote access, and can deliver a device's first
configuration. The Nixstasis client is part of the immutable image, enabled through the `[nixstasis]` section of
`build.toml`. Two build-time choices decide how it is used:

- **Enrollment only** (`provisioning.bootstrap_transport = "network"`, the default). The device enrolls with Nixstasis,
  and provisioning still happens through the local bootstrap console.
- **Fleet bootstrap** (`provisioning.bootstrap_transport = "nixstasis"`). Nixstasis also delivers the first
  configuration, and the provisioning API listens only on loopback.

Turning on the client alone never opens or closes the provisioning API; only `bootstrap_transport` does that. The
operator steps are in [Fleet Bootstrap](../provisioning/fleet-bootstrap.md).

## Enrollment

1. The device boots with no remote-management credential.
2. The Nixstasis client identifies the device by the MAC address of its `wan` interface.
   `atomixos.nixstasis.identityInterface` defaults to the WAN interface and becomes the client's `identity.interface`.
   If that interface is missing, registration fails and heartbeats report no MAC, rather than using another NIC's MAC.
3. Nixstasis checks that MAC against its approved inventory.
4. If the device is approved, Nixstasis returns a device UUID and a runtime token.
5. The client stores that identity, with the registered MAC, at `/data/nixstasis/id` and uses it for every later
   request. Until approval, the enrollment proof and MAC live in `/data/nixstasis/registration`, so a restart reuses the
   same MAC.

Enrollment does not change how the provisioning API listens.

## Fleet Bootstrap Flow

In fleet mode the provisioning API binds only to `127.0.0.1:8080`, and Nixstasis reaches it through a temporary FRP
tunnel. Each step needs its own authorization:

1. The client registers and waits for approval. Approval issues the runtime identity but does not start the tunnel.
2. Nixstasis issues a separate `remote_access_token` and selects the named `atomixos-bootstrap` profile. Only then does
   the client start FRPC.
3. The profile, owned by the client, opens one plain-HTTP route to `127.0.0.1:8080` and rewrites the `Host` header to
   `localhost`. AtomixOS does not accept arbitrary FRPC configuration, plugins, targets, or credentials.
4. Nixstasis submits the exact `config.toml` or bundle bytes to `POST /api/config` and polls the job it gets back. It
   does not use the browser Boot UI, `/apply`, or its CSRF token, and it never writes `/data/config` directly.
5. The device validates, stages, activates, health-checks, and if needed rolls back the configuration exactly as it
   would for a local upload. Nixstasis records the final success or failure before it withdraws the route.
6. If the upload or polling result is unknown, Nixstasis keeps the route for an explicit retry decision, withdrawal, or
   expiry; it never resends on its own. Once the route is withdrawn, the client stops FRPC.

After provisioning, the API stays on loopback. Later re-applies need an SSH signature like any other re-apply. Fleet
mode never opens the WAN bootstrap port and never moves the API to the LAN gateway address.

The image gets the client from the pinned `nixstasis` flake input.

## Trust Model

- The MAC address is an identifier, not a secret.
- Inventory approval decides whether a device may enroll.
- The runtime token in `/data/nixstasis/id` is the first lasting management credential.
- A separate remote-access lease authorizes each temporary FRP route.
- FRP credentials exist only at runtime. They never appear in `build.toml`, build metadata, or rendered route files.
- The client derives the FRP proxy name from the registered device UUID; images cannot configure it.
- Runtime scripts may run only commands listed in `atomixos.nixstasis.runtime.execCommands`, and may pass arguments
  only as exact vectors listed in `runtime.execCommandArgs` under the command's absolute path.
- The client requires HTTPS for the Nixstasis API. `atomixos.nixstasis.allowLoopbackHttp` permits plain HTTP to a
  loopback API, for tests only.
- Nixstasis-managed SSH keys live in `/data/nixstasis/.ssh/authorized_keys`, apart from provisioned operator keys.

## Who Owns What

The device is responsible for:

- LAN gateway services (`dnsmasq`, `chrony`, the firewall)
- SSH access for LAN and VPN recovery
- RAUC updates and rollback
- the loopback provisioning API and its full configuration pipeline
- keeping enrollment state under `/data/nixstasis`

Nixstasis is responsible for inventory approval, remote-access authorization, route selection, delivering the
configuration, polling jobs, its audit records, and withdrawing routes. The public FRPS and Caddy deployment that
carries the tunnels belongs to the Nixstasis deployment, not to this repository.
