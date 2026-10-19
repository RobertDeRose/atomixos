# Building

All build outputs target `aarch64-linux`. Builds require an `aarch64-linux` builder -- either the nix-darwin
`linux-builder` (recommended on macOS), a Lima VM, or a native Linux system.

## Prerequisites

- [Nix](https://nixos.org/download.html) with flakes enabled
- [mise](https://mise.jdx.dev/) for task running (recommended)
- An `aarch64-linux` builder (nix-darwin `linux-builder`, Lima VM, or native)

## Building with mise

```sh
# Install tools and hooks
mise install

# Run formatting, linting, and documentation checks
mise run check

# Evaluate the flake without building checks
./scripts/nix-with-build-config.sh flake check --no-build

# Build individual artifacts (--board rock64|cm3, default rock64)
mise run build:squashfs        # result-rock64-squashfs/
mise run build:rauc-bundle     # result-rock64-rauc-bundle/
mise run build:boot-script     # result-rock64-boot-script/

# Build for the default board (ROCK64)
mise run build

# Build for the CM3 with the Radxa IO board
mise run build --board cm3
```

`mise run build` accepts `--board rock64|cm3` (default: `rock64`). It validates effective build policy before touching
retained links, prepares replacements under `.new` links, and publishes them only after all builds succeed. Each board
keeps its retained links in its own folder:

| Link                        | Contents                                                                                               |
|-----------------------------|--------------------------------------------------------------------------------------------------------|
| `.gcroots/<board>/current`  | The latest `.#<board>` package: `image/`, `rauc-bundle/`, `uboot/`, `uboot-env-tools/`, `boot-script/` |
| `.gcroots/<board>/previous` | The last distinct earlier build, in the same layout                                                    |
| `.gcroots/<board>/toplevel` | The system closure, so rebuilds reuse the kernel and packages                                          |

The image is `.gcroots/<board>/current/image/atomixos-<board>-<release>.img`. Every link is a registered Nix GC root, so
`mise run gc` keeps it. Use `-o <path>` to copy the selected image.
When a local override is active, the destination filename must include `-dev`; an unmarked destination is rejected
before evaluation or retained-link mutation. A validation or later build failure leaves prior retained roots unchanged.

## Local Build Overrides

Create an ignored repository-root `build.dev.toml` to test build-policy changes before committing them. Included `mise`
tasks detect it automatically and print this warning before each affected Nix evaluation:

```text
WARNING: applying local build.dev.toml overrides; outputs will be marked -dev.
```

The overlay may contain only fields being tested. See [Build Configuration](./reference/build-configuration.md) for the
schema, watchdog backend examples, disablement behavior, and task matrix. Local-override image and bundle filenames
include `-dev`, and their metadata records `local_override` as `true`.

To promote a tested change, copy the intended values into committed `build.toml`, remove `build.dev.toml`, run
`./scripts/nix-with-build-config.sh flake check`, and rebuild. To abandon or recover from a malformed override, remove
or rename `build.dev.toml` and
rerun the command. Nix reports TOML syntax errors with source locations and schema errors with field paths; no prior
retained root is removed by validation failure.

### Verify Build Policy Evidence

Image and RAUC bundle output directories contain `build.toml` and `build-metadata.json`. Verify the lowercase SHA-256 in
metadata against the exact policy bytes:

```sh
artifact_dir=.gcroots/rock64/current/image   # or rauc-bundle, or a result-<board>-image link
nix shell nixpkgs#coreutils nixpkgs#jq -c sh -c '
  expected=$(jq -r .policy_sha256 "$1/build-metadata.json")
  printf "%s  %s\n" "$expected" "$1/build.toml" | sha256sum -c -
' _ "$artifact_dir"
```

To compare a sidecar with a running image, copy both sidecars to the device without changing them and compare bytes:

```sh
scp "$artifact_dir"/build.toml "$artifact_dir"/build-metadata.json atomixos:/tmp/
ssh atomixos \
  'cmp /tmp/build.toml /etc/atomixos/build.toml &&
   cmp /tmp/build-metadata.json /etc/atomixos/build-metadata.json'
```

The `-dev` suffix and `local_override` field describe local build-policy overrides only. They do not establish signing
trust or release readiness.

### Building via Lima VM

All build tasks accept `--lima` to run inside a Lima VM. This is useful when the Lima VM has a warm Nix store cache or
when the nix-darwin `linux-builder` is not configured.

```sh
# Build the retained artifacts inside the default Lima VM
mise run build -- --lima

# Use a specific Lima VM
mise run build -- --lima --vm my-builder

# Build CM3 via Lima
mise run build -- --board cm3 --lima
```

The task ensures the Lima VM is started before building. The macOS home directory is mounted at the same path inside
Lima, so the flake path works unchanged.

## Build Artifacts

Every Nix output below is an attribute of the board package `.#<board>` (`rock64` or `cm3`); every mise task takes
`--board` (default `rock64`).

| Artifact        | mise Task           | Nix Output              | Description                          |
|-----------------|---------------------|-------------------------|--------------------------------------|
| Shipped set     |                     | `.#<board>`             | One `result/` subdirectory each      |
| Squashfs rootfs | `build:squashfs`    | `.#<board>.squashfs`    | Compressed root filesystem (~300 MB) |
| RAUC bundle     | `build:rauc-bundle` | `.#<board>.rauc-bundle` | Signed `.raucb` for OTA updates      |
| Boot script     | `build:boot-script` | `.#<board>.boot-script` | Compiled U-Boot `boot.scr`           |
| Disk image      | `build`             | `.#<board>.image`       | `.gcroots/<board>/current/image/`    |

## Building with Nix Directly

Direct Git-backed Nix commands use committed `build.toml` only. They intentionally do not discover ignored
`build.dev.toml`; use the supported `mise` tasks when testing a local overlay.

```sh
# Build every CM3 artifact (result-cm3/image, result-cm3/rauc-bundle, ...)
nix build .#cm3 -o result-cm3

# Build only the flashable ROCK64 image
nix build .#rock64.image -o result-rock64-image

# Build only the ROCK64 squashfs
nix build .#rock64.squashfs -o result-rock64-squashfs
```

## Image Naming

The flashable image filename includes the pinned NixOS release series from `flake.nix`:

- Current: `atomixos-rock64-26.05.img` or `atomixos-cm3-26.05.img`
- Pattern: `atomixos-<board>-<series>.img` (from the board target and pinned nixpkgs series)

When you move to a new NixOS series (e.g., `nixos-26.05`), update `flake.nix`/`flake.lock` and rebuild. The image name
updates automatically.

## Squashfs Size Constraint

The squashfs image must fit within the 1 GB rootfs partition slot. The build script enforces this with a size check --
the build fails if the image exceeds the limit. The current NixOS closure compresses to approximately 300-400 MB.

To keep the closure small, the flake uses an overlay to strip unnecessary dependencies:

- `crun` is built without CRIU support (removes `criu` + `python3`, saving ~102 MB)
- Documentation, man pages, fonts, and XDG utilities are all disabled
- `security.sudo` is disabled (uses `run0` instead)
- `environment.defaultPackages` is emptied
