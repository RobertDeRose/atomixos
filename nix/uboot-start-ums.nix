# U-Boot Kconfig shared by both boards: act on START_UMS (set from Linux with
# fw_setenv) in PREBOOT, before the RAUC bootmeth selects a slot, so USB mass
# storage recovery still works when the selected slot's boot.scr is unreadable.
# eMMC is mmc 0 in U-Boot on both boards (rk3328-u-boot.dtsi overrides the
# upstream ROCK64 aliases; CM3 aliases it upstream).
''
  CONFIG_USE_PREBOOT=y
  CONFIG_PREBOOT="if test x''${START_UMS} = x1; then echo START_UMS=1 requested, entering USB mass storage mode; setenv START_UMS; saveenv; echo Write a new image over the OTG USB cable, then unplug to reboot; ums 0 mmc 0; reset; fi"
''
