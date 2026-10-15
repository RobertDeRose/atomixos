# U-Boot "sandbox" build: a native binary that runs U-Boot commands on the build
# host, used to execute boot.scr and PREBOOT without hardware. Built from the
# board U-Boot's source and version so the shell matches the devices.
{
  buildUBoot,
  uboot,
}:
buildUBoot {
  defconfig = "sandbox_defconfig";
  inherit (uboot) src version;
  extraMakeFlags = [ "NO_SDL=1" ];
  filesToInstall = [ "u-boot" ];
  extraMeta.platforms = [ "aarch64-linux" ];
  # Drop what the script tests do not need and what fails to build or link in
  # the Nix sandbox (SDL display, EFI capsule tooling, unit tests, UPL).
  extraConfig = ''
    CONFIG_VIDEO_SANDBOX_SDL=n
    CONFIG_SANDBOX_SDL=n
    CONFIG_EFI_LOADER=n
    CONFIG_UNIT_TEST=n
    CONFIG_LTO=n
    CONFIG_CMD_UPL=n
    CONFIG_UPL=n
    CONFIG_EFI_CAPSULE_ON_DISK=n
    CONFIG_EFI_CAPSULE_AUTHENTICATE=n
  '';
}
