{
  pkgs,
  hostPkgs ? pkgs,
  self,
  ...
}:

let
  nixos-lib = import (pkgs.path + "/nixos/lib") { };
  kernelConfig = import ../../modules/kernel-config.nix { inherit (pkgs) lib; };
  qemuInitrdModule =
    { lib, pkgs, ... }:
    {
      fileSystems."/" = lib.mkForce {
        device = "/dev/disk/by-label/nixos";
        fsType = "ext4";
      };

      boot.initrd.postMountCommands = lib.mkForce "";
      boot.initrd.systemd.services.initrd-prepare-overlay-lower.enable = lib.mkForce false;
      systemd.repart.enable = lib.mkForce false;

      boot.loader.grub.enable = false;
      boot.loader.generic-extlinux-compatible.enable = true;

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
              ARCH_ROCKCHIP = lib.mkForce no;
              ARCH_VIRT = lib.mkForce yes;
              COMPILE_TEST = lib.mkForce no;
              OF = lib.mkForce yes;
              BLK_DEV_INITRD = lib.mkForce yes;
              RD_ZSTD = lib.mkForce yes;
              DEVTMPFS = lib.mkForce yes;
              DEVTMPFS_MOUNT = lib.mkForce yes;
              TMPFS = lib.mkForce yes;
              TMPFS_POSIX_ACL = lib.mkForce yes;
              ARM_PSCI_FW = lib.mkForce yes;
              ARM_GIC = lib.mkForce yes;
              ARM_GIC_V3 = lib.mkForce yes;
              ARM_ARCH_TIMER = lib.mkForce yes;
              SERIAL_AMBA_PL011 = lib.mkForce yes;
              SERIAL_AMBA_PL011_CONSOLE = lib.mkForce yes;
              PCI = lib.mkForce yes;
              PCI_HOST_GENERIC = lib.mkForce yes;
              VIRTIO_MENU = lib.mkForce yes;
              VIRTIO = lib.mkForce yes;
              VIRTIO_PCI = lib.mkForce yes;
              VIRTIO_BLK = lib.mkForce yes;
              VIRTIO_NET = lib.mkForce yes;
              VIRTIO_MMIO = lib.mkForce yes;
              VIRTIO_MMIO_CMDLINE_DEVICES = lib.mkForce yes;
              EXT4_FS = lib.mkForce yes;
              EXT4_USE_FOR_EXT2 = lib.mkForce yes;
              RTC_DRV_PL031 = lib.mkForce yes;
              NFT_REJECT = lib.mkForce module;
              I6300ESB_WDT = lib.mkForce module;
              MMC = lib.mkForce no;
              MMC_DW = lib.mkForce no;
              MMC_DW_ROCKCHIP = lib.mkForce no;
              STMMAC_ETH = lib.mkForce no;
              STMMAC_PLATFORM = lib.mkForce no;
              DWMAC_ROCKCHIP = lib.mkForce no;
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

      boot.initrd.availableKernelModules = lib.mkForce [
        "virtio_pci"
        "virtio_blk"
        "virtio_net"
        "squashfs"
        "f2fs"
        "overlay"
      ];

      boot.initrd.kernelModules = lib.mkForce [ "dm_mod" ];
      boot.supportedFilesystems = [
        "vfat"
        "f2fs"
      ];
      boot.initrd.supportedFilesystems = [
        "vfat"
        "f2fs"
      ];
    };
in
nixos-lib.runTest {
  name = "initrd-fresh-flash-marker";

  inherit hostPkgs;

  nodes.gateway =
    { lib, ... }:
    {
      imports = [
        ../../modules/base.nix
        qemuInitrdModule
      ];

      _module.args = {
        inherit self;
        developmentMode = false;
      };

      virtualisation = {
        memorySize = 1024;
        diskSize = 2048;
        emptyDiskImages = [ 4096 ];
      };

      system.stateVersion = "25.11";

      # This test only needs the initrd repartition/detection path.
      networking.firewall.enable = false;
      systemd.services.first-boot.enable = false;
      systemd.services.quadlet-sync.enable = false;
      systemd.services.os-verification.enable = false;
      atomixos.rauc = {
        bootloader = "custom";
        statusFile = "/tmp/rauc.status";
        slots = {
          boot0 = "/dev/disk/by-partlabel/boot-a";
          boot1 = "/dev/disk/by-partlabel/boot-b";
          rootfs0 = "/dev/disk/by-partlabel/rootfs-a";
          rootfs1 = "/dev/disk/by-partlabel/rootfs-b";
        };
      };

      # Point initrd repart at the extra disk, leaving the main VM disk as the
      # regular writable root filesystem.
      boot.initrd.systemd.enable = lib.mkForce true;
      boot.initrd.systemd.repart.enable = lib.mkForce true;
      boot.initrd.systemd.repart.device = lib.mkForce "/dev/vdb";
    };

  testScript = ''
    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    gateway.succeed("test -f /etc/atomixos/fresh-flash")
    gateway.succeed("journalctl -b -u systemd-repart --no-pager | grep 'Applying changes to /dev/vdb'")
    gateway.succeed("journalctl -b -u systemd-repart --no-pager | grep 'boot-b'")
    gateway.succeed("journalctl -b -u systemd-repart --no-pager | grep 'rootfs-b'")
    gateway.succeed("journalctl -b -u systemd-repart --no-pager | grep ' data '")

    gateway.succeed("sync")
    gateway.crash()

    gateway.start()
    gateway.wait_for_unit("multi-user.target")

    gateway.succeed("test ! -f /etc/atomixos/fresh-flash")

    gateway.log("initrd fresh-flash marker test passed")
  '';
}
