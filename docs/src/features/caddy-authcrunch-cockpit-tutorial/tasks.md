# Tasks: caddy-authcrunch-cockpit-tutorial

## T000 -- Feature spec review

- [x] Review `design.md` for completeness and accuracy
- [x] Confirm bearer token auth approach with cockpit authentication.md
- [ ] Confirm AuthCrunch Caddyfile syntax against current docs
- [x] Resolve open design questions (bearer auth, custom image, `.build` support)

## T00A -- Add Quadlet `.build` support

This is a new infrastructure prerequisite discovered during spec review.
The cockpit-ws container requires a custom image (adds Python 3 to Fedora
minimal base). Quadlet supports `.build` units; config.toml needs to support
them the same way it supports `.network` and `.volume`.

- [ ] Add `buildDefinition` to `schemas/config.schema.json` (`$defs`)
- [ ] Add optional `build` top-level key to schema
- [ ] Implement `render_builds()` in `first-boot-provision.py`
  (follow `render_networks()`/`render_volumes()` pattern)
- [ ] Register `.build` units in `quadlet-runtime.json` (mode: rootful)
- [ ] Update `sync-quadlet` to handle `.build` files
- [ ] Update NixOS test to cover `.build` rendering and sync
- [ ] Validate that `.build` Quadlet units trigger image build on first
  `systemctl daemon-reload` + container start

## T00B -- Write cockpit-ws Containerfile

- [ ] Create `files/cockpit/Containerfile` based on `quay.io/cockpit/ws:latest`
- [ ] Add `python3` via `dnf install --setopt=install_weak_deps=False`
- [ ] Verify the built image has Python 3 available
- [ ] Keep the Containerfile minimal (single RUN layer)

## T001 -- Write the bearer auth script

- [ ] Create `cockpit-bearer-auth` Python script using only stdlib
- [ ] Implement cockpit authorize protocol (read challenge, send response)
- [ ] Implement HS256 JWT validation against `JWT_SHARED_KEY` env var
- [ ] Extract user email and roles from JWT claims
- [ ] Map `authp/admin` to `admin` user, `authp/user` to `viewer` user
- [ ] Exec `cockpit-bridge` as the mapped user
- [ ] Test the script standalone with a crafted JWT

## T002 -- Write the Caddyfile

- [ ] Configure Entra OIDC identity provider with placeholder values
- [ ] Configure authentication portal with JWT signing
- [ ] Configure user transforms for group-to-role mapping
- [ ] Configure authorization policy for management routes
- [ ] Configure reverse proxy to cockpit-ws at localhost:9090
- [ ] Configure `/auth*` route for authentication portal
- [ ] Configure `/cockpit/*` route with authorization policy
- [ ] Validate Caddyfile syntax against AuthCrunch docs

## T003 -- Write cockpit.conf

- [ ] Configure `[WebService]` section for reverse proxy mode
- [ ] Configure `[bearer]` section pointing to the auth script
- [ ] Configure `Origins` with placeholder domain
- [ ] Configure `UrlRoot` for `/cockpit/` path prefix
- [ ] Set appropriate idle timeout

## T004 -- Write config.toml

- [ ] Define `version = 1`
- [ ] Define `admin.ssh_keys` with placeholder public key
- [ ] Define `firewall.inbound.wan` with ports 80 and 443 open (TCP)
- [ ] Define `health.required` listing `caddy-gateway.service` and
  `cockpit-ws.service`
- [ ] Define `caddy-gateway` container (rootful, AuthCrunch image)
- [ ] Define `cockpit-ws` container (rootful, custom build image ref)
- [ ] Define `cockpit-ws` build section referencing Containerfile
- [ ] Define `management` network with subnet
- [ ] Define `caddy-data` volume with local driver
- [ ] Configure `Environment` keys with placeholder values
  (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`,
  `JWT_SHARED_KEY`)
- [ ] Configure `Volume` mounts for Caddyfile, cockpit.conf, bearer auth
  script using `${FILES_DIR}` tokens
- [ ] Configure Podman socket mount for cockpit-ws container
- [ ] Verify all placeholder values are obvious (`<AZURE_TENANT_ID>`, etc.)

## T005 -- Validate config.toml

- [ ] Run `first-boot-provision validate` on the tutorial config
- [ ] Fix any schema or semantic validation errors
- [ ] Verify all rendered Quadlet files have correct content

## T006 -- Write NixOS VM test

- [ ] Create test that imports the tutorial config bundle
- [ ] Assert rendered `caddy-gateway.container` exists and has correct content
- [ ] Assert rendered `cockpit-ws.container` exists and has correct content
- [ ] Assert rendered `cockpit-ws.build` exists and has correct content
- [ ] Assert rendered `management.network` exists and has correct content
- [ ] Assert rendered `caddy-data.volume` exists and has correct content
- [ ] Assert bundle files are copied to `/data/config/files/`
- [ ] Assert `quadlet-runtime.json` includes all expected units
  (containers, network, volume, build)

## T007 -- Write tutorial documentation page

- [ ] Write introduction explaining what the tutorial builds
- [ ] Document Azure App Registration prerequisites step by step
- [ ] Document the authentication flow with a diagram
- [ ] Present the complete config.toml with annotations
- [ ] Present the Caddyfile with annotations
- [ ] Present cockpit.conf with annotations
- [ ] Present the bearer auth script with annotations
- [ ] Present the Containerfile with annotations
- [ ] Document the bundle directory structure
- [ ] Document how to build and apply the bundle
- [ ] Document role mapping (admin group -> sudoless admin,
  user group -> generic user)
- [ ] Document cockpit-podman requirements and NixOS module sketch
- [ ] Document security considerations and production hardening notes
- [ ] Add placeholders table listing all values that must be substituted

## T008 -- Update docs/src/SUMMARY.md

- [ ] Create a Tutorials section in SUMMARY.md (does not exist yet)
- [ ] Add tutorial entry under the new Tutorials section

## T009 -- Update planned-features.md

- [ ] Update `caddy-authcrunch-cockpit-tutorial` status to `in-progress`

## T999 -- Feature close-out

- [ ] All tasks T00A-T009 completed
- [ ] Tutorial config passes `first-boot-provision validate`
- [ ] NixOS VM test passes
- [ ] Documentation builds without errors
- [ ] design.md and delivered behavior agree
- [ ] No unresolved design questions remain
