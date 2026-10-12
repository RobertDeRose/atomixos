# Fleet Bootstrap via Nixstasis

## References

- Beads feature root: `atomixos-mol-efd`
- Design record: [design.md](design.md)

## Delivered Capability

Fleet images can opt into an immutable Nixstasis bootstrap transport without changing the
existing provisioning API. The build policy keeps the default `network` transport for
standalone, personal, and development images. An explicit `nixstasis` transport binds the
first-boot API to loopback at `127.0.0.1:8080`, suppresses WAN/LAN bootstrap exposure, and
uses a named `atomixos-bootstrap` plain-HTTP route through Nixstasis.

The server-side flow remains gated by device approval, a separate `remote_access_token`,
route startup, complete `POST /api/config` submission, asynchronous job polling, terminal
result recording, and lease withdrawal. AtomixOS continues to validate, stage, promote,
activate, health-check, and roll back the canonical config or bundle through its existing
pipeline. Browser Boot UI access remains a separate local workflow; it is not the fleet
transport.

## User-Facing Behavior

Operators build fleet images with non-secret `[provisioning]` and `[nixstasis]` policy in
`build.toml`. The Nixstasis client consumes the fixed route profile and rewrites the local
`Host` header to `localhost`; arbitrary FRPC TOML, plugins, targets, and credentials are not
accepted. After initial provisioning, the one-time remote-access lease is withdrawn, the
FRP session is cleaned up, the socket remains loopback-only, and later re-apply uses the
existing SSH-signature boundary.

## Design Integration

The feature reuses the immutable build-policy evaluator, NixOS option mapping, socket
activation, firewall policy, Nixstasis client, and provisioning service. It adds no second
provisioning command, direct `/data` write, network fallback, or credential path. External
route-profile, Host-rewrite, and server-delivery ownership remains with Nixstasis tasks
`nixstasis-255`, `nixstasis-fss`, and `nixstasis-4gg`.

## Operational Impact

A fleet image must be built with the reviewed Nixstasis API URL and FRP server address and
must be approved by the Nixstasis server before its initial bundle can be delivered. If
Nixstasis is unavailable, the device remains locally recoverable but cannot complete
server-side bootstrap until enrollment and remote access resume. The Nixstasis server
delivery task `nixstasis-4gg` owns the existing FRPS/Caddy HTTP path; public deployment
validation remains its external release/integration check and is not run in this
AtomixOS repository.

## Reference and Contracts

- [Fleet bootstrap operations](../../provisioning/fleet-bootstrap.md)
- [Nixstasis enrollment architecture](../../architecture/overwatch-enrollment.md)
- [Runtime boundaries](../../runtime-boundaries.md)
- [Build configuration reference](../../reference/build-configuration.md)
- [Testing](../../testing.md)
- [Nixstasis client design](../nixstasis-client/design.md)

## Test Coverage

- `checks.<system>.nixstasis-client` covers Nixstasis registration, identity reuse, polling, the FRP launch boundary, and
  the post-enrollment API outage path on `aarch64-darwin` and `aarch64-linux`.
- `checks.<system>.fleet-bootstrap` covers the loopback fleet socket, the named AtomixOS route profile, Host rewriting,
  withdrawal, and token secrecy.
- `checks.<system>.build-configuration` covers rejection of invalid fleet transport policy.

## Design Reconciliation

### Delivered as Designed

- Explicit immutable transport policy with `network` as the default.
- Loopback-only fleet listener and no WAN/LAN bootstrap fallback.
- Approval, remote-access lease, named route profile, existing API job, withdrawal, and
  SSH-signature gates.
- Existing validation, staging, promotion, activation, rollback, and job-reporting path.
- Credential secrecy and bounded Nixstasis ownership boundaries.

### Intentional Changes

- The fleet VM test models asynchronous `202 Accepted` job submission and polling rather
  than synchronous validation responses.
- FRP cleanup assertions verify service/runtime cleanup rather than relying on a child
  process signal trap.

### Deferred Work

- Public FRPS/Caddy deployment validation remains outside this AtomixOS feature and is
  owned by Nixstasis server delivery.

### Rejected or Removed Scope

- A second provisioning API or direct `/data` mutation path.
- Browser Boot UI as the fleet transport.
- Arbitrary server-provided FRPC TOML, plugins, targets, or secrets.
- WAN/LAN fallback exposure in fleet images.

## Documentation Updated

- `docs/src/features/fleet-bootstrap-via-nixstasis/index.md`
- `docs/src/features/index.md`
- `docs/src/SUMMARY.md`
- `docs/src/planned-features.md`
- `docs/src/architecture/overwatch-enrollment.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/provisioning/fleet-bootstrap.md`
- `docs/src/reference/build-configuration.md`
- `docs/src/testing.md`
