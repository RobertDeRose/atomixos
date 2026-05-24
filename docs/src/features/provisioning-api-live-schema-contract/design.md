# Feature: provisioning-api-live-schema-contract

## Overview

Treat the live OpenAPI schema exposed by the provisioning service as a supported client
contract, not incidental framework output. The provisioning API already exposes online schema
routes; this feature makes the documented request bodies, headers, responses, errors,
operation IDs, and domain tags deliberate and tested.

This feature builds on the provisioning API foundation and should keep `config.toml` and
supported config bundles as the canonical import/export artifacts.

## Source

- `docs/src/planned-features.md` planned feature: `provisioning-api-live-schema-contract`.
- Existing provisioning API service and live schema routes.
- Existing provisioning API documentation in `docs/src/provisioning.md`,
  `docs/src/runtime-boundaries.md`, and `docs/src/data-flow.md`.

## Goals

1. Make the live OpenAPI schema a stable enough contract for generated and online clients.
2. Ensure mutating and validation routes document accurate request bodies, auth headers,
   responses, and error shapes.
3. Preserve route operation IDs and domain tags for client generation.
4. Exclude Boot UI/static routes from the API schema unless they are deliberately documented.
5. Add automated tests that fail when API routes drift from the intended schema contract.
6. Keep schema generation dependency-light and aligned with Litestar conventions already in
   use.

## Non-Goals

- Replacing `config.toml` as the canonical import/export/backup artifact.
- Adding OAuth, JWT, or additional authentication solely for documentation access.
- Building a separate static documentation site for the API.
- Adding typed partial configuration endpoints.
- Supporting every incidental framework route as public API.

## Intended Contract

The live OpenAPI schema should document the provisioning API routes that operators or clients
are expected to call:

- `GET /api/health`
- `GET /api/nonce`
- `POST /api/validate`
- `POST /api/config`
- `GET /api/jobs/{job_id}`

The schema should include:

- Stable operation IDs suitable for client generation.
- Domain tags that match the route purpose.
- Request bodies for TOML/config-bundle upload and validation paths.
- Authentication headers for provisioned-device re-apply and validation where required.
- Response schemas for accepted jobs, validation results, job status, and errors.
- Accurate status codes for success, validation failure, auth failure, conflict/single-flight,
  and internal failure cases.

Boot UI pages, static assets, and implementation-only routes should stay out of the public API
schema unless explicitly documented and tested as public contract.

Schema contract tests should use the live Litestar app test client and fetch
`/schema/openapi.json`. That validates the exposed online schema instead of a separate helper
that could drift from runtime route registration.

Raw `config.toml` and supported config-bundle uploads are modeled as
`application/octet-stream` binary request bodies. The `x-config-filename` header documents how
clients preserve the original filename so the server can distinguish raw TOML from supported
bundle formats.

Error responses should reuse existing typed API error response models where routes return
domain errors, and should document framework error response shapes where Litestar guards return
authentication or request rejection errors. This feature should not introduce a separate error
envelope unless existing runtime behavior changes.

## Compatibility

- Existing API paths and JSON response shapes should remain compatible unless the review phase
  identifies a documented bug that must be corrected.
- Existing first-boot token behavior and provisioned-device SSH signature authentication must
  remain unchanged.
- Programmatic clients should continue to submit full configs through `POST /api/config` and
  poll jobs through `GET /api/jobs/{job_id}`.

## Validation Requirements

- Add tests that fetch or generate the OpenAPI schema and assert route coverage.
- Assert stable operation IDs and expected tags for each public API route.
- Assert request-body and response-schema presence for mutating and job routes.
- Assert required auth/nonce/signature headers appear in documented routes where applicable.
- Assert Boot UI/static routes are excluded from the API schema unless intentionally included.
- Preserve existing API behavior tests while adding schema-level coverage.

## Security And Safety

- Live schema exposure is intentional for online clients; schema docs must not expose secrets,
  generated nonces, private keys, or example credentials.
- Schema documentation must not imply unauthenticated re-apply on provisioned devices.
- Schema routes must not bypass existing Host, Origin, Referer, bootstrap-token, nonce, or SSH
  signature checks for mutating endpoints.
- Error schemas should be useful without leaking sensitive request content.

## Documentation Impact

Likely affected docs:

- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/provisioning.md`
- `docs/src/planned-features.md` after implementation close-out
- API schema tests under `scripts/atomixos_provision/tests/`

## Success Criteria

- Generated clients can submit config, validate config, poll jobs, and handle errors using
  the live schema.
- Tests fail if a public API route is missing from the schema or loses its operation ID/tag.
- Mutating routes document request bodies, responses, and required auth headers accurately.
- Boot UI/static routes remain excluded from the public API schema unless deliberately added.
- Docs and tests describe the same API contract.

## Risks And Tradeoffs

- Litestar defaults may need explicit overrides for binary or multi-format request bodies.
- Schema tests add maintenance cost but prevent silent client drift.
- Over-documenting implementation routes could accidentally expand the public API surface.
- Tight schema assertions may need careful wording to allow harmless framework metadata changes.

## Dependencies

- Provisioning API foundation.
- Existing typed response models in the provisioning package.
- Existing route registration and live OpenAPI schema exposure.

## Suggested Validation

- Python tests against the generated OpenAPI schema.
- Existing provisioning API tests for runtime behavior.
- `hk check -a` before close-out.

## Open Questions

None.
