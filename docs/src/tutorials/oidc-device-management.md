# OIDC-Authenticated Device Management

This tutorial builds an OIDC-authenticated management stack on AtomixOS using
three components:

- **Caddy with AuthCrunch** -- reverse proxy with Microsoft Entra OIDC login
  and JWT-based authorization
- **Cockpit-ws** -- browser-based device management console
- **Bearer token bridge** -- eliminates double authentication by passing
  AuthCrunch JWTs directly to Cockpit

The result is a single sign-on flow: users authenticate once through Entra ID,
and Cockpit trusts the JWT issued by AuthCrunch.

## Contents

<!-- toc -->

## Prerequisites

### Azure App Registration

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

### Local Users

The AtomixOS device needs two local users that Cockpit sessions will run as:

- `admin` -- device administrator (created by AtomixOS provisioning)
- `viewer` -- restricted read-only user (must be created separately or via a
  NixOS module)

## Architecture

```mermaid
graph TD
    internet((Internet)) -- "ports 80, 443" --> caddy

    subgraph caddy["Caddy + AuthCrunch"]
        ca1["/auth* → OIDC portal"]
        ca2["/cockpit/* → reverse proxy"]
    end

    caddy -- "localhost:9090" --> cockpit

    subgraph cockpit["Cockpit-ws"]
        co1["bearer token auth"]
        co2["JWT → local user mapping"]
        co3["→ cockpit-bridge"]
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
6. Caddy validates the JWT and reverse-proxies to Cockpit
7. Cockpit's bearer auth command validates the JWT signature, maps
   `authp/admin` to the `admin` user and `authp/user` to `viewer`, then
   launches `cockpit-bridge` as that user

## Bundle Structure

```text
config.example.toml
files/
  caddy/
    Caddyfile
  cockpit/
    Containerfile
    cockpit.conf
    cockpit-bearer-auth
```

Copy this bundle, rename `config.example.toml` to `config.toml`, substitute
the placeholder values, and provision the device.

## Placeholder Values

Replace these values before provisioning:

| Placeholder                | Where                   | Description                          |
|----------------------------|-------------------------|--------------------------------------|
| `<SSH_PUBLIC_KEY>`         | config.toml             | Your SSH public key for admin access |
| `<AZURE_TENANT_ID>`        | config.toml             | Entra directory (tenant) ID          |
| `<AZURE_CLIENT_ID>`        | config.toml             | App registration client ID           |
| `<AZURE_CLIENT_SECRET>`    | config.toml             | App registration client secret       |
| `<JWT_SHARED_KEY>`         | config.toml             | Shared HMAC-SHA256 signing key       |
| `<GATEWAY_DOMAIN>`         | Caddyfile, cockpit.conf | Public domain name of the device     |
| `<ENTRA_ADMIN_GROUP_NAME>` | Caddyfile               | Entra group name for admin role      |

Generate the JWT shared key with:

```bash
openssl rand -base64 32
```

## Configuration Files

### config.toml

The config defines two rootful containers, a network, a volume, and a build:

```toml
{{#include ../features/caddy-authcrunch-cockpit-tutorial/bundle/config.example.toml}}
```

Key points:

- Both containers are `privileged = true`: Caddy needs ports 80/443 (privileged),
  and Cockpit-ws needs host-level access for system management
- The `cockpit-ws` container depends on its build service via `After`
- The `${FILES_DIR}` token is replaced at provision time with the path to
  the extracted bundle files
- The `management` network is defined for future use when containers move
  off host networking

### Caddyfile

```caddyfile
{{#include ../features/caddy-authcrunch-cockpit-tutorial/bundle/files/caddy/Caddyfile}}
```

Key points:

- The `order` directives register the authenticate and authorize handlers
- The identity provider block configures Entra OIDC via the `azure` driver
- The portal issues JWTs signed with the shared key
- `transform user` blocks assign base roles (`authp/user`) and promote
  admin group members to `authp/admin`
- The authorization policy uses `crypto key verify` (verify-only, not
  sign-verify) and `validate bearer header` to pass the JWT downstream
- `inject headers with claims` adds JWT claims as HTTP headers for
  cockpit-ws

### cockpit.conf

```ini
{{#include ../features/caddy-authcrunch-cockpit-tutorial/bundle/files/cockpit/cockpit.conf}}
```

Key points:

- `AllowUnencrypted = true` because TLS terminates at Caddy
- `LoginTo = false` disables the host selector (single-device mode)
- `UrlRoot = /cockpit/` matches the Caddy route prefix
- The `[bearer]` section tells cockpit-ws to invoke the auth script for
  requests with Bearer tokens

### cockpit-bearer-auth

```python
{{#include ../features/caddy-authcrunch-cockpit-tutorial/bundle/files/cockpit/cockpit-bearer-auth}}
```

The script:

1. Sends a `*` challenge to cockpit-ws via the cockpit authorize protocol
2. Receives the Bearer token from the response
3. Validates the HS256 JWT signature using `JWT_SHARED_KEY`
4. Checks token expiration
5. Maps `authp/admin` to the `admin` user and `authp/user` to `viewer`
6. Execs `cockpit-bridge` as the mapped user via `runuser`

Uses only Python stdlib -- no pip dependencies required.

### Containerfile

```dockerfile
{{#include ../features/caddy-authcrunch-cockpit-tutorial/bundle/files/cockpit/Containerfile}}
```

The upstream `quay.io/cockpit/ws` image is Fedora minimal without Python.
This custom image adds `python3` so the bearer auth script can run.

## Building and Applying

Package the bundle as a tarball:

```bash
cp config.example.toml config.toml
# Edit config.toml with your values
tar -czf config.tar.gz config.toml files/
```

Apply to the device using the bootstrap server or USB provisioning. See
[Provisioning](../provisioning.md) for details.

## Cockpit-Podman

The Cockpit Podman integration (`cockpit-podman`) lets operators manage
containers through the Cockpit UI. This requires `cockpit-podman` to be
installed on the host (in the NixOS closure), which is a base image change.

A NixOS module sketch for adding cockpit-podman:

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
