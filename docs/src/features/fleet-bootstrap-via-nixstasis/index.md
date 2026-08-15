# Fleet Bootstrap via Nixstasis

## Delivery Summary

- Beads feature root: `atomixos-mol-efd`
- Status: ready for delivery
- Pull request: not created
- Merge commit: not merged
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
server-side bootstrap until enrollment and remote access resume. Public FRPS/Caddy
end-to-end validation remains an external integration/release check.

## Reference and Contracts

- [Fleet bootstrap operations](../../provisioning/fleet-bootstrap.md)
- [Nixstasis enrollment architecture](../../architecture/overwatch-enrollment.md)
- [Runtime boundaries](../../runtime-boundaries.md)
- [Build configuration reference](../../reference/build-configuration.md)
- [Testing](../../testing.md)
- [Nixstasis client design](../nixstasis-client/design.md)

## Validation Evidence

- `nix build .#checks.aarch64-darwin.nixstasis-client --no-link`
- `nix build .#checks.aarch64-darwin.fleet-bootstrap --no-link`
- `nix build .#checks.aarch64-linux.nixstasis-client --no-link`
- `nix build .#checks.aarch64-linux.fleet-bootstrap --no-link`
- `uv run --no-project python scripts/check-docs.py`
- `mdbook build docs`
- Full `hk check -a` with the pinned formatter/tooling path
- Focused Nix evaluation, `nixfmt`, Ruff, shellcheck, actionlint, rumdl, tombi, typos,
  whitespace, and documentation checks

The four exact VM build logs are:

- `/tmp/atomixos-fleet-bzo3-nixstasis-client-darwin-final-v2.log`
- `/tmp/atomixos-fleet-bzo3-fleet-bootstrap-darwin-final-v3.log`
- `/tmp/atomixos-fleet-bzo3-nixstasis-client-linux-final.log`
- `/tmp/atomixos-fleet-bzo3-fleet-bootstrap-linux-final.log`

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
- Documentation now records the delivered implementation and close-out evidence.

### Deferred Work

- Public FRPS/Caddy end-to-end validation remains outside this AtomixOS feature.
- Nixstasis follow-ups `nixstasis-04t` and `nixstasis-5do` remain separately tracked.
- Pull-request or merge delivery has not yet been selected.

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

## Audit Trail

- Implementation: `f9b26acb3641fb11d67620a0ef2fd1589231db48`
- Documentation reconciliation: `e01027e8563e927988483f736c279188f3c475bf`
- Nixstasis revisions: `nixstasis-255` at
  `a0f230ab107c38995d5cd074dc3277708ae2cfba`, `nixstasis-fss` at
  `9e195c96e05cd42b420ee1331fd81a9d8f1cbc8e`, and `nixstasis-4gg` at
  `6afcb7641b3cd4ed3db467df26b1b8ffc780f863`
- Implementation review: approved after resolving F-001 and F-002.
- Documentation review: approved with no findings.
- Review-topology migration evidence: `a4049f5f5a043da363825ac5d6bd6d0e46a1f337`.
- Delivery remains pending an explicit PR, merge, or ready action.
