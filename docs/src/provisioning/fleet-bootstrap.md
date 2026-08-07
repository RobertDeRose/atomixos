# Fleet Bootstrap via Nixstasis

Fleet images use Nixstasis as the first-boot trust gate. The AtomixOS provisioning API remains the component that
validates and applies the canonical `config.toml` or complete config bundle; Nixstasis only authorizes and transports
the initial request.

## Build Policy

Fleet exposure is an immutable build decision, not a runtime `config.toml` setting:

```toml
[provisioning]
bootstrap_transport = "nixstasis"

[nixstasis]
enable = true
api_url = "https://nixstasis.example.invalid"
frp_server_addr = "frps.example.invalid"
frp_server_port = 7000
```

The policy requires Nixstasis to be enabled and requires the public API and FRP server addresses. It contains no device
or FRP credentials. Standalone and development images retain the default `bootstrap_transport = "network"` behavior.

## Enrollment and Initial Upload

1. Flash the reviewed fleet image.
2. The device starts the immutable Nixstasis registration/polling client and keeps its identity under
   `/data/nixstasis`.
3. Approve the device in Nixstasis.
4. Request remote access for the device. Approval and remote access are separate gates.
5. Nixstasis selects the AtomixOS bootstrap route profile. The client uses the existing FRPS connection and HTTP-vhost
   path, forwarding plain HTTP to the local `127.0.0.1:8080` provisioning service and presenting `Host: localhost` to
   that service.
6. Submit the initial complete config through the existing programmatic `POST /api/config` endpoint. The request is
   staged, validated, promoted, activated, health-checked, and rolled back using the normal provisioning pipeline.
7. Withdraw remote access after the initial job succeeds. The client stops FRPC.

The local API is not reachable on WAN or LAN in this mode. The browser-only Boot UI and its bootstrap CSRF token are not
the fleet transport; use the server-side/programmatic API path.

## Recovery and Failure

Nixstasis or FRP outages do not block boot, local SSH recovery, or the loopback provisioning service. The device remains
unprovisioned until enrollment and remote access become available. The fleet image does not silently open a WAN or LAN
fallback listener.

A transport change requires a new immutable image. Runtime `config.toml` cannot switch a device between network and
Nixstasis bootstrap modes. After initial provisioning, re-apply requests use the existing SSH-signature authentication
and never rely on the first-boot exception.

## Verification

Before releasing a fleet image, verify:

- `/etc/atomixos/build.toml` records `bootstrap_transport = "nixstasis"`;
- the effective Nixstasis API and FRP server addresses are correct and non-secret;
- `ss -ltn` shows the bootstrap service only on `127.0.0.1:8080`;
- no pending WAN bootstrap rule is installed;
- Nixstasis approval and remote-access lease are both required before FRPC starts;
- the server can submit and poll the existing provisioning job;
- the remote-access lease is withdrawn after successful promotion.
