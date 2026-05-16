# Config Reapply Improvements Tasks

- [x] Confirm the canonical `config.toml` top-level sections: `[users]`, `[network]`, `[health]`, `[os_upgrade]`, and `[containers]`.
- [x] Reject legacy top-level `[admin]`, `[firewall]`, `[lan]`, `[container]`, `[network]`, `[volume]`, and `[build]` config without migration because AtomixOS is unreleased.
- [x] Use SSH-key challenge-response with an existing admin key for re-apply authentication.
- [x] Manage declared `[users.<name>]` local users in this feature.

## T010 - Define the official config schema

- [x] Replace `schemas/config.schema.json` with the new canonical schema used by validation and documentation.
- [x] Define `[users]` schema with default `isAdmin = false` and default empty `ssh_key`.
- [x] Add username validation and reserved-system-user rejection.
- [x] Define `[network]` schema for dnsmasq and firewall rules.
- [ ] Define `[network]` schema for DNS servers, search domains, interfaces, and default gateway once runtime support is
  implemented.
- [x] Define `[containers]` schema for nested container, network, volume, and build Quadlet units.
- [x] Add cross-field validation for admin SSH keys, LAN subnet, DHCP range, port ranges, and required service references.
- [x] Ensure schema errors include precise config paths and actionable messages.

## T020 - Implement config parser restructure

- [x] Update `first-boot-provision.py` to parse `[users]` instead of top-level `[admin]`.
- [x] Persist normalized managed user state under `/data/config` for boot-time and re-apply materialization.
- [x] Render managed user state and SSH authorized keys for all declared users.
- [x] Add a runtime user apply service that materializes managed users from persisted config on boot and re-apply.
- [x] Lock or disable managed users removed during config re-apply.
- [x] Update LAN settings parsing to consume `[network]` while preserving current defaults.
- [x] Update firewall parsing to consume firewall rules under `[network]`.
- [x] Update Quadlet rendering to consume `[containers.container]`, `[containers.network]`, `[containers.volume]`, and
  `[containers.build]`.
- [x] Keep rendered persistent outputs compatible with existing runtime services unless those services are intentionally
  updated.

## T030 - Harden re-apply authentication

- [x] Detect already-provisioned devices by active persisted config state.
- [x] Add nonce issuance for short-lived re-apply authentication challenges.
- [x] Verify SSH signatures against active admin user keys before accepting candidate config bytes.
- [x] Require authentication for `POST /api/config` when active config exists.
- [x] Keep first provisioning unauthenticated for fresh devices without existing operator credentials.
- [x] Add tests for unauthenticated rejection and authenticated acceptance.

## T040 - Implement atomic candidate apply

- [x] Validate and render candidate config in a temporary candidate directory.
- [x] Prevent candidate validation/rendering from mutating active `/data/config`.
- [x] Promote candidate config to `/data/config` with a crash-safe directory replacement strategy.
- [x] Preserve the previous config in a rollback location until apply is confirmed.
- [x] Clean up stale candidate and rollback state safely.

## T050 - Implement rollback on failed activation

- [x] Apply LAN settings, firewall state, and Quadlet sync after candidate promotion.
- [x] Confirm required services reach the expected active state.
- [x] Restore previous config if apply or service confirmation fails.
- [x] Re-apply previous LAN, firewall, and Quadlet state after rollback.
- [x] Return clear API errors describing validation or activation failures.

## T060 - Update examples and operator docs

- [x] Update provisioning docs for the new `config.toml` structure.
- [x] Update data-flow and runtime-boundary docs for candidate apply and rollback state.
- [x] Update LAN/network docs for `[network]` defaults and overrides.
- [x] Update Caddy/AuthCrunch/Cockpit tutorial config and docs to use `[containers]`.
- [x] Update code-reference docs for parser, rendered files, and API behavior.

## T070 - Add automated validation

- [x] Add unit tests for schema defaults and invalid key rejection.
- [x] Add unit tests for users/admin SSH key extraction.
- [x] Add unit tests for managed user creation/update/disable behavior.
- [ ] Add boot or VM coverage proving managed users are materialized from `/data/config` after reboot (deferred: requires
  persistent VM disk).
- [x] Add unit tests for network defaults, dnsmasq defaults, and firewall rule rendering.
- [x] Add unit tests for nested `[containers]` Quadlet rendering.
- [x] Add unit tests for SSH-key challenge-response authentication.
- [x] Add VM or integration test for successful authenticated re-apply.
- [x] Add VM or integration test for invalid config preserving active state.
- [x] Add VM or integration test for activation failure rollback.

## T999 - Final verification and release readiness

- [ ] Run the repository's relevant formatting, unit, and Nix checks.
- [ ] Verify docs, examples, specs, and implementation all describe the same `config.toml` contract.
- [ ] Verify no unauthenticated re-apply path remains on already-provisioned devices.
- [ ] Verify first provisioning still works from `/boot/config.toml`, USB, and bootstrap UI.
- [ ] Record any intentionally deferred compatibility or migration work before merging.
