# Config Reapply Improvements

## Delivery Summary

- Beads feature root: `atomixos-iej`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `72f6209c49d8abc5f8ab7268e10bb76f01a32b5b`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS validates a canonical versioned `config.toml`, authenticates provisioned-device re-apply with admin SSH
signatures, renders a complete candidate without touching active state, promotes it crash-safely, activates required
runtime state, and restores the prior config when activation or health checks fail.

## User-Facing Behavior

Fresh-device provisioning remains locally unauthenticated under its bootstrap boundary. Once provisioned, mutating config
paths require a single-use nonce and SSH signature from an active admin key. Invalid config leaves active state intact;
accepted work returns asynchronous progress and a failed activation reports rollback status.

## Design Integration

`config.toml` is the sole desired-state contract. Candidate, active, and rollback directories are managed as one
promotion state machine on F2FS-compatible storage. Users, networking, firewall, Quadlet, health, and later partial API
operations all reuse that state machine.

## Operational Impact

Operators must retain an active admin key and sign the exact request path and payload digest. Re-apply can restart
services or change networking. Recovery detects interrupted promotion state, and failed activation attempts to restore
both desired files and runtime behavior.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Firmware Data Flow](../../data-flow.md)
- [Authentication](../../architecture/authentication.md)
- `schemas/config.schema.json`

## Validation Evidence

- Provisioning package tests cover schema defaults and rejection, admin keys, authentication, candidate rendering,
  promotion, recovery, activation, and rollback.
- `nix/tests/first-boot-provision.nix` covers successful authenticated re-apply, invalid candidate preservation, and
  activation rollback.
- Commit `72f6209c49d8abc5f8ab7268e10bb76f01a32b5b` delivered the canonical schema/parser, VM coverage, examples, and docs;
  later hardening and package-refactor commits preserved the contract.

## Design Reconciliation

### Delivered as Designed

Canonical schema, managed users, SSH challenge-response, isolated candidate rendering, crash-safe promotion, required
health, activation, rollback, recovery, and documentation were delivered.

### Intentional Changes

The original monolithic script later became the Litestar provisioning package and privilege-separated worker. Those
changes retain this feature's desired-state, authentication, and promotion invariants.

### Deferred Work

A persistent-disk VM case for managed-user materialization after reboot remains deferred. Unreleased pre-version-2
config shapes require reprovisioning rather than an in-place migration.

### Rejected or Removed Scope

Unauthenticated post-provision re-apply, reset tokens, direct active-state overwrite, compatibility for unreleased legacy
shapes, and divergent partial state remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/architecture/authentication.md`
- examples and affected reference pages

## Audit Trail

Legacy tasks T000-T999 were imported and closed under `atomixos-iej`; explicitly deferred validation remains recorded in
the source task evidence. Commit `72f6209c49d8abc5f8ab7268e10bb76f01a32b5b` is the initial integrated delivery, with
network and activation extensions reconciled by their own delivered features.
