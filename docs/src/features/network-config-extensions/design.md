<!-- workflow-migration:legacy-markdown-to-beads -->

# Feature: Network Config Extensions

## Metadata

- Beads feature root: `atomixos-ky9`
- Feature slug: `network-config-extensions`
- Design path: `docs/src/features/network-config-extensions/design.md`
- Implemented record: `docs/src/features/network-config-extensions/index.md`
- Base branch: `dev`
- Status: delivered

## Feature Summary

Extend the canonical network contract with bounded DNS, search-domain, default-route, and Ethernet interface settings
that use the existing atomic config apply and rollback pipeline.

## User Intent

Operators need to change supported appliance networking from desired state without rebuilding the image or creating a
second network control plane. Omitted fields must retain the initial gateway profile's safe defaults.

## User-Facing Behavior

`config.toml` accepts validated resolver, route, and supported `ethN` settings. Conflicting LAN gateway values fail
before promotion; successful changes apply through systemd-networkd and roll back with the rest of config state.

## Requirements

The schema must reject unsafe names, malformed IP/CIDR/domain values, incompatible interface modes, unknown keys, and
conflicting `eth1`/dnsmasq gateway values. IP forwarding stays disabled and firewall exposure remains independently
controlled.

## Existing Context

Config re-apply already owned dnsmasq, NTP, firewall, candidate promotion, activation, and rollback. The network helper
already materialized gateway defaults. This feature fills the explicitly deferred host resolver, route, and interface
contract without replacing those boundaries.

## Proposed Design

Parse the bounded fields into normalized desired state, render derived files below `/data/config`, reconcile one
effective LAN CIDR, and apply the result idempotently through the existing network activation service. The detailed
field semantics and runtime targets remain below.

## Architecture Consistency

The design reuses `config.toml` as authority, `/data/config` as persisted derived state, systemd-networkd as runtime
owner, and shared promotion/rollback. It preserves gateway-local DNS, fail-closed validation, immutable rootfs, and no
forwarding.

## Operational Considerations

Route and resolver changes may interrupt management connectivity during apply. The activation path must report failure
clearly and restore prior state. Unchanged config must not rewrite runtime files, and LAN DHCP/NTP behavior must continue
to derive from the effective gateway address.

## Documentation Impact

Update `docs/src/provisioning.md`, `docs/src/provisioning/lan-range.md`, `docs/src/data-flow.md`,
`docs/src/runtime-boundaries.md`, `docs/src/specs/lan-gateway.md`, and `docs/src/operations/ntp-settings.md`. Create the
implemented record at `docs/src/features/network-config-extensions/index.md`.

## Validation Strategy

Use provisioning parser/schema tests, `tests/test_lan_gateway_apply.py`, config re-apply rollback coverage, Nix module
checks, and documentation validation. Include defaults, invalid values, CIDR conflicts, idempotency, and failed apply.

## Implementation Decomposition

The work separates schema/parser validation, derived-state rendering, runtime application, docs/examples, and automated
validation. Imported Beads tasks under `atomixos-ky9` preserve those slices and their close-out evidence.

## Dependencies and Parallelism

The feature depends on Config Reapply Improvements. Schema and docs could advance with renderer work, while runtime
activation depended on normalized render output and rollback integration.

## Risks and Tradeoffs

Applying network state can disrupt the connection used to submit it, and a bounded contract cannot express arbitrary
networkd features. Restricting supported interfaces and behavior reduces flexibility but preserves safe rendering,
rollback, and appliance invariants.

## Overview

Extend the canonical `config.toml` `[network]` contract beyond the current
dnsmasq, NTP, and firewall subset so operators can configure host DNS resolver
servers, DNS search domains, default gateway behavior, and explicit Ethernet
interface settings without editing the base image.

This feature completes the deferred `[network]` schema work recorded by
`config-reapply-improvements` and turns the project-plan open question for
additional network properties into a concrete implementation scope.

## Source

- `docs/src/planned-features.md` open question: Additional `[network]`
  properties.
- `docs/src/features/config-reapply-improvements/design.md`: `[network]`
  already owns device networking, DNS, dnsmasq, and firewall configuration, but
  DNS servers, search domains, arbitrary interface configuration, and default
  gateway configuration were deferred until runtime support exists.
- Config Reapply Improvements task T010 deferred the DNS, search, interface,
  and default-gateway schema until runtime support was implemented.

## Goals

1. Add a typed, validated `[network]` config model for:
   - `dns_servers`
   - `dns_search_domains`
   - `default_gateway`
   - `interfaces`
2. Preserve the current default gateway appliance behavior when operators do not
   set the new fields:
   - `eth0` remains the WAN DHCP client.
   - `eth1` remains the LAN gateway.
   - dnsmasq remains enabled by default for LAN.
   - IP forwarding remains disabled.
3. Apply network settings through the same candidate, promotion, activation,
   health-check, and rollback path used by config re-apply.
4. Keep `/data/config` rendered network state derived from `config.toml`; do not
   introduce a second mutable network control plane.
5. Update schema, parser, docs, and tests together so the accepted config shape
   and runtime behavior stay aligned.

## Non-Goals

- Enabling router behavior or IP forwarding.
- Adding WiFi or Bluetooth support.
- Replacing systemd-networkd as the host network renderer.
- Managing arbitrary networkd options beyond the explicitly supported subset.
- Changing the current LAN dnsmasq DNS model to forward unknown client queries
  upstream. LAN dnsmasq remains gateway-local DNS only unless a later feature
  explicitly changes that boundary.
- Adding dynamic partial network APIs in this feature. Future partial APIs must
  reuse the same full-state validation and apply pipeline.
- Migrating legacy or unreleased config shapes.

## Proposed Config Contract

The feature should extend `[network]` with a small explicit schema. Field names
are snake_case to match the existing config style.

```toml
[network]
dns_servers = ["1.1.1.1", "9.9.9.9"]
dns_search_domains = ["lan.example"]
default_gateway = "192.0.2.1"

[network.interfaces.eth0]
mode = "dhcp"

[network.interfaces.eth1]
mode = "static"
address = "172.20.30.1/24"
dns_servers = ["172.20.30.1"]
dns_search_domains = ["lan"]
```

### Field Semantics

- `network.dns_servers`: optional list of DNS resolver IP addresses for `eth0`.
  Interface-specific resolver lists override this list rather than appending to
  it. The LAN gateway DNS service remains gateway-local and does not inherit
  these resolvers.
- `network.dns_search_domains`: optional list of DNS search domains for `eth0`.
  Interface-specific search lists override this list rather than appending to it.
- `network.default_gateway`: optional host default route gateway. The value must
  be an IPv4 address. Omit the field to keep DHCP/default route behavior. Empty
  strings are invalid. When multiple interfaces are configured, the top-level
  default gateway applies to `eth0` unless an interface-specific gateway is set.
- `network.interfaces.<name>.mode`: `dhcp` or `static`.
- `network.interfaces.<name>.address`: required for `static`, omitted or rejected
  for `dhcp`. Must be CIDR notation.
- `network.interfaces.<name>.gateway`: optional per-interface IPv4 gateway. Omit
  the field when the interface should not render a static gateway. Empty strings
  are invalid.
- `network.interfaces.<name>.dns_servers`: optional per-interface DNS resolver
  list.
- `network.interfaces.<name>.dns_search_domains`: optional per-interface DNS
  search list.

Only Ethernet interfaces supported by the current image may be configured in this
feature. That means `eth0`, `eth1`, and additional USB Ethernet interfaces named
by the existing systemd-networkd link policy. WiFi interface configuration is out
of scope until hardware and firmware support are selected. Because `eth1` remains
the LAN gateway, `network.interfaces.eth1.mode` must be `static` when `eth1` is
configured.

### Default Compatibility

When none of these new fields are provided, the rendered network state must match
the current behavior documented by `config-reapply-improvements`:

- `eth0` uses DHCP for WAN.
- `eth1` uses `172.20.30.1/24` as the LAN gateway.
- DHCP option 3, 6, and 42 point LAN clients at the gateway IP.
- chrony serves NTP to LAN clients.
- Host DNS on WAN follows DHCP-provided DNS when no explicit DNS fields are set.
- LAN dnsmasq remains gateway-local DNS only and does not forward unknown client
  queries upstream.
- IP forwarding stays disabled.

`network.interfaces.eth1.address` and `network.dnsmasq.gateway_cidr` describe the
same LAN gateway address. If either field is set, implementation must reconcile
them into one effective LAN gateway CIDR before rendering. If both fields are set
and disagree, validation must fail before candidate promotion. dnsmasq gateway,
DNS, and NTP DHCP options must derive from the same effective LAN gateway IP.

## Runtime Rendering

Implementation should continue to render derived network state under
`/data/config` and apply it through the existing activation path.

Expected render targets include the existing `lan-settings.json` plus one or more
new derived files consumed by the network apply service for host resolver,
interface, and route state. The exact new file names are implementation details,
but they must remain under `/data/config`, be documented in `data-flow.md` and
`runtime-boundaries.md`, and be safe to roll back with the candidate config
directory.

This feature should extend or replace the current `lan-gateway-apply.service`
boundary only as needed. It must keep LAN dnsmasq/chrony application and host
interface/route/resolver application in the same validated candidate apply flow,
with clear restart ordering and failure reporting.

The apply path must be idempotent:

- Re-applying the same config should not change rendered files.
- Rollback should restore the previous rendered network behavior.
- Invalid candidate network config must not mutate active runtime networking.

## Validation Requirements

- Reject unknown keys under `[network]` and `[network.interfaces.<name>]`.
- Validate IP address values and CIDR values with precise config paths.
- Reject interface names that cannot be safely rendered as systemd-networkd unit
  fragments or are outside the supported Ethernet naming policy.
- Require `address` for static interfaces.
- Reject `address` for DHCP interfaces unless the implementation documents a
  concrete mixed mode.
- Reject `default_gateway` and interface gateways that are not IP addresses.
- Reject DNS server values that are not IP addresses.
- Reject empty-string gateway and default-gateway values; absence is the only
  no-static-gateway sentinel.
- Reject empty `dns_servers` entries and empty `dns_search_domains` entries.
- Detect conflicts between `network.interfaces.eth1.address` and
  `network.dnsmasq.gateway_cidr` before promotion.

## Security And Safety

- IP forwarding must remain disabled regardless of configured interfaces or
  gateways.
- New interface configuration must not open firewall ports. Firewall exposure
  remains controlled by `[network.firewall]`.
- Config rendering must not allow path traversal through interface names.
- New route rendering must not create forwarding behavior, NAT, or FORWARD-chain
  exceptions.
- Network re-apply must preserve fail-closed behavior: invalid config, failed
  activation, or failed required health checks trigger rollback.

## Detailed Documentation Changes

Likely affected docs:

- `docs/src/provisioning.md`
- `docs/src/provisioning/lan-range.md`
- `docs/src/data-flow.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/operations/ntp-settings.md`
- `docs/src/specs/lan-gateway.md`
- `docs/src/reference/flake-outputs.md` if tests or outputs change
- `docs/src/code-reference/modules.md`
- `docs/src/code-reference/scripts.md`
- `docs/src/planned-features.md`

## Success Criteria

- `config.toml` validates and applies the new `[network]` fields.
- Defaults stay byte-for-byte or behaviorally equivalent when new fields are
  absent.
- Invalid network settings fail before active `/data/config` promotion.
- Authenticated re-apply can change DNS/search/default-gateway/interface settings
  and roll back on activation failure.
- LAN gateway docs and rendered state explicitly reconcile
  `network.dnsmasq.gateway_cidr` with `network.interfaces.eth1.address`.
- Tests cover parser/schema validation, render output, activation/rollback, and
  at least one VM or integration path for applied network behavior.

## Resolved Review Decisions

1. Empty strings are not accepted as gateway sentinels. Absence means “do not
   render a static gateway.”
2. Interface-specific DNS resolver and search lists override top-level lists for
   that interface.
3. This feature accepts currently supported Ethernet interface names only. WiFi
   remains out of scope.

## Open Questions

None.
