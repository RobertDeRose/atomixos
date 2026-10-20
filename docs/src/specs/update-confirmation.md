# Update Confirmation

Acceptance contract for the local health check that commits a slot. The exact checks are listed under
[os-verification.sh](../code-reference/scripts.md#os-verificationsh).

## Requirements

### Local health-check service

`os-verification.service` runs on every boot except the first and checks that the system is healthy before committing
the RAUC slot. The check needs no external server.

#### Scenario: Health check runs on an update boot

- Given `/data/.completed_first_boot` exists
- When the device reaches `multi-user.target`
- Then `os-verification.service` starts
- And it checks service health

### Sustained health check

After the first checks pass, the service repeats them every 5 seconds for 60 seconds to catch restart loops, transient
service failures, network regressions, and failed required units.

#### Scenario: Restart loop detected

- Given `dnsmasq.service` passes the first check
- But it crashes and restarts during the 60-second window
- Then the sustained check fails
- And the slot is not committed

#### Scenario: Network or required-unit regression detected

- Given `wan`, `lan`, and the provisioned required units pass the first check
- But one of them fails during the 60-second window
- Then the sustained check fails
- And the slot is not committed

### Successful confirmation commits the slot

When every check passes, the service runs `rauc status mark-good` for the booted slot, which resets its boot counter and
stops rollback. It does this on every healthy boot, even when RAUC already reports the slot as good: RAUC reports a slot
good while it has tries left, and U-Boot uses one try on every boot, so skipping the call would let three plain
reboots exhaust the slot.

#### Scenario: Slot committed on success

- Given all health checks pass for 60 seconds
- When `rauc status mark-good` runs
- Then the booted slot is committed as good
- And `BOOT_x_LEFT` is reset to 3

#### Scenario: Healthy boot of a good slot restores its tries

- Given the booted slot is already good and U-Boot decremented `BOOT_x_LEFT` for this boot
- When all health checks pass
- Then `rauc status mark-good` runs
- And `BOOT_x_LEFT` is reset to 3

### WAN check separates regressions from outages

The WAN check fails when `wan` is missing or networkd reports its configuration as failed, because committing that image
would strand a device that is updated over WAN. A missing WAN address only warns: it usually means a cable, ISP, or DHCP
outage, which must not roll back a working image.

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

### Failed confirmation leaves the slot uncommitted

If any check fails, the service exits non-zero. The slot stays uncommitted, and its counter keeps decrementing on each
boot until rollback.

#### Scenario: Gradual rollback on failure

- Given the health checks fail on every boot of slot B
- Then each boot decrements `BOOT_B_LEFT`
- And after three boots U-Boot rolls back to slot A
