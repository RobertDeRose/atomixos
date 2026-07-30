# Activation Options

## Delivery Summary

- Beads feature root: `atomixos-ivy`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `7c4bb43471e26e4a424da4d93bf88ee5dc98bf40`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS accepts bounded activation timing, restart ordering, degraded-service allowances, and rollback strategy in
`config.toml`. Validated policy is rendered to `/data/config/activation-policy.json` and consumed by the shared
provisioning activation path.

## User-Facing Behavior

Operators can tune activation timeout and settle periods, restart declared container services in an explicit order, and
allow selected declared services to remain degraded. Rollback remains the only accepted failure strategy. Unknown units,
conflicting required/degraded sets, unsafe values, and unsupported strategies are rejected before promotion.

## Design Integration

Activation policy is desired state, not executable script input. Unit names are limited to declared services, rendering
is deterministic, and the existing candidate promotion, health checking, job reporting, and rollback boundaries remain
authoritative.

## Operational Impact

Longer timing values delay terminal job results. Restart ordering can temporarily interrupt services. Degraded units are
reported without converting unrelated activation failures into success. Failed activation restores the previous config
and policy.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Firmware Data Flow](../../data-flow.md)

## Validation Evidence

- `scripts/atomixos_provision/tests/test_config.py` covers schema and policy validation.
- `scripts/atomixos_provision/tests/test_activation.py` covers timing, restart, degraded, and rollback behavior.
- `scripts/atomixos_provision/tests/test_provision.py` covers integration with the shared apply pipeline.
- Commit `7c4bb43471e26e4a424da4d93bf88ee5dc98bf40` changed the runtime and focused tests together.

## Design Reconciliation

### Delivered as Designed

Bounded timeout, settle, restart, degraded-service, and `rollback` strategy support were delivered through rendered
policy and the common activation path.

### Intentional Changes

The implementation retained explicit route/service wiring and the existing job manager rather than introducing a new
workflow engine.

### Deferred Work

A dedicated persistent-state VM activation-policy case remains deferred; parser, renderer, runtime, rollback, and
compatibility behavior have focused automated coverage.

### Rejected or Removed Scope

`keep-failed`, `manual-confirm`, arbitrary commands, and unrestricted systemd unit control remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/planned-features.md`

## Audit Trail

Legacy tasks T000-T999 were imported under `atomixos-ivy` and closed from delivery evidence. Runtime implementation is
corroborated by commit `7c4bb43471e26e4a424da4d93bf88ee5dc98bf40`; close-out reconciliation is recorded in
`315ed5fc5dda05f4a039b318b2a355e4c1a00f44`.
