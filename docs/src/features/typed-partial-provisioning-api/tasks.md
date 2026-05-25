# Typed Partial Provisioning API Tasks

## T000 - Review and confirm feature spec

- [x] Confirm feature name, branch name, and docs path.
- [x] Resolve first-implementation endpoint scope.
- [x] Resolve config export and TOML formatting behavior.
- [x] Resolve whether config export is part of this feature.
- [x] Resolve typed representation for flexible Quadlet sections if container endpoints are
  included.
- [x] Confirm affected docs, OpenAPI requirements, and validation requirements.

## T010 - Define partial update model

- [x] Define typed request/response schemas for selected endpoint scope.
- [x] Define patch-to-full-state conversion rules.
- [x] Define how current `/data/config/config.toml` is loaded and rewritten.
- [x] Define failure behavior for missing current config, malformed stored config, and invalid
  partial requests.
- [x] Add unit tests for typed request validation and patch conversion.

## T020 - Reuse full config validation and apply pipeline

- [x] Add service-layer support for applying a typed partial request as a full candidate config.
- [x] Reuse existing validate, render, promote, activate, rollback, and job progress behavior.
- [x] Preserve single-flight behavior for partial updates and full imports.
- [x] Ensure failed partial updates leave previous config and rendered state active.
- [x] Add tests for successful and failed partial apply paths.

## T030 - Add selected API endpoints

- [x] Add selected typed route handlers with SSH signature authentication.
- [x] Return async job responses equivalent to `POST /api/config` for mutating endpoints.
- [x] Add route tests for auth failures, validation failures, conflicts, and accepted jobs.
- [x] Ensure first-boot unauthenticated mutation behavior is not expanded by partial endpoints.

## T040 - Update live OpenAPI schema coverage

- [x] Add operation IDs and tags for each new route.
- [x] Document request bodies, auth headers, job responses, and error responses.
- [x] Extend live schema tests so new routes cannot drift silently.
- [x] Verify existing public API schema assertions still pass.

## T050 - Add integration or VM coverage

- [x] Add VM coverage for at least one user partial update.
- [x] Add VM coverage for at least one network or container partial update if included in scope.
- [x] Verify rollback behavior for a failed partial update, or document why VM rollback coverage is
  deferred.

  Deferred: failed partial rollback is covered by Python service/pipeline tests and the existing VM
  full re-apply rollback path. A dedicated failed partial rollback VM case is deferred because the
  partial endpoints reuse the same locked transform-to-full-config apply path and adding another
  activation-failure branch would extend the already broad provisioning VM test without new runtime
  machinery.

## T060 - Update docs

- [x] Update provisioning docs with partial API usage and auth behavior.
- [x] Update runtime boundary docs to state partial endpoints produce full desired state.
- [x] Update data-flow docs for patch-to-full-state promotion flow.
- [x] Update planned-features status after implementation is complete.
- [x] Update live schema contract feature docs if route surface expectations change.

## T999 - Final verification and release readiness

- [x] Run relevant Python tests for parser, patch conversion, API routes, and OpenAPI schema.
- [x] Run relevant Nix or VM tests for selected endpoint scope.
- [x] Run formatting/linting for touched files.
- [x] Run `hk check -a` before final review.
- [x] Verify docs, OpenAPI schema, route implementation, and tests describe the same contract.
- [x] Verify no partial endpoint bypasses full config validation, auth, activation, or rollback.
- [x] Record any intentionally deferred partial endpoint groups before close-out.
