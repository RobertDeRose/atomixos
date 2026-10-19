# Update Confirmation

> Source: `docs/src/features/rock64-ab-image/design.md#update-confirmation`

## Requirements

### ADDED: Local health-check service

The `os-verification.service` runs after `multi-user.target` on every boot (except the first). It validates that the
system is healthy before committing the RAUC slot. No external network dependency is required for the check itself.

#### Scenario: Health check runs on update boot

- Given `/data/.completed_first_boot` exists (not first boot)
- When the device reaches `multi-user.target`
- Then `os-verification.service` starts
- And it checks service health

### ADDED: Sustained health check

After initial checks pass, the service monitors for 60 seconds (checking every 5 seconds) to catch restart loops,
transient service failures, network regressions, and required provisioned-unit failures.

#### Scenario: Restart loop detected

- Given `dnsmasq.service` passes the initial check
- But it crashes and restarts during the 60-second sustain window
- Then the sustained health check fails
- And the slot is not committed

#### Scenario: Network or required unit regression detected

- Given wan, lan, and provisioned required units pass the initial check
- But one check fails during the 60-second sustain window
- Then the sustained health check fails
- And the slot is not committed

### ADDED: Successful confirmation commits slot

When all checks pass (services and sustained), the service runs `rauc status mark-good` to commit the current
slot. This resets the boot counter and prevents further rollback. It does this on every healthy boot, including when
RAUC already reports the slot as good: RAUC reports a slot good while it has boot tries left, and U-Boot uses one try
on every boot, so skipping the call would let three plain reboots exhaust the slot.

#### Scenario: Slot committed on success

- Given all health checks pass for 60 seconds
- When `rauc status mark-good` is called
- Then the booted slot is committed as "good"
- And `BOOT_x_LEFT` is reset to the maximum value

#### Scenario: Healthy boot of a good slot restores its tries

- Given the booted slot is already good and U-Boot decremented `BOOT_x_LEFT` for this boot
- When all health checks pass
- Then `rauc status mark-good` is called
- And `BOOT_x_LEFT` is reset to the maximum value

### ADDED: WAN check separates regressions from outages

The WAN check fails when `wan` is missing or networkd reports its configuration as failed, because committing such an
image would strand a device that receives updates over WAN. A missing WAN address only warns: it usually means a cable,
ISP, or DHCP outage, which must not roll back a working image.

#### Scenario: WAN outage during an update boot

- Given `wan` exists and is configured but has no address
- When the health checks run
- Then the service logs a warning
- And the slot is committed if every other check passes

#### Scenario: WAN interface missing after an update

- Given the new image no longer provides `wan`
- When the health checks run
- Then the WAN check fails
- And the slot is not committed

### ADDED: Failed confirmation leaves slot uncommitted

If any check fails, the service exits non-zero. The slot remains uncommitted, and the boot counter continues to
decrement on each subsequent boot until rollback occurs.

#### Scenario: Gradual rollback on failure

- Given health checks fail on every boot of slot B
- Then each boot decrements `BOOT_B_LEFT`
- And after 3 boots, U-Boot rolls back to slot A
