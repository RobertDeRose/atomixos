# Caddy AuthCrunch Cockpit Tutorial

AtomixOS ships an example bundle and tutorial for an OIDC-authenticated management stack. Caddy with AuthCrunch is the
public sign-in boundary: it maps identity-provider groups to roles and lets only administrators reach Cockpit, which
runs behind the proxy. The example exercises config-managed containers, networks, volumes, builds, and bundle files.
The original plan is in the [design record](design.md); Beads tracks the work under `atomixos-b45`.

## What changed for users

- **Operators** copy `example/caddy-oidc`, replace the marked identity-provider, domain, key, and secret values, then
  validate and apply it as a normal configuration bundle.
- Users with the admin role reach Cockpit through Caddy; other users do not.
- The tutorial covers Microsoft Entra setup and how to substitute another OIDC provider.

## How it fits in

The stack is an operator-provisioned application, not part of the immutable OS. Caddy is the only public sign-in
boundary: it forwards the AuthCrunch JWT to Cockpit as a bearer token, `cockpit-auth-atomixos` accepts only tokens with
the `authp/admin` role and maps them to the `admin` user, and `start-cockpit` reaches the host over SSH to `127.0.0.1`.
Powerful host socket mounts are explicit and limited to the admin management container. Quadlet units come from the
normal provisioning contract.

## Running it

Operators own identity-provider setup, DNS, certificates, secrets, role mappings, and version compatibility. The example
uses local TLS for a local deployment and needs production hardening before it faces the Internet.

## Differences from the design

The example moved from an embedded feature bundle to `example/caddy-oidc`, adopted the final Cockpit container layout,
centralized its variables, and follows the canonical configuration schema. The design ran `cockpit-ws` with
`--local-session`; the delivered example instead authenticates the forwarded JWT and opens Cockpit sessions over SSH,
so the configuration must declare a user named `admin`.

## Not included

- Identity-provider validation against a real tenant, image builds on target hardware, secret rotation, and production
  hardening are left to the operator.
- Cockpit in the base image, double authentication, SAML guidance, and a dedicated VM test.

## Tests

The provisioning tests for containers, networks, volumes, builds, bundle files, and Quadlet synchronization cover the
paths the example uses.

## Related pages

- [OIDC-Authenticated Device Management](../../tutorials/oidc-device-management.md)
- `example/caddy-oidc/config.toml`, `example/caddy-oidc/files/Caddyfile`, and
  `example/caddy-oidc/files/cockpit/Containerfile`
