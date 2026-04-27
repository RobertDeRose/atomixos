## MODIFIED Requirements

### Requirement: /data partition survives updates

The /data partition SHALL NOT be modified by RAUC updates or rootfs slot switches. It SHALL persist across all
updates and rollbacks. Provisioned operator configuration SHALL be stored under `/data/config/`, and wiping `/data`
SHALL reset the device to an unprovisioned state without removing the existing slot layout.

#### Scenario: Data survives an A/B slot switch

- **WHEN** a file is written to /data, then an update switches the active slot from A to B
- **THEN** the file is still present and unmodified on /data after the slot switch

#### Scenario: Wiping /data preserves slot layout but resets provisioning state

- **WHEN** `/data` is reformatted on a device whose `boot-b` and `rootfs-b` partitions already exist
- **THEN** the device retains its slot layout but re-enters the unprovisioned first-boot provisioning flow on the next
  boot
