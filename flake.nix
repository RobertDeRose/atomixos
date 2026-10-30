{
  description = "Rock64 A/B image - NixOS-based OTA-updatable edge gateway";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    nixstasis.url = "github:RobertDeRose/nixstasis/5d9f74e3fb770d503653301a07e7c628f1dd169c";
  };

  outputs =
    {
      self,
      nixpkgs,
      nixstasis,
      ...
    }:
    let
      system = "aarch64-linux";

      # ── Closure size overlay ──────────────────────────────────────────────
      # Override packages to strip unnecessary transitive dependencies that
      # bloat the read-only squashfs image.
      embeddedOverlay = _final: prev: {
        # Build crun without CRIU support — removes criu (+ python3 ~102 MB)
        # from the runtime closure. CRIU checkpoint/restore is not needed on
        # an embedded gateway.
        crun = prev.crun.overrideAttrs (old: {
          buildInputs = builtins.filter (p: p.pname or "" != "criu") (old.buildInputs or [ ]);
          configureFlags = (old.configureFlags or [ ]) ++ [ "--disable-criu" ];
          env = (old.env or { }) // {
            NIX_LDFLAGS = builtins.replaceStrings [ "-lcriu" ] [ "" ] (old.env.NIX_LDFLAGS or "");
          };
        });
      };

      pkgs = import nixpkgs {
        inherit system;
        overlays = [ embeddedOverlay ];
      };

      buildConfigurationEvaluator = import ./nix/build-policy.nix {
        lib = nixpkgs.lib;
      };
      buildDevConfigPath = builtins.getEnv "ATOMIXOS_BUILD_DEV_CONFIG";
      effectiveBuildConfig = buildConfigurationEvaluator.evaluate {
        baseName = "build.toml";
        baseText = builtins.readFile ./build.toml;
        overlayName = "build.dev.toml";
        overlayText = if buildDevConfigPath == "" then null else builtins.readFile buildDevConfigPath;
      };
      partitionLayout = import ./nix/partition-layout.nix;

      # Userspace fw_printenv/fw_setenv built from the same U-Boot source,
      # version, and environment config as the board bootloader. Only the
      # cross_tools/envtools targets are built, so no BL31/TPL firmware is needed.
      mkUbootEnvTools =
        uboot:
        pkgs.buildUBoot {
          inherit (uboot) defconfig;
          src = uboot.src;
          version = uboot.version;
          extraConfig = uboot.extraConfig;
          extraPatches = uboot.patches or [ ];
          installDir = "$out/bin";
          hardeningDisable = [ ];
          dontStrip = false;
          crossTools = true;
          extraMakeFlags = [
            "HOST_TOOLS_ALL=y"
            "NO_SDL=1"
            "cross_tools"
            "envtools"
          ];
          filesToInstall = [ "tools/env/fw_printenv" ];
          postInstall = ''
            ln -s "$out/bin/fw_printenv" "$out/bin/fw_setenv"
          '';
        };

      developmentMode = builtins.getEnv "DEVELOPMENT" == "1";

      # Shared module that applies the overlay to NixOS configurations
      overlayModule =
        { ... }:
        {
          nixpkgs.overlays = [ embeddedOverlay ];
        };

      # Per-board inputs to the artifact chain. Everything else (DTB path, RAUC
      # slots and compatible, system closure) comes from the board's NixOS config.
      boards = {
        rock64 = {
          nixosConfig = self.nixosConfigurations.rock64.config;
          uboot = pkgs.callPackage ./nix/uboot.nix { };
          bootScript = {
            bootargsBase = "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xff130000 loglevel=7 rootwait";
            recoveryButtonPin = "100";
            # Move initrd clear of the relocated kernel (default 0x06000000 overlaps it).
            ramdiskAddr = "0x08000000";
          };
        };
        # Radxa CM3 on its IO board (RK3566; different U-Boot/firmware/DTB).
        cm3 = {
          nixosConfig = self.nixosConfigurations.cm3.config;
          uboot = pkgs.callPackage ./nix/uboot-cm3.nix { };
          bootScript = {
            bootargsBase = "console=ttyS2,1500000 earlycon=uart8250,mmio32,0xfe660000 loglevel=7 rootwait";
            recoveryButtonPin = ""; # no ROCK64 reset-button GPIO on CM3
            ramdiskAddr = ""; # keep RK3568 U-Boot defaults (kernel 0x02000000, initrd 0x12180000)
          };
        };
      };

      # One board's artifact chain as a single derivation: building it links the
      # shipped artifacts into subdirectories ($out/image, $out/rauc-bundle, ...),
      # and every artifact stays buildable on its own as an attribute (.#cm3.image).
      mkBoardPackages =
        board:
        {
          nixosConfig,
          uboot,
          bootScript,
        }:
        let
          # U-Boot env tools from the same source/version as the bootloader, to
          # avoid env format mismatches.
          ubootEnvTools = mkUbootEnvTools uboot;
          squashfs = pkgs.callPackage ./nix/squashfs.nix {
            inherit nixosConfig maxSquashfsSize;
          };
          bootScriptPackage = pkgs.callPackage ./nix/boot-script.nix (
            {
              inherit nixosConfig;
              # Embed the squashfs store hash so U-Boot prints a build ID on serial.
              buildId = builtins.substring 0 32 (baseNameOf (toString squashfs));
            }
            // bootScript
          );
          # Shared boot-slot filesystem consumed by factory and update artifacts.
          bootPartition = pkgs.callPackage ./nix/boot-partition.nix {
            inherit nixosConfig partitionLayout;
            bootScript = bootScriptPackage;
          };
          artifacts = {
            # U-Boot with persistent env + RAUC A/B bootmeth, and its env tools.
            inherit uboot squashfs;
            uboot-env-tools = ubootEnvTools;
            boot-script = bootScriptPackage;
            boot-partition = bootPartition;
            # Signed RAUC bundle (boot + rootfs). Uses the committed development
            # signing keys; override signingCert/signingKeyPath for production.
            rauc-bundle = pkgs.callPackage ./nix/rauc-bundle.nix {
              inherit nixosConfig bootPartition;
              buildConfiguration = effectiveBuildConfig;
              squashfsImage = squashfs;
              signingCert = ./certs/dev.signing.cert.pem;
              signingKeyPath = ./certs/dev.signing.key.pem;
            };
            # Flashable eMMC disk image.
            image = pkgs.callPackage ./nix/image.nix {
              inherit
                nixosConfig
                bootPartition
                uboot
                partitionLayout
                ;
              buildConfiguration = effectiveBuildConfig;
              squashfsImage = squashfs;
            };
          };
          # The board package links what is flashed, shipped, or needed on the host;
          # squashfs and boot-partition are already inside the image and bundle, so
          # they stay attributes only and retained roots do not pin them twice.
          shipped = removeAttrs artifacts [
            "squashfs"
            "boot-partition"
          ];
        in
        pkgs.linkFarm "atomixos-${board}" shipped // artifacts;

      # Maximum squashfs image size (1 GB)
      # NixOS + Podman + systemd baseline is ~450-500 MB compressed.
      # 1 GB provides headroom for future additions.
      maxSquashfsSize = partitionLayout.rootfs.sizeMiB * 1024 * 1024;

      bundleTestVmModule =
        { lib, pkgs, ... }:
        let
          bundleTestSerialGetty = pkgs.writeShellScript "bundle-test-serial-getty" ''
            set -eu
            tty="$1"
            term="''${2:-vt220}"
            autologin_user=admin
            if grep -qw 'atomixos.bundle-test.root-debug=1' /proc/cmdline; then
              autologin_user=root
            fi
            exec ${lib.getExe' pkgs.util-linux "agetty"} \
              --login-program ${pkgs.shadow}/bin/login \
              --issue-file /etc/issue:/etc/issue.d:/run/issue:/run/issue.d \
              --autologin "$autologin_user" \
              "$tty" --keep-baud "$term"
          '';
        in
        {
          virtualisation = {
            memorySize = 4096;
            diskSize = 8192;
            writableStore = true;
            qemu.options = [
              "-smp 4"
              "-nographic"
              "-netdev user,id=lan.0,net=172.20.30.0/24,dhcpstart=172.20.30.10,hostfwd=tcp:127.0.0.1:8080-172.20.30.1:8080"
              "-device virtio-net-pci,netdev=lan.0,mac=52:54:00:12:30:01"
            ];
          };

          networking.hostName = lib.mkForce "gateway";
          services.getty.autologinUser = lib.mkForce "admin";
          systemd.services."serial-getty@".serviceConfig.ExecStart = lib.mkForce [
            ""
            "${bundleTestSerialGetty} %I $TERM"
          ];
          atonic.firewall.extraInputRules = ''
            tcp dport { 22, 80, 443 } accept comment "bundle-test forwarded WAN services"
          '';

          environment.systemPackages = [ pkgs.curl ];
        };
    in
    {
      lib.effectiveBuildConfiguration = effectiveBuildConfig;

      # ── NixOS system configurations ────────────────────────────────────────

      nixosConfigurations.rock64 = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/build-configuration.nix
          ./modules/hardware-rock64.nix
        ];
        specialArgs = {
          inherit
            self
            developmentMode
            effectiveBuildConfig
            nixstasis
            ;
        };
      };

      nixosConfigurations.cm3 = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/build-configuration.nix
          ./modules/hardware-cm3.nix
        ];
        specialArgs = {
          inherit
            self
            developmentMode
            effectiveBuildConfig
            nixstasis
            ;
        };
      };

      nixosConfigurations.rock64-qemu = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          overlayModule
          ./modules/base.nix
          ./modules/build-configuration.nix
          ./modules/hardware-qemu.nix
        ];
        specialArgs = {
          inherit
            self
            developmentMode
            effectiveBuildConfig
            nixstasis
            ;
        };
      };

      nixosConfigurations.bundle-test-vm = nixpkgs.lib.nixosSystem {
        inherit system;
        modules = [
          "${nixpkgs}/nixos/modules/virtualisation/qemu-vm.nix"
          overlayModule
          ./modules/base.nix
          ./modules/build-configuration.nix
          ./modules/hardware-qemu.nix
          bundleTestVmModule
        ];
        specialArgs = {
          inherit
            self
            developmentMode
            effectiveBuildConfig
            nixstasis
            ;
        };
      };

      # ── Package outputs ────────────────────────────────────────────────────

      # One package per board (rock64, cm3); see mkBoardPackages.
      packages.${system} = builtins.mapAttrs mkBoardPackages boards;

      # Expose aarch64-linux packages on aarch64-darwin so `nix build .#cm3`
      # works from macOS. Nix delegates the actual build to the linux-builder
      # (configured in nix-darwin). Without this, `nix build .#cm3` on macOS
      # looks for packages.aarch64-darwin.cm3 which doesn't exist.
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
            provisioning-export = import ./nix/tests/provisioning-export.nix netTestArgs;
            first-boot-source-discovery = import ./nix/tests/first-boot-source-discovery.nix netTestArgs;
            nixstasis-module = import ./nix/tests/nixstasis-module.nix netTestArgs;
            nixstasis-client = import ./nix/tests/nixstasis-client.nix netTestArgs;
            fleet-bootstrap = import ./nix/tests/fleet-bootstrap.nix netTestArgs;
            watchdog-module = import ./nix/tests/watchdog-module.nix netTestArgs;
            watchdog-missing-device = import ./nix/tests/watchdog-missing-device.nix netTestArgs;
            forensics-podman-log-path = import ./nix/tests/forensics-podman-log-path.nix netTestArgs;
            forensics-rsyslog-path = import ./nix/tests/forensics-rsyslog-path.nix netTestArgs;
            forensics-rsyslog-buffering = import ./nix/tests/forensics-rsyslog-buffering.nix netTestArgs;
            forensics-shutdown-flush = import ./nix/tests/forensics-shutdown-flush.nix netTestArgs;
            chrony-wan-recovery = import ./nix/tests/chrony-wan-recovery.nix netTestArgs;
            network-isolation = import ./nix/tests/network-isolation.nix netTestArgs;
            kernel-security = import ./nix/tests/kernel-security.nix netTestArgs;
            interface-naming = import ./nix/tests/interface-naming.nix netTestArgs;
            rootless-storage = import ./nix/tests/rootless-storage.nix netTestArgs;
            ssh-host-keys = import ./nix/tests/ssh-host-keys.nix netTestArgs;
            ssh-wan-toggle = import ./nix/tests/ssh-wan-toggle.nix netTestArgs;
          };

          allTests = raucTests // netTests;
          evalChecks = {
            cm3-board = import ./nix/tests/cm3-board.nix netTestArgs;
            boot-script = import ./nix/tests/boot-script.nix netTestArgs;
            boot-partition-size = import ./nix/tests/boot-partition-size.nix netTestArgs;
            uboot-scripts = import ./nix/tests/uboot-scripts.nix netTestArgs;
            device-tree-overlay = import ./nix/tests/device-tree-overlay.nix netTestArgs;
            build-config-workflow = import ./nix/tests/build-config-workflow.nix netTestArgs;
            os-upgrade-query = import ./nix/tests/os-upgrade-query.nix netTestArgs;
            build-configuration = import ./nix/tests/build-configuration.nix netTestArgs;
            e2e-launcher = import ./nix/tests/e2e-launcher.nix netTestArgs;
            lan-defaults = import ./nix/tests/lan-defaults.nix netTestArgs;
            partition-layout = import ./nix/tests/partition-layout.nix netTestArgs;
            nixstasis-module = import ./nix/tests/nixstasis-module.nix netTestArgs;
            watchdog-module = import ./nix/tests/watchdog-module.nix netTestArgs;
          };

          # Linux checks — run under TCG (software emulation), no KVM needed.
          # Use: nix build .#checks.aarch64-linux.rauc-slots
          linuxChecks = (builtins.mapAttrs (_: dropKvm) allTests) // evalChecks;

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
            cm3-board = import ./nix/tests/cm3-board.nix darwinNetTestArgs;
            boot-partition-size = import ./nix/tests/boot-partition-size.nix darwinNetTestArgs;
            uboot-scripts = import ./nix/tests/uboot-scripts.nix darwinNetTestArgs;
            device-tree-overlay = import ./nix/tests/device-tree-overlay.nix darwinNetTestArgs;
            build-config-workflow = import ./nix/tests/build-config-workflow.nix darwinNetTestArgs;
            os-upgrade-query = import ./nix/tests/os-upgrade-query.nix darwinNetTestArgs;
            build-configuration = import ./nix/tests/build-configuration.nix darwinNetTestArgs;
            e2e-launcher = import ./nix/tests/e2e-launcher.nix darwinNetTestArgs;
            lan-defaults = import ./nix/tests/lan-defaults.nix darwinNetTestArgs;
            partition-layout = import ./nix/tests/partition-layout.nix darwinNetTestArgs;
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
            provisioning-export = import ./nix/tests/provisioning-export.nix darwinNetTestArgs;
            first-boot-source-discovery = import ./nix/tests/first-boot-source-discovery.nix darwinNetTestArgs;
            nixstasis-module = import ./nix/tests/nixstasis-module.nix darwinNetTestArgs;
            nixstasis-client = import ./nix/tests/nixstasis-client.nix darwinNetTestArgs;
            fleet-bootstrap = import ./nix/tests/fleet-bootstrap.nix darwinNetTestArgs;
            watchdog-module = import ./nix/tests/watchdog-module.nix darwinNetTestArgs;
            watchdog-missing-device = import ./nix/tests/watchdog-missing-device.nix darwinNetTestArgs;
            forensics-podman-log-path = import ./nix/tests/forensics-podman-log-path.nix darwinNetTestArgs;
            forensics-rsyslog-path = import ./nix/tests/forensics-rsyslog-path.nix darwinNetTestArgs;
            forensics-rsyslog-buffering = import ./nix/tests/forensics-rsyslog-buffering.nix darwinNetTestArgs;
            forensics-shutdown-flush = import ./nix/tests/forensics-shutdown-flush.nix darwinNetTestArgs;
            chrony-wan-recovery = import ./nix/tests/chrony-wan-recovery.nix darwinNetTestArgs;
            network-isolation = import ./nix/tests/network-isolation.nix darwinNetTestArgs;
            kernel-security = import ./nix/tests/kernel-security.nix darwinNetTestArgs;
            rootless-storage = import ./nix/tests/rootless-storage.nix darwinNetTestArgs;
            ssh-wan-toggle = import ./nix/tests/ssh-wan-toggle.nix darwinNetTestArgs;
          };
        in
        {
          ${system} = linuxChecks;
          "aarch64-darwin" = darwinTests;
        };

      # ── QEMU VM for development ───────────────────────────────────────────

      apps.${system} = {
        # Quick access: nix run .#rock64-qemu-vm
        rock64-qemu-vm = {
          type = "app";
          program = "${self.nixosConfigurations.rock64-qemu.config.system.build.vm}/bin/run-nixos-vm";
        };

        bundle-test-vm = {
          type = "app";
          program = "${self.nixosConfigurations.bundle-test-vm.config.system.build.vm}/bin/run-gateway-vm";
        };
      };
    };
}
