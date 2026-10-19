# Network Config Extensions

Operators can set host DNS servers, search domains, a default route, and Ethernet interface settings in `config.toml`.
The values go through the same validated candidate, promotion, activation, and rollback pipeline as the rest of the
configuration. When the fields are absent, the isolated gateway defaults apply. The original plan is in the
[design record](design.md); Beads tracks the work under `atomixos-ky9`.

## What changed for users

- **Operators** configure top-level DNS servers and search domains, a default gateway, and supported `ethN` interfaces.
- A static interface address must come with a matching prefix.
- The LAN gateway and dnsmasq values must agree.
- Changing the LAN address no longer requires rebuilding the image.

## How it fits in

Validated values render to derived network state under `/data/config`. `scripts/lan-gateway-apply.py` applies that
state idempotently through systemd-networkd and the resolver configuration. A failed network activation rolls back with
the rest of the configuration, and IP forwarding stays disabled.

## Running it

Keep the effective `lan` address and the dnsmasq gateway CIDR consistent. DNS and route changes can briefly affect
connectivity during a re-apply; if activation fails, the previous desired state is restored.

## Differences from the design

Network settings use the provisioning service's shared desired-state pipeline instead of a separate network management
API.

## Not included

- Wi-Fi configuration, other interface classes, and DHCP client options beyond the bounded contract.
- Routing or forwarding between interfaces, empty gateway placeholders, and unbounded interface names.

## Tests

- `tests/test_lan_gateway_apply.py`: applying derived state and handling failures.
- `scripts/atomixos_provision/tests/`: accepted and rejected network values and the rendered state.
- `nix/tests/first-boot-provision.nix`: candidate promotion and rollback on re-apply.

## Related pages

- [Provisioning](../../provisioning.md)
- [LAN Range Configuration](../../provisioning/lan-range.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Data Flow](../../data-flow.md)
- [LAN Gateway specification](../../specs/lan-gateway.md)
- [NTP Settings](../../operations/ntp-settings.md)
