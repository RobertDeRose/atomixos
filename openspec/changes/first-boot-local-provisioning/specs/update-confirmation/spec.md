## MODIFIED Requirements

### Requirement: Manifest-driven container health checks

If `/data/config/config.toml` exists, the confirmation service SHALL treat the explicit health requirements imported
from that provisioning artifact as the source of truth for required application units. The confirmation service SHALL
verify that each required container or service reaches its expected healthy running state before the slot can be
committed. If no valid provisioning state exists on a production first boot, the slot SHALL remain uncommitted.

#### Scenario: Provisioned health requirements define required units

- **WHEN** the confirmation service runs on a provisioned device with a valid imported `config.toml`
- **THEN** it reads the explicit health requirements derived from that provisioning state to determine which units must
  be healthy before committing the slot

#### Scenario: Missing provisioning state blocks production first-boot commit

- **WHEN** the device is in the production first-boot path and no valid local provisioning state has been imported
- **THEN** the slot remains uncommitted rather than being marked good unconditionally
