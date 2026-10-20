# Activation Options

Operators can tune how a provisioned configuration is activated: how long activation may take, the order in which
container services restart, which services may stay degraded, and what happens on failure. The policy lives in
`config.toml`, is validated before anything changes, and is rendered to `/data/config/activation-policy.json` for the
shared activation path. The original plan is in the [design record](design.md); Beads tracks the work under
`atomixos-ivy`.

## What changed for users

- **Operators** set activation timeout and settle periods in `config.toml`.
- **Operators** restart declared container services in an explicit order.
- **Operators** allow named declared services to remain degraded without failing activation.
- Rollback is the only accepted failure strategy.

Unknown units, a service listed as both required and degraded, unsafe values, and unsupported strategies are rejected
before the new configuration is promoted.

## How it fits in

Activation policy is desired state, not script input. Unit names are limited to declared services, rendering is
deterministic, and the existing candidate promotion, health checking, job reporting, and rollback steps stay in charge.

## Running it

- Longer timing values delay the terminal job result.
- Restart ordering can briefly interrupt services.
- Degraded units are reported, but unrelated activation failures still fail the job.
- A failed activation restores the previous configuration and policy.

## Differences from the design

The implementation kept explicit route and service wiring and the existing job manager instead of adding a workflow
engine.

## Not included

- There is no dedicated persistent-state VM test for activation policy; parsing, rendering, runtime, rollback, and
  compatibility have focused automated tests.
- `keep-failed`, `manual-confirm`, arbitrary commands, and unrestricted systemd unit control are not supported.

## Tests

- `scripts/atomixos_provision/tests/test_config.py`: schema and policy validation.
- `scripts/atomixos_provision/tests/test_activation.py`: timing, restart order, degraded services, and rollback.
- `scripts/atomixos_provision/tests/test_provision.py`: integration with the shared apply pipeline.

## Related pages

- [Provisioning](../../provisioning.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
