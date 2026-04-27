## 1. Provisioning Contract

- [x] 1.1 Define the supported `config.toml` schema for `admin`, `health`, and `quadlet.<type>.<name>.<section>` data
- [x] 1.2 Define the TOML-to-Quadlet rendering rules, including how arrays map to repeated Quadlet directives
- [x] 1.3 Define the canonical persisted layout under `/data/config/`, including the imported `config.toml` and rendered
  Quadlet unit files

## 2. First-Boot Source Discovery

- [ ] 2.1 Add initrd fresh-flash detection that checks whether `boot-b` is absent before repartitioning and persists a
  marker for the switched-root provisioning path
- [ ] 2.2 Implement provisioning source search in fresh-flash order: `/boot/config.toml`, then USB mass storage, then
  bootstrap web console
- [ ] 2.3 Implement reprovision source search in reset order: USB mass storage, then bootstrap web console

## 3. Import And Validation

- [x] 3.1 Import a discovered `config.toml` into durable state under `/data/config/`
- [x] 3.2 Render structured Quadlet definitions from `config.toml` into canonical files under `/data/config/quadlet/`
- [x] 3.3 Validate the minimum provisioning contract: admin password hash, at least one admin SSH key, at least one
  Quadlet-defined service, and explicit health requirements

## 4. First-Boot Commit Behavior

- [ ] 4.1 Change the production first-boot path so slot confirmation happens only after successful provisioning import
  and validation
- [ ] 4.2 Update the confirmation/health path to consume explicit health requirements from imported provisioning state
- [ ] 4.3 Preserve a development-safe fallback strategy for existing development-mode workflows while the new production
  gate is introduced

## 5. Bootstrap Web Console

- [ ] 5.1 Add a constrained local bootstrap web console for unprovisioned devices when no seed file is found
- [ ] 5.2 Support uploading an existing `config.toml` through the bootstrap console
- [ ] 5.3 Support generating a valid `config.toml` from a basic form and applying it locally

## 6. Reprovisioning And Documentation

- [ ] 6.1 Define and implement reprovisioning behavior so wiping `/data` returns the device to provisioning mode without
  replaying `/boot/config.toml`
- [x] 6.2 Update OpenSpec/docs to describe `/boot` initial seeding, USB reprovisioning, bootstrap UI fallback, and the
  `/data/config/` persistence boundary
- [ ] 6.3 Add focused validation coverage for fresh flash, reprovisioning, seed-source precedence, and TOML-to-Quadlet
  rendering
