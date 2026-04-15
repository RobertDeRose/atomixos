# Update & Rollback Flow

AtomixOS uses RAUC for A/B slot management combined with U-Boot boot-count logic and a hardware watchdog to guarantee
automatic recovery from failed updates.

## Normal Update Cycle

```text
1. os-upgrade.service polls update server for new .raucb bundle
2. rauc install writes boot + rootfs to the INACTIVE slot pair
3. RAUC sets U-Boot env: BOOT_ORDER=B A, BOOT_B_LEFT=3
4. Device reboots into new slot
5. U-Boot decrements BOOT_B_LEFT on each boot attempt
6. os-verification.service runs health checks:
   - eth0 has WAN address, eth1 has the configured LAN gateway IP
   - dnsmasq, chronyd running
   - containers from /persist/config/health-manifest.yaml are healthy
   - sustained 60s stability check
7a. All pass  -> rauc status mark-good (slot committed)
7b. Any fail  -> exit non-zero, boot-count continues to decrement
8. After 3 failed boots -> U-Boot falls back to previous good slot
```

## Boot-Count Mechanism

U-Boot maintains three environment variables for slot selection:

| Variable      | Purpose                            | Example |
|---------------|------------------------------------|---------|
| `BOOT_ORDER`  | Slot priority (first = preferred)  | `"A B"` |
| `BOOT_A_LEFT` | Remaining boot attempts for slot A | `3`     |
| `BOOT_B_LEFT` | Remaining boot attempts for slot B | `3`     |

On each boot, the `boot.scr` script:

1. Reads `BOOT_ORDER` to determine which slot to try first
2. Checks if the preferred slot has attempts remaining (`BOOT_x_LEFT > 0`)
3. Decrements the counter and saves the environment (`saveenv`)
4. Loads kernel, initrd, and DTB from that slot's boot partition
5. Sets `root=PARTLABEL=rootfs-a` (or `rootfs-b`) and boots

If a slot's counter reaches 0, it is skipped and the next slot in `BOOT_ORDER` is tried. This ensures automatic rollback
after 3 consecutive boot failures.

## Health Check Details

The `os-verification.service` performs these checks before committing a slot:

1. **Service checks**: dnsmasq and chronyd must be active
2. **Network checks**: eth0 must have a WAN IP; eth1 must have the expected LAN gateway IP
3. **Container checks**: all containers listed in `/persist/config/health-manifest.yaml` must reach `running` state
   (5-minute timeout)
4. **Sustained check**: all above conditions must hold for 60 seconds (checked every 5 seconds) to catch restart loops

Only after all checks pass does the service run `rauc status mark-good`, which resets the boot counter and commits the
slot.

## First Boot Exception

On initial device provisioning, no containers or health manifest exist yet. The `first-boot.service` handles this by
unconditionally marking the slot as good and writing a sentinel file (`/persist/.completed_first_boot`). After this, all
subsequent boots use the full health-check path.

## Watchdog Integration

The RK3328 hardware watchdog (`dw_wdt`) is configured with:

- **Runtime watchdog**: 30 seconds -- if systemd hangs, the device reboots
- **Reboot watchdog**: 10 minutes -- if a reboot hangs, the watchdog forces a hard reset

Both scenarios feed into the boot-count rollback path: the reboot increments the failure count, and after 3 failures the
previous slot is restored.

## Update Polling

The `os-upgrade.service` runs on a systemd timer:

- First check: 5 minutes after boot
- Subsequent checks: every 1 hour (configurable)
- Random delay: up to 10 minutes (prevents thundering herd across fleet)

The service queries the update server with the device's MAC address and current version. If a newer bundle is available,
it downloads to `/persist`, installs via `rauc install`, and reboots. The architecture is designed to be swappable with
hawkBit for server-push updates.
