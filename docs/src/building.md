# Building

Every AtomixOS artifact targets `aarch64-linux`, so you need an `aarch64-linux` builder: the nix-darwin
`linux-builder` (recommended on macOS), a Lima VM, or a native Linux machine.

## Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- [mise](https://mise.jdx.dev/) for tools and tasks
- An `aarch64-linux` builder

Install the pinned tools and Git hooks once per clone:

```sh
mise install --locked
```

[Developer Tooling](development/tooling.md) covers the quality gate and hooks.

## Build with mise

```sh
# Run formatting, linting, and documentation checks
mise run check

# Evaluate the flake without building anything
./scripts/nix-with-build-config.sh flake check --no-build

# Build one artifact
mise run build:squashfs --board rock64      # result-rock64-squashfs/
mise run build:rauc-bundle --board rock64   # result-rock64-rauc-bundle/
mise run build:boot-script --board rock64   # result-rock64-boot-script/

# Build every artifact for the Rock64
mise run build --board rock64

# Build every artifact for the Radxa CM3 on the CM3 IO board
mise run build --board cm3
```

`mise run build` requires `--board rock64|cm3`; it never assumes a board, because an image built for one board writes
the wrong bootloader onto the other. It is safe to interrupt or fail:

1. It validates the effective build policy before touching any retained link.
2. It builds every replacement under a `.new` link.
3. It publishes the replacements only after all builds succeed.

A failed validation or build leaves the previous retained roots unchanged. Each board keeps its retained links in its own
folder:

| Link                        | Contents                                                                                               |
|-----------------------------|--------------------------------------------------------------------------------------------------------|
| `.gcroots/<board>/current`  | The latest `.#<board>` package: `image/`, `rauc-bundle/`, `uboot/`, `uboot-env-tools/`, `boot-script/` |
| `.gcroots/<board>/previous` | The last distinct earlier build, in the same layout                                                    |
| `.gcroots/<board>/toplevel` | The system closure, so rebuilds reuse the kernel and packages                                          |

The image is `.gcroots/<board>/current/image/atomixos-<board>-<release>.img`. Every link is a registered Nix GC root,
so `mise run gc` keeps it. Pass `-o <path>` to also copy the image to a path of your choice.

## Artifacts

Every Nix output is an attribute of the board package `.#<board>` (`rock64` or `cm3`), and every build task requires
`--board`.

| Artifact        | mise task           | Nix output              | Description                                      |
|-----------------|---------------------|-------------------------|--------------------------------------------------|
| Shipped set     | `build`             | `.#<board>`             | One subdirectory per artifact                    |
| Squashfs rootfs | `build:squashfs`    | `.#<board>.squashfs`    | Compressed read-only root filesystem             |
| RAUC bundle     | `build:rauc-bundle` | `.#<board>.rauc-bundle` | Signed `<board>.raucb` for OTA updates           |
| Boot script     | `build:boot-script` | `.#<board>.boot-script` | Compiled U-Boot `boot.scr`                       |
| Disk image      | `build`             | `.#<board>.image`       | Retained under `.gcroots/<board>/current/image/` |

[Flake Outputs](reference/flake-outputs.md) lists every output.

## Image naming

The image filename carries the board and the NixOS release series pinned in `flake.nix`:
`atomixos-<board>-<series>.img`, for example `atomixos-rock64-26.05.img` or `atomixos-cm3-26.05.img` when the flake
follows `nixos-26.05`. Moving to a new series means updating `flake.nix` and
`flake.lock`; the name follows automatically. Images and bundles built with a local override add `-dev` to the name.

## Local build overrides

To try a build-policy change before committing it, create an ignored `build.dev.toml` at the repository root. It holds
only the fields you are testing. The `mise` tasks detect it and print this warning before each Nix evaluation it
affects:

```text
WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.
```

Outputs built with an override have `-dev` in their filenames and `"local_override": true` in their metadata. When an
override is active, `mise run build --board <board> -o <path>` rejects a destination name without `-dev` before it
evaluates anything.

Direct Nix commands use the committed `build.toml` only; they never read `build.dev.toml`. Use the `mise` tasks, or
`./scripts/nix-with-build-config.sh`, to build with an override.

- **Promote a change:** copy the values into `build.toml`, delete `build.dev.toml`, run
  `./scripts/nix-with-build-config.sh flake check`, and rebuild.
- **Abandon or recover:** delete or rename `build.dev.toml` and rerun the command. Nix reports TOML syntax errors with
  the source location and schema errors with the field path. A validation failure never removes a retained root.

[Build Configuration](reference/build-configuration.md) defines the schema, the watchdog backends, and the full task
matrix.

## Verify build policy evidence

Image and RAUC bundle output directories carry `build.toml` and `build-metadata.json`. Check that the metadata's SHA-256
matches the policy bytes:

```sh
artifact_dir=.gcroots/rock64/current/image   # or rauc-bundle, or a result-<board>-image link
nix shell nixpkgs#coreutils nixpkgs#jq -c sh -c '
  expected=$(jq -r .policy_sha256 "$1/build-metadata.json")
  printf "%s  %s\n" "$expected" "$1/build.toml" | sha256sum -c -
' _ "$artifact_dir"
```

To confirm that a running device was built from the same policy, copy both files to it unchanged and compare bytes:

```sh
scp "$artifact_dir"/build.toml "$artifact_dir"/build-metadata.json atomixos:/tmp/
ssh atomixos \
  'cmp /tmp/build.toml /etc/atomixos/build.toml &&
   cmp /tmp/build-metadata.json /etc/atomixos/build-metadata.json'
```

The `-dev` suffix and `local_override` field only say that a local override was used. They say nothing about signing
trust or release readiness.

## Build in a Lima VM

Every build task accepts `--lima`. Use it when the nix-darwin `linux-builder` is not set up, or when a Lima VM already
has a warm Nix store.

```sh
# Build inside the default Lima VM
mise run build -- --board rock64 --lima

# Build inside a specific Lima VM
mise run build -- --board rock64 --lima --vm my-builder

# Build the CM3 inside the default Lima VM
mise run build -- --board cm3 --lima
```

The task starts the VM if needed. Lima mounts your macOS home directory at the same path, so the flake path works
unchanged.

## Build with Nix directly

```sh
# Build every CM3 artifact (result-cm3/image, result-cm3/rauc-bundle, ...)
nix build .#cm3 -o result-cm3

# Build only the flashable Rock64 image
nix build .#rock64.image -o result-rock64-image

# Build only the Rock64 squashfs
nix build .#rock64.squashfs -o result-rock64-squashfs
```

## Squashfs size limit

The squashfs image must fit the 1 GB rootfs slot. `scripts/build-squashfs.sh` checks the size and fails the build if the
image is too large.

To keep the closure small:

- the flake overlay builds `crun` without CRIU, which drops `criu` and `python3` (about 100 MB);
- documentation, man pages, fonts, and XDG utilities are disabled;
- `security.sudo` is disabled, and `run0` is used instead;
- `environment.defaultPackages` is empty.
