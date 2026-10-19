# First-Boot Local Provisioning

AtomixOS provisions a freshly flashed or reset device from one validated `config.toml`. The device looks for that file
on the boot partition (only on a fresh flash), then on removable USB media, and finally offers a local bootstrap
console. The accepted configuration is stored under `/data/config`, rendered into runtime configuration, and applied
before the first slot is confirmed. The original plan is in the [design record](design.md); Beads tracks the work under
`atomixos-ehv`.

## What changed for users

- A freshly flashed image prefers `/boot/config.toml`, then USB media, then the bootstrap console.
- A reprovisioned device skips the stale boot-partition file and prefers USB before the console.
- **Operators** can upload or paste a configuration in the console and download the accepted file.
- Provisioning must set up admin SSH access, required services, and health requirements before the slot is confirmed.
- After provisioning, the console listens only on the configured LAN address.

## How it fits in

Immutable OS content stays in the squashfs root, and `/data/config` holds the operator's durable intent. The initrd
records a fresh flash before repartitioning, and services in the switched root read that marker. Rendered Quadlet
units stay under `/data/config/quadlet` and are synchronized to the standard rootful and rootless Quadlet search paths.

## Running it

- Wiping `/data` returns a device to provisioning mode without replaying `/boot/config.toml`.
- A failed import, runtime apply, or required health check leaves the current slot unconfirmed.
- The bootstrap console is for provisioning and recovery, not general device management.

## Differences from the design

The original one-shot importer became the long-lived provisioning API service. It keeps this feature's source order
and desired-state contract and adds asynchronous jobs and a privilege-separated apply step.

## Not included

- Remote fleet delivery; see [Fleet Bootstrap via Nixstasis](../fleet-bootstrap-via-nixstasis/index.md).
- cloud-init, Compose as the device contract, arbitrary file writes, and a long-lived management UI.

## Tests

- `nix/tests/initrd-fresh-flash-marker.nix`: fresh-flash detection in the initrd.
- `nix/tests/first-boot-source-discovery.nix`: source order and reprovisioning.
- `nix/tests/first-boot-provision.nix`: schema validation, import, rendering, the bootstrap UI, and runtime apply.

## Related pages

- [Provisioning](../../provisioning.md)
- [Data Flow](../../data-flow.md)
- [Runtime Boundaries](../../runtime-boundaries.md)
- [Partition Layout](../../architecture/partition-layout.md)
- [Authentication](../../architecture/authentication.md)
