# Settings shared by the Rockchip boards (ROCK64/RK3328, CM3/RK3566).
# Board modules import this and add their kernel, device tree, storage paths,
# and U-Boot environment location.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  ubootEnvTools = config.atomixos.ubootEnvTools;

  serialRootDebugScript = pkgs.writeShellScript "serial-root-debug" ''
    set -euo pipefail

    env_value="$(${ubootEnvTools}/bin/fw_printenv -n _RUT_OH_ 2>/dev/null || true)"
    if [ "$env_value" != "1" ]; then
      exit 0
    fi

    ${pkgs.systemd}/bin/systemctl stop serial-getty@ttyS2.service
    ${pkgs.systemd}/bin/systemctl start serial-root-debug@ttyS2.service
    ${ubootEnvTools}/bin/fw_setenv _RUT_OH_
  '';

  # Request U-Boot USB mass storage recovery on the next boot (START_UMS PREBOOT).
  bootToUms = pkgs.writeShellScriptBin "boot_to_ums" ''
    set -euo pipefail

    echo "Setting START_UMS=1 in the U-Boot environment"
    ${ubootEnvTools}/bin/fw_setenv START_UMS 1

    echo "Rebooting so U-Boot enters USB mass storage mode"
    exec ${pkgs.systemd}/bin/systemctl reboot
  '';
in
{
  # U-Boot handles booting — no bootloader managed by NixOS
  boot.loader.grub.enable = false;
  boot.loader.generic-extlinux-compatible.enable = false;

  # Keep both stage-1 and stage-2 aware of the filesystems we provision in the
  # initrd so the required mkfs/fsck helpers are available to systemd-repart.
  boot.supportedFilesystems = [
    "vfat"
    "f2fs"
  ];
  boot.initrd.supportedFilesystems = [
    "vfat"
    "f2fs"
  ];

  # /boot is boot slot A, which RAUC overwrites when B is running, and RAUC
  # refuses to install to a mounted slot. Mount it only on access (first-boot
  # reads the fresh-flash /boot/config.toml seed) and unmount it when idle, so
  # it is not mounted during later updates.
  fileSystems."/boot".options = [
    "noauto"
    "x-systemd.automount"
    "x-systemd.idle-timeout=1min"
  ];

  # The eMMC gap before the first GPT partition holds SPL and U-Boot (and on
  # CM3 the U-Boot environment). systemd-repart's default discard pass trims
  # that gap, which destroys the bootloader and breaks subsequent reboots.
  boot.initrd.systemd.repart.discard = false;

  # Realtek RTL8153 USB NIC revisions request rtl_nic patch blobs. Install only
  # those instead of all of linux-firmware (~700 MB).
  hardware.firmware = [ (pkgs.callPackage ../nix/rtl815x-firmware.nix { }) ];

  environment.systemPackages = [ bootToUms ];

  # Login prompt on the debug serial console (UART2, ttyS2 @ 1.5 Mbaud).
  systemd.services."serial-getty@ttyS2" = {
    enable = true;
    wantedBy = [ "getty.target" ];
    serviceConfig.Restart = "always";
  };

  # ── Physical serial root recovery (break-glass) ───────────────────────────
  # Root is locked and there is no built-in operator account. With serial
  # access, set `_RUT_OH_=1` (fw_setenv in Linux, or `setenv _RUT_OH_ 1;
  # saveenv` at the U-Boot prompt): the next boot replaces the ttyS2 getty with
  # a root autologin and clears the flag, so it lasts for one boot.
  atomixos.serialRootDebug.enable = true;

  systemd.services."serial-root-debug@" = lib.mkIf config.atomixos.serialRootDebug.enable {
    description = "Serial root debug autologin on %I";
    after = [ "systemd-user-sessions.service" ];
    serviceConfig = {
      Type = "idle";
      ExecStart = "${pkgs.util-linux}/sbin/agetty --autologin root --keep-baud 1500000,115200,57600,38400 -8 -L %I vt220";
      Restart = "always";
      RestartSec = "0";
      TTYPath = "/dev/%I";
      TTYReset = true;
      TTYVHangup = true;
      IgnoreSIGPIPE = false;
      SendSIGHUP = true;
    };
  };

  systemd.services.serial-root-debug-gate = lib.mkIf config.atomixos.serialRootDebug.enable {
    description = "Enable serial root debug when _RUT_OH_=1";
    after = [
      "data.mount"
      "serial-getty@ttyS2.service"
    ];
    wants = [ "data.mount" ];
    wantedBy = [ "multi-user.target" ];
    unitConfig.RequiresMountsFor = [ "/data" ];
    path = [
      pkgs.coreutils
      pkgs.systemd
      ubootEnvTools
    ];
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
      ExecStart = serialRootDebugScript;
    };
  };

  # boot-storage-debug probes ROCK64's SPI NOR and mmcblk1; keep it off on
  # normal images.
  systemd.services.boot-storage-debug.wantedBy = lib.mkForce [ ];
}
