# Network Config Extensions

## Delivery Summary

- Beads feature root: `atomixos-ky9`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `77a151669d6aa7d342bb70f12db6d15d14628fae`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS accepts bounded host DNS, search-domain, default-route, and Ethernet interface settings in `config.toml` and
applies them through the same validated candidate, promotion, activation, and rollback pipeline as other desired state.
The isolated gateway defaults remain intact when these fields are absent.

## User-Facing Behavior

Operators can configure top-level DNS servers and search domains, a default gateway, and supported `ethN` interfaces.
Static interface configuration is validated as a coherent address/prefix pair. LAN gateway and dnsmasq values must agree,
and WiFi remains outside this contract.

## Design Integration

Validated values render to derived network state under `/data/config`. `lan-gateway-apply.py` applies that state
idempotently through systemd-networkd and resolver configuration. A failed network activation participates in the shared
config rollback path, and IP forwarding remains disabled.

## Operational Impact

Supported LAN address changes no longer require rebuilding the immutable image. Operators must keep the effective
`eth1` address and dnsmasq gateway CIDR consistent. DNS and route changes can temporarily affect connectivity during
re-apply, so activation failures restore the prior desired state.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [LAN Range Configuration](../../provisioning/lan-range.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Firmware Data Flow](../../data-flow.md)
- [LAN Gateway Specification](../../specs/lan-gateway.md)
- [NTP Settings](../../operations/ntp-settings.md)

## Validation Evidence

- `tests/test_lan_gateway_apply.py` covers derived state application and failure handling.
- Provisioning package tests cover accepted and rejected network schema values and rendered state.
- Existing re-apply tests cover candidate promotion and rollback integration.
- Commit `77a151669d6aa7d342bb70f12db6d15d14628fae` changed the runtime apply script, focused tests, modules,
  and reader docs together.

## Design Reconciliation

### Delivered as Designed

DNS, search domains, default routes, supported Ethernet interface configuration, LAN CIDR reconciliation, preserved
defaults, idempotent apply, rollback, and fail-closed forwarding behavior were delivered.

### Intentional Changes

The delivered implementation uses the provisioning service's common desired-state pipeline rather than a separate
network management API.

### Deferred Work

WiFi configuration, arbitrary interface classes, DHCP client customization beyond the bounded contract, and routing or
forwarding remain separate work.

### Rejected or Removed Scope

Empty gateway sentinels, unbounded interface names, and config paths that enable forwarding remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/provisioning/lan-range.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/data-flow.md`
- `docs/src/specs/lan-gateway.md`
- `docs/src/operations/ntp-settings.md`

## Audit Trail

Legacy tasks T000-T999 were imported under `atomixos-ky9` and closed from delivery evidence. Commit
`77a151669d6aa7d342bb70f12db6d15d14628fae` corroborates the runtime, test, module, and documentation integration.
