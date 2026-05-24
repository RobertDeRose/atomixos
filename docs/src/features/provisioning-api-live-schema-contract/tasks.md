# Provisioning API Live Schema Contract Tasks

## T000 - Review and confirm feature spec

- [x] Confirm feature name, branch name, and docs path.
- [x] Confirm the public API routes that must appear in the live schema.
- [x] Confirm Boot UI/static route exclusion rules.
- [x] Resolve test strategy for live schema generation.
- [x] Resolve request-body modeling for raw TOML and config bundles.
- [x] Resolve whether to introduce shared typed error schemas.
- [x] Confirm affected docs and validation requirements.

## T010 - Audit current API schema output

- [x] Generate or fetch the current OpenAPI schema in tests.
- [x] Record current public route coverage, operation IDs, tags, request bodies, responses,
  and auth/header documentation.
- [x] Identify Boot UI/static/implementation routes that should remain excluded.
- [x] Add a focused audit test or fixture that future tasks can build on.

## T020 - Stabilize public route schema metadata

- [x] Ensure each public API route has the intended operation ID.
- [x] Ensure each public API route has the intended domain tag.
- [x] Ensure `POST /api/config` and `POST /api/validate` document accepted request bodies.
- [x] Ensure `GET /api/nonce` and `GET /api/jobs/{id}` document response schemas.
- [x] Ensure success and error status codes are documented accurately.
- [x] Add schema assertions for route metadata and response coverage.

## T030 - Document authentication and request headers

- [x] Document bootstrap-token behavior where relevant for first-boot UI submission paths.
- [x] Document provisioned-device SSH signature headers for mutating and validation routes.
- [x] Document nonce request and nonce/signature failure responses.
- [x] Ensure schema/docs do not imply unauthenticated provisioned-device re-apply.
- [x] Add tests for required header documentation.

## T040 - Exclude non-public routes from schema

- [x] Verify Boot UI page routes are absent from the public API schema unless explicitly
  documented.
- [x] Verify static asset routes are absent from the public API schema.
- [x] Add tests that prevent accidental inclusion of implementation-only routes.

## T050 - Update docs

- [x] Update `docs/src/specs/provisioning-api.md` for the live schema contract.
  Not applicable: this repo has no standalone provisioning API spec page; the contract is
  documented in `docs/src/provisioning.md`, `docs/src/runtime-boundaries.md`, and
  `docs/src/data-flow.md`.
- [x] Update runtime or data-flow docs if schema exposure or route semantics change.
- [x] Update provisioning docs if client usage guidance changes.
- [x] Update `docs/src/planned-features.md` after implementation is complete.

## T999 - Final verification and release readiness

- [x] Run relevant Python tests for API behavior and OpenAPI schema coverage.
- [x] Run formatting/linting for touched files.
- [x] Run `hk check -a` before final review.
- [x] Verify docs, route implementation, schema output, and tests describe the same contract.
- [x] Verify no live schema route exposes secrets or weakens authentication semantics.
- [x] Record any intentionally deferred API schema behavior before close-out.
  Deferred: Litestar emits a deprecation warning for inferred typed path parameters on
  `/api/jobs/{job_id:str}`. The warning is pre-existing and does not block this schema
  contract feature.
