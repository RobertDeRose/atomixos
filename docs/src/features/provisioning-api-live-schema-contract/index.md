# Provisioning API Live Schema Contract

The provisioning service's live OpenAPI document, at `/schema/openapi.json`, is a supported client contract. Public
routes declare stable operation IDs, domain tags, request bodies, authentication headers, success and error responses,
and typed schemas. The Boot UI, static assets, and internal routes are left out. The original plan is in the
[design record](design.md); Beads tracks the work under `atomixos-doh`.

## What changed for users

- **Client developers** can discover how to request a nonce, upload or validate a configuration, poll jobs, and read
  typed responses and errors.
- The schema documents the SSH signature headers for provisioned devices and the first-boot behavior, without implying
  any unauthenticated way to change a provisioned device.

## How it fits in

Schema metadata sits next to the explicit Litestar route wiring and typed domain schemas. Tests inspect the live
document the application generates, so framework defaults cannot slip into the public contract unnoticed.

## Running it

Clients may generate bindings from the live schema, but `config.toml` and bundles remain the canonical desired-state
artifacts. Review schema compatibility whenever public routes, payloads, authentication, or errors change.

## Differences from the design

The contract is described in the existing provisioning, runtime, and data-flow pages instead of a separate API chapter.
The live document is the exact machine-readable reference.

## Not included

- Boot UI routes in OpenAPI, OAuth or JWT just for schema access, and replacing `config.toml` as the canonical
  artifact.

## Tests

- `scripts/atomixos_provision/tests/test_app.py`: public route coverage, operation IDs, tags, request bodies, headers,
  responses, error schemas, and exclusion of UI and static routes.
- Controller tests keep the API behavior behind the documented schema.

## Related pages

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
