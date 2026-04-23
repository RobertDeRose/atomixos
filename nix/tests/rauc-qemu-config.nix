{
  # The production image uses its own nftables module and disables the default
  # NixOS firewall. Mirror that here so RAUC QEMU tests do not depend on the
  # iptables-nft compatibility path from firewall-start.
  networking.firewall.enable = false;

  atomixos.rauc = {
    slots = {
      boot0 = "/dev/vdb";
      boot1 = "/dev/vdc";
      rootfs0 = "/dev/vdd";
      rootfs1 = "/dev/vde";
    };

    # Simulate U-Boot slot selection in QEMU using the custom backend.
    bootloader = "custom";
  };
}
