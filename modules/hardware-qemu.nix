# QEMU aarch64-virt hardware configuration for development/testing.
# Shares all service configuration from base.nix but targets virtual hardware.
{
  config,
  lib,
  pkgs,
  ...
}:

let
  kernelConfig = import ./kernel-config.nix { inherit lib; };
in
{
  # QEMU VM runner uses a regular writable root disk, not the Rock64
  # squashfs+overlay layout from base.nix.
  fileSystems."/" = lib.mkForce {
    device = "/dev/disk/by-label/nixos";
    fsType = "ext4";
  };

  # Boot partition handling in base.nix is Rock64/eMMC-specific.
  fileSystems."/boot" = lib.mkForce {
    device = "none";
    fsType = "tmpfs";
    options = [ "mode=0755" ];
  };

  fileSystems."/persist" = lib.mkForce {
    device = "none";
    fsType = "tmpfs";
    options = [ "mode=0755" ];
    neededForBoot = false;
  };

  boot.initrd.postMountCommands = lib.mkForce "";

  environment.etc.fstab.text = lib.mkForce ''
    # QEMU VM layout
    /dev/disk/by-label/nixos / ext4 defaults 0 1
    none /boot tmpfs mode=0755 0 0
    none /persist tmpfs mode=0755 0 0
  '';

  # Persist partition provisioning is Rock64-specific.
  systemd.repart.enable = lib.mkForce false;

  # ── Boot configuration ───────────────────────────────────────────────────────

  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = true;

  # ── Kernel ───────────────────────────────────────────────────────────────────

  # Reuse the same stripped custom kernel baseline as Rock64 and add only the
  # minimal aarch64-virt support needed to boot under the NixOS QEMU test VM.
  boot.kernelPackages = pkgs.linuxPackagesFor (
    pkgs.linux_latest.override {
      enableCommonConfig = false;
      autoModules = false;
      ignoreConfigErrors = true;
    }
  );

  boot.kernelPatches = [
    {
      name = "qemu-stripped";
      patch = null;
      structuredExtraConfig =
        kernelConfig.baseKernelConfig
        // kernelConfig.optionalKernelConfig
        // (with lib.kernel; {
          # QEMU aarch64-virt platform support.
          ARCH_ROCKCHIP = lib.mkForce no;
          ARCH_VIRT = lib.mkForce yes;
          COMPILE_TEST = lib.mkForce no;

          # Generic ARM virt boot plumbing.
          OF = lib.mkForce yes;
          BLK_DEV_INITRD = lib.mkForce yes;
          RD_ZSTD = lib.mkForce yes;
          DEVTMPFS = lib.mkForce yes;
          DEVTMPFS_MOUNT = lib.mkForce yes;
          TMPFS = lib.mkForce yes;
          TMPFS_POSIX_ACL = lib.mkForce yes;

          # QEMU virt CPU/interrupt/timer/firmware path.
          ARM_PSCI_FW = lib.mkForce yes;
          ARM_GIC = lib.mkForce yes;
          ARM_GIC_V3 = lib.mkForce yes;
          ARM_ARCH_TIMER = lib.mkForce yes;

          # QEMU serial console.
          SERIAL_AMBA_PL011 = lib.mkForce yes;
          SERIAL_AMBA_PL011_CONSOLE = lib.mkForce yes;

          # PCI + virtio devices used by the NixOS test framework.
          PCI = lib.mkForce yes;
          PCI_HOST_GENERIC = lib.mkForce yes;
          VIRTIO_MENU = lib.mkForce yes;
          VIRTIO = lib.mkForce yes;
          VIRTIO_PCI = lib.mkForce yes;
          VIRTIO_BLK = lib.mkForce yes;
          VIRTIO_NET = lib.mkForce yes;
          VIRTIO_MMIO = lib.mkForce yes;
          VIRTIO_MMIO_CMDLINE_DEVICES = lib.mkForce yes;

          # Root filesystem and useful virtual-hardware helpers.
          EXT4_FS = lib.mkForce yes;
          EXT4_USE_FOR_EXT2 = lib.mkForce yes;
          RTC_DRV_PL031 = lib.mkForce yes;
          NFT_REJECT = lib.mkForce module;
          I6300ESB_WDT = lib.mkForce module;

          # Rock64-only boot paths should not be required in the VM.
          MMC = lib.mkForce no;
          MMC_DW = lib.mkForce no;
          MMC_DW_ROCKCHIP = lib.mkForce no;
          STMMAC_ETH = lib.mkForce no;
          STMMAC_PLATFORM = lib.mkForce no;
          DWMAC_ROCKCHIP = lib.mkForce no;
          # USB-net driver prompts can be processed later than the top-level
          # disables, so keep the selected PHY satisfiable until those selectors
          # collapse out.
          PHYLIB = lib.mkForce yes;
          REALTEK_PHY = lib.mkForce module;
          AX88796B_PHY = lib.mkForce module;
          BROADCOM_PHY = lib.mkForce module;
          BCM54140_PHY = lib.mkForce no;
          BCM7XXX_PHY = lib.mkForce module;
          BCM_NET_PHYLIB = lib.mkForce module;
          MARVELL_PHY = lib.mkForce no;
          MICROCHIP_PHY = lib.mkForce module;
          SMSC_PHY = lib.mkForce module;
          DP83869_PHY = lib.mkForce no;
          SPI_ROCKCHIP = lib.mkForce no;
          I2C_RK3X = lib.mkForce no;
          MFD_RK8XX_I2C = lib.mkForce no;
          REGULATOR_RK808 = lib.mkForce no;
          RTC_DRV_RK808 = lib.mkForce no;
          ROCKCHIP_THERMAL = lib.mkForce no;
          PHY_ROCKCHIP_INNO_USB2 = lib.mkForce no;
          PHY_ROCKCHIP_NANENG_COMBO_PHY = lib.mkForce no;
          DW_WATCHDOG = lib.mkForce no;

          # Keep the QEMU test image simple.
          USB_NET_DRIVERS = lib.mkForce no;
          USB_USBNET = lib.mkForce no;
          USB_NET_AX8817X = lib.mkForce no;
          USB_LAN78XX = lib.mkForce no;
          USB_DWC2 = lib.mkForce no;
          USB_DWC2_HOST = lib.mkForce no;
          USB_DWC3 = lib.mkForce no;
          USB_DWC3_HOST = lib.mkForce no;
        });
    }
  ];

  # QEMU virtio drivers
  boot.initrd.availableKernelModules = lib.mkForce [
    "virtio_pci"
    "virtio_blk"
    "virtio_net"
    "squashfs"
    "f2fs"
    "overlay"
  ];

  # The generic VM module requests extra virtio initrd modules for a graphical
  # console, but this test VM is headless and keeps DRM disabled.
  boot.initrd.kernelModules = lib.mkForce [ "dm_mod" ];

  # ── Virtual hardware ─────────────────────────────────────────────────────────

  # QEMU uses software watchdog
  # (systemd watchdog config from watchdog.nix still applies,
  #  but hardware watchdog is simulated)

  # ── RAUC slot device paths (virtio block devices) ──────────────────────────
  # When launched with the test runner (scripts/run-qemu-rauc-test.sh), QEMU
  # attaches four extra virtio-blk disks for A/B slot testing:
  #   vdb = boot A (vfat, 128 MB)
  #   vdc = boot B (vfat, 128 MB)
  #   vdd = rootfs A (1 GB)
  #   vde = rootfs B (1 GB)
  #
  # The primary disk (vda) is the NixOS root filesystem.
}
