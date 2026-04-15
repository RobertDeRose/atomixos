# Base NixOS configuration shared between Rock64 hardware and QEMU targets.
# Contains all service configuration, networking, firewall, and application setup.
# Hardware-specific settings (kernel, DTB, device paths) are in separate modules.
{
  config,
  lib,
  pkgs,
  self,
  ...
}:

{
  imports = [
    ./networking.nix
    ./firewall.nix
    ./lan-gateway.nix
    ./openvpn.nix
    ./rauc.nix
    ./cockpit.nix
    ./traefik.nix
    ./first-boot.nix
    ./os-verification.nix
    ./os-upgrade.nix
    ./watchdog.nix
  ];

  # ── Base system ──────────────────────────────────────────────────────────────

  system.stateVersion = "25.11";

  time.timeZone = "UTC";
  i18n.defaultLocale = "en_US.UTF-8";

  networking.hostName = "gateway";

  # ── Closure size reduction ──────────────────────────────────────────────────
  # These options remove large packages that are unnecessary on an embedded
  # read-only A/B image device. Updates are applied via RAUC, not nix.

  # Disable the Nix daemon entirely — on a read-only squashfs image there is
  # no writable /nix/store so the daemon, nix CLI, and all their transitive
  # dependencies (aws-sdk-cpp, boost, etc.) are dead weight.
  nix.enable = false;

  # Disable documentation — saves ~45 MB (manual, man pages, info, doc)
  documentation.enable = false;
  documentation.man.enable = false;
  documentation.nixos.enable = false;

  # Disable installer tools (nixos-rebuild, etc.) — this is a read-only A/B
  # image device, not a traditional NixOS install.
  system.disableInstallerTools = true;

  # Clear NixOS default packages (perl, rsync, strace) — none are needed on
  # a minimal embedded gateway.
  environment.defaultPackages = lib.mkForce [ ];

  # Disable desktop-oriented XDG defaults — removes shared-mime-info (~8 MB),
  # hicolor-icon-theme, sound-theme-freedesktop from the closure.
  xdg.mime.enable = false;
  xdg.icons.enable = false;
  xdg.sounds.enable = false;

  # Disable bash tab-completion framework — removes bash-completion (~3 MB)
  # from etc-bashrc. Not needed on a headless embedded device.
  programs.bash.completion.enable = false;

  # Disable font configuration — removes fontconfig-bin, freetype, dejavu-fonts
  # from system-path. No graphical output on this device.
  fonts.fontconfig.enable = false;

  # Override filesystem support packages — NixOS unconditionally adds dosfstools
  # and (with legacy initrd) e2fsprogs. We only use squashfs + f2fs, and
  # f2fs-tools is already in environment.systemPackages.
  system.fsPackages = lib.mkForce [ ];

  # Disable storage/boot subsystems we don't use — each defaults to true and
  # adds its tools to environment.systemPackages.
  boot.bcache.enable = false; # bcache-tools (~220 KB)
  boot.kexec.enable = false; # kexec-tools (~300 KB) — no kexec on A/B image
  services.lvm.enable = false; # lvm2 (~150 KB) — no LVM or device-mapper

  # Disable systemd-timesyncd — we use chrony for NTP (chrony also serves
  # NTP to LAN devices, which timesyncd cannot do).
  services.timesyncd.enable = false;

  # D-Bus config files shipped by systemd reference the systemd-timesync
  # user even when timesyncd is disabled. Declare it so dbus-daemon doesn't
  # log "Unknown username" and stall during startup.
  users.users.systemd-timesync = {
    isSystemUser = true;
    group = "systemd-timesync";
  };
  users.groups.systemd-timesync = { };

  # Disable EFI-related units — Rock64 uses U-Boot, not UEFI.
  boot.loader.efi.canTouchEfiVariables = false;
  systemd.services.systemd-boot-update.enable = false;

  # ── Writable /var directory structure ───────────────────────────────────────
  # /var starts empty on every boot (the squashfs lower layer only has an
  # empty /var directory; writes go to the tmpfs upper layer of the overlay).
  # systemd services expect their StateDirectory / CacheDirectory / working
  # dirs to exist under /var. tmpfiles.d rules create them early in boot.
  systemd.tmpfiles.rules = [
    "d /var/empty 0555 root root -"
    "d /var/lib 0755 root root -"
    "d /var/lib/systemd 0755 root root -"
    "d /var/lib/systemd/network 0755 systemd-network systemd-network -"
    "d /var/lib/private 0700 root root -"
    "d /var/lib/private/systemd 0700 root root -"
    "d /var/lib/private/systemd/resolve 0755 systemd-resolve systemd-resolve -"
    "d /var/lib/chrony 0750 chrony chrony -"
    "d /var/lib/dnsmasq 0755 dnsmasq dnsmasq -"
    "d /var/cache 0755 root root -"
    "d /var/cache/nscd 0755 nscd nscd -"
    "d /var/log 0755 root root -"
    "d /var/log/journal 2755 root systemd-journal -"
    "d /var/db 0755 root root -"
    "d /var/run 0755 root root -"
  ];

  # Root filesystem — the squashfs device declared here tells the NixOS initrd
  # what to mount at /mnt-root during stage 1. Our postMountCommands then wrap
  # it in an overlayfs before switch_root. At runtime / is the overlay, while
  # the squashfs is available at /media/root-ro.
  #
  # At runtime U-Boot selects the active slot via kernel cmdline
  # (root=PARTLABEL=rootfs-a). This declaration satisfies NixOS assertions and
  # provides the fallback device; the actual root is overridden by the bootloader.
  #
  # Note: no "ro" in options — the kernel cmdline has "ro" for the initial
  # squashfs mount, but after the overlay wraps it, the root should be writable.
  # If we put "ro" here, systemd-remount-fs would read /etc/fstab and remount
  # the overlay as read-only, defeating the purpose of the writable upper layer.
  fileSystems."/" = {
    device = "/dev/disk/by-partlabel/rootfs-a";
    fsType = "squashfs";
  };

  # ── OverlayFS: writable root over read-only squashfs ─────────────────────────
  # The squashfs root is immutable. Instead of mounting individual tmpfs at
  # /etc, /var, /tmp, etc. (which breaks systemd's mount namespace sandboxing),
  # we use a single OverlayFS that presents a unified writable root:
  #   lower = squashfs (read-only, contains the full NixOS system)
  #   upper = tmpfs (ephemeral, lost on reboot)
  #
  # This is set up in the initrd via postMountCommands (after the squashfs root
  # is mounted at /mnt-root but before switch_root). The overlay makes the
  # entire root tree writable, so systemd sandboxing (PrivateTmp, ProtectHome,
  # etc.) works correctly — no mount propagation issues.
  #
  # Persistent state lives on /persist (f2fs partition, created on first boot).
  # The tmpfs upper layer is intentionally ephemeral: every boot starts clean
  # from the verified squashfs image, which is ideal for A/B OTA updates.
  boot.initrd.postMountCommands = ''
    # Move the squashfs root out of /mnt-root so we can overlay it
    mkdir -p /mnt-lower
    mount --move /mnt-root /mnt-lower

    # Create a tmpfs for the writable upper layer
    mkdir -p /mnt-upper
    mount -t tmpfs -o mode=0755,size=256M tmpfs /mnt-upper
    mkdir -p /mnt-upper/upper /mnt-upper/work

    # Mount the overlay as the new root
    mount -t overlay overlay \
      -o lowerdir=/mnt-lower,upperdir=/mnt-upper/upper,workdir=/mnt-upper/work \
      /mnt-root

    # Make the lower (squashfs) and upper (tmpfs) layers accessible inside
    # the final root for debugging/inspection
    mkdir -p /mnt-root/media/root-ro /mnt-root/media/root-rw
    mount --move /mnt-lower /mnt-root/media/root-ro
    mount --move /mnt-upper /mnt-root/media/root-rw
  '';

  # Persistent state — survives reboots, separate from the ephemeral overlay.
  # nofail: on first boot the partition doesn't exist yet (create-persist.service
  # creates it), and even on subsequent boots it's not essential for basic operation.
  # x-systemd.device-timeout=60s: allow time for create-persist.service on first boot.
  fileSystems."/persist" = {
    device = "/dev/disk/by-partlabel/persist";
    fsType = "f2fs";
    neededForBoot = false;
    options = [
      "nofail"
      "x-systemd.device-timeout=60s"
    ];
  };

  # ── First-boot persist partition creation ───────────────────────────────────
  # The upstream systemd-repart.service has DefaultDependencies=no and runs
  # very early (Before=sysinit.target). On our squashfs+tmpfs setup it silently
  # exits with code 76 (can't find root block device) because the GPT backup
  # header is stranded at the image boundary after dd'ing a smaller image onto
  # a larger eMMC. We disable the upstream unit and use a custom service that:
  #   1. Fixes the GPT backup header (sfdisk --relocate)
  #   2. Runs systemd-repart with an explicit device path
  #   3. Triggers udev so /dev/disk/by-partlabel/persist appears
  # On subsequent boots the persist partition exists and the service is a no-op.

  # Keep the repart definition files in /etc/repart.d/ (NixOS generates them).
  systemd.repart = {
    enable = true;
    partitions."50-persist" = {
      # Custom type UUID so systemd-repart won't match this definition against
      # existing boot partitions (which are also linux-generic).
      # Generated deterministically: uuid5(NAMESPACE_URL, "atomixos://persist-partition")
      Type = "aad64a60-5bcb-5c83-b9c9-5e446f5dba3e";
      Label = "persist";
      Format = "f2fs";
      MakeDirectories = "/config /config/ssh-authorized-keys /containers /logs";
    };
  };

  # Disable the upstream unit — it can't reliably find our root device.
  systemd.services.systemd-repart.enable = lib.mkForce false;

  # Custom service that creates the persist partition on first boot.
  systemd.services.create-persist = {
    description = "Create persist partition on first boot";
    wantedBy = [ "local-fs.target" ];
    before = [ "local-fs.target" ];
    after = [
      "systemd-udevd.service" # udev must be running for trigger --settle
    ];
    wants = [
      "modprobe@dm_mod.service"
      "modprobe@loop.service"
    ];
    unitConfig = {
      DefaultDependencies = false;
      ConditionPathExists = "!/dev/disk/by-partlabel/persist";
    };
    serviceConfig = {
      Type = "oneshot";
      RemainAfterExit = true;
    };
    path = [
      config.systemd.package
      pkgs.util-linux
      pkgs.f2fs-tools
    ];
    script = ''
      set -euo pipefail

      # With overlayfs root, findmnt / shows "overlay" not the block device.
      # The squashfs lower layer is bind-mounted at /media/root-ro — use that
      # to find the actual block device, then resolve to the parent disk.
      root_part=$(findmnt -n -o SOURCE /media/root-ro)
      disk=$(lsblk -n -o PKNAME "$root_part" | head -1)
      if [ -z "$disk" ]; then
        echo "ERROR: cannot determine parent disk for $root_part"
        exit 1
      fi
      disk="/dev/$disk"
      echo "Root partition: $root_part, disk: $disk"

      # Fix the GPT backup header — after dd'ing a smaller image onto a larger
      # eMMC the backup header is stranded at the old image boundary.
      echo "Relocating GPT backup header to end of $disk..."
      sfdisk --relocate gpt-bak-std "$disk"

      # Re-read the partition table so the kernel sees the updated GPT with
      # correct backup header location. Without this, systemd-repart can't
      # see the free space beyond the old image boundary.
      echo "Re-reading partition table..."
      partx -u "$disk" || blockdev --rereadpt "$disk" || true

      # Create the persist partition using systemd-repart definitions.
      echo "Running systemd-repart on $disk..."
      systemd-repart --definitions=/etc/repart.d --dry-run=no "$disk"

      # Trigger udev so /dev/disk/by-partlabel/persist appears.
      udevadm trigger --settle "$disk"

      echo "Persist partition created successfully."
    '';
  };

  # ── Users ────────────────────────────────────────────────────────────────────

  users.mutableUsers = false;

  # Root login for serial console debugging — allows emergency access when
  # /persist is not yet provisioned. Set an empty password for initial boot
  # testing; the serial console is physically secured.
  users.users.root = {
    hashedPassword = "";
  };

  users.users.admin = {
    isNormalUser = true;
    extraGroups = [
      "wheel"
      "podman"
    ];

    # Password hash read from /persist at boot. The image ships with no
    # credentials — the hash is written during device provisioning (unique
    # per device, EN18031 compliant). The file must contain a single line
    # with a hash suitable for chpasswd -e (e.g. mkpasswd -m sha-512).
    hashedPasswordFile = "/persist/config/admin-password-hash";
  };

  # Disable sudo and doas — use systemd's run0 for privilege escalation instead.
  # run0 is already part of systemd 258.5 (zero additional closure cost) and
  # doesn't require suid binaries or PAM configuration.
  security.sudo.enable = false;

  # Disable X11 auth forwarding in su's PAM config — shadow.nix defaults this
  # to true, which drags xauth + 9 X11 libraries (~6.5 MB) into the closure.
  # Completely unnecessary on a headless embedded gateway.
  security.pam.services.su.forwardXAuth = lib.mkForce false;

  # ── Core services ────────────────────────────────────────────────────────────

  # Podman for container workloads
  virtualisation.podman = {
    enable = true;
    dockerCompat = true; # Provides `docker` CLI alias
    defaultNetwork.settings.dns_enabled = true;
  };

  # OpenSSH for remote access
  services.openssh = {
    enable = true;
    settings = {
      PasswordAuthentication = false;
      PermitRootLogin = "no";
    };
    # Load SSH public keys from /persist — written during device provisioning.
    # Uses %u (username) so each user gets their own key file.
    authorizedKeysFiles = [ "/persist/config/ssh-authorized-keys/%u" ];
    # Allow password auth from localhost only — the Cockpit pod (running on
    # the host network) SSHes to 127.0.0.1 using the provisioned password.
    # Remote/WAN SSH remains key-only.
    extraConfig = ''
      Match Address 127.0.0.1,::1
        PasswordAuthentication yes
    '';
  };

  # Mask systemd-ssh-generator outputs — systemd 258+ auto-creates sshd
  # socket units that conflict with our explicitly managed sshd.service
  # (port 22 "Address already in use"). We manage SSH via services.openssh.
  systemd.sockets.sshd-unix-local.enable = false;
  systemd.sockets.sshd-unix-export.enable = false;

  # ── Essential packages ───────────────────────────────────────────────────────

  environment.systemPackages = with pkgs; [
    nano
    htop
    curl
    jq
    f2fs-tools
    kmod # modprobe — systemd needs this for loading kernel modules
    python3Minimal # Required by Cockpit (pod) for systemd D-Bus interaction
  ];
}
