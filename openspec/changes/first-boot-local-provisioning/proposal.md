# Proposal

## Why

The current image and first-boot flow still reflect a development-oriented model: first boot can commit the slot before
production access credentials and application stack configuration exist, and provisioning is split across ad hoc files
manually copied into `/data/config/` after boot. This makes fresh installs, reprovisioning, and future Nixstasis
integration less coherent than they need to be.

This change defines a single local first-boot provisioning contract based on `config.toml`, so a freshly flashed or
reprovisioned device can acquire its admin credentials and Quadlet-managed application stack from a well-defined source
order without baking per-device secrets into the base image.

## What Changes

- Add a first-boot local provisioning flow that discovers a single `config.toml` seed from `/boot`, then USB mass
  storage, then a local bootstrap web console
- Define a bounded `config.toml` schema for provisioning admin SSH keys, explicit health
  requirements, and structured Quadlet unit definitions
- Persist the imported provisioning state under `/data/config/`, including the source `config.toml` and rendered
  Quadlet units
- Distinguish initial fresh-flash provisioning from reprovisioning using `boot-b absent` as the discriminator so
  `/boot/config.toml` is a day-0 seed source only
- Redefine the first-boot path so production slot confirmation happens after provisioning import and validation rather
  than unconditionally after Linux boots
- Introduce a constrained local bootstrap web console that can upload an existing `config.toml` or generate one from a
  simple form when no seed file is found

## Capabilities

### New Capabilities

- `first-boot-local-provisioning`: Source discovery, import, validation, reprovisioning behavior, and bootstrap UI for
  local provisioning from `config.toml`

### Modified Capabilities

- `partition-layout`: Clarify that provisioned operator configuration persists under `/data/config/`, and that
  reprovisioning is driven by wiping `/data` while preserving the slot layout
- `update-confirmation`: Change the first-boot contract so production slot confirmation depends on successful local
  provisioning and explicit health requirements rather than unconditional first-boot commit

## Impact

- **Affected code**: `first-boot.service`, `scripts/first-boot.sh`, provisioning tasks/scripts, bootstrap web
  management path, and the runtime consumers of `/data/config/`
- **Affected storage layout**: `/data/config/` becomes the canonical home for imported `config.toml` and rendered
  Quadlet files
- **Affected operational workflows**: fresh flash, reprovisioning, bench setup, and future Nixstasis alignment
- **Security**: preserves the current no-secrets-in-image stance while making first-boot bootstrap behavior an explicit
  part of the device trust model
