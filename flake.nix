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

      developmentMode = builtins.getEnv "DEVELOPMENT" == "1";
      developmentAdminPasswordHashFile = builtins.getEnv "ADMIN_PASSWORD_HASH_FILE";

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
        specialArgs = {
          inherit self developmentMode developmentAdminPasswordHashFile;
        };
      };

      nixosConfigurations.rock64-qemu = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/hardware-qemu.nix
        ];
        specialArgs = {
          inherit self developmentMode developmentAdminPasswordHashFile;
        };
      };

      # ── Package outputs ────────────────────────────────────────────────────

      packages.${system} = {
        # Custom U-Boot with SPI flash env + RAUC A/B bootmeth
        uboot = pkgs.callPackage ./nix/uboot.nix { };

        # Userspace U-Boot env tools built from the same U-Boot source/version
        # as the Rock64 bootloader, to avoid env format mismatches.
        uboot-env-tools = pkgs.buildUBoot {
          defconfig = "rock64-rk3328_defconfig";
          src = self.packages.${system}.uboot.src;
          version = self.packages.${system}.uboot.version;
          extraConfig = self.packages.${system}.uboot.extraConfig;
          extraPatches = self.packages.${system}.uboot.patches or [ ];
          installDir = "$out/bin";
          hardeningDisable = [ ];
          dontStrip = false;
          crossTools = true;
          BL31 = "${pkgs.armTrustedFirmwareRK3328}/bl31.elf";
          extraMakeFlags = [
            "HOST_TOOLS_ALL=y"
            "NO_SDL=1"
            "cross_tools"
            "envtools"
          ];
          filesToInstall = [
            "tools/env/fw_printenv"
          ];
          postInstall = ''
            ln -s "$out/bin/fw_printenv" "$out/bin/fw_setenv"
          '';
        };

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
          bootScript = self.packages.${system}.boot-script;
          signingCert = ./certs/dev.signing.cert.pem;
          signingKeyPath = ./certs/dev.signing.key.pem;
          caCert = ./certs/dev.ca.cert.pem;
        };

        # U-Boot boot script compiled for Rock64
        boot-script = pkgs.callPackage ./nix/boot-script.nix {
          # Embed squashfs store hash so U-Boot prints a build ID on serial
          buildId = builtins.substring 0 32 (baseNameOf (toString self.packages.${system}.squashfs));
          systemClosure = rock64Config.system.build.toplevel;
        };

        # Flashable disk image for eMMC provisioning
        # Flash with: dd if=result-image/atomixos-<nixos-series>.img of=/dev/mmcblkN bs=4M
        # Or use a tool like Etcher.
        image = pkgs.callPackage ./nix/image.nix {
          nixosConfig = rock64Config;
          squashfsImage = self.packages.${system}.squashfs;
          bootScript = self.packages.${system}.boot-script;
          ubootRock64 = self.packages.${system}.uboot;
        };
      };

      # Expose aarch64-linux packages on aarch64-darwin so `nix build .#image`
      # works from macOS. Nix delegates the actual build to the linux-builder
      # (configured in nix-darwin). Without this, `nix build .#image` on macOS
      # looks for packages.aarch64-darwin.image which doesn't exist.
      packages."aarch64-darwin" = self.packages.${system};

      # ── Tests ────────────────────────────────────────────────────────────

      checks =
        let
          # Common args for all RAUC tests
          raucTestArgs = {
            inherit pkgs self;
            raucModule = ./modules/rauc.nix;
            qemuModule = ./modules/hardware-qemu.nix;
          };

          # Drop "kvm" from requiredSystemFeatures so tests can run under
          # TCG (software emulation) in environments without /dev/kvm.
          dropKvm =
            base:
            base.overrideTestDerivation (prev: {
              requiredSystemFeatures = builtins.filter (f: f != "kvm") (prev.requiredSystemFeatures or [ ]);
            });
          # Common args for firewall/network tests (no RAUC modules needed)
          netTestArgs = {
            inherit pkgs self;
            qemuModule = ./modules/hardware-qemu.nix;
          };

          # All test derivations (system-independent — hostPkgs assigned below)
          raucTests = {
            rauc-slots = import ./nix/tests/rauc-slots.nix raucTestArgs;
            rauc-update = import ./nix/tests/rauc-update.nix raucTestArgs;
            rauc-rollback = import ./nix/tests/rauc-rollback.nix raucTestArgs;
            rauc-confirm = import ./nix/tests/rauc-confirm.nix raucTestArgs;
            rauc-power-loss = import ./nix/tests/rauc-power-loss.nix raucTestArgs;
            rauc-watchdog = import ./nix/tests/rauc-watchdog.nix raucTestArgs;
          };

          netTests = {
            firewall = import ./nix/tests/firewall.nix netTestArgs;
            network-isolation = import ./nix/tests/network-isolation.nix netTestArgs;
            ssh-wan-toggle = import ./nix/tests/ssh-wan-toggle.nix netTestArgs;
          };

          allTests = raucTests // netTests;

          # Linux checks — run under TCG (software emulation), no KVM needed.
          # Use: nix build .#checks.aarch64-linux.rauc-slots
          linuxChecks = builtins.mapAttrs (_: dropKvm) allTests;

          # Darwin checks — test driver runs natively on macOS using
          # Apple Virtualization Framework (apple-virt). The linux-builder
          # builds the VM system closures; QEMU runs on the Mac host.
          # Use: nix build .#checks.aarch64-darwin.rauc-slots
          darwinPkgs = import nixpkgs { system = "aarch64-darwin"; };
          darwinRaucTestArgs = raucTestArgs // {
            hostPkgs = darwinPkgs;
          };
          darwinNetTestArgs = netTestArgs // {
            hostPkgs = darwinPkgs;
          };
          darwinTests = {
            rauc-slots = import ./nix/tests/rauc-slots.nix darwinRaucTestArgs;
            rauc-update = import ./nix/tests/rauc-update.nix darwinRaucTestArgs;
            rauc-rollback = import ./nix/tests/rauc-rollback.nix darwinRaucTestArgs;
            rauc-confirm = import ./nix/tests/rauc-confirm.nix darwinRaucTestArgs;
            rauc-power-loss = import ./nix/tests/rauc-power-loss.nix darwinRaucTestArgs;
            rauc-watchdog = import ./nix/tests/rauc-watchdog.nix darwinRaucTestArgs;
            firewall = import ./nix/tests/firewall.nix darwinNetTestArgs;
            network-isolation = import ./nix/tests/network-isolation.nix darwinNetTestArgs;
            ssh-wan-toggle = import ./nix/tests/ssh-wan-toggle.nix darwinNetTestArgs;
          };
        in
        {
          ${system} = linuxChecks;
          "aarch64-darwin" = darwinTests;
        };

      # ── QEMU VM for development ───────────────────────────────────────────

      # Quick access: nix run .#rock64-qemu-vm
      apps.${system}.rock64-qemu-vm = {
        type = "app";
        program = "${self.nixosConfigurations.rock64-qemu.config.system.build.vm}/bin/run-nixos-vm";
      };

      # ── Development shell ────────────────────────────────────────────────

      devShells.${system}.default = pkgs.mkShell {
        packages = [ pkgs.mdbook ];
      };

      devShells."aarch64-darwin".default =
        let
          darwinPkgs = import nixpkgs { system = "aarch64-darwin"; };
        in
        darwinPkgs.mkShell {
          packages = [ darwinPkgs.mdbook ];
        };
    };
}
