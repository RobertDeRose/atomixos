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

# Check the flake evaluates cleanly
mise run check

# Build individual artifacts
mise run build:squashfs        # result-squashfs/
mise run build:rauc-bundle     # result-rauc-bundle/
mise run build:boot-script     # result-boot-script/
mise run build:image           # result-image/

# Build everything
mise run build
```

### Building via Lima VM

All build tasks accept `--lima` to run inside a Lima VM. This is useful when the Lima VM has a warm Nix store cache or
when the nix-darwin `linux-builder` is not configured.

```sh
# Build the disk image inside the default Lima VM
mise run build:image -- --lima

# Use a specific Lima VM
mise run build:image -- --lima --vm my-builder

# Build everything via Lima
mise run build -- --lima
```

The task ensures the Lima VM is started before building. The macOS home directory is mounted at the same path inside
Lima, so the flake path works unchanged.

## Build Artifacts

| Artifact        | mise Task           | Nix Output                           | Description                          |
|-----------------|---------------------|--------------------------------------|--------------------------------------|
| Squashfs rootfs | `build:squashfs`    | `packages.aarch64-linux.squashfs`    | Compressed root filesystem (~300 MB) |
| RAUC bundle     | `build:rauc-bundle` | `packages.aarch64-linux.rauc-bundle` | Signed `.raucb` for OTA updates      |
| Boot script     | `build:boot-script` | `packages.aarch64-linux.boot-script` | Compiled U-Boot `boot.scr`           |
| Disk image      | `build:image`       | `packages.aarch64-linux.image`       | Flashable eMMC image (~2.3 GB)       |

## Building with Nix Directly

```sh
# Build the flashable image
nix build .#image -o result-image

# Build only the squashfs
nix build .#squashfs -o result-squashfs
```

## Image Naming

The flashable image filename includes the pinned NixOS release series from `flake.nix`:

- Current: `atomixos-25.11.img` (from `nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11"`)
- Pattern: `atomixos-<series>.img`

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
