# Design — Fleet Bootstrap via Nixstasis

## Metadata

- Beads feature root: `atomixos-mol-efd`
- Feature slug: `fleet-bootstrap-via-nixstasis`
- Design path: `docs/src/features/fleet-bootstrap-via-nixstasis/design.md`
- Implemented record: `docs/src/features/fleet-bootstrap-via-nixstasis/index.md`
- Base branch: `dev`
- Status: draft

## Feature Summary

Add an explicit build-time fleet bootstrap policy that enrolls a device through Nixstasis and exposes the existing
AtomixOS provisioning API only through an approved Nixstasis FRP session. The API, canonical `config.toml`/bundle
format, validation pipeline, and post-provision SSH-signature contract remain unchanged.

## User Intent

Fleet and production devices need a stronger first-boot trust model than tokenless LAN/WAN bootstrap. A device should
first be accepted into the Nixstasis fleet, then receive a short-lived remote-access grant, and only then accept the
server-provided initial configuration. Standalone, personal, and development images must retain the existing
network-bootstrap behavior.

The Nixstasis client remains immutable base-system code in the root squashfs. AtomixOS consumes the released,
server-directed, bounded FRP route-profile capability from `nixstasis-255`, the bounded Host rewrite follow-up
`nixstasis-fss`, and the server-side delivery action `nixstasis-4gg`; it does not implement a second Nixstasis protocol
or a direct server-to-root mutation path.

## Goals

1. Extend the strict build-stage `build.toml` contract with an explicit provisioning transport and non-secret Nixstasis
   settings.
2. Preserve the existing network bootstrap as the default transport for standalone/personal/development images.
3. Add an opt-in `nixstasis` transport that binds the provisioning API to loopback and removes WAN bootstrap exposure.
4. Configure a named Nixstasis route profile for plain HTTP to `127.0.0.1:8080`, using the existing FRPS control and
   HTTP-vhost connections and rewriting the local `Host` to `localhost`.
5. Reuse the existing programmatic `POST /api/config` endpoint and complete config-bundle pipeline for the initial
   server-provided configuration.
6. Keep the remote-access token as the authorization gate: approval issues the device runtime credential, and a
   separate `remote_access_token` starts the tunnel.
7. Stop treating the initial provisioning path as an open LAN/WAN listener after successful promotion; the fleet
   socket remains loopback-only and later re-apply remains SSH-signature authenticated.
8. Test the policy, socket binding, firewall behavior, Nixstasis configuration, and first-boot flow without requiring
   an end-to-end public FRP deployment.

## Non-Goals

- Replacing or extending the AtomixOS provisioning API.
- Adding a Nixstasis command that writes `/data/config` directly or bypasses the provisioning worker.
- Allowing arbitrary FRPC TOML or unrestricted server-selected local targets in AtomixOS.
- Implementing Nixstasis server approval, remote-access UI, FRP route-profile protocol, Host rewrite, or Caddy
  deployment in this repository; those remain Nixstasis ownership, tracked by `nixstasis-255`, `nixstasis-fss`, and
  `nixstasis-4gg`.
- Exposing the first-boot Boot UI as a general remote management interface. Fleet delivery uses the existing
  programmatic `/api/config` route; the browser-only `/apply` CSRF flow remains local UI behavior.
- Ongoing fleet orchestration or post-provision re-apply authorization. The initial server-provided configuration is the
  scope; subsequent re-apply uses the existing SSH-signature boundary.
- Moving the local API to ports 80 or 443. External HTTPS termination remains Nixstasis/Caddy responsibility; the local
  plain HTTP service remains on loopback port 8080.

## User-Facing Behavior

The committed build policy contains the existing watchdog section plus explicit transport defaults:

```toml
version = 1

[watchdog]
enable_hardware = false
backend = "external"
runtime_timeout = "30s"
reboot_timeout = "10min"

[provisioning]
bootstrap_transport = "network"

[nixstasis]
enable = false
api_url = ""
frp_server_addr = ""
frp_server_port = 7000
```

A fleet image changes only the reviewed non-secret build policy:

```toml
[provisioning]
bootstrap_transport = "nixstasis"

[nixstasis]
enable = true
api_url = "https://nixstasis.example.invalid"
frp_server_addr = "frps.example.invalid"
frp_server_port = 7000
```

Whenever `nixstasis.enable = true`, the evaluator requires a non-empty API URL and non-empty FRP server address,
independent of the selected provisioning transport. Enabling Nixstasis while retaining
`bootstrap_transport = "network"` is valid and does not alter the provisioning listener.

Fleet first boot proceeds as follows:

1. The image starts the loopback-only AtomixOS provisioning socket on `127.0.0.1:8080`.
2. The immutable Nixstasis client registers using its device identity and waits for approval without blocking local
   boot or recovery.
3. After approval, the client persists the issued identity and polls heartbeats.
4. When Nixstasis issues `remote_access_token` plus the named `atomixos-bootstrap` route profile, the client starts
   FRPC. The released route-profile client capability plus `nixstasis-fss` provide the plain HTTP loopback route and
   local `Host: localhost` rewrite.
5. The Nixstasis server-side delivery action tracked by `nixstasis-4gg` uses the existing FRP HTTP path to submit the
   canonical config file or bundle to `POST /api/config`. No new AtomixOS API credential or mutation path is introduced.
6. AtomixOS validates, stages, promotes, activates, and health-checks the same desired state as every other complete
   config submission.
7. Nixstasis withdraws the one-time remote-access grant. The client stops FRPC. The AtomixOS API remains loopback-only
   and provisioned re-apply still requires SSH signatures.

## Requirements

### Functional Requirements

- Version 1 build configuration accepts only the explicitly documented `provisioning` and `nixstasis` fields in
  addition to existing fields; unknown fields fail closed.
- `bootstrap_transport` accepts exactly `network` and `nixstasis`.
- The committed default remains `network`; all existing network-bootstrap tests and behavior continue to work.
- When `nixstasis.enable` is true, the policy requires non-empty non-secret `api_url` and `frp_server_addr`,
  regardless of transport; `frp_server_port` remains a validated port with default `7000`.
- Effective build configuration maps to NixOS options without parsing TOML in runtime modules.
- The AtomixOS bootstrap socket listens on `0.0.0.0:8080` for `network` transport and `127.0.0.1:8080` for `nixstasis`
  transport.
- Fleet mode never installs the first-boot WAN nftables rule for TCP port 8080.
- Fleet mode never rebinds the bootstrap socket to the provisioned LAN gateway address.
- The Nixstasis module consumes the upstream route-profile capability for the named `atomixos-bootstrap` profile with
  a plain HTTP local target at `127.0.0.1:8080` and, after `nixstasis-fss`, a local host-header rewrite to `localhost`.
- The route profile uses the existing FRPS connection and HTTP-vhost ingress; no new device listener or FRPS port is
  required.
- Existing `remote_access_token` start/stop behavior remains the authorization gate, and token withdrawal stops the
  tunnel.
- The existing `POST /api/config` route accepts the server-provided complete config/bundle while unprovisioned and
  continues through the existing staged root-worker pipeline.
- Fleet mode does not expose the Boot UI's browser token as a replacement for Nixstasis authorization.
- Build provenance records the effective fleet/network transport and Nixstasis enablement in the immutable canonical
  build policy and metadata outputs.

### Quality Requirements

- Build configuration validation is deterministic, strict, and shared by direct checks and supported build wrappers.
- No Nixstasis token, FRP auth token, signing key, or runtime credential enters `build.toml`, derivation metadata, or
  immutable `/etc/atomixos` policy files.
- A loopback-only fleet socket remains unreachable through WAN and LAN interfaces even when the general LAN firewall is
  open.
- A route-profile mismatch or unavailable upstream capability fails closed during evaluation or client startup and does
  not silently fall back to network bootstrap.
- The fleet flow remains outage-tolerant: Nixstasis registration, polling, and FRP failures do not prevent local boot,
  local SSH recovery, or the local provisioning service from starting.
- Validation must distinguish the fleet profile from the existing network profile and cover both transport choices.

### Compatibility and Migration Requirements

- Existing `build.toml` files are migrated by adding the committed defaults; direct Nix commands continue to use the
  committed policy.
- Existing `build.dev.toml` overlays remain partial and inherit the new defaults.
- Existing Nixstasis-enabled network-bootstrap images retain their current API exposure unless they opt into the new
  transport.
- Existing Nixstasis token-only heartbeat responses continue to work through the upstream client's compatibility mode;
  AtomixOS fleet builds require the published route-profile capability before they are released.
- Existing `/api/config`, bundle import/export, first-boot UI, SSH signature, staging, rollback, and socket activation
  contracts remain compatible.

## Existing Context

`build.toml` is a strict version-1 immutable policy currently consumed only by the watchdog module. Its evaluator,
canonical renderer, local overlay wrapper, metadata, and artifact sidecars are in `nix/build-configuration.nix` and
`modules/build-configuration.nix`.

`modules/first-boot.nix` owns `atomixos-bootstrap.socket` and currently listens on `0.0.0.0:8080`. The network firewall
adds the WAN bootstrap rule through `bootstrap-wan-toggle.service` while initial promotion is pending. The LAN gateway
module writes a runtime systemd drop-in that rebinds the socket to the configured LAN gateway after provisioning.

The provisioning service already supports tokenless first-boot programmatic `/api/config`, canonical config bundles,
async single-flight/staged jobs, validation, activation, rollback, and post-provision SSH-signature authentication.
Its browser-origin checks accept a local rewritten `Host`; the fleet route is intentionally a server-to-device
programmatic path rather than a remote Boot UI path.

The Nixstasis client is already packaged into the immutable AtomixOS base and stores identity/runtime state under
`/data/nixstasis`. The released Nixstasis route-profile capability selects the built-in `atomixos-bootstrap` profile,
which renders a plain HTTP target at `127.0.0.1:8080`; `nixstasis-fss` adds the local Host rewrite needed by the
existing bootstrap security check. FRP session startup remains gated by `remote_access_token`. The server-side bundle
action is tracked separately by `nixstasis-4gg`.

## Proposed Design

### Build Policy and NixOS Mapping

Extend the shared build evaluator with two strict sections:

- `[provisioning].bootstrap_transport`: enum `network` or `nixstasis`, defaulting to `network`.
- `[nixstasis]`: `enable` boolean, `api_url` string, `frp_server_addr` string, and `frp_server_port` integer.

The canonical renderer emits the new sections in a fixed order. The effective result exposes typed values consumed by
`modules/build-configuration.nix`, which maps them to a small `atomixos.provisioning` option and the existing
`atomixos.nixstasis` options. Runtime modules never read TOML or environment variables to choose the trust boundary.

The Nixstasis route profile is a fixed AtomixOS capability, not a user-provided arbitrary FRPC document:

```text
profile: atomixos-bootstrap
proxy kind: plain HTTP
local target: 127.0.0.1:8080
local Host rewrite: localhost (provided by nixstasis-fss)
```

The upstream Nixstasis route-profile contract owns the heartbeat wire representation, profile validation, FRPC
rendering, restart behavior, and future typed route extension. AtomixOS supplies this build-declared capability only
when the client is enabled and consumes the published upstream package revision.

### Listener and Firewall Boundary

Introduce an enum-valued NixOS option, default `network`, for the bootstrap transport. The socket unit selects the
address at evaluation time:

- `network`: `0.0.0.0:8080` (existing behavior).
- `nixstasis`: `127.0.0.1:8080`.

The firewall module conditionally installs the pending-promotion WAN rule only for `network`. The LAN gateway apply
path and runtime rebind service become no-ops for `nixstasis`; they continue to generate the existing LAN drop-in for
`network`. The loopback socket, rather than a transport-specific provisioned-firewall rule, is the fleet reachability
boundary.

First-boot discovery still waits for valid provisioning when no boot/USB seed exists. In fleet mode, the Nixstasis
client's approved FRP route is the transport that can reach the existing loopback service. No new wait loop or direct
filesystem handoff is added.

### Fleet Request and Trust Flow

The Nixstasis server remains responsible for inventory approval and remote-access authorization. Device approval alone
only produces the normal runtime identity; the separate heartbeat remote-access response is required before FRPC starts.
The server-side delivery action tracked by `nixstasis-4gg` selects the `atomixos-bootstrap` profile and withdraws the
lease after the promotion result is known.

That server action submits the existing complete config artifact to `/api/config`. The network service receives it
through the loopback FRP route, stages it as usual, and delegates privileged promotion to the existing root worker. The
first-boot exception is scoped by the existing unprovisioned-state guard; no Nixstasis credential is written into
`/data/config`.

The `nixstasis-fss` route-profile rewrite presents `Host: localhost`, allowing the existing bootstrap host validation to
remain narrow. The feature documents the fleet uploader as programmatic; browser-origin/CSRF behavior remains owned by
the local Boot UI and is not weakened for remote proxy traffic.

### Post-Provision Behavior

Successful initial provisioning does not change the immutable transport policy. In fleet mode the socket remains on
loopback; the normal LAN rebind is deliberately disabled. Nixstasis remote access is withdrawn by the server and the
client stops FRPC. If later remote access is granted for another route profile, post-provision config mutation still
requires the existing SSH signature headers and admin signer state.

## Architecture Consistency

### Existing Patterns Reused

- Strict, versioned, non-secret `build.toml` policy and canonical provenance.
- NixOS module assertions and evaluation-time policy mapping.
- Immutable Nixstasis client code with persistent state under `/data/nixstasis`.
- Existing Nixstasis `remote_access_token` FRP lifecycle.
- Existing socket activation, staged root-worker, config bundle, validation, activation, and rollback pipeline.
- Existing firewall default-deny WAN policy and runtime drop-ins under `/run/systemd/system`.

### Invariants Preserved

- Runtime `config.toml` never controls immutable fleet exposure policy.
- No default credentials or embedded Nixstasis/FRP secrets.
- Nixstasis outage never blocks local boot or recovery.
- No IP forwarding or new inbound WAN listener is introduced.
- Complete config import remains the canonical provisioning mutation path.
- Post-provision re-apply remains signature-authenticated.
- The Nixstasis client remains outside Podman and survives container-layer failure.

### New Decisions Introduced

- Provisioning transport is an explicit independent build policy, not an implicit consequence of enabling Nixstasis.
- Fleet transport binds the existing API to loopback port 8080 rather than moving it to local ports 80/443.
- Nixstasis server approval and remote-access lease are separate required gates.
- The initial FRP capability is a named build-declared route profile; arbitrary route specifications are a future typed,
  security-reviewed extension of Nixstasis, not part of this feature.
- Fleet delivery is programmatic `/api/config`; the Boot UI remains a local browser workflow.

### Architecture Documentation Changes

Update the enrollment architecture to show the approval → remote-access-token → FRP route → existing provisioning
API flow. Update runtime-boundary and provisioning pages to distinguish network and Nixstasis transports and to
document the loopback-only fleet invariant.

## Operational Considerations

A fleet image must be built with a reviewed `build.toml` containing the Nixstasis API URL and FRP server address. These
values are public routing configuration, not credentials. The Nixstasis server must approve the device and issue the
remote-access lease/profile before uploading the initial bundle.

Operators should verify, before release:

- the effective build policy identifies `bootstrap_transport = "nixstasis"`;
- `ss` shows the bootstrap service only on `127.0.0.1:8080`;
- no WAN bootstrap nftables rule exists;
- Nixstasis registration and heartbeat succeed without token leakage;
- the server can submit and poll the existing config job through the route;
- the route is withdrawn after successful provisioning.

If Nixstasis is unavailable, a fleet device remains unprovisioned and locally recoverable but cannot complete
server-side bootstrap until enrollment/remote access resumes. A local recovery seed remains available only if the
image/operator uses an explicit supported seed path; it does not silently widen the network listener.

## Documentation Impact

| Documentation concern      | Exact page                                                                        | Create or update        | Planned change                                                                                        | Owning Beads task    |
|----------------------------|-----------------------------------------------------------------------------------|-------------------------|-------------------------------------------------------------------------------------------------------|----------------------|
| Architecture               | `docs/src/architecture/overwatch-enrollment.md`                                   | Update                  | Document approval, remote-access lease, FRP route profile, and existing provisioning API flow         | `atomixos-mol-bzo.4` |
| Architecture               | `docs/src/runtime-boundaries.md`                                                  | Update                  | Document build-selected network versus loopback fleet exposure and state ownership                    | `atomixos-mol-bzo.4` |
| Usage / Operations         | `docs/src/provisioning/fleet-bootstrap.md`                                        | Create                  | Explain fleet image policy, enrollment prerequisites, initial bundle upload, recovery, and withdrawal | `atomixos-mol-bzo.4` |
| Reference                  | `docs/src/reference/build-configuration.md`                                       | Update                  | Add provisioning and Nixstasis fields, assertions, canonical rendering, and non-secret boundary       | `atomixos-mol-bzo.1` |
| Development                | `docs/src/testing.md`                                                             | Update                  | Add focused fleet policy, socket, firewall, and mock enrollment validation                            | `atomixos-mol-bzo.3` |
| Navigation                 | `docs/src/SUMMARY.md`                                                             | Update                  | Register the new fleet-bootstrap operations page and feature design                                   | `atomixos-mol-bzo.4` |
| Roadmap                    | `docs/src/planned-features.md`                                                    | Update                  | Add the planned fleet bootstrap feature and Nixstasis dependency                                      | `atomixos-mol-bzo.4` |
| Implemented Feature Record | `docs/src/features/fleet-bootstrap-via-nixstasis/index.md`                        | Create during close-out | Record delivery, validation, and external Nixstasis dependency evidence                               | lifecycle close-out  |
| Implemented Feature Index  | `docs/src/features/index.md` and the implemented section in `docs/src/SUMMARY.md` | Update during close-out | Index the delivered feature record with the repository's implemented-feature navigation               | lifecycle close-out  |

## Validation Strategy

- Add evaluator tests for defaults, canonical rendering, valid fleet configuration, required-field assertions,
  invalid transport, invalid ports, unknown fields, and no-secret policy behavior.
- Add NixOS evaluation assertions for both listener addresses, Nixstasis option mapping, route-profile rendering, and
  contradictory policy rejection.
- Extend firewall-focused checks to prove network mode retains pending WAN bootstrap behavior and fleet mode does not
  install a WAN 8080 rule.
- Extend first-boot/LAN-gateway checks to prove network mode rebinds to the configured LAN address while fleet mode
  remains loopback-only after config promotion.
- Add the `fleet-bootstrap` VM check with a mock Nixstasis API and bounded FRP client/profile fixture. Verify
  registration, `atomixos-bootstrap` profile selection, loopback API reachability, complete `/api/config` job
  application, token withdrawal, and absence of credential leakage. Full public FRPS/Caddy transport remains a separate
  integration check.
- Run `nix build .#checks.aarch64-darwin.build-configuration --no-link`,
  `nix build .#checks.aarch64-darwin.firewall --no-link`,
  `nix build .#checks.aarch64-darwin.fleet-bootstrap --no-link`, and the matching `aarch64-linux` checks when the
  builder is available. Run `uv run scripts/check-docs.py` and `mdbook build docs` for documentation changes.
- Run the existing provisioning Python suite and repository-standard validation after review fixes stabilize.
- Record the external Nixstasis revisions/tasks `nixstasis-255`, `nixstasis-fss`, and `nixstasis-4gg` used by the
  integration test and release build.

## Implementation Decomposition

1. Extend and validate the strict build configuration, map effective policy to NixOS options, and update the build
   configuration reference.
2. Apply the transport policy to the bootstrap socket, WAN firewall toggle, and LAN rebind path; keep network
   behavior unchanged and document the tests.
3. Consume the released Nixstasis route-profile capability, render the named plain-HTTP loopback profile, and add the
   mock enrollment/FRP integration scenario.
4. Reconcile architecture, operations, testing, navigation, and roadmap documentation.

## Dependencies and Parallelism

The feature depends on the delivered Nixstasis route-profile contract `nixstasis-255`, the Host rewrite follow-up
`nixstasis-fss`, and the server-side bundle delivery action `nixstasis-4gg`. Build-policy work can be reviewed
independently. Runtime transport work depends on the new build-policy option. Nixstasis integration and fleet VM
validation depend on the policy mapping and the pinned upstream route-profile package. Documentation reconciliation
follows the stable behavior and test evidence.

## Rollout and Migration

The committed build policy defaults to network bootstrap, so existing images and direct Nix workflows keep their current
behavior. Fleet builds opt in explicitly and must contain all required public Nixstasis endpoints. No `/data`
migration is required. Switching an existing deployment from network to fleet transport requires a new immutable image
and a planned re-enrollment/recovery procedure; runtime `config.toml` cannot change the transport.

## Risks and Tradeoffs

- **Upstream dependency timing:** fleet integration cannot be released before `nixstasis-fss` and `nixstasis-4gg` are
  implemented, documented, and pinned alongside the delivered `nixstasis-255` route-profile contract.
- **Initial fleet outage:** an unapproved or offline device cannot receive its server bundle; local recovery remains
  possible but the image does not silently open a network listener.
- **FRP route exposure:** the route is authorized by the Nixstasis remote-access lease and external server policy;
  post-provision withdrawal is operationally required.
- **Host validation:** local `Host` rewriting preserves the narrow API allowlist but means browser-origin requests
  through the remote route are not the supported upload path.
- **Static base policy:** a transport change requires a new image, which is intentional for an immutable trust boundary.
- **Route-profile expansion:** arbitrary server route configuration could expose unintended local services; future
  support must be typed, capability-scoped, and separately reviewed.

## Rejected Alternatives

- **New Nixstasis provisioning command:** rejected because the existing `/api/config` pipeline already provides
  validation, staging, privilege separation, promotion, activation, rollback, and job reporting.
- **Direct server writes to `/data/config`:** rejected because it bypasses the root worker and canonical desired-state
  pipeline.
- **Move the API to local port 443:** rejected because the service is plain HTTP, port ownership may conflict with
  provisioned Caddy, and external HTTPS is already provided by Nixstasis/Caddy.
- **Use the current `http2https` proxy unchanged:** rejected because it expects a local HTTPS target and cannot
  reach the current plain HTTP Uvicorn service on port 8080.
- **Implicit fleet mode from `nixstasis.enable`:** rejected because enabling remote management must not silently change
  the provisioning trust boundary.
- **Arbitrary server-supplied FRPC/TOML:** rejected for the initial feature because it would let a server expose
  unrestricted local services; the upstream task provides a future typed extension point instead.
- **Keep WAN/LAN bootstrap as fallback in fleet images:** rejected because it defeats the stronger enrollment gate.

## Open Questions

None required for implementation once the external Nixstasis tasks `nixstasis-fss` and `nixstasis-4gg` are available.
The route-profile wire format is owned and versioned by `nixstasis-255`; AtomixOS consumes the published contract
rather than choosing a duplicate representation.

## Deferred Decisions

- Future typed route kinds and controlled server-provided target capabilities remain Nixstasis-owned follow-up work.
- Ongoing server-initiated post-provision config re-apply remains outside this initial bootstrap feature.
- Full public FRPS/Caddy end-to-end validation remains an integration/release check after the local VM boundary passes.

## Planning Record

### Questions Asked and Answers

- **Should the existing provisioning API remain the mutation path?** Yes. The Nixstasis route transports the existing
  programmatic `/api/config` request; no new AtomixOS API or command is added.
- **Can the plain HTTP route share the existing FRPS connection and HTTP-vhost port?** Yes. `http2https` is a local
  plugin mode, not a separate FRPS connection. The fleet route uses the same FRPS ports with a plain HTTP proxy to
  loopback 8080.
- **Should Nixstasis dynamically configure arbitrary FRPC plugins?** The initial contract uses named, build-declared
  profiles. A future typed extension may expand route kinds and controlled capabilities, but arbitrary TOML is not part
  of this feature.
- **Should provisioning exposure be implicit from Nixstasis enablement?** No. `provisioning.bootstrap_transport` is an
  explicit independent policy; Nixstasis can be enabled while preserving network bootstrap.
- **What is the fleet trust sequence?** Device approval first, separate `remote_access_token` second, existing API
  upload third, server withdrawal after successful initial promotion.
- **Who owns server-side bundle delivery?** Nixstasis task `nixstasis-4gg` owns the approved-device action that selects
  `atomixos-bootstrap`, submits `/api/config`, polls the job, and withdraws the lease; AtomixOS owns only the local
  transport and existing provisioning pipeline.

### Assumptions

- Nixstasis `nixstasis-255` delivers the backward-compatible, versioned `atomixos-bootstrap` route-profile contract;
  `nixstasis-fss` adds the local host-header rewrite.
- Nixstasis `nixstasis-4gg` delivers the approved-device server-side bundle action and job polling contract.
- Nixstasis/Caddy external authorization remains the server-side operator boundary for the FRP HTTP route.
- The server-side uploader submits `/api/config` without browser `Origin`/`Referer` headers through the rewritten
  loopback route.
- Public Nixstasis and FRPS endpoint values are acceptable immutable build inputs and contain no credentials.

### Design Changes During Planning

- The design initially considered a new Nixstasis provisioning command; it was replaced with transport reuse through
  the existing API.
- The initial idea of using local ports 80/443 was replaced with loopback port 8080 and a plain HTTP FRP route.
- The route configuration was narrowed from arbitrary plugin data to named build-declared profiles, with future typed
  expansion explicitly deferred.
- Nixstasis enablement and provisioning transport were separated into independent build policy fields.
- The actual upstream profile name was reconciled to `atomixos-bootstrap`; Host rewriting and server-side delivery are
  explicit Nixstasis dependencies.

### Source Material

- `modules/first-boot.nix`
- `modules/firewall.nix`
- `modules/lan-gateway.nix`
- `modules/nixstasis.nix`
- `nix/build-configuration.nix`
- `scripts/first-boot.sh`
- `scripts/lan-gateway-apply.py`
- `scripts/provisioned-firewall-inbound.py`
- `scripts/atomixos_provision/src/atomixos_provision/domain/config/controller.py`
- `scripts/atomixos_provision/src/atomixos_provision/bootstrap_security.py`
- `docs/src/features/build-configuration/design.md`
- `docs/src/features/nixstasis-client/design.md`
- `/Users/DeRoseR/workspace/personal/nixstasis/packages/client/build/root-dir/usr/share/nixstasis/frpc.toml`
- `/Users/DeRoseR/workspace/personal/nixstasis/packages/client/internal/frp/manager.go`
- `/Users/DeRoseR/workspace/personal/nixstasis/packages/client/internal/transport/client.go`
- `/Users/DeRoseR/workspace/personal/nixstasis/deploy/compose/caddy/Caddyfile`
- External tasks `nixstasis-255`, `nixstasis-fss`, and `nixstasis-4gg`
- Skill version evidence:

  <!--
  schema=dstack.skill-version.v1 skill=plan-features installed=0.8.4 canonical=unavailable status=unavailable installed_source=/Users/DeRoseR/.agents/skills/plan-features/SKILL.md checked_at=2026-08-06T21:30:23.043246Z
  -->
