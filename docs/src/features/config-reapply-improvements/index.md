# Config Reapply Improvements

AtomixOS validates a canonical, versioned `config.toml`, authenticates changes to a provisioned device with an
administrator's SSH signature, renders a complete candidate without touching the active state, promotes it safely
across crashes, and restores the previous configuration when activation or health checks fail. The original plan is in
the [design record](design.md); Beads tracks the work under `atomixos-iej`.

## What changed for users

- A fresh device still accepts its first configuration locally without authentication.
- Once provisioned, every configuration change needs a single-use nonce and an SSH signature from an active admin key.
- An invalid configuration leaves the active state untouched.
- Accepted work reports progress asynchronously, and a failed activation reports its rollback.

## How it fits in

`config.toml` is the only desired-state contract. Candidate, active, and rollback directories form one promotion state
machine on F2FS-compatible storage. Users, networking, firewall, Quadlet units, health checks, and the partial API all
reuse it.

## Running it

Operators must keep an active admin key and sign the exact request path and payload digest. Re-applying can restart
services or change networking. Recovery detects an interrupted promotion, and a failed activation restores both the
desired files and the runtime behavior.

## Differences from the design

The original single script became the Litestar provisioning package with a privilege-separated worker. The desired-state,
authentication, and promotion rules of this feature carry over unchanged.

## Not included

- A persistent-disk VM test for managed users after a reboot.
- In-place migration of unreleased configuration shapes older than version 2; those devices must be reprovisioned.
- Unauthenticated changes after provisioning, reset tokens, direct overwrites of active state, and partial state that
  diverges from `config.toml`.

## Tests

- `scripts/atomixos_provision/tests/`: schema defaults and rejection, admin keys, authentication, candidate rendering,
  promotion, recovery, activation, and rollback.
- `nix/tests/first-boot-provision.nix`: authenticated re-apply, preservation of the active state after an invalid
  candidate, and activation rollback.

## Related pages

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
- [Authentication](../../architecture/authentication.md)
- `schemas/config.schema.json`
