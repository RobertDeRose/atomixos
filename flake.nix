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
        # Flash with: dd if=result-image/atomixos-<nixos-series>.img of=/dev/mmcblkN bs=4M
        # Or use a tool like Etcher.
        image = pkgs.callPackage ./nix/image.nix {
          nixosConfig = rock64Config;
          squashfsImage = self.packages.${system}.squashfs;
          bootScript = self.packages.${system}.boot-script;
        };
      };

      # ── Tests ────────────────────────────────────────────────────────────

      checks.${system} =
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
          };
        in
        {
          # Verify RAUC slot logic works in QEMU with virtual block devices.
          # Boots a minimal VM with four extra virtio disks and validates
          # `rauc status` sees all A/B slot pairs.
          rauc-slots = dropKvm (import ./nix/tests/rauc-slots.nix raucTestArgs);

          # Verify RAUC bundle install switches to the inactive slot pair.
          # Builds a test bundle, installs it, and confirms the primary
          # slot switches from A to B.
          rauc-update = dropKvm (import ./nix/tests/rauc-update.nix raucTestArgs);

          # Verify RAUC rollback: install to slot B, mark B bad, verify
          # primary reverts to A. Tests the custom bootloader backend's
          # state management that underpins U-Boot boot-count rollback.
          rauc-rollback = dropKvm (import ./nix/tests/rauc-rollback.nix raucTestArgs);

          # Verify os-verification service confirms a RAUC slot after
          # successful health checks (dnsmasq, chronyd, eth0/eth1 IPs).
          # No health manifest — container checks are skipped.
          rauc-confirm = dropKvm (import ./nix/tests/rauc-confirm.nix raucTestArgs);

          # Verify power loss during RAUC install leaves the previous
          # slot intact. Crashes the VM mid-install and reboots.
          rauc-power-loss = dropKvm (import ./nix/tests/rauc-power-loss.nix raucTestArgs);

          # Verify watchdog-triggered reboot leads to RAUC rollback.
          # Freezes systemd (kill -STOP 1) to trigger the i6300esb
          # watchdog, then verifies boot-count exhaustion rolls back
          # from slot B to slot A.
          rauc-watchdog = dropKvm (import ./nix/tests/rauc-watchdog.nix raucTestArgs);

          # Verify nftables firewall rules: WAN allows HTTPS + OpenVPN,
          # LAN allows SSH + DHCP + NTP, everything else dropped.
          firewall = dropKvm (import ./nix/tests/firewall.nix netTestArgs);

          # Verify LAN devices get DHCP/NTP from gateway but cannot
          # reach WAN addresses (ip_forward=0, no routing).
          network-isolation = dropKvm (import ./nix/tests/network-isolation.nix netTestArgs);

          # Verify SSH-on-WAN toggle: flag file enables/disables SSH
          # on the WAN interface via dynamic nftables rule.
          ssh-wan-toggle = dropKvm (import ./nix/tests/ssh-wan-toggle.nix netTestArgs);
        };

      # ── QEMU VM for development ───────────────────────────────────────────

      # Quick access: nix run .#rock64-qemu-vm
      apps.${system}.rock64-qemu-vm = {
        type = "app";
        program = "${self.nixosConfigurations.rock64-qemu.config.system.build.vm}/bin/run-nixos-vm";
      };
    };
}
