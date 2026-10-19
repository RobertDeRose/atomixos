# Fleet Bootstrap

A fleet image takes its first configuration through Nixstasis instead of the network bootstrap console. Nixstasis
decides when a device may be provisioned and carries the request to it; the device's own provisioning API still
validates and applies the `config.toml` or bundle exactly as it would locally. A `/boot/config.toml` or USB seed, if
present, is still used first.

## Build a fleet image

Fleet mode is fixed when you build the image; `config.toml` cannot switch it. Set it in `build.toml`:

```toml
[provisioning]
bootstrap_transport = "nixstasis"

[nixstasis]
enable = true
api_url = "https://nixstasis.example.invalid"
frp_server_addr = "frps.example.invalid"
frp_server_port = 7000
```

Fleet mode requires Nixstasis to be enabled and its API and FRP server addresses to be set. The policy holds no device
or FRP credentials. Images built with the default `bootstrap_transport = "network"` provision locally. The exact
fields and their validation are in [Build Configuration](../reference/build-configuration.md).

In a fleet image the provisioning service listens only on `127.0.0.1:8080`. It is not reachable from the WAN or LAN
side, and the browser bootstrap console is not used.

## Provision a fleet device

1. Flash the fleet image.
2. Power the device on. The Nixstasis client registers it, keeps its identity under `/data/nixstasis`, and polls the
   Nixstasis server.
3. Approve the device in Nixstasis.
4. Request remote access for the device. Approval and remote access are separate steps; both are needed before the
   client opens a tunnel.
5. Run the Nixstasis delivery action for the device's configuration. It uses the `atomixos-bootstrap` route profile:
   the client forwards plain HTTP over its existing FRP connection to the local provisioning service at
   `127.0.0.1:8080`, presenting `Host: localhost`.
6. The action sends the configuration to `POST /api/config` as `application/octet-stream` and polls the returned
   `/api/jobs/<job_id>`. The device applies it like any other change, including health checks and rollback.
7. The action records the final result, then withdraws remote access, and the client stops its tunnel.

The delivery action retries only documented `409 Conflict` responses. If an upload or a poll gives an unclear answer,
it does not post the configuration again; the remote-access lease stays open so you can check the job and then withdraw
access yourself, or let the lease expire. A failed result withdraws access just like a successful one.

After the first configuration, changes use the normal signed API described in
[Change a provisioned device](../provisioning.md#change-a-provisioned-device).

## When Nixstasis is unreachable

A Nixstasis or FRP outage does not block booting, local SSH recovery, or the local provisioning service. The device
simply stays unprovisioned until enrollment and remote access work again. It never falls back to opening the
provisioning service on the WAN or LAN side. To change the transport, build and flash a new image.

## Check a fleet image before release

- `/etc/atomixos/build.toml` on the device records `bootstrap_transport = "nixstasis"`.
- The Nixstasis API and FRP server addresses are correct and contain no secrets.
- `ss -ltn` shows the provisioning service only on `127.0.0.1:8080`.
- The firewall has no WAN rule for port `8080`.
- The client starts its tunnel only after the device is approved and granted remote access.
- The delivery action can submit and poll a provisioning job without reposting an unclear request.
- The final result is recorded before remote access is withdrawn.

[Nixstasis Enrollment](../architecture/nixstasis-enrollment.md) explains the trust model behind these steps.
