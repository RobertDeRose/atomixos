# Buffered Journald Boundary Spec

## ADDED Requirements

### Requirement: Host journald is tmpfs-first during runtime

The system SHALL configure host journald to keep general runtime logs in
volatile storage during normal runtime so routine host logging remains
memory-first rather than continuously writing to persistent media.

#### Scenario: Runtime host logs stay memory-first

- **WHEN** the device writes a non-critical host journal entry during normal
  runtime
- **THEN** that entry is written into the volatile runtime journal rather than
  directly to persistent journal storage on `/data`

### Requirement: Runtime journal usage is explicitly bounded

The system SHALL apply an explicit runtime journal size cap so memory-first
logging does not grow without bound.

#### Scenario: Runtime journal stays within the configured cap

- **WHEN** runtime journal usage reaches the configured storage cap
- **THEN** journald rotates or removes older runtime journal data before
  exceeding that cap

### Requirement: General logs are written to `/data/logs` in large sequential batches

The system SHALL use a RAM-queued batching layer behind volatile journald so
general host log data is appended to persistent storage under `/data/logs` in
large, infrequent, sequential writes rather than in many small direct writes.

#### Scenario: Buffered host logs are appended during runtime buffering flushes

- **WHEN** the device continues normal runtime logging and the buffering layer
  reaches its configured write threshold or flush interval
- **THEN** buffered general host journal data is appended to persistent storage
  under `/data/logs` in a large sequential write

### Requirement: Buffered general logs are flushed to `/data/logs` on orderly shutdown

The system SHALL flush the current buffered general log state to persistent
storage under `/data/logs` during orderly shutdown so the latest clean shutdown
retains the most recent buffered host diagnostics.

#### Scenario: Orderly shutdown persists buffered host logs

- **WHEN** the device performs an orderly reboot or poweroff
- **THEN** the buffered general log queue is flushed to persistent storage
  under `/data/logs` before shutdown completes

### Requirement: Container logs follow the same buffered journald boundary

The system SHALL configure Podman to use the `journald` log driver so routine
container stdout and stderr are recorded through journald instead of file-based
container logs, and SHALL keep those logs inside the same tmpfs-first,
RAM-queued, batched-append, and shutdown-flushed pipeline as other non-Tier 0
logs.

#### Scenario: Container logs are sent to journald

- **WHEN** a container writes to stdout or stderr during normal operation
- **THEN** that log traffic is emitted through journald and follows the same
  buffered runtime retention policy and batched `/data/logs` append path as
  other non-Tier 0 logs
