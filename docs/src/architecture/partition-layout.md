# Partition Layout

The Rock64's 16 GB eMMC holds raw U-Boot at the start, two A/B slot pairs, and a persistent `/data` partition at the
end. The flashable image carries only slot A. On the first boot, `systemd-repart` in the initrd creates slot B and
`/data` in the space that follows, before the real root is mounted, so nothing has to be repartitioned while the system
is running.

`nix/partition-layout.nix` is the single source for partition labels, type GUIDs, offsets, and sizes. Image assembly,
initrd repartitioning, and the squashfs size check all read it. The exact contract is in the
[Partition Layout specification](../specs/partition-layout.md).

## Layout

```text
Offset     Size       Content          Filesystem     Notes
0          16 MB      U-Boot           raw            idbloader @ sector 64, u-boot.itb @ sector 16384
16 MB      128 MB     boot-a           vfat           kernel Image, initrd, DTB, boot.scr
144 MB     1024 MB    rootfs-a         squashfs       zstd, 1 MB blocks; the OverlayFS lower layer
1168 MB    128 MB     boot-b           vfat           created on first boot
1296 MB    1024 MB    rootfs-b         squashfs       created on first boot
2320 MB    remaining  data             f2fs           created on first boot
```

## Slot Pairing

RAUC manages two slot pairs. Each pair is a boot partition and a root filesystem partition that are always written
together:

| Slot | Boot partition | Root filesystem partition |
|------|----------------|---------------------------|
| A    | boot-a (p1)    | rootfs-a (p2)             |
| B    | boot-b (p3)    | rootfs-b (p4)             |

An update writes the new kernel and DTB to the inactive boot partition and the new squashfs to the inactive root
partition. The running pair is never touched, so a failed or interrupted update leaves the device on its working image.

## U-Boot Region

U-Boot fills the first 16 MB of the eMMC as raw data, outside any partition. The RK3328 boot ROM loads it from fixed
sector offsets:

| Component       | Sector offset | Byte offset | Description                    |
|-----------------|---------------|-------------|--------------------------------|
| `idbloader.img` | 64            | 32 KB       | First-stage loader (TPL + SPL) |
| `u-boot.itb`    | 16384         | 8 MB        | U-Boot proper (FIT image)      |

The U-Boot environment, which holds the RAUC boot variables, lives in SPI flash rather than on the eMMC. Linux sees it
as `/dev/mtd0`, at offset `0x140000` with size `0x2000`. Keeping it off the eMMC avoids a raw-write fault on some
budget eMMC modules that can corrupt the boot area; `nix/uboot.nix` builds U-Boot with this setting.

## Data Partition

`/data` survives every update and rollback. Provisioning and the running system keep their state here:

```text
/data/
  .completed_first_boot              First-boot sentinel
  config/                            Operator configuration imported by provisioning
    config.toml                      The accepted source configuration
    admin-signers                    Admin SSH keys trusted to sign configuration re-applies
    ssh-authorized-keys/<user>       Per-user SSH authorized keys
    files/                           Files delivered in a configuration bundle
  ssh/ssh_host_ed25519_key           The device's SSH host key, generated on first boot
  clock/last-known                   Last known time, saved every 15 minutes and at shutdown
  nixstasis/                         Nixstasis identity and remote-access keys, when enabled
  containers/rootless/               Podman storage for rootless containers
  logs/                              Durable host and application logs written by rsyslog
```

[Runtime Boundaries](../runtime-boundaries.md) lists every file that provisioning writes under `/data/config`.

## Logging Tiers

Logging is memory-first to limit eMMC wear, with a bounded durable copy:

```text
Tier 1  journald           Host and container logs in memory (Storage=volatile, capped at 32 MB)
Tier 2  /data/logs         rsyslog drains the journal through an in-memory queue and appends in batches
```

A sudden power loss can drop the newest entries still in memory. The reasoning is in
[Design Decisions](../design-decisions.md#two-tier-runtime-logging).
