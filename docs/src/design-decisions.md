# Design Decisions

The main architectural choices behind AtomixOS, why they were made, and what they cost. AtomixOS targets appliances
deployed far from anyone who could fix them by hand, on aarch64 single-board computers that boot from eMMC (the ROCK64
and the Radxa CM3), so most decisions favor recoverability over flexibility.

## RAUC for A/B updates

**Choice:** RAUC manages the A/B slots.

**Why:** RAUC integrates with U-Boot, has clear slot configuration, and has a NixOS module. SWUpdate offers more, such
as scripted handlers and delta updates, but that flexibility is not needed here.

**Cost:** Updates write whole images, never deltas. A full root filesystem write takes longer than a delta but is
simpler and more reliable.

## Squashfs root filesystem

**Choice:** A read-only squashfs root under an OverlayFS with a tmpfs upper layer.

**Why:** Squashfs rules out drift: every boot starts from a known-good state. It compresses well (zstd, 1 MB blocks).
The OverlayFS, assembled in the initrd, gives systemd the single writable root it needs for sandboxing options such as
`PrivateTmp` and `ProtectHome`. Lasting state lives on `/data` (f2fs).

**Cost:** Anything not written to `/data` is gone after a reboot. That is the point for an appliance, but writable
directories have to be placed deliberately.

## Per-slot boot partitions

**Choice:** Each slot has its own vfat boot partition with the kernel, initrd, DTB, and boot script.

**Why:** Pairing boot and root in one slot keeps them consistent. With separate slot sets, a failed update could leave a
kernel and root filesystem from different versions.

**Rejected:** One shared boot partition holding both kernels. It would be a single point of failure and would complicate
the boot script.

## Fixed eMMC layout

**Choice:** 16 MB of raw U-Boot, 128 MB boot and 1 GB root partitions per slot, and the rest for `/data`. See
[Partition Layout](architecture/partition-layout.md).

**Why:** 128 MB comfortably holds a kernel, initrd, DTB, and script. 1 GB per root slot leaves room for the system
closure to grow, and `/data` keeps most of the eMMC for containers, logs, and configuration.

**Risk:** If the closure outgrows 1 GB, the slots must grow, which shrinks `/data` and means reprovisioning every device.
The build checks the squashfs size against the slot size to catch this early.

## U-Boot built from nixpkgs

**Choice:** Build each board's U-Boot from a nixpkgs package with a small configuration override, rather than
maintaining a fork: `ubootRock64` in `nix/uboot.nix` for ROCK64, and `ubootRock3C` with the `radxa-cm3-io-rk3566`
defconfig in `nix/uboot-cm3.nix` for the CM3.

**Why:** The nixpkgs packages are tested, reproducible, and follow upstream. The overrides only change configuration:
RAUC's boot method handles slot selection and boot counters, EFI boot is off, and SD cards are removed from the boot
targets so nobody can hijack boot with a card. The environment lives in SPI flash on ROCK64 and in two redundant copies
on the CM3's eMMC, because the CM3's SPI flash is optional.

**Cost:** AtomixOS uses whichever U-Boot version nixpkgs provides.

## Hardware watchdog off by default

**Choice:** systemd hardware watchdog enforcement is opt-in through `build.toml`, which also selects the watchdog
device; see [Watchdog Backend Selection](reference/build-configuration.md#watchdog-backend-selection).

**Why:** A watchdog that resets a board before its timing and rollback behavior are proven on that hardware can trap a
device in a reboot loop in the field. Keeping it off by default means each release profile turns it on only after
physical reset-timing, rollback, and soak testing.

**How it fits:** systemd is the only watchdog owner, and watchdog resets use up boot tries like any failed boot, so they
lead into the normal rollback path.

## Local health checks only

**Choice:** `os-verification.service` confirms a slot from local checks alone and never contacts a server.

**Why:** The device must decide on its own. If the WAN is down after an update, the device should still commit a healthy
slot or roll back a broken one. Asking a server would make confirmation depend on the network at the worst moment.

## Remote management in Nixstasis

**Choice:** Keep remote web management out of the image and use Nixstasis as an optional control plane.

**Why:** The Nixstasis client already opens reverse tunnels and handles remote-access credentials. Running the web
management and its sign-in in Nixstasis avoids pulling container images on first boot, keeps the image smaller, and keeps
the device focused on gateway and update work.

**Cost:** Remote management depends on enrollment and a working tunnel. Without them, local recovery is over SSH, not an
on-device web UI.

## No VPN in the base image

**Choice:** The image ships no VPN client. Remote access goes through the optional Nixstasis client, which opens outbound
tunnels, so the device needs no inbound port for it.

**Why:** A VPN client in the image needs per-device credentials and a server, and a recovery tunnel that has to be
configured separately is rarely configured at all. Nixstasis already provides enrolled, outbound-only remote access.

**Cost:** A device built without Nixstasis has no remote tunnel. Recovery is over key-only SSH, the serial console, or USB
mass storage. A deployment can still run a VPN client as a privileged container from `config.toml` for outbound
traffic, but the firewall drops new connections that arrive over the tunnel: the provisioned firewall opens ports only on
the `wan` and `lan` interfaces, so a container VPN cannot be used to reach the device itself.

## No IP forwarding

**Choice:** IP forwarding is off in the kernel, and the nftables `forward` chain drops everything.

**Why:** EN 18031 asks for a hard network boundary: LAN devices must not reach the internet. WAN ports for applications
open only when provisioned, and forwarding stays off regardless.

## NIC naming with .link files

**Choice:** systemd `.link` files name the interfaces, not udev rules.

**Why:** `.link` files are systemd's own mechanism and match each board's onboard NIC by a stable platform path. They
rename it to `wan` and the USB Ethernet adapter to `lan`, names the kernel never assigns. Renaming to a kernel name such
as `eth0` fails when a USB adapter registered first and took it, which would leave the onboard WAN port with the LAN
name and its open LAN firewall rule. The match rules are in [NIC Naming](architecture/network-topology.md#nic-naming).

## nftables firewall

**Choice:** nftables with per-interface rules.

**Why:** nftables is the current Linux firewall framework, with simpler rule syntax than iptables, and NixOS supports it
directly through `networking.nftables`.

## Update polling first

**Choice:** Updates come from simple HTTP polling (`os-upgrade.service`). The `os-upgrade.useHawkbit` option is kept as
a seam for a hawkBit client later.

**Why:** Polling needs no fleet server beyond a small HTTP endpoint and is enough for the current scale. hawkBit is not
a working update path; see [Update Polling](architecture/update-rollback.md#update-polling).

## QEMU test target

**Choice:** A `rock64-qemu` NixOS configuration runs the same services as the hardware image on virtio devices, with a
file-based RAUC backend.

**Why:** Hardware testing is slow and needs physical boards. The QEMU target exercises the RAUC lifecycle, firewall
rules, and health checks in VMs that run in CI. Its RAUC backend imitates U-Boot's slot selection with files.

## Key-only authentication

**Choice:** No default passwords, a locked root password, no built-in operator account, key-only SSH, a serial
break-glass path, and optional Nixstasis remote management. See [Authentication](architecture/authentication.md).

**Why:** The image does not host a web management or sign-in stack. Key-only SSH and locked passwords leave nothing to
brute-force, and Nixstasis keeps remote-management credentials outside the image.

## Small system closure

**Choice:** Cut the closure size hard with overlays, disabled features, and trimmed dependencies:

- `crun` built without CRIU, which drops Python from the closure
- no documentation, man pages, fonts, XDG files, `sudo`, or bash completion
- empty `defaultPackages` and `fsPackages`
- bcache, kexec, and LVM support turned off

**Why:** A smaller closure leaves more headroom in the 1 GB root slot and makes every full-image update smaller.

## Two-tier runtime logging

**Choice:** journald keeps host and container logs in memory, and rsyslog drains them through an in-memory queue into
batched appends on `/data/logs`.

**Why:** A fully persistent journal would wear the eMMC with constant small writes. Keeping the journal in memory, capping
its size, and sending Podman logs the same way keeps routine logging cheap, while `/data/logs` still holds lasting
diagnostics written in larger batches.

**Cost:** Durability is bounded, not absolute. A sudden power loss can lose the newest entries still in memory.

## Risks and trade-offs

| Risk                            | Mitigation                                                                                        |
|---------------------------------|---------------------------------------------------------------------------------------------------|
| eMMC wear                       | `/data` uses f2fs; root slots are written only during updates; logs are batched                   |
| U-Boot environment corruption   | The environment is on SPI flash, away from the eMMC; corruption is handled by normal recovery     |
| Root slot too small             | The closure is kept small, and the build checks the squashfs against the slot size                |
| No application health list      | `os-verification` checks the gateway alone unless `/data/config/health-required.json` names units |
| A provisioned application fails | Key-only SSH, the Nixstasis client, and serial recovery live in the image, not in containers      |
| No delta updates                | Full-image updates cost more bandwidth but cannot leave a partial state                           |
| No automatic WAN SSH            | Deliberate: an operator must create the flag file                                                 |
