# Partition Layout

The Rock64's 16 GB eMMC uses a fixed A/B partition layout with raw U-Boot at the beginning and a persistent data
partition at the end. The flash image carries slot A only; initrd `systemd-repart` creates slot B and `/data` on first
boot.

## Layout

```text
Offset     Size       Content          Filesystem     Notes
0          16 MB      U-Boot           raw            idbloader @ sector 64, u-boot.itb @ sector 16384
16 MB      128 MB     boot-a           vfat           kernel Image, initrd, DTB, boot.scr
144 MB     1024 MB    rootfs-a         squashfs       zstd compressed, 1 MB blocks; used as OverlayFS lower layer
1168 MB    128 MB     boot-b           vfat           created on first boot by initrd systemd-repart
1296 MB    1024 MB    rootfs-b         --             created on first boot by initrd systemd-repart
2320 MB    remaining  data             f2fs           created on first boot by initrd systemd-repart
```

## Slot Pairing

RAUC manages two slot pairs. Each pair contains a boot partition and a rootfs partition that are always written together
atomically:

| Slot | Boot Partition | Rootfs Partition |
|------|----------------|------------------|
| A    | boot-a (p1)    | rootfs-a (p2)    |
| B    | boot-b (p3)    | rootfs-b (p4)    |

An update writes the new kernel/DTB to the inactive boot partition and the new squashfs to the inactive rootfs
partition. The active slot pair is never modified during an update.

## U-Boot Region

U-Boot occupies the first 16 MB of the eMMC as raw data (no partition). The RK3328 boot ROM loads the initial bootloader
from fixed sector offsets:

| Component       | Sector Offset | Byte Offset | Description                    |
|-----------------|---------------|-------------|--------------------------------|
| `idbloader.img` | 64            | 32 KB       | First-stage loader (TPL + SPL) |
| `u-boot.itb`    | 16384         | 8 MB        | U-Boot proper (FIT image)      |

U-Boot environment is stored redundantly at offsets `0x3F8000` and `0x3FC000` (both 16 KB), providing power-loss
resilience for the boot-count variables.

## Data Partition

The flashable image leaves the space after `rootfs-a` unallocated. On first boot,
initrd `systemd-repart` creates `boot-b`, `rootfs-b`, and `/data` there before the
live system is mounted. This avoids repartitioning from the switched-root system
while still preserving the inactive slot and `/data` across all updates and
rollbacks.

Contents created during provisioning:

```text
/data/
  .completed_first_boot              First-boot sentinel
  config/
    admin-password-hash              SHA-512 password hash (per-device)
    ssh-authorized-keys/admin        Operator's SSH public key
    nixstasis/                       Planned enrollment key and agent state
    openvpn/client.conf              OpenVPN recovery tunnel config (optional)
  containers/                        Reserved for future application workloads
  logs/                              Persistent log storage
```
