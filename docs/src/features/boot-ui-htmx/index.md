# Boot UI HTMX

The first-boot console is a small server-rendered interface. Operators upload or paste a configuration, submit it as an
asynchronous provisioning job, and watch progress until it succeeds, warns, fails, or rolls back, then follow the final
forwarding URL. There is no frontend build pipeline. The original plan is in the [design record](design.md); Beads
tracks the work under `atomixos-hns`.

## What changed for users

- **Operators** on desktop or mobile submit a configuration and see progress before the job finishes.
- A second submission while a job is running gets a conflict response.
- The console disappears once the device is provisioned. The programmatic API keeps its own first-boot and
  SSH-signature rules.

## How it fits in

The UI routes live in the provisioning service but are left out of the public OpenAPI document. Browser submissions
carry the bootstrap CSRF token and pass Host, Origin, and Referer checks. Read-only status fragments expose only the
fields the page displays, and only during first boot.

## Running it

The page is server-rendered HTML with minimal progressive enhancement, so there is no Node or Vite asset pipeline and
no single-page-app state. Job progress follows the provisioning service's job lifecycle. Provisioned devices do not
serve `/`, `/apply`, or the UI fragments.

## Differences from the design

The implementation renders fragments on the server with minimal browser behavior instead of shipping a separately
versioned HTMX or SPA build.

## Not included

- A general management UI after provisioning.
- Vite or SPA tooling, the old signing-challenge UI, UI routes in the public OpenAPI document, and unauthenticated
  changes after provisioning.

## Tests

- `scripts/atomixos_provision/tests/test_app.py`: page controls, asynchronous submission, progress and terminal
  fragments, conflicts, escaping, CSRF and origin failures, and unavailability after provisioning.
- The live-schema tests in the same file check that UI, static, and fragment routes stay out of OpenAPI.

## Related pages

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
