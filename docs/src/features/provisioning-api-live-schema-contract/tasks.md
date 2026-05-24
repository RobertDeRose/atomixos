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

- [ ] Generate or fetch the current OpenAPI schema in tests.
- [ ] Record current public route coverage, operation IDs, tags, request bodies, responses,
  and auth/header documentation.
- [ ] Identify Boot UI/static/implementation routes that should remain excluded.
- [ ] Add a focused audit test or fixture that future tasks can build on.

## T020 - Stabilize public route schema metadata

- [ ] Ensure each public API route has the intended operation ID.
- [ ] Ensure each public API route has the intended domain tag.
- [ ] Ensure `POST /api/config` and `POST /api/validate` document accepted request bodies.
- [ ] Ensure `GET /api/nonce` and `GET /api/jobs/{id}` document response schemas.
- [ ] Ensure success and error status codes are documented accurately.
- [ ] Add schema assertions for route metadata and response coverage.

## T030 - Document authentication and request headers

- [ ] Document bootstrap-token behavior where relevant for first-boot UI submission paths.
- [ ] Document provisioned-device SSH signature headers for mutating and validation routes.
- [ ] Document nonce request and nonce/signature failure responses.
- [ ] Ensure schema/docs do not imply unauthenticated provisioned-device re-apply.
- [ ] Add tests for required header documentation.

## T040 - Exclude non-public routes from schema

- [ ] Verify Boot UI page routes are absent from the public API schema unless explicitly
  documented.
- [ ] Verify static asset routes are absent from the public API schema.
- [ ] Add tests that prevent accidental inclusion of implementation-only routes.

## T050 - Update docs

- [ ] Update `docs/src/specs/provisioning-api.md` for the live schema contract.
- [ ] Update runtime or data-flow docs if schema exposure or route semantics change.
- [ ] Update provisioning docs if client usage guidance changes.
- [ ] Update `docs/src/planned-features.md` after implementation is complete.

## T999 - Final verification and release readiness

- [ ] Run relevant Python tests for API behavior and OpenAPI schema coverage.
- [ ] Run formatting/linting for touched files.
- [ ] Run `hk check -a` before final review.
- [ ] Verify docs, route implementation, schema output, and tests describe the same contract.
- [ ] Verify no live schema route exposes secrets or weakens authentication semantics.
- [ ] Record any intentionally deferred API schema behavior before close-out.
