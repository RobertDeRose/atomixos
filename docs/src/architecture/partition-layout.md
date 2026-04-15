# Partition Layout

The Rock64's 16 GB eMMC uses a fixed A/B partition layout with raw U-Boot at the beginning and a persistent data
partition at the end.

## Layout

```text
Offset     Size       Content          Filesystem     Notes
0          16 MB      U-Boot           raw            idbloader @ sector 64, u-boot.itb @ sector 16384
16 MB      128 MB     boot-a           vfat           kernel Image, initrd, DTB, boot.scr
144 MB     128 MB     boot-b           vfat           (populated by RAUC on update)
272 MB     1024 MB    rootfs-a         squashfs       zstd compressed, 1 MB blocks
1296 MB    1024 MB    rootfs-b         squashfs       (populated by RAUC on update)
2320 MB    ~13.3 GB   persist          f2fs           containers, config, state, logs
```

## Slot Pairing

RAUC manages two slot pairs. Each pair contains a boot partition and a rootfs partition that are always written together
atomically:

| Slot | Boot Partition | Rootfs Partition |
|------|----------------|------------------|
| A    | boot-a (p1)    | rootfs-a (p3)    |
| B    | boot-b (p2)    | rootfs-b (p4)    |

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

## Persist Partition

The `/persist` partition is **not** included in the flashable image. On first boot, a custom `create-persist.service`
fixes the GPT backup header (stranded at the old image boundary after dd'ing a smaller image onto the larger eMMC), then
invokes `systemd-repart` with an explicit device path to create and format the partition as f2fs using all remaining
eMMC space. This partition survives all updates and rollbacks.

Contents created during provisioning:

```text
/persist/
  .completed_first_boot              First-boot sentinel
  config/
    admin-password-hash              SHA-512 password hash (per-device)
    ssh-authorized-keys/admin        Operator's SSH public key
    traefik/                         Traefik static/dynamic config, TLS certs
    health-manifest.yaml             Container health entries for os-verification
    openvpn/client.conf              OpenVPN recovery tunnel config (optional)
  containers/                        Podman container storage
  logs/                              Persistent log storage
```
