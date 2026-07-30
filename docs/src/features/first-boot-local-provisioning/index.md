# First-Boot Local Provisioning

## Delivery Summary

- Beads feature root: `atomixos-ehv`
- Status: delivered
- Pull request: not recorded in the legacy workflow
- Primary delivery commit: `ff96939469c76dc62d7f681fab7de0cca8dbd7f6`
- Design record: [design.md](design.md)

## Delivered Capability

AtomixOS provisions a freshly flashed or reset appliance from one validated `config.toml` contract. The device searches
the initial boot partition only on a fresh flash, then removable USB media, and finally a constrained local bootstrap
console. Accepted desired state is persisted under `/data/config`, rendered into runtime configuration, and applied
before the first slot is confirmed.

## User-Facing Behavior

- Fresh images prefer `/boot/config.toml`, then USB media, then the bootstrap console.
- Reprovisioned devices skip the stale boot-partition seed and prefer USB before the console.
- Operators can upload or paste config through the first-boot console and download the accepted artifact.
- Provisioning must establish admin SSH access, required services, and health requirements before slot confirmation.
- The console narrows to the configured LAN endpoint after initial provisioning.

## Design Integration

The implementation keeps immutable OS content in the squashfs root and treats `/data/config` as the durable operator
intent boundary. Initrd records fresh-flash state before repartitioning; switched-root services consume that marker.
Rendered Quadlet state remains durable under `/data/config/quadlet` and is synchronized to standard rootful or rootless
Quadlet discovery paths.

## Operational Impact

Wiping `/data` returns a device to provisioning mode without replaying `/boot/config.toml`. A failed import, runtime
apply, or required health check leaves the current slot unconfirmed. The bootstrap console is a recovery and
provisioning surface, not a general device-management UI.

## Reference and Contracts

- [Provisioning](../../provisioning.md)
- [Firmware Data Flow](../../data-flow.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Partition Layout](../../architecture/partition-layout.md)
- [Authentication](../../architecture/authentication.md)

## Validation Evidence

The legacy close-out records successful coverage in:

- `nix/tests/initrd-fresh-flash-marker.nix` for initrd fresh-flash detection;
- `nix/tests/first-boot-source-discovery.nix` for source order and reprovisioning;
- `nix/tests/first-boot-provision.nix` for schema validation, import, rendering, bootstrap UI, and runtime application;
- documentation validation and the mdBook build.

Commit `ff96939469c76dc62d7f681fab7de0cca8dbd7f6` updated the implementation, all three focused Nix tests, and the
reader-facing provisioning documentation together.

## Design Reconciliation

### Delivered as Designed

The single config contract, fresh-flash marker, ordered local sources, `/data/config` persistence boundary, structured
Quadlet rendering, same-boot activation, and provisioning-aware slot confirmation were delivered.

### Intentional Changes

The original one-shot importer later evolved into the long-lived provisioning API service. That service preserves this
feature's source discovery and desired-state contract while adding asynchronous jobs and a privilege-separated apply
boundary.

### Deferred Work

Remote fleet delivery remains outside this local provisioning feature. Nixstasis enrollment is tracked separately.

### Rejected or Removed Scope

Cloud-init, compose as the canonical appliance contract, arbitrary file writes, and a long-lived general management UI
remain rejected.

## Documentation Updated

- `docs/src/provisioning.md`
- `docs/src/data-flow.md`
- `docs/src/runtime-boundaries.md`
- `docs/src/architecture/partition-layout.md`
- `docs/src/architecture/authentication.md`
- `docs/src/hardware-testing.md`

## Audit Trail

Legacy tasks T001-T021 were mapped into Beads and closed from implementation evidence. The feature root is
`atomixos-ehv`; its imported lifecycle and implementation records preserve the original task text. Primary delivery is
corroborated by commit `ff96939469c76dc62d7f681fab7de0cca8dbd7f6` and the paths listed above.
