# Network Config Extensions Tasks

## T000 - Review and confirm feature spec

- [x] Confirm feature name, scope, and non-goals.
- [x] Confirm resolved review decisions in `design.md` still match operator
  needs.
- [x] Confirm the accepted `[network]` field names and default semantics.
- [x] Confirm docs that must be updated with implementation.

## T010 - Define config contract and validation

- [x] Extend `schemas/config.schema.json` for `dns_servers`,
  `dns_search_domains`, `default_gateway`, and `interfaces`.
- [x] Extend the provisioning config parser for the new `[network]` fields.
- [x] Add validation for IP addresses, CIDR addresses, DNS search domains, and
  safe interface names.
- [x] Add cross-field validation for static interface requirements and LAN
  gateway/dnsmasq conflicts.
- [x] Reject empty gateway sentinel values; absence is the only no-static-gateway
  signal.
- [x] Validate that configurable interfaces are limited to supported Ethernet
  names and do not include WiFi.
- [x] Add precise validation error tests for each invalid network path.

## T020 - Render derived network state

- [x] Define the derived network state files under `/data/config`.
- [x] Render host DNS resolver settings from top-level and interface-specific
  network config.
- [x] Render default gateway and interface mode/address settings.
- [x] Reconcile `network.interfaces.eth1.address` with
  `network.dnsmasq.gateway_cidr` into one effective LAN gateway CIDR.
- [x] Preserve existing LAN gateway defaults when new fields are absent.
- [x] Keep rendered state compatible with candidate promotion and rollback.

## T030 - Apply runtime network settings

- [x] Update the network apply service or script to consume the derived network
  state.
- [x] Keep network apply idempotent for unchanged config.
- [x] Ensure failed apply returns a clear error and triggers config rollback.
- [x] Ensure IP forwarding remains disabled after apply and reboot.

## T040 - Update docs and examples

- [x] Update provisioning docs for the extended `[network]` contract.
- [x] Update LAN range docs to explain runtime config replaces the old rebuild
  workflow for supported LAN gateway changes.
- [x] Update data-flow and runtime-boundary docs for derived network state.
- [x] Update LAN gateway spec for effective LAN CIDR reconciliation and DNS
  behavior.
- [x] Update operation docs for DNS and NTP interactions.
- [x] Update config-reapply tasks to mark the deferred network schema/runtime
  support complete only after implementation and validation pass.
- [x] Move the planned-features open question to resolved status only after the
  feature is implemented.

## T050 - Add automated validation

- [x] Add parser/schema unit tests for accepted network config.
- [x] Add parser/schema unit tests for invalid IP, CIDR, domain, gateway, and
  interface-name values.
- [x] Add render tests proving default behavior is preserved when fields are
  absent.
- [x] Add tests proving conflicting `network.interfaces.eth1.address` and
  `network.dnsmasq.gateway_cidr` values are rejected.
- [x] Add render tests for top-level DNS/search/default gateway and
  interface-specific overrides.
- [x] Add tests proving LAN dnsmasq remains gateway-local DNS and does not
  forward unknown LAN client queries upstream.
- [x] Add re-apply coverage for network settings through the shared promotion
  path.
- [x] Add rollback coverage for failed network activation.

## T999 - Final verification and release readiness

- [x] Run the relevant formatting, unit, and Nix checks.
- [x] Run `hk check -a` before final review.
- [x] Verify docs, schema, parser, renderer, and runtime behavior describe the
  same `[network]` contract.
- [x] Verify no new config path enables IP forwarding or unexpected firewall
  exposure.
- [x] Record any intentionally deferred network behavior before close-out.
