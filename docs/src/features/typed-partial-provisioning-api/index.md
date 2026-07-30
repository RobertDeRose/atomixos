# Typed Partial Provisioning API

## Delivery Summary

- Beads feature root: `atomixos-c08`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `47fa62ae442f0c6972938f8be45bcfbed9be5413`
- Design record: [design.md](design.md)

## Delivered Capability

The provisioning service exposes authenticated typed partial endpoints for users, network settings, containers,
container networks, and container volumes, plus config export. Every mutation loads current desired state, applies a
typed transformation, produces a complete canonical `config.toml`, and reuses the normal asynchronous apply pipeline.

## User-Facing Behavior

Provisioned-device clients sign partial requests with the existing nonce and SSH-signature contract. Accepted mutations
return the same job model as full imports. Invalid patches, missing current config, concurrent work, activation failures,
and rollback results use the same errors and state transitions as full config submission.

## Design Integration

Partial endpoints are input conveniences, not a second state store. They never mutate derived JSON, Quadlet files,
systemd state, users, or networking directly. Full desired state remains auditable and exportable, and the live OpenAPI
schema owns the transport contract.

## Operational Impact

Partial rewrites preserve semantic desired state but not comments or original TOML ordering. Mutations remain
single-flight and can trigger the same service restarts or network changes as a full import. Config export provides the
backup and clone bookend.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Firmware Data Flow](../../data-flow.md)
- Live route: `/schema/openapi.json`

## Validation Evidence

- `scripts/atomixos_provision/tests/test_partial_config.py` covers typed validation and patch-to-full-state conversion.
- Service, route, provisioning, and live-schema tests cover auth, conflicts, jobs, errors, and shared apply behavior.
- `nix/tests/first-boot-provision.nix` covers selected partial updates through the device integration path.
- Commit `47fa62ae442f0c6972938f8be45bcfbed9be5413` changed implementation, tests, VM coverage, and docs together.

## Design Reconciliation

### Delivered as Designed

Typed user, network, container, network, and volume endpoints, full-state conversion, shared validation/apply/rollback,
async jobs, config export, auth, and OpenAPI coverage were delivered.

### Intentional Changes

Endpoint scope was bounded to the operations with a stable typed model; flexible internal rendered state was not exposed.

### Deferred Work

A dedicated VM activation-failure case for partial updates remains deferred because the same pipeline is covered by
focused partial tests and existing full re-apply rollback VM behavior.

### Rejected or Removed Scope

Arbitrary JSON Patch, direct derived-state mutation, a database, divergent desired state, and unauthenticated
post-provision partial mutation remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/planned-features.md`

## Audit Trail

Legacy tasks T000-T999 were imported and closed under `atomixos-c08`. Commit
`47fa62ae442f0c6972938f8be45bcfbed9be5413` is the integrated delivery evidence for code, tests, VM behavior, and docs.
