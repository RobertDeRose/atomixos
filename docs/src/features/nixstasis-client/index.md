# Nixstasis Client

## Delivery Summary

- Beads feature root: `atomixos-4hw`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commits: `f3cf5a5bb9fdd2812a1c875063f16ac8ac5802b6`,
  `80a1c84c272e7432c6e17aaf0b6b4e7be3562809`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS can package the Nixstasis client in the immutable base system, enroll eligible devices, persist identity under
`/data/nixstasis`, poll without blocking local recovery, accept bounded remote-access requests, and maintain a separate
Nixstasis SSH authorization path.

## User-Facing Behavior

When enabled with a valid API URL, the device registers and reuses its persisted identity, periodically reports through
the heartbeat endpoint, and can launch the configured FRP boundary from a server response. WAN or server outages back
off without preventing local boot or operator recovery.

## Design Integration

Nixstasis is base-system management code rather than an application container. Its identity and authorized keys are
separate from provisioned operator config, and its command surface is deny-by-default. Services order after networking
but do not become a boot-success prerequisite.

## Operational Impact

Operators configure the API URL, persistent paths, poll/retry behavior, and enablement through NixOS options. Enrollment
state survives OS updates because it is stored on `/data`. The remote server owns inventory eligibility and orchestration;
AtomixOS owns the bounded client execution and local recovery boundary.

## Reference and Contracts

- [Nixstasis Enrollment](../../architecture/overwatch-enrollment.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Testing](../../testing.md)
- `modules/nixstasis.nix`

## Validation Evidence

- `nix/tests/nixstasis-module.nix` validates options and rendered configuration.
- `nix/tests/nixstasis-client.nix` uses a mock API to validate registration, identity reuse, polling, outage behavior,
  and the FRP launch boundary.
- Commit `f3cf5a5bb9fdd2812a1c875063f16ac8ac5802b6` delivered the module integration.
- Commit `80a1c84c272e7432c6e17aaf0b6b4e7be3562809` delivered the focused VM test.

## Design Reconciliation

### Delivered as Designed

Immutable packaging, persistent identity, registration and polling services, backoff, separate SSH keys, command
allowlisting, and mock-server validation were delivered.

### Intentional Changes

Full FRP tunnel transport was narrowed to validation of the launch boundary; remote tunnel reliability belongs to
integration with the Nixstasis server and deployment network.

### Deferred Work

End-to-end validation against a production Nixstasis deployment remains operational integration work.

### Rejected or Removed Scope

On-device fleet orchestration, a hosted management UI, replacement of provisioned operator keys, and boot dependence on
remote availability remain out of scope.

## Documentation Updated

- `docs/src/architecture/overwatch-enrollment.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/testing.md`
- `docs/src/planned-features.md`

## Audit Trail

All 39 legacy tasks including T999 were imported and closed under `atomixos-4hw`. Module, VM, and close-out evidence is
preserved by commits `f3cf5a5bb9fdd2812a1c875063f16ac8ac5802b6`,
`80a1c84c272e7432c6e17aaf0b6b4e7be3562809`, and `3ca38d6227c51be14a31462fa57506e524dd69a4`.
