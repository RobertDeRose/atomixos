# Fleet Bootstrap via Nixstasis

Fleet images can receive their first configuration through Nixstasis instead of the local network, without a second
provisioning API. The default `network` transport stays in place for standalone, personal, and development images. An
explicit `nixstasis` transport binds the first-boot API to `127.0.0.1:8080`, keeps it off WAN and LAN, and exposes it
only through a named `atomixos-bootstrap` plain-HTTP route through Nixstasis. The original plan is in the
[design record](design.md); Beads tracks the work under `atomixos-mol-efd`.

## What changed for users

- **Operators** build fleet images with non-secret `[provisioning]` and `[nixstasis]` policy in `build.toml`.
- Delivery is gated: the server must approve the device, issue a separate `remote_access_token`, and start the route
  before it submits the complete configuration with `POST /api/config`. It then polls the job, records the result, and
  withdraws the lease.
- After initial provisioning, the one-time remote-access lease is withdrawn, the FRP session is cleaned up, the socket
  stays loopback-only, and later changes use the normal SSH-signature flow.
- The browser console is a separate local workflow, not the fleet transport.

## How it fits in

The feature reuses the build-policy evaluator, NixOS option mapping, socket activation, firewall policy, the Nixstasis
client, and the provisioning service. AtomixOS still validates, stages, promotes, activates, health-checks, and rolls
back the configuration or bundle through its usual pipeline. The Nixstasis client uses a fixed route profile and
rewrites the local `Host` header to `localhost`; it accepts no arbitrary FRPC TOML, plugins, targets, or credentials.
Route profiles, Host rewriting, and server-side delivery belong to Nixstasis.

## Running it

A fleet image must be built with the reviewed Nixstasis API URL and FRP server address, and the Nixstasis server must
approve the device before its first bundle can be delivered. If Nixstasis is unavailable, the device stays recoverable
locally but cannot finish server-side bootstrap until enrollment and remote access resume. See
[Fleet Bootstrap](../../provisioning/fleet-bootstrap.md) for the procedure.

## Differences from the design

- The fleet VM test models asynchronous `202 Accepted` submission and polling instead of synchronous validation
  responses.
- FRP cleanup is checked through service and runtime cleanup instead of a signal trap in a child process.

## Not included

- Validation of a public FRPS and Caddy deployment, which belongs to the Nixstasis server.
- A second provisioning API, direct writes to `/data`, the browser console as the fleet transport, server-supplied FRPC
  configuration or secrets, and a WAN or LAN fallback in fleet images.

## Tests

- `checks.<system>.nixstasis-client`: registration, identity reuse, polling, the FRP launch boundary, and an API outage
  after enrollment.
- `checks.<system>.fleet-bootstrap`: the loopback socket, the named route profile, Host rewriting, withdrawal, and
  token secrecy.
- `checks.<system>.build-configuration`: rejection of invalid fleet transport policy.

## Related pages

- [Fleet Bootstrap](../../provisioning/fleet-bootstrap.md)
- [Nixstasis Enrollment](../../architecture/nixstasis-enrollment.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Build Configuration](../../reference/build-configuration.md)
- [Testing](../../testing.md)
- [Nixstasis Client](../nixstasis-client/index.md)
