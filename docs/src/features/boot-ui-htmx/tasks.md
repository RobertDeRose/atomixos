# Boot UI HTMX Tasks

## T000 - Review and confirm feature spec

- [x] Confirm feature name, branch name, and docs path.
- [x] Confirm first implementation keeps Boot UI first-boot only.
- [x] Confirm upload and paste flows remain in scope.
- [x] Confirm no SPA/frontend build pipeline is introduced.
- [x] Confirm UI-only routes remain excluded from live OpenAPI unless deliberately
  documented.

## T010 - Inventory current Boot UI behavior

- [x] Review existing `/`, `/apply`, static asset, and provisioning API route behavior.
- [x] Identify current bootstrap token, Host, Origin, and Referer enforcement points.
- [x] Identify current tests covering first-boot-only exposure and programmatic
  `/api/config` behavior.
- [x] Identify and remove or avoid stale first-boot signing challenge UI helpers.
- [x] Document any compatibility behavior that must remain unchanged before editing.

## T020 - Design server-rendered HTMX flow

- [x] Define the page layout for upload and paste provisioning on desktop and mobile.
- [x] Define job progress, success, warning, error, and rollback fragments.
- [x] Define `/apply` behavior so browser submissions return job progress without
  blocking until provisioning completes.
- [x] Decide whether HTMX is vendored as a static asset or avoided with minimal
  progressive enhancement.
- [x] Define polling behavior and terminal-state handling for job progress.
- [x] Ensure all rendered dynamic values are escaped.

## T030 - Implement first-boot UI routes and fragments

- [x] Replace or extend the first-boot page with server-rendered HTMX markup.
- [x] Preserve upload config submission through the existing apply pipeline.
- [x] Preserve pasted config submission through the existing apply pipeline.
- [x] Change browser apply submission to use the asynchronous job path instead of
  synchronous `run_sync` provisioning.
- [x] Add job progress fragment rendering that reads the existing job manager state.
- [x] Preserve final forwarding URL display on successful provisioning.
- [x] Remove or keep unreachable stale signing challenge controls from the first-boot UI.
- [x] Keep provisioned-device `/` and `/apply` behavior unavailable.

## T040 - Preserve security boundaries

- [x] Keep bootstrap token checks on browser form submissions.
- [x] Keep Host, Origin, and Referer protections for browser routes.
- [x] Ensure any fragment mutation route is first-boot only and token protected.
- [x] Ensure read-only job fragment routes are first-boot only and expose only needed
  job display fields.
- [x] Verify programmatic first-boot `POST /api/config` remains tokenless.
- [x] Verify no unauthenticated post-provision mutation path is introduced.

## T050 - Update tests

- [x] Add route tests for first-boot page rendering and expected form controls.
- [x] Add route tests for HTMX job progress, success, failure, warnings, and rollback
  display.
- [x] Add route tests proving browser apply returns before the job completes and
  reports `409` while another job is running.
- [x] Add tests for CSRF failure and browser origin failure paths.
- [x] Add tests proving `/`, `/apply`, and UI fragments are unavailable after
  provisioning.
- [x] Add tests proving stale signing challenge controls are not exposed in the
  first-boot UI.
- [x] Add or preserve tests proving Boot UI/static/fragment routes are excluded from
  live OpenAPI.

## T060 - Update docs

- [x] Update provisioning docs to describe the first-boot HTMX UI flow.
- [x] Update runtime boundary docs if route or first-boot behavior descriptions change.
- [x] Update live schema contract feature docs if API/schema route expectations change.
- [x] Update planned-features status after implementation is complete.

## T999 - Final verification and release readiness

- [x] Run relevant Python route and UI tests.
- [x] Run relevant OpenAPI schema exclusion tests.
- [x] Run formatting/linting for touched files.
- [x] Run `hk check -a` before final review.
- [x] Manually or automatically verify desktop and mobile rendering behavior.
- [x] Verify docs, implementation, and tests describe the same Boot UI contract.
- [x] Verify no post-provision unauthenticated mutation path was introduced.
