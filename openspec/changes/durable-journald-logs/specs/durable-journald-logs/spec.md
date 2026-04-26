# Volatile Journald Boundary Spec

## ADDED Requirements

### Requirement: Host journald remains volatile and bounded

The system SHALL configure host journald to keep general runtime logs in
volatile storage rather than persisting the full journal onto `/data`.
The system SHALL set an explicit `RuntimeMaxUse` cap of `64 MiB`.

#### Scenario: General host logs do not survive reboot

- **WHEN** the device writes a non-critical host journal entry and then reboots
- **THEN** that entry is not guaranteed to remain available after the reboot

#### Scenario: Runtime journal stays within the configured cap

- **WHEN** runtime journal usage reaches the configured storage cap
- **THEN** journald rotates or removes older runtime journal data before
  exceeding `64 MiB`

### Requirement: Container logs follow the same volatile-first boundary

The system SHALL configure Podman to use the `journald` log driver so routine
container stdout and stderr are recorded through journald instead of file-based
container logs.

#### Scenario: Container logs are sent to journald

- **WHEN** a container writes to stdout or stderr during normal operation
- **THEN** that log traffic is emitted through journald and follows the same
  volatile runtime retention policy as other non-Tier 0 logs
