# Typed Partial Provisioning API

The provisioning service has authenticated, typed endpoints for changing part of the configuration: users, network
settings, containers, container networks, and container volumes, plus configuration export. Each change loads the
current desired state, applies a typed transformation, produces a complete canonical `config.toml`, and runs through
the normal asynchronous apply pipeline. The original plan is in the [design record](design.md); Beads tracks the work
under `atomixos-c08`.

## What changed for users

- **Client developers** sign partial requests with the existing nonce and SSH-signature contract.
- Accepted changes return the same job model as a full import.
- Invalid patches, missing configuration, concurrent work, activation failures, and rollbacks produce the same errors
  and state transitions as a full submission.

## How it fits in

Partial endpoints are a convenience for input, not a second state store. They never change derived JSON, Quadlet
files, systemd state, users, or networking directly. The full desired state stays auditable and exportable, and the
live OpenAPI schema defines the transport contract.

## Running it

A partial change keeps the meaning of the configuration but not its comments or original TOML ordering. Changes run
one at a time and can restart services or change networking, just like a full import. Export provides the backup and
clone path.

## Differences from the design

Endpoints cover only operations with a stable typed model; flexible internal rendered state is not exposed.

## Not included

- A VM test for activation failure through a partial endpoint; the shared pipeline is covered by focused partial tests
  and the full re-apply rollback VM test.
- Arbitrary JSON Patch, direct changes to derived state, a database, divergent desired state, and unauthenticated
  partial changes after provisioning.

## Tests

- `scripts/atomixos_provision/tests/test_partial_config.py`: typed validation and conversion to full state.
- Service, route, provisioning, and live-schema tests: authentication, conflicts, jobs, errors, and the shared apply
  pipeline.
- `nix/tests/first-boot-provision.nix`: selected partial updates on a VM.

## Related pages

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
