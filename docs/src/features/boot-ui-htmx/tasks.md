# Boot UI HTMX Tasks

## T000 - Review and confirm feature spec

- [ ] Confirm feature name, branch name, and docs path.
- [ ] Confirm first implementation keeps Boot UI first-boot only.
- [ ] Confirm upload and paste flows remain in scope.
- [ ] Confirm no SPA/frontend build pipeline is introduced.
- [ ] Confirm UI-only routes remain excluded from live OpenAPI unless deliberately
  documented.

## T010 - Inventory current Boot UI behavior

- [ ] Review existing `/`, `/apply`, static asset, and provisioning API route behavior.
- [ ] Identify current bootstrap token, Host, Origin, and Referer enforcement points.
- [ ] Identify current tests covering first-boot-only exposure and programmatic
  `/api/config` behavior.
- [ ] Identify and remove or avoid stale first-boot signing challenge UI helpers.
- [ ] Document any compatibility behavior that must remain unchanged before editing.

## T020 - Design server-rendered HTMX flow

- [ ] Define the page layout for upload and paste provisioning on desktop and mobile.
- [ ] Define job progress, success, warning, error, and rollback fragments.
- [ ] Define `/apply` behavior so browser submissions return job progress without
  blocking until provisioning completes.
- [ ] Decide whether HTMX is vendored as a static asset or avoided with minimal
  progressive enhancement.
- [ ] Define polling behavior and terminal-state handling for job progress.
- [ ] Ensure all rendered dynamic values are escaped.

## T030 - Implement first-boot UI routes and fragments

- [ ] Replace or extend the first-boot page with server-rendered HTMX markup.
- [ ] Preserve upload config submission through the existing apply pipeline.
- [ ] Preserve pasted config submission through the existing apply pipeline.
- [ ] Change browser apply submission to use the asynchronous job path instead of
  synchronous `run_sync` provisioning.
- [ ] Add job progress fragment rendering that reads the existing job manager state.
- [ ] Preserve final forwarding URL display on successful provisioning.
- [ ] Remove or keep unreachable stale signing challenge controls from the first-boot UI.
- [ ] Keep provisioned-device `/` and `/apply` behavior unavailable.

## T040 - Preserve security boundaries

- [ ] Keep bootstrap token checks on browser form submissions.
- [ ] Keep Host, Origin, and Referer protections for browser routes.
- [ ] Ensure any fragment mutation route is first-boot only and token protected.
- [ ] Ensure read-only job fragment routes are first-boot only and expose only needed
  job display fields.
- [ ] Verify programmatic first-boot `POST /api/config` remains tokenless.
- [ ] Verify no unauthenticated post-provision mutation path is introduced.

## T050 - Update tests

- [ ] Add route tests for first-boot page rendering and expected form controls.
- [ ] Add route tests for HTMX job progress, success, failure, warnings, and rollback
  display.
- [ ] Add route tests proving browser apply returns before the job completes and
  reports `409` while another job is running.
- [ ] Add tests for CSRF failure and browser origin failure paths.
- [ ] Add tests proving `/`, `/apply`, and UI fragments are unavailable after
  provisioning.
- [ ] Add tests proving stale signing challenge controls are not exposed in the
  first-boot UI.
- [ ] Add or preserve tests proving Boot UI/static/fragment routes are excluded from
  live OpenAPI.

## T060 - Update docs

- [ ] Update provisioning docs to describe the first-boot HTMX UI flow.
- [ ] Update runtime boundary docs if route or first-boot behavior descriptions change.
- [ ] Update live schema contract feature docs if API/schema route expectations change.
- [ ] Update planned-features status after implementation is complete.

## T999 - Final verification and release readiness

- [ ] Run relevant Python route and UI tests.
- [ ] Run relevant OpenAPI schema exclusion tests.
- [ ] Run formatting/linting for touched files.
- [ ] Run `hk check -a` before final review.
- [ ] Manually or automatically verify desktop and mobile rendering behavior.
- [ ] Verify docs, implementation, and tests describe the same Boot UI contract.
- [ ] Verify no post-provision unauthenticated mutation path was introduced.
