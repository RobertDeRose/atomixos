{
  description = "Rock64 A/B image - NixOS-based OTA-updatable edge gateway";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";
  };

  outputs =
    { self, nixpkgs, ... }:
    let
      system = "aarch64-linux";

      # ── Closure size overlay ──────────────────────────────────────────────
      # Override packages to strip unnecessary transitive dependencies that
      # bloat the read-only squashfs image.
      embeddedOverlay = final: prev: {
        # Build crun without CRIU support — removes criu (+ python3 ~102 MB)
        # from the runtime closure. CRIU checkpoint/restore is not needed on
        # an embedded gateway.
        crun = prev.crun.overrideAttrs (old: {
          buildInputs = builtins.filter (p: p.pname or "" != "criu") (old.buildInputs or [ ]);
          configureFlags = (old.configureFlags or [ ]) ++ [ "--disable-criu" ];
          NIX_LDFLAGS = builtins.replaceStrings [ "-lcriu" ] [ "" ] (old.NIX_LDFLAGS or "");
        });
      };

      pkgs = import nixpkgs {
        inherit system;
        overlays = [ embeddedOverlay ];
      };

      # Shared module that applies the overlay to NixOS configurations
      overlayModule =
        { ... }:
        {
          nixpkgs.overlays = [ embeddedOverlay ];
        };

      # Build the NixOS system for the Rock64
      rock64System = self.nixosConfigurations.rock64;
      rock64Config = rock64System.config;

      # Maximum squashfs image size (1 GB)
      # NixOS + Podman + systemd baseline is ~450-500 MB compressed.
      # 1 GB provides headroom for future additions.
      maxSquashfsSize = 1024 * 1024 * 1024;
    in
    {
      # ── NixOS system configurations ────────────────────────────────────────

      nixosConfigurations.rock64 = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/hardware-rock64.nix
        ];
        specialArgs = { inherit self; };
      };

      nixosConfigurations.rock64-qemu = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/hardware-qemu.nix
        ];
        specialArgs = { inherit self; };
      };

      # ── Package outputs ────────────────────────────────────────────────────

      packages.${system} = {
        # Squashfs root filesystem image
        squashfs = pkgs.callPackage ./nix/squashfs.nix {
          nixosConfig = rock64Config;
          inherit maxSquashfsSize;
        };

        # Signed RAUC bundle (multi-slot: boot + rootfs)
        # Uses development signing keys by default (committed to repo).
        # For production: override signingCert/signingKeyPath with production keys.
        rauc-bundle = pkgs.callPackage ./nix/rauc-bundle.nix {
          nixosConfig = rock64Config;
          squashfsImage = self.packages.${system}.squashfs;
          signingCert = ./certs/dev.signing.cert.pem;
          signingKeyPath = ./certs/dev.signing.key.pem;
          caCert = ./certs/dev.ca.cert.pem;
        };

        # U-Boot boot script compiled for Rock64
        boot-script = pkgs.callPackage ./nix/boot-script.nix { };

        # Flashable disk image for eMMC provisioning
        # Flash with: dd if=result-image/rock64.img of=/dev/mmcblkN bs=4M
        # Or use a tool like Etcher.
        image = pkgs.callPackage ./nix/image.nix {
          nixosConfig = rock64Config;
          squashfsImage = self.packages.${system}.squashfs;
          bootScript = self.packages.${system}.boot-script;
        };
      };

      # ── QEMU VM for development ───────────────────────────────────────────

      # Quick access: nix run .#rock64-qemu-vm
      apps.${system}.rock64-qemu-vm = {
        type = "app";
        program = "${self.nixosConfigurations.rock64-qemu.config.system.build.vm}/bin/run-nixos-vm";
      };
    };
}
