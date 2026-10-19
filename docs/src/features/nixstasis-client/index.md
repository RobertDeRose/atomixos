# Nixstasis Client

AtomixOS can include the Nixstasis client in the immutable base system. An enabled device enrolls, keeps its identity
under `/data/nixstasis`, polls the server without blocking local recovery, accepts bounded remote-access requests, and
keeps a Nixstasis SSH authorization path separate from operator keys. The original plan is in the
[design record](design.md); Beads tracks the work under `atomixos-4hw`.

## What changed for users

- With a valid API URL, the device registers, reuses its stored identity, and reports through the heartbeat endpoint.
- The server can ask the device to start the configured FRP tunnel.
- WAN or server outages back off without blocking boot or local recovery.

## How it fits in

Nixstasis is base-system management code, not an application container. Its identity and authorized keys are separate
from the provisioned operator configuration, and it runs nothing that is not explicitly allowed. Its services start
after networking but are not required for a boot to count as successful.

## Running it

Operators configure enablement, the API URL, storage paths, and poll and retry behavior through the options in
`modules/nixstasis.nix`. Enrollment state lives on `/data`, so it survives OS updates. The Nixstasis server decides which
devices are eligible and what they do; AtomixOS runs the bounded client and keeps local recovery available.

## Differences from the design

The VM test proves the transient FRP unit and the credential boundary with a mock `frpc` instead of a full tunnel.
Tunnel reliability depends on the Nixstasis server and the deployment network.

## Not included

- Validation against a production Nixstasis deployment.
- Fleet orchestration on the device, a hosted management UI, replacing provisioned operator keys, and making boot
  depend on the server.

## Tests

- `nix/tests/nixstasis-module.nix`: options and rendered configuration.
- `nix/tests/nixstasis-client.nix`: registration, identity reuse, polling, outages, and a transient FRP unit, against a
  mock API and a mock `frpc`.

## Related pages

- [Nixstasis Enrollment](../../architecture/nixstasis-enrollment.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Testing](../../testing.md)
