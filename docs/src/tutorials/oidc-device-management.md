# OIDC-Authenticated Device Management

This tutorial builds an OIDC-authenticated management stack on AtomixOS using
three components:

- **Caddy with AuthCrunch** -- reverse proxy with Microsoft Entra OIDC login
  and JWT-based authorization
- **Cockpit-ws** -- browser-based device management console
- **Admin-only route policy** -- allows administrators to reach Cockpit while
  leaving room for user-facing application routes

The result is a single sign-on flow: users authenticate once through Entra ID,
and Caddy only exposes the Cockpit management console to admin users.

This tutorial is designed for local device management on a LAN. Caddy uses its
internal certificate authority instead of Let's Encrypt, so the device does not
need a publicly routed domain or inbound internet access.

## Contents

<!-- toc -->

## Prerequisites

The example bundle uses Microsoft Entra by default because Entra group claims
map cleanly to admin/user roles. You can use any AuthCrunch-supported OIDC
provider by changing the Caddyfile identity provider block, callback URI, and
role mapping rules.

### Microsoft Entra App Registration

1. In the Azure portal, open **Microsoft Entra ID** > **App registrations**
2. Select **New registration**
3. Set the redirect URI to:

   ```text
   https://<GATEWAY_DOMAIN>/auth/oauth2/azure/authorization-code-callback
   ```

4. Note the **Application (client) ID** and **Directory (tenant) ID**
5. Under **Certificates & secrets**, create a new client secret and copy its
   value
6. Under **Token configuration** > **Add groups claim**, select **Security
   groups**
7. Create two Entra security groups:
   - `AtomixOS-Admins` -- full device administration
   - `AtomixOS-Users` -- read-only monitoring access
8. Assign users to the appropriate groups

### Google OAuth Client

For Google, create an OAuth client in Google Cloud Console instead of an Entra
app registration:

1. Open **APIs & Services** > **Credentials**
2. Create an **OAuth client ID** for a web application
3. Add this authorized redirect URI:

   ```text
   https://<GATEWAY_DOMAIN>/auth/oauth2/google/authorization-code-callback
   ```

4. Note the client ID and client secret
5. Decide how to assign admin access. Common options are a Google Workspace
   group claim, a hosted-domain claim, or an explicit email allow-list in the
   AuthCrunch transform rules.

Then replace the Entra identity provider block in the Caddyfile with a Google
provider block. The exact AuthCrunch driver options may vary by AuthCrunch
version; the important values are the provider name (`google`), realm
(`google`), client ID, client secret, and callback URI path.

```caddyfile
oauth identity provider google {
    realm google
    driver google
    client_id {env.GOOGLE_CLIENT_ID}
    client_secret {env.GOOGLE_CLIENT_SECRET}
    scopes openid email profile
}
```

Also update `enable identity provider azure` to `enable identity provider
google` and update transform rules from `match realm azure` to `match realm

## Architecture

```mermaid
graph TD
    lan((Local LAN browser)) -- "ports 80, 443" --> caddy

    subgraph caddy["Caddy + AuthCrunch"]
        ca1["/auth* → OIDC portal"]
        ca2["/cockpit/* → admin-only reverse proxy"]
        ca3["/app/* → user application routes"]
    end

    caddy -- "localhost:9090" --> cockpit

    subgraph cockpit["Cockpit-ws"]
        co1["--local-session"]
        co2["cockpit-bridge"]
        co3["host D-Bus and Podman sockets"]
    end
```

### Authentication Flow

1. User navigates to `https://<GATEWAY_DOMAIN>/cockpit/`
2. Caddy checks for a valid JWT cookie; if absent, redirects to `/auth/`
3. AuthCrunch initiates Entra OIDC login
4. After authentication, AuthCrunch maps Entra groups to roles:
   - `AtomixOS-Admins` group receives the `authp/admin` role
   - `AtomixOS-Users` group receives the `authp/user` role
5. AuthCrunch issues a JWT cookie with the mapped roles
6. Caddy validates the JWT and allows `/cockpit/*` only for `authp/admin`
7. Cockpit runs behind Caddy with `--local-session`; Cockpit performs no second
   login and relies on Caddy for authentication and authorization

## Bundle Structure

```text
example/caddy-oidc/
config.toml
files/
  caddy/
    Caddyfile
  cockpit/
    Containerfile
```

Substitute the placeholder values in `config.toml`, package this directory, and
provision the device. The Caddyfile and generated Cockpit configuration read
those values from container environment variables.

## Placeholder Values

Replace these values before provisioning:

| Placeholder                | Where       | Description                          |
|----------------------------|-------------|--------------------------------------|
| `<SSH_PUBLIC_KEY>`         | config.toml | Your SSH public key for admin access |
| `<AZURE_TENANT_ID>`        | config.toml | Entra directory (tenant) ID          |
| `<AZURE_CLIENT_ID>`        | config.toml | App registration client ID           |
| `<AZURE_CLIENT_SECRET>`    | config.toml | App registration client secret       |
| `<JWT_SHARED_KEY>`         | config.toml | Shared HMAC-SHA256 signing key       |
| `<GATEWAY_DOMAIN>`         | config.toml | Local DNS name for the device        |
| `<ENTRA_ADMIN_GROUP_NAME>` | config.toml | Entra group name for admin role      |

If you switch to Google or another provider, replace the Azure placeholders
with that provider's client ID/secret variables and update the Caddyfile
environment entries accordingly.

Generate the JWT shared key with:

```bash
openssl rand -base64 32
```

## Configuration Files

## Local DNS and TLS

The browser must resolve `<GATEWAY_DOMAIN>` to the device's LAN address. Use one
of these local options:

- Add a DNS record on your LAN router or development DNS server
- Add a hosts-file entry on the workstation you use to manage the device
- Use another local name resolution mechanism that maps the name to the device
  IP address

For example, if the gateway is reachable at `172.20.30.1`:

```text
172.20.30.1 gateway.example.com
```

Caddy serves HTTPS for this name with `tls internal`. That avoids public ACME
validation and works even when the domain is not reachable from the internet.
Browsers will not trust Caddy's local CA by default; either trust the Caddy root
CA from the `caddy-data` volume on your management workstation or accept the
browser warning for local testing.

### config.toml

The config defines two rootful containers, a network, a volume, and a build:

```toml
{{#include ../../../example/caddy-oidc/config.toml}}
```

Key points:

- Caddy is `privileged = true` because it binds ports 80/443
- Cockpit-ws is `privileged = true` because it runs a local management session
  with host D-Bus, systemd, journal, and Podman sockets mounted into the container
- The `cockpit-ws` container depends on its build service via `After` and
  `Requires`
- `Pull = "never"` prevents Podman from trying to fetch the locally built
  `localhost/cockpit-ws:latest` tag from a registry
- The `cockpit-ws` build uses `Network = "host"` to avoid Podman build-time
  netavark/nftables setup on constrained device images
- The `${FILES_DIR}` token is replaced at provision time with the path to
  the extracted bundle files
- `GATEWAY_DOMAIN` is passed to both containers; Caddy uses it for the site
  address and Cockpit uses it to generate the real-device and VM-forwarded
  origins in `/etc/cockpit/cockpit.conf`
- Caddy uses `tls internal`, so HTTPS is local-only and does not require public
  DNS or Let's Encrypt validation
- The `management` network is defined for future use when containers move
  off host networking

### Caddyfile

```caddyfile
{{#include ../../../example/caddy-oidc/files/caddy/Caddyfile}}
```

Key points:

- The `order` directives register the authenticate and authorize handlers
- The identity provider block configures Entra OIDC via the `azure` driver
- The portal issues JWTs signed with the shared key
- The portal explicitly lists Cockpit as an application link; AuthCrunch does
  not discover Caddy routes automatically
- `transform user` blocks assign base roles (`authp/user`) and promote
  admin group members to `authp/admin`
- `admin-policy` restricts `/cockpit/*` to `authp/admin`
- `user-policy` is provided for user-facing applications that should allow
  both `authp/admin` and `authp/user`
- `tls internal` tells Caddy to issue a certificate from its local CA instead of
  using public ACME/Let's Encrypt
- `/` redirects to `/cockpit/`, and `/cockpit` normalizes to `/cockpit/`
- `GATEWAY_DOMAIN` and `ENTRA_ADMIN_GROUP_NAME` come from container
  environment variables set in `config.toml`

### Containerfile

```dockerfile
{{#include ../../../example/caddy-oidc/files/cockpit/Containerfile}}
```

The custom image adds Cockpit's bridge and management modules, then starts
cockpit-ws with `--local-session`. Cockpit itself does not authenticate users;
Caddy's admin-only OIDC policy protects the route. The startup command writes
`/etc/cockpit/cockpit.conf` from `GATEWAY_DOMAIN`, so the example only requires
editing `config.toml`.

## Building and Applying

Package the bundle as a tarball:

```bash
# Edit config.toml with your values
tar --zstd -cvf config.tar.zst -C <repo>/example/caddy-oidc .
```

Apply to the device using the bootstrap server or USB provisioning. See
[Provisioning](../provisioning.md) for details.

## Cockpit-Podman

The Cockpit Podman integration (`cockpit-podman`) lets operators manage
containers through the Cockpit UI. In this example it is installed into the
Cockpit container and uses the mounted host Podman socket at
`/run/podman/podman.sock`.

A future NixOS module could make Cockpit a native host service instead of a
containerized admin application:

```nix
{ pkgs, ... }:
{
  environment.systemPackages = [ pkgs.cockpit-podman ];
}
```

This is outside the scope of the tutorial config bundle and requires
rebuilding the AtomixOS base image.

## Security Considerations

This tutorial uses HS256 (symmetric) JWT signing for simplicity. For
production deployments:

- **Use public DNS and public certificates** if exposing the device outside a
  trusted local network. The tutorial intentionally uses Caddy internal TLS for
  local management, not internet deployment.
- **Use asymmetric keys (RS256/ES256)** instead of a shared HMAC secret.
  AuthCrunch supports RSA and ECDSA key pairs.
- **Rotate secrets regularly.** The `JWT_SHARED_KEY` and Azure client secret
  should be rotated on a schedule.
- **Use secret files** instead of environment variables for sensitive values.
  Podman supports `--secret` mounts that avoid exposing secrets in Quadlet
  files on disk.
- **Pin image tags** in production. The tutorial uses `:latest` for
  convenience; production should pin to specific versions.
- **Restrict Cockpit access.** The `viewer` user should have minimal
  permissions. Consider using Cockpit's `cockpit.conf` `[Ssh-Login]`
  restrictions.
