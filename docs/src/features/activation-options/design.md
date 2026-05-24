# Feature: activation-options

## Overview

Extend the canonical `[activation]` config contract beyond `required` so
operators can control activation health-check timing, restart behavior, and
non-required service tolerance through `config.toml` without adding a parallel
mutation path.

This feature turns the `Additional [activation] options` planned-feature question
into a concrete implementation scope. It must build on the existing validate,
render, promote, activate, and rollback pipeline.

## Source

- `docs/src/planned-features.md` open question: Additional `[activation]`
  options.
- Existing provisioning and re-apply flow in `atomixos-provision`.
- Existing `activation.required` semantics for required unit health checks.

## Goals

1. Add a typed, validated `[activation]` config model for selected operational
   controls:
   - `required`
   - `timeout_seconds`
   - `settle_seconds`
   - `restart`
   - `allow_degraded`
   - `strategy`
2. Preserve current behavior when only `activation.required` is present.
3. Keep all activation decisions inside the existing candidate promotion and
   rollback flow.
4. Make failed activation outcomes explicit and predictable for API callers,
   CLI callers, and logs.
5. Update schema, parser, runtime docs, and tests together so the accepted
   config shape and behavior stay aligned.

## Non-Goals

- Adding partial activation APIs.
- Adding a separate mutable activation control plane outside `/data/config`.
- Disabling authentication or weakening re-apply authorization.
- Making failed units silently acceptable by default.
- Implementing service-specific recovery logic beyond configured restart and
  health-check policy.
- Changing Quadlet safety boundaries or network/firewall behavior.
- Keeping a failed candidate config active after activation failure. `keep-failed`
  and `manual-confirm` remain deferred because the current provisioning contract
  is fail-closed rollback.

## Proposed Config Contract

The feature should extend `[activation]` with explicit keys:

```toml
[activation]
required = ["myapp"]
timeout_seconds = 120
settle_seconds = 5
restart = ["myapp"]
allow_degraded = []
strategy = "rollback"
```

Defaults when optional fields are absent:

| Field             | Default    |
|-------------------|------------|
| `timeout_seconds` | `300`      |
| `settle_seconds`  | `0`        |
| `restart`         | `[]`       |
| `allow_degraded`  | `[]`       |
| `strategy`        | `rollback` |

### Field Semantics

- `activation.required`: list of provisioned units that must become healthy for
  activation success. Existing semantics are preserved.
- `activation.timeout_seconds`: maximum time to wait for activation health checks
  and the activation hook before treating activation as failed. Valid range is
  `1..3600` seconds.
- `activation.settle_seconds`: delay after service restart/application before
  evaluating health checks. Valid range is `0..300` seconds. `0` means health
  checks may run immediately after activation commands complete.
- `activation.restart`: explicit ordered list of provisioned services to restart
  during activation. Values must refer to known declared container service names
  without the `.service` suffix.
- `activation.allow_degraded`: list of provisioned services whose failed runtime
  status is reported but does not cause rollback. Values must refer to known
  declared container service names without the `.service` suffix and must not
  overlap with `required`.
- `activation.strategy`: activation failure strategy. The first implementation
  supports only `rollback`, which restores the previous config on activation
  failure. Other strategies remain deferred.

## Compatibility

When new activation options are absent, current behavior must remain unchanged:

- `required` remains mandatory and continues to validate against known
  provisioned containers.
- Candidate promotion rolls back on activation failure.
- Required units are checked with the existing default timeout/check behavior.
- `strategy` defaults to `rollback`.

Any new default must be documented and covered by tests.

## Runtime Rendering

Activation policy must be rendered to `/data/config/activation-policy.json`, not
read directly from arbitrary source files at activation time. The file must be
documented in `data-flow.md` and `runtime-boundaries.md`.

The activation path must remain single-flight and candidate-scoped:

- Validate config and render activation policy into the candidate root.
- Promote candidate state atomically.
- Apply services and activation policy.
- Roll back the candidate on activation failure.
- Report final status through the same API/CLI job result path.

## Validation Requirements

- Reject unknown keys under `[activation]`.
- Require `required` to remain a list of known unit names.
- Validate `timeout_seconds` as an integer in `1..3600`.
- Validate `settle_seconds` as an integer in `0..300`.
- Validate `restart` and `allow_degraded` entries as known safe unit names.
- Reject overlap between `required` and `allow_degraded`.
- Reject any `strategy` value other than `rollback`.

## Security And Safety

- Re-apply authentication must remain required on provisioned devices.
- Activation options must not allow arbitrary command execution or arbitrary
  systemd unit manipulation.
- Unit references must be restricted to provisioned Quadlet services already
  rendered in `quadlet-runtime.json`; this feature must not expose arbitrary
  platform unit restarts.
- Activation options must not change firewall exposure, IP forwarding, or Quadlet
  network safety boundaries.
- Failure reporting must be explicit about rollback status and degraded runtime
  service status.

## Documentation Impact

Likely affected docs:

- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/features/config-reapply-improvements/design.md`
- `docs/src/features/config-reapply-improvements/tasks.md`
- `docs/src/specs/provisioning-api.md` if API job results change
- `docs/src/provisioning.md` if user-facing config examples include activation
  policy
- `schemas/config.schema.json`

## Success Criteria

- `config.toml` validates and applies the new `[activation]` fields.
- Defaults remain behaviorally equivalent when fields are absent.
- Invalid activation policy fails before active `/data/config` promotion.
- Authenticated re-apply can use supported activation options and reports clear
  final status.
- Rollback strategy behavior and degraded runtime status reporting are tested.
- Docs, schema, parser, renderer, activation flow, and tests describe the same
  contract.

## Risks And Tradeoffs

- Restart ordering can create coupling between units. Validation should keep the
  accepted unit names narrow and predictable.
- Long timeouts can block apply jobs. The `1..3600` timeout bound prevents
  accidental indefinite waits while still allowing slow image pulls or service
  startup.
- `keep-failed` and `manual-confirm` would require new recovery semantics and are
  intentionally deferred to preserve the current fail-closed rollback boundary.

## Deferred Behavior

- `strategy = "keep-failed"` and `strategy = "manual-confirm"` are deferred.
- Restarting platform-managed units is deferred; `activation.restart` is limited
  to provisioned Quadlet services.

## Open Questions

None.
