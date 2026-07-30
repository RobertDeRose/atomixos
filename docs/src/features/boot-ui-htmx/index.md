# Boot UI HTMX

## Delivery Summary

- Beads feature root: `atomixos-hns`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `2c9c2df28f5d1e02640c3c3496ebf24e07c7584c`
- Design record: [design.md](design.md)

## Delivered Capability

The first-boot console is a small server-rendered HTMX-style interface for uploading or pasting config, submitting an
asynchronous provisioning job, polling bounded status fragments, and showing success, warnings, failure, rollback, and
the final forwarding URL without a frontend build pipeline.

## User-Facing Behavior

Desktop and mobile operators can submit config and see progress before the job completes. A concurrent submission gets a
conflict response. The UI disappears after provisioning, while the programmatic API remains governed by its separate
first-boot and SSH-signature rules.

## Design Integration

UI routes remain in the provisioning service but are excluded from public OpenAPI. Browser submissions retain the
bootstrap CSRF token plus Host, Origin, and Referer checks. Read-only status fragments expose only necessary display
fields and are available only during first boot.

## Operational Impact

The interface uses server-rendered HTML and minimal progressive enhancement, so there is no Node/Vite asset pipeline or
SPA state. Job progress follows the existing in-process and staged-worker lifecycle. Provisioned devices do not expose
`/`, `/apply`, or UI fragments.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Firmware Data Flow](../../data-flow.md)

## Validation Evidence

- Provisioning route tests cover page controls, asynchronous submission, progress and terminal fragments, conflicts,
  escaping, CSRF/origin failures, and post-provision unavailability.
- Live-schema tests prove UI, static, and fragment routes remain excluded.
- Commit `2c9c2df28f5d1e02640c3c3496ebf24e07c7584c` changed UI implementation, tests, docs, and roadmap together.

## Design Reconciliation

### Delivered as Designed

Upload and paste flows, async jobs, status fragments, first-boot-only exposure, bootstrap browser controls, escaping,
mobile/desktop rendering, and OpenAPI exclusion were delivered.

### Intentional Changes

The implementation uses server-rendered fragments and minimal browser behavior rather than introducing a separately
versioned HTMX or SPA build artifact.

### Deferred Work

A general post-provision management UI remains outside this feature.

### Rejected or Removed Scope

Vite/SPA tooling, stale signing-challenge UI, UI routes in public OpenAPI, and unauthenticated post-provision mutation
remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/planned-features.md`

## Audit Trail

Legacy tasks T000-T999 were imported and closed under `atomixos-hns`. Commit
`2c9c2df28f5d1e02640c3c3496ebf24e07c7584c` provides integrated implementation, test, and documentation evidence;
`434d372d90bbd56b1960ec4ec5c1c603ce445683` records terminal polling clarification.
