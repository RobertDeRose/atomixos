# Feature: typed-partial-provisioning-api

## Overview

Add typed partial configuration endpoints for common operator workflows while preserving
`config.toml` and supported config bundles as the canonical import, export, and backup format.

Partial changes must not mutate derived runtime files directly. Each partial request should
load the current desired config, apply a typed patch to produce a full desired state, validate
and render that full state through the existing provisioning pipeline, then promote and
activate atomically with the same rollback behavior as full config imports.

## Source

- `docs/src/planned-features.md` planned feature: `typed-partial-provisioning-api`.
- Existing provisioning API foundation, live OpenAPI schema contract, and full config
  re-apply flow.
- Existing docs for provisioning, runtime boundaries, and data flow.

## Goals

1. Add typed partial endpoints for high-value common edits in priority order.
2. Preserve full `config.toml` as the authoritative desired-state artifact on disk.
3. Ensure partial updates and full config imports converge on the same validated rendered
   state.
4. Reuse existing validate, render, promote, activate, rollback, job, and authentication
   behavior.
5. Keep the live OpenAPI schema accurate for every new typed endpoint.
6. Avoid a database or divergent persistent state store.

## Non-Goals

- Arbitrary JSON Patch over internal rendered state.
- Mutating files directly under `/data/config` outside the full config pipeline.
- Fleet-level orchestration.
- Replacing full config import/export or config bundles.
- Adding unauthenticated post-provision mutation paths.
- Building a complete device management UI.

## Proposed Endpoint Scope

The first implementation includes all planned endpoint groups:

1. Managed users: add/update/remove declared users and SSH keys.
2. Network/LAN settings: update DNS, gateway, interface, dnsmasq, NTP, and firewall fields
   that already exist in `config.toml`.
3. Container services: add/update/remove declared Quadlet container definitions.
4. Volumes and networks: add/update/remove declared Quadlet volume and network definitions.

The implementation may still land these groups in separate commits, but close-out should not
declare the feature complete until all groups are implemented, validated, documented, or
explicitly deferred by a later spec change.

## Intended API Model

Partial endpoints should be typed and domain-oriented rather than generic document patches.
Potential route shapes:

```text
GET /api/config/export
PUT /api/config/users/{name}
DELETE /api/config/users/{name}
PATCH /api/config/network
PUT /api/config/containers/{name}
DELETE /api/config/containers/{name}
PUT /api/config/container-networks/{name}
DELETE /api/config/container-networks/{name}
PUT /api/config/container-volumes/{name}
DELETE /api/config/container-volumes/{name}
```

Each mutating endpoint should:

1. Require the same provisioned-device SSH signature authentication as full re-apply.
2. Load `/data/config/config.toml` as the current desired state.
3. Apply the typed request into an in-memory full config document.
4. Validate and render the full candidate state.
5. Promote, activate, and roll back through the existing job pipeline.
6. Persist the resulting full `config.toml` in canonical generated TOML format so
   export/backup remains authoritative.
7. Return an async job response equivalent to `POST /api/config`.

Read/export endpoints should be reviewed carefully. They may require authentication on
provisioned devices because exported config can include operational details and SSH public keys.
This feature includes `GET /api/config/export`; on provisioned devices it must require SSH
signature authentication and return the current canonical `config.toml` bytes.

Flexible Quadlet sections should use a typed outer API shape with validated resource names and
resource kinds, while preserving section maps for Quadlet pass-through content. The existing
config parser and renderer remain the authority for rejecting unsafe or unsupported Quadlet
values after the partial request is converted to a full config.

## Compatibility

- Existing `POST /api/config`, `POST /api/validate`, `GET /api/jobs/{job_id}`, and
  first-boot behavior must remain unchanged.
- Full config import must remain the canonical recovery and backup path.
- Partial updates must fail closed and roll back the same way as full re-apply.
- Existing config files must continue to validate without new required fields.

## Validation Requirements

- Typed request schemas must reject unknown fields and invalid values before candidate
  promotion.
- Patch-to-full-state conversion must preserve unrelated config sections semantically. Partial
  updates rewrite `/data/config/config.toml` in canonical generated TOML format; comments and
  original ordering are not preserved.
- Candidate validation must run against the same schema and semantic parser as full imports.
- Failed partial updates must leave the previous `/data/config/config.toml` and rendered state
  active.
- New routes must appear in the live OpenAPI schema with operation IDs, tags, request bodies,
  auth headers, job responses, and error responses.

## Security And Safety

- Provisioned-device partial mutations must require SSH signature authentication.
- No endpoint may mutate derived JSON, Quadlet files, systemd drop-ins, firewall state, or user
  state directly.
- Request bodies must not allow arbitrary systemd unit manipulation or shell command injection.
- Config export returns the current canonical desired config and must require authentication on
  provisioned devices. The current config model contains SSH public keys but no private keys or
  generated secrets; if future secret-bearing fields exist, export behavior must redact or
  require explicit design.
- Partial updates must preserve the existing single-flight job boundary.

## Documentation Impact

Likely affected docs:

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/planned-features.md`
- `docs/src/features/provisioning-api-live-schema-contract/design.md`
- API route tests under `scripts/atomixos_provision/tests/`

## Success Criteria

- At least one typed partial update path produces the same on-disk desired state as an
  equivalent full config import.
- Failed partial updates roll back identically to failed full imports.
- Live OpenAPI accurately documents each new endpoint.
- Existing full config import, validation, and job polling behavior continue to pass tests.
- Docs describe the same partial-update contract as the implementation.

## Risks And Tradeoffs

- More API surface increases schema, validation, and authorization maintenance.
- Rewriting canonical TOML discards comments and original ordering, trading edit history for a
  deterministic single desired-state artifact.
- Some edits may require restart ordering or activation health semantics not yet modeled.
- Container partial updates can be complex because Quadlet sections are flexible and nested.

## Dependencies

- Provisioning API foundation.
- Live OpenAPI schema contract.
- Existing config parser, renderer, activation policy, and rollback flow.

## Suggested Validation

- Python tests for typed request validation.
- Python tests for patch-to-full-state conversion.
- API route tests for auth, single-flight jobs, errors, and OpenAPI schema coverage.
- VM tests for at least one user update and one container or network partial update.
- `hk check -a` before close-out.

## Open Questions

None.
