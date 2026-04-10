# Update Confirmation Spec

## ADDED Requirements

### Requirement: Local health-check service validates system and container health

A systemd oneshot service (`apollo-confirm.service`) SHALL run after boot (after `multi-user.target`). It SHALL perform
local health checks on system services and manifest-defined containers. It SHALL NOT depend on network connectivity to
an external server.

#### Scenario: System services are validated

- **WHEN** `apollo-confirm.service` runs after boot
- **THEN** it checks that Cockpit, dnsmasq (DHCP), chronyd (NTP), and network interfaces (eth0 with WAN address, eth1 at
  172.20.30.1) are healthy

#### Scenario: Service runs only on uncommitted slots

- **WHEN** the device boots on a slot that has already been marked good
- **THEN** `apollo-confirm.service` detects this via `rauc status` and exits immediately without performing health
  checks

### Requirement: Manifest-driven container health checks

If `/persist/apollo/health-manifest.yaml` exists, the confirmation service SHALL read it and verify that each listed
container is in "running" state via podman. The service SHALL wait up to 5 minutes for all containers to reach running
state, checking every 10 seconds.

#### Scenario: All manifest containers are running

- **WHEN** all containers listed in the health manifest are in "running" state
- **THEN** the service proceeds to the sustained health check phase

#### Scenario: Container fails to start within timeout

- **WHEN** a container listed in the manifest does not reach "running" state within 5 minutes
- **THEN** the service exits with a non-zero status and the slot remains uncommitted

#### Scenario: No manifest exists

- **WHEN** `/persist/apollo/health-manifest.yaml` does not exist (unprovisioned or development image)
- **THEN** the service skips container health checks and proceeds directly to system health checks and the sustained
  check phase

### Requirement: Sustained health check catches restart loops

After all system and container checks pass, the confirmation service SHALL continue checking every 5 seconds for 60
seconds. If any container restarts (restart count increments) or stops during this period, the check SHALL fail.

#### Scenario: All services stable for 60 seconds

- **WHEN** all checks pass continuously for 60 seconds
- **THEN** the service calls `rauc status mark-good` to commit the slot

#### Scenario: Container restart loop detected

- **WHEN** a container restarts during the 60-second sustained check period
- **THEN** the service exits with a non-zero status and the slot remains uncommitted

### Requirement: Successful confirmation commits the slot

After all health checks pass and the 60-second sustained period completes, the service SHALL call `rauc status
mark-good` to commit the current slot, preventing rollback.

#### Scenario: Slot is committed after successful checks

- **WHEN** all system and container health checks pass for the sustained period
- **THEN** the service runs `rauc status mark-good` and the active slot's boot attempt counter is reset to its maximum

### Requirement: Failed confirmation leaves slot uncommitted

If any health check fails, the service SHALL NOT call `rauc status mark-good`. The slot SHALL remain uncommitted,
meaning the boot attempt counter continues to decrement on subsequent reboots, eventually triggering rollback.

#### Scenario: Failed checks lead to rollback

- **WHEN** the confirmation service fails on every boot attempt and the boot counter is exhausted
- **THEN** U-Boot rolls back to the previous slot on the next reboot

### Requirement: Health manifest is provided by provisioning

The health manifest file (`/persist/apollo/health-manifest.yaml`) SHALL be placed on the /persist partition by the
device provisioning process (initial flash or remote provisioning service). The image SHALL NOT include a default
manifest.

#### Scenario: Manifest defines required containers

- **WHEN** the health manifest is read by the confirmation service
- **THEN** it contains a list of container names that must be in "running" state for the slot to be committed
