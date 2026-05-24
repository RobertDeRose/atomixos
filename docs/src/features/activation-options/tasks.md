# Activation Options Tasks

## T000 - Review and confirm feature spec

- [x] Confirm feature name, scope, and non-goals.
- [x] Resolve whether `keep-failed` belongs in the first implementation.
- [x] Resolve the accepted unit namespace for `activation.restart` and
  `activation.allow_degraded`.
- [x] Confirm bounds and defaults for timeout and settle values.
- [x] Confirm affected docs and validation requirements.

## T010 - Define config contract and validation

- [x] Extend `schemas/config.schema.json` for the selected `[activation]`
  fields.
- [x] Extend the provisioning parser for activation policy.
- [x] Validate numeric bounds for timeout and settle values.
- [x] Validate unit references against provisioned Quadlet services.
- [x] Reject unknown keys and unsupported strategy values.
- [x] Reject conflicting policy, including overlap between `required` and
  `allow_degraded`.
- [x] Add parser/schema tests for accepted and rejected activation policy.

## T020 - Render derived activation state

- [x] Define `/data/config/activation-policy.json` as the derived activation
  policy state.
- [x] Render activation policy from validated `config.toml`.
- [x] Preserve current defaults when new fields are absent.
- [x] Keep rendered state compatible with candidate promotion and rollback.

## T030 - Apply activation policy at runtime

- [x] Update the activation path to consume rendered activation policy.
- [x] Apply configured settle and timeout behavior.
- [x] Apply explicit restart ordering if included in the accepted scope.
- [x] Preserve rollback-on-failure as the default behavior.
- [x] Reject non-rollback strategies while preserving a future extension point.
- [x] Ensure failure states remain clear for API and CLI callers.

## T040 - Update docs and examples

- [x] Update runtime boundary docs for activation policy state.
- [x] Update data-flow docs for rendered activation policy.
- [x] Update provisioning docs or examples if operator-facing config changes.
- [x] Update config-reapply feature docs/tasks to mark deferred activation
  options resolved only after implementation and validation pass.
- [x] Update API/spec docs if job result semantics change.

## T050 - Add automated validation

- [x] Add unit tests for default activation behavior compatibility.
- [x] Add unit tests for timeout and settle policy validation.
- [x] Add render tests for `activation-policy.json` defaults and explicit
  values.
- [x] Add tests for restart and degraded policy validation.
- [x] Add tests for rollback strategy behavior.
- [x] Add tests rejecting deferred strategies such as `keep-failed` and
  `manual-confirm`.
- [ ] Add integration or VM coverage for at least one activation policy path.
  Deferred: unit coverage exercises parser, renderer, runtime, rollback, and
  compatibility paths; VM activation-policy coverage requires the existing VM
  harness to support persistent re-apply state.

## T999 - Final verification and release readiness

- [x] Run the relevant formatting, unit, and Nix checks.
- [x] Run `hk check -a` before final review.
- [x] Verify docs, schema, parser, renderer, and runtime behavior describe the
  same `[activation]` contract.
- [x] Verify no activation option enables arbitrary command execution or unsafe
  systemd unit manipulation.
- [x] Record any intentionally deferred activation behavior before close-out.
