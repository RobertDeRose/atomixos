# Update Confirmation

> Source: `openspec/changes/rock64-ab-image/specs/update-confirmation/spec.md`

## Requirements

### ADDED: Local health-check service

The `os-verification.service` runs after `multi-user.target` on every boot (except the first). It validates that the
system is healthy before committing the RAUC slot. No external network dependency is required for the check itself.

#### Scenario: Health check runs on update boot

- Given `/persist/.completed_first_boot` exists (not first boot)
- When the device reaches `multi-user.target`
- Then `os-verification.service` starts
- And it checks service health and container status

### ADDED: Manifest-driven container checks

The health manifest at `/persist/config/health-manifest.yaml` lists container names that must be running. The service
waits up to 5 minutes for all listed containers to reach `running` state via `podman inspect`.

#### Scenario: Container check passes

- Given the health manifest lists `cockpit-ws` and `traefik`
- And both containers start within 5 minutes
- Then the container health check passes

#### Scenario: No manifest file

- Given `/persist/config/health-manifest.yaml` does not exist
- Then the container health check is skipped
- And only service checks are performed

### ADDED: Sustained health check

After initial checks pass, the service monitors for 60 seconds (checking every 5 seconds) to catch restart loops and
transient failures.

#### Scenario: Restart loop detected

- Given `dnsmasq.service` passes the initial check
- But it crashes and restarts during the 60-second sustain window
- Then the sustained health check fails
- And the slot is not committed

### ADDED: Successful confirmation commits slot

When all checks pass (services, containers, sustained), the service runs `rauc status mark-good` to commit the current
slot. This resets the boot counter and prevents further rollback.

#### Scenario: Slot committed on success

- Given all health checks pass for 60 seconds
- When `rauc status mark-good` is called
- Then the booted slot is committed as "good"
- And `BOOT_x_LEFT` is reset to the maximum value

### ADDED: Failed confirmation leaves slot uncommitted

If any check fails, the service exits non-zero. The slot remains uncommitted, and the boot counter continues to
decrement on each subsequent boot until rollback occurs.

#### Scenario: Gradual rollback on failure

- Given health checks fail on every boot of slot B
- Then each boot decrements `BOOT_B_LEFT`
- And after 3 boots, U-Boot rolls back to slot A

### ADDED: Health manifest provided by provisioning

The health manifest is not shipped in the image. It is written to `/persist/config/health-manifest.yaml` during [eMMC
provisioning](../provisioning/emmc-provisioning.md). This allows different devices to have different container
configurations.
