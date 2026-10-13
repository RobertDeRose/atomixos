# Realtek RTL8153 USB NIC patch blobs requested by r8152 for the LAN dongles
# matched in modules/networking.nix. Shared by every hardware board so the
# image ships only these files instead of all of linux-firmware.
{
  runCommand,
  linux-firmware,
}:
runCommand "rtl815x-firmware" { } ''
  mkdir -p "$out/lib/firmware/rtl_nic"

  for fw in \
    rtl8153a-2.fw \
    rtl8153a-3.fw \
    rtl8153a-4.fw \
    rtl8153b-2.fw \
    rtl8153c-1.fw
  do
    install -m0644 "${linux-firmware}/lib/firmware/rtl_nic/$fw" "$out/lib/firmware/rtl_nic/$fw"
  done
''
