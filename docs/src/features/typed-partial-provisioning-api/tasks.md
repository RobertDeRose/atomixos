# Typed Partial Provisioning API Tasks

## T000 - Review and confirm feature spec

- [ ] Confirm feature name, branch name, and docs path.
- [x] Resolve first-implementation endpoint scope.
- [x] Resolve config export and TOML formatting behavior.
- [x] Resolve whether config export is part of this feature.
- [x] Resolve typed representation for flexible Quadlet sections if container endpoints are
  included.
- [ ] Confirm affected docs, OpenAPI requirements, and validation requirements.

## T010 - Define partial update model

- [ ] Define typed request/response schemas for selected endpoint scope.
- [ ] Define patch-to-full-state conversion rules.
- [ ] Define how current `/data/config/config.toml` is loaded and rewritten.
- [ ] Define failure behavior for missing current config, malformed stored config, and invalid
  partial requests.
- [ ] Add unit tests for typed request validation and patch conversion.

## T020 - Reuse full config validation and apply pipeline

- [ ] Add service-layer support for applying a typed partial request as a full candidate config.
- [ ] Reuse existing validate, render, promote, activate, rollback, and job progress behavior.
- [ ] Preserve single-flight behavior for partial updates and full imports.
- [ ] Ensure failed partial updates leave previous config and rendered state active.
- [ ] Add tests for successful and failed partial apply paths.

## T030 - Add selected API endpoints

- [ ] Add selected typed route handlers with SSH signature authentication.
- [ ] Return async job responses equivalent to `POST /api/config` for mutating endpoints.
- [ ] Add route tests for auth failures, validation failures, conflicts, and accepted jobs.
- [ ] Ensure first-boot unauthenticated mutation behavior is not expanded by partial endpoints.

## T040 - Update live OpenAPI schema coverage

- [ ] Add operation IDs and tags for each new route.
- [ ] Document request bodies, auth headers, job responses, and error responses.
- [ ] Extend live schema tests so new routes cannot drift silently.
- [ ] Verify existing public API schema assertions still pass.

## T050 - Add integration or VM coverage

- [ ] Add VM coverage for at least one user partial update.
- [ ] Add VM coverage for at least one network or container partial update if included in scope.
- [ ] Verify rollback behavior for a failed partial update, or document why VM rollback coverage is
  deferred.

## T060 - Update docs

- [ ] Update provisioning docs with partial API usage and auth behavior.
- [ ] Update runtime boundary docs to state partial endpoints produce full desired state.
- [ ] Update data-flow docs for patch-to-full-state promotion flow.
- [ ] Update planned-features status after implementation is complete.
- [ ] Update live schema contract feature docs if route surface expectations change.

## T999 - Final verification and release readiness

- [ ] Run relevant Python tests for parser, patch conversion, API routes, and OpenAPI schema.
- [ ] Run relevant Nix or VM tests for selected endpoint scope.
- [ ] Run formatting/linting for touched files.
- [ ] Run `hk check -a` before final review.
- [ ] Verify docs, OpenAPI schema, route implementation, and tests describe the same contract.
- [ ] Verify no partial endpoint bypasses full config validation, auth, activation, or rollback.
- [ ] Record any intentionally deferred partial endpoint groups before close-out.
