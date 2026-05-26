# Feature: boot-ui-htmx

## Overview

Redesign the first-boot Boot UI as a small server-rendered HTMX interface while
preserving the existing upload and paste provisioning flow, bootstrap CSRF token
controls, and programmatic `/api/config` behavior.

The Boot UI remains a first-provisioning convenience only. It must be available
before the device is provisioned and unavailable after `/data/config/config.toml`
exists. The UI should submit full config files or supported bundles to the
existing asynchronous provisioning API, then show job progress and the final
result without adding a single-page application or frontend build pipeline.

## Source

- `docs/src/planned-features.md` planned feature: `boot-ui-htmx`.
- Existing provisioning API foundation, job polling, bootstrap browser origin
  protections, and Boot UI route behavior.
- Existing docs for provisioning and runtime boundaries.

## Goals

1. Replace the current static first-boot form experience with server-rendered HTMX
   interactions.
2. Preserve upload and paste config submission paths for complete `config.toml`
   files and supported config bundles.
3. Show asynchronous provisioning job progress using the returned `job_url`.
4. Keep the UI usable on desktop and mobile browsers without adding a SPA or
   JavaScript build pipeline.
5. Preserve Host, Origin, Referer, and bootstrap token protections for browser
   form submissions.
6. Keep programmatic first-boot `POST /api/config` behavior unchanged.

## Non-Goals

- Full on-device management UI after provisioning.
- Typed partial configuration editing in the Boot UI.
- Replacing programmatic `/api/config`, `/api/validate`, or `/api/jobs/{job_id}`.
- Adding a Vite, React, or SPA frontend pipeline.
- Adding unauthenticated post-provision mutation paths.

## Intended UI Model

The implementation should keep the Boot UI server-rendered by the Python
provisioning service. HTMX may be served as a small static asset or vendored file
if needed, but the page should not require a separate build step.

The first implementation should support these operator flows:

1. Visit `/` before provisioning and see the first-boot provisioning page.
2. Upload a `config.toml` file or supported config bundle.
3. Paste raw `config.toml` text into a text area.
4. Submit through a browser route protected by the bootstrap CSRF token and
   browser origin checks.
5. Receive a `202`-style asynchronous job from the existing apply job manager and
   a progress fragment that polls the job URL until success or failure. The
   browser route must not block until provisioning completes.
6. Show validation/apply errors, rollback status when present, warnings, and final
   forwarding URL when provisioning succeeds.

The existing programmatic `POST /api/config` route remains tokenless only before
initial provisioning. Browser form submission continues to use the bootstrap token
as a CSRF control and must not broaden mutation access after provisioning.

The Boot UI is a first-boot UI, not a re-apply signing UI. Existing unused
client-side signing challenge helpers should be removed or left unreachable; the
new page must not ask operators to download signing challenges or upload SSH
signatures for first provisioning.

## Route And API Impact

Likely affected routes:

```text
GET /                  first-boot Boot UI page
POST /apply            browser form submission for upload or pasted config, returning job progress UI
GET /ui/jobs/{job_id}  optional first-boot-only HTML job progress fragment
GET /api/jobs/{job_id} existing job polling API used by HTMX fragments
```

The implementation may add UI-only fragment routes if useful, but they must be
excluded from the live OpenAPI client contract unless they are deliberately
documented as public API routes.

Any new UI-only mutation route must enforce the same first-boot-only exposure,
bootstrap token, and browser origin protections as the current `/apply` route.
Read-only UI fragment routes that expose job state must remain first-boot-only and
must not expose more job information than the existing Boot UI needs to display.

## Compatibility

- Existing `POST /api/config` programmatic first-boot behavior must remain
  unchanged.
- Existing provisioned-device behavior must remain fail-closed: `/` and `/apply`
  are unavailable after provisioning.
- Existing config validation, candidate promotion, activation, rollback, and job
  semantics must remain unchanged.
- Browser `/apply` should use the same `JobManager.submit` async path as
  programmatic apply jobs instead of the current synchronous `run_sync` behavior.
- Existing live OpenAPI schema assertions must continue to exclude Boot UI and
  static asset routes unless the API contract intentionally changes.

## Security And Safety

- Browser form submissions must keep bootstrap CSRF token checks.
- Host, Origin, and Referer validation must not be weakened.
- HTMX fragment routes must not become unauthenticated mutation surfaces.
- First-boot HTMX job fragments must be inaccessible after provisioning and should
  not create a durable bearer token, cookie, or post-provision polling capability.
  The only exception is a one-time terminal fragment for a job submitted through
  the first-boot UI, so the browser can render success or failure after successful
  initial provisioning creates `/data/config/config.toml`.
- UI rendering must escape operator-provided config text, job errors, warnings,
  service names, and URLs.
- The UI must not expose secret material beyond what the existing first-boot form
  already handles locally in the browser.

## Documentation Impact

Likely affected docs:

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/features/provisioning-api-live-schema-contract/design.md`
- API/UI route tests under `scripts/atomixos_provision/tests/`

## Success Criteria

- An operator can complete first provisioning from desktop and mobile browsers via
  upload or paste.
- The UI reflects async job progress and final success or failure state.
- The final success view includes the forwarding URL when one is returned.
- UI route tests cover first-boot-only exposure, CSRF failure paths, and job
  progress rendering.
- The first-boot page no longer exposes stale re-apply signing challenge controls.
- Existing programmatic provisioning API tests and OpenAPI schema exclusion tests
  still pass.

## Risks And Tradeoffs

- More UI affordances increase bootstrap attack surface if fragment routes are not
  scoped carefully.
- HTMX fragments must stay aligned with the job response shape.
- Browser polling can create extra load if polling intervals are too aggressive,
  though first-boot usage is low volume.
- Mobile usability can regress if the UI relies on dense desktop-only layouts.

## Dependencies

- Provisioning API foundation.
- Existing single-flight async apply jobs and `GET /api/jobs/{job_id}`.
- Existing bootstrap browser origin and CSRF protections.

## Suggested Validation

- Python route tests for Boot UI rendering, CSRF rejection, first-boot-only
  exposure, form submission, and job fragment states.
- Python route tests proving `/apply` returns job progress before the apply work
  completes and returns `409` while another job is running.
- Python tests confirming Boot UI/static/fragment routes remain excluded from live
  OpenAPI unless intentionally documented.
- Manual browser check in the VM or local server for desktop and mobile viewport
  behavior.
- `hk check -a` before close-out.

## Open Questions

None.
