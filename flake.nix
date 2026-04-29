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

      mkDocsToolchain =
        pkgsFor:
        let
          mkReleaseTool =
            {
              pname,
              version,
              repo,
              binaries,
              platforms,
            }:
            pkgsFor.stdenvNoCC.mkDerivation {
              inherit pname version;
              src = pkgsFor.fetchurl {
                url = "https://github.com/${repo}/releases/download/v${version}/${
                  platforms.${pkgsFor.stdenv.hostPlatform.system}.asset
                }";
                hash = platforms.${pkgsFor.stdenv.hostPlatform.system}.hash;
              };
              dontUnpack = true;
              dontConfigure = true;
              dontBuild = true;
              installPhase = ''
                runHook preInstall
                mkdir -p "$out/bin"
                tmpdir=$(mktemp -d)
                tar -xzf "$src" -C "$tmpdir"
                ${builtins.concatStringsSep "\n                " (
                  map (bin: ''install -m755 "$tmpdir/${bin}" "$out/bin/${bin}"'') binaries
                )}
                runHook postInstall
              '';
              meta.platforms = builtins.attrNames platforms;
            };

          mdbook = mkReleaseTool {
            pname = "mdbook";
            version = "0.5.2";
            repo = "rust-lang/mdBook";
            binaries = [ "mdbook" ];
            platforms = {
              aarch64-darwin = {
                asset = "mdbook-v0.5.2-aarch64-apple-darwin.tar.gz";
                hash = "sha256-2i9VZT6W4/bhxT4uE+kcwM+86KuXHC4N55LA8fjSQiI=";
              };
              aarch64-linux = {
                asset = "mdbook-v0.5.2-aarch64-unknown-linux-musl.tar.gz";
                hash = "sha256-+yKb/caN1sk2kuZMUCpnqNPS/DXDfGH8cnaIQ+ZHat0=";
              };
            };
          };

          mdbook-mermaid = mkReleaseTool {
            pname = "mdbook-mermaid";
            version = "0.17.0";
            repo = "badboy/mdbook-mermaid";
            binaries = [ "mdbook-mermaid" ];
            platforms = {
              aarch64-darwin = {
                asset = "mdbook-mermaid-v0.17.0-aarch64-apple-darwin.tar.gz";
                hash = "sha256-bkprt0I6A9aML1hpv+fT6rM5MERSEpd5qdmr5MUQA08=";
              };
              aarch64-linux = {
                asset = "mdbook-mermaid-v0.17.0-aarch64-unknown-linux-musl.tar.gz";
                hash = "sha256-NywujvH1n2XkCIdRfs81NYfDww+39JEeLsJQ4Mph2AY=";
              };
            };
          };
        in
        [
          mdbook
          mdbook-mermaid
          pkgsFor.nixfmt
        ];

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
          inherit self developmentMode;
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
          inherit self developmentMode;
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
            initrd-fresh-flash-marker = import ./nix/tests/initrd-fresh-flash-marker.nix {
              inherit pkgs self;
            };
            first-boot-provision = import ./nix/tests/first-boot-provision.nix netTestArgs;
            first-boot-source-discovery = import ./nix/tests/first-boot-source-discovery.nix netTestArgs;
            forensics-mount-selection = import ./nix/tests/forensics-mount-selection.nix netTestArgs;
            forensics-ordering = import ./nix/tests/forensics-ordering.nix netTestArgs;
            forensics-podman-log-path = import ./nix/tests/forensics-podman-log-path.nix netTestArgs;
            forensics-persistence = import ./nix/tests/forensics-persistence.nix netTestArgs;
            forensics-readback = import ./nix/tests/forensics-readback.nix netTestArgs;
            forensics-rsyslog-path = import ./nix/tests/forensics-rsyslog-path.nix netTestArgs;
            forensics-rsyslog-buffering = import ./nix/tests/forensics-rsyslog-buffering.nix netTestArgs;
            forensics-shutdown-flush = import ./nix/tests/forensics-shutdown-flush.nix netTestArgs;
            forensics-rollover = import ./nix/tests/forensics-rollover.nix netTestArgs;
            forensics-slot-transition = import ./nix/tests/forensics-slot-transition.nix netTestArgs;
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
            initrd-fresh-flash-marker = import ./nix/tests/initrd-fresh-flash-marker.nix {
              inherit self;
              pkgs = darwinPkgs;
              hostPkgs = darwinPkgs;
            };
            first-boot-provision = import ./nix/tests/first-boot-provision.nix darwinNetTestArgs;
            first-boot-source-discovery = import ./nix/tests/first-boot-source-discovery.nix darwinNetTestArgs;
            forensics-mount-selection = import ./nix/tests/forensics-mount-selection.nix darwinNetTestArgs;
            forensics-ordering = import ./nix/tests/forensics-ordering.nix darwinNetTestArgs;
            forensics-podman-log-path = import ./nix/tests/forensics-podman-log-path.nix darwinNetTestArgs;
            forensics-persistence = import ./nix/tests/forensics-persistence.nix darwinNetTestArgs;
            forensics-readback = import ./nix/tests/forensics-readback.nix darwinNetTestArgs;
            forensics-rsyslog-path = import ./nix/tests/forensics-rsyslog-path.nix darwinNetTestArgs;
            forensics-rsyslog-buffering = import ./nix/tests/forensics-rsyslog-buffering.nix darwinNetTestArgs;
            forensics-shutdown-flush = import ./nix/tests/forensics-shutdown-flush.nix darwinNetTestArgs;
            forensics-rollover = import ./nix/tests/forensics-rollover.nix darwinNetTestArgs;
            forensics-slot-transition = import ./nix/tests/forensics-slot-transition.nix darwinNetTestArgs;
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
        packages = (mkDocsToolchain pkgs) ++ [ pkgs.zsh ];
        shellHook = ''
          case $- in
            *i*)
              if [ -z "''${IN_NIX_ZSH:-}" ] && [ -z "''${ZSH_VERSION:-}" ]; then
                export IN_NIX_ZSH=1
                exec ${pkgs.zsh}/bin/zsh -i
              fi
              ;;
          esac
        '';
      };

      devShells."aarch64-darwin".default =
        let
          darwinPkgs = import nixpkgs { system = "aarch64-darwin"; };
        in
        darwinPkgs.mkShell {
          packages = (mkDocsToolchain darwinPkgs) ++ [ darwinPkgs.zsh ];
          shellHook = ''
            case $- in
              *i*)
                if [ -z "''${IN_NIX_ZSH:-}" ] && [ -z "''${ZSH_VERSION:-}" ]; then
                  export IN_NIX_ZSH=1
                  exec ${darwinPkgs.zsh}/bin/zsh -i
                fi
                ;;
            esac
          '';
        };
    };
}
