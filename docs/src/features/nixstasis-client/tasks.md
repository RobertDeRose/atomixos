# Tasks: nixstasis-client

## Feature Spec And Setup

- [x] T000 Create feature branch and worktree from `dev`
- [x] T001 Draft `design.md` from `docs/src/planned-features.md`
- [x] T002 Review design against existing AtomixOS docs and Nixstasis client source
- [x] T003 Resolve FRP validation scope before implementation

## Upstream Nixstasis Flake Packaging

- [x] T010 Add `flake.nix` and lockfile support to the Nixstasis repository
- [x] T011 Expose a Nixstasis client package for the AtomixOS target architecture
- [x] T012 Ensure the Nixstasis package includes `nixstasis`, `frpc`, `frpc.toml`, and required runtime assets
- [x] T013 Add upstream package checks for the client binary and installed runtime assets
- [x] T014 Add the Nixstasis repository as an AtomixOS flake input
- [x] T015 Add a closure-size check or build output note for the added client and FRP assets (aarch64-linux client output: 9.3M; closure: 77.0M)

## AtomixOS Module And Configuration

- [x] T020 Add an AtomixOS NixOS module for `atomixos.nixstasis.*` options
- [x] T021 Render `/etc/nixstasis/config.yaml` from NixOS options
- [x] T022 Configure persistent identity and authorized-keys paths under `/data/nixstasis`
- [x] T023 Pass `NIXSTASIS_*` environment overrides to match AtomixOS paths
- [x] T024 Add module assertions for required API URL and safe path configuration
- [x] T025 Add Nix/module tests or VM assertions for rendered config and unit environment

## Systemd Integration

- [x] T030 Add `nixstasis-registration.service` using `nixstasis register`
- [x] T031 Add `nixstasis-poll.service` using `nixstasis poll`
- [x] T032 Ensure units order after network availability without blocking boot
- [x] T033 Add restart/backoff behavior for WAN or server outages
- [x] T034 Add hardening appropriate for a base-system management client
- [x] T035 Ensure `systemd-run`, `systemctl`, and FRP paths are available for remote-access sessions

## SSH And Runtime Boundary

- [x] T040 Add Nixstasis authorized-keys path to OpenSSH without replacing provisioned operator keys
- [x] T041 Keep Nixstasis remote-access state separate from `/data/config/ssh-authorized-keys/%u`
- [x] T042 Render deny-by-default runtime command allowlist into client config
- [x] T043 Document the operational difference between provisioned admin keys and Nixstasis-issued keys

## VM And Integration Tests

- [x] T050 Add a mock Nixstasis API service for NixOS VM tests
- [x] T051 Test registration against `POST /api/v1/devices/register`
- [x] T052 Test identity persistence under `/data` across service restart
- [x] T053 Test polling against `POST /api/v1/devices/{id}/heartbeat`
- [x] T054 Test server outage after enrollment does not stop local recovery targets
- [x] T055 Test heartbeat `remote_access_token` reaches the FRP launch boundary without full tunnel validation
- [x] T056 Add the new VM check to flake outputs and testing docs

## Documentation And Closeout

- [ ] T900 Update Nixstasis enrollment architecture docs with implemented behavior
- [ ] T901 Update runtime-boundary docs for base-system Nixstasis client responsibility
- [ ] T902 Update testing docs with mock-server validation
- [ ] T903 Add this feature spec to `docs/src/SUMMARY.md` if feature specs are listed there
- [ ] T904 Update `docs/src/planned-features.md` after implementation completes
- [ ] T999 Run targeted tests, VM validation, docs reconciliation, and close out the feature spec
