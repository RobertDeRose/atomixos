# Caddy AuthCrunch Cockpit Tutorial

## Delivery Summary

- Beads feature root: `atomixos-b45`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `52ca7b6fc97004769554d495c227693b6bf74dc6`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS documents and ships an example bundle for an OIDC-authenticated local management stack. Caddy with AuthCrunch
is the public authentication boundary, maps identity-provider groups to roles, and gates Cockpit running behind the
proxy. The example exercises config-managed containers, networks, volumes, builds, and bundle files.

## User-Facing Behavior

Operators copy the example, replace clearly marked identity-provider, domain, key, and secret values, then validate and
apply it as a normal config bundle. Admin-role users can reach Cockpit through Caddy; lower-privilege users do not gain
that route. The tutorial explains Entra setup and how to substitute another OIDC provider.

## Design Integration

The stack remains an operator-provisioned application, not immutable OS content. Caddy is the sole public login boundary
for Cockpit's local-session mode. Powerful host socket mounts are explicit and restricted to the admin management
container. Quadlet state is produced through the normal provisioning contract.

## Operational Impact

Operators own identity-provider setup, DNS, certificates, secrets, role mappings, and version compatibility. The example
uses local TLS for the documented local deployment and requires production hardening before Internet exposure.

## Reference and Contracts

- [OIDC-Authenticated Device Management](../../tutorials/oidc-device-management.md)
- `example/caddy-oidc/config.toml`
- `example/caddy-oidc/files/Caddyfile`
- `example/caddy-oidc/files/cockpit/Containerfile`

## Validation Evidence

- The tutorial's config passes the provisioning validator according to legacy close-out evidence.
- Existing provisioning tests cover container, network, volume, build, bundle-file, and Quadlet synchronization paths.
- Commit `52ca7b6fc97004769554d495c227693b6bf74dc6` introduced the tutorial, design, roadmap entry, and navigation.
- Later commits moved the example into `example/caddy-oidc` and reconciled local-device behavior and config evolution.

## Design Reconciliation

### Delivered as Designed

OIDC setup guidance, group-to-role mapping, Caddy authorization, admin-only Cockpit access, structured config, bundle
layout, provider substitution, and security guidance were delivered.

### Intentional Changes

The example evolved from an embedded feature bundle to `example/caddy-oidc`, moved Cockpit toward the final container
layout, centralized variables, and tracked later canonical config schema changes.

### Deferred Work

Real-tenant identity-provider validation, image-build validation on target hardware, secret rotation, and broader
production hardening remain operator or deployment concerns.

### Rejected or Removed Scope

Cockpit in the base image, double authentication, SAML guidance, and a dedicated duplicate VM test remain out of scope.

## Documentation Updated

- `docs/src/tutorials/oidc-device-management.md`
- `docs/src/SUMMARY.md`
- `docs/src/planned-features.md`
- `example/caddy-oidc/`

## Audit Trail

Legacy tasks T000-T999, including numeric mappings for the former T00A/T00B prerequisites, were imported under
`atomixos-b45`. T006 is preserved as intentionally skipped because existing provisioning tests cover the same paths.
The primary tutorial delivery is commit `52ca7b6fc97004769554d495c227693b6bf74dc6`.
