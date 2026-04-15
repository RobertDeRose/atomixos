# Direct eMMC Provisioning

For factory deployment, the `provision:emmc` task partitions, formats, and fully populates an eMMC module in a single
step. This includes generating per-device credentials for EN18031 compliance.

> **Requirement**: Linux host with root access. The eMMC must be attached as a block device (e.g., via USB adapter).

## Usage

```sh
mise run provision:emmc /dev/mmcblk1 \
  /path/to/uboot \
  /path/to/kernel-Image \
  /path/to/rk3328-rock64.dtb \
  /path/to/rootfs.squashfs \
  --ssh-key ~/.ssh/id_ed25519.pub
```

## What it Does

1. **Validates** all input files and checks the squashfs fits within the 1 GB slot
2. **Prompts for admin password** (minimum 8 characters, EN18031 compliant) and generates SHA-512 hash
3. **Partitions** the eMMC with GPT (4 slot partitions + persist)
4. **Writes U-Boot** to raw sectors (idbloader @ sector 64, u-boot.itb @ sector 16384)
5. **Deploys slot A** -- kernel + DTB to boot-a (vfat), squashfs to rootfs-a
6. **Creates /persist** as f2fs and populates it with:

### Provisioned Credentials

| Path                                           | Content                                             |
|------------------------------------------------|-----------------------------------------------------|
| `/persist/config/admin-password-hash`          | SHA-512 bcrypt hash of the admin password           |
| `/persist/config/ssh-authorized-keys/admin`    | Operator's SSH public key (if `--ssh-key` provided) |
| `/persist/config/traefik/traefik.yaml`         | Traefik static config (entrypoints, providers)      |
| `/persist/config/traefik/dynamic/cockpit.yaml` | Cockpit reverse proxy route                         |
| `/persist/config/traefik/dynamic/oidc.yaml`    | Forward-auth OIDC template (disabled by default)    |
| `/persist/config/traefik/certs/server.crt`     | Self-signed TLS certificate (EC P-256, 10 years)    |
| `/persist/config/traefik/certs/server.key`     | TLS private key                                     |
| `/persist/config/health-manifest.yaml`         | Container health entries (cockpit-ws, traefik)      |

## Traefik Configuration

The provisioning script generates a complete Traefik setup:

- **Entrypoints**: `:443` (websecure, TLS) and `:80` (redirect to HTTPS)
- **Cockpit route**: `PathPrefix("/cockpit")` routed to `http://127.0.0.1:9090`
- **OIDC middleware**: Forward-auth template for Microsoft Entra (disabled by default, edit to enable)
- **LAN bypass**: Clients from `172.20.30.0/24` and `127.0.0.1/8` skip OIDC and authenticate with the local password

## Validation

After writing, the script re-mounts `/persist` read-only and verifies:

- Password hash file exists and is non-empty
- SSH key file exists (if provided)
- Traefik config files exist
- TLS certificate is valid
- Health manifest is valid YAML

## Flags

| Flag               | Description                           |
|--------------------|---------------------------------------|
| `-y`, `--yes`      | Skip confirmation prompt              |
| `--ssh-key <path>` | SSH public key or path to `.pub` file |
