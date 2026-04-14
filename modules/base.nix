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
  # /var is a tmpfs — empty on every boot. systemd services expect their
  # StateDirectory / CacheDirectory / working dirs to exist under /var.
  # tmpfiles.d rules create them early in boot (before services start).
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

  # Root filesystem — at runtime U-Boot selects the active slot via kernel cmdline
  # (root=PARTLABEL=rootfs-a). This declaration satisfies NixOS assertions and provides
  # the fallback device; the actual root is overridden by the bootloader.
  fileSystems."/" = {
    device = "/dev/disk/by-partlabel/rootfs-a";
    fsType = "squashfs";
    options = [ "ro" ];
  };

  # ── Writable tmpfs overlays for read-only squashfs root ─────────────────────
  # The squashfs root is immutable. NixOS Stage 2 needs writable /etc, /var, /tmp
  # for runtime state (systemd, /etc/resolv.conf, /var/log, etc.).
  # These tmpfs mounts are ephemeral — persistent state lives on /persist.
  fileSystems."/etc" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0755"
      "size=50M"
    ];
    neededForBoot = true;
  };

  fileSystems."/var" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0755"
      "size=100M"
    ];
    neededForBoot = true;
  };

  fileSystems."/tmp" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=1777"
      "size=50M"
    ];
    neededForBoot = true;
  };

  fileSystems."/root" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0700"
      "size=5M"
    ];
    neededForBoot = true;
  };

  fileSystems."/home" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0755"
      "size=10M"
    ];
    neededForBoot = true;
  };

  # /bin and /usr/bin — NixOS activation scripts create /bin/sh and /usr/bin/env
  # symlinks. On a read-only squashfs root these directories must be writable.
  fileSystems."/bin" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0755"
      "size=1M"
    ];
    neededForBoot = true;
  };

  fileSystems."/usr" = {
    device = "tmpfs";
    fsType = "tmpfs";
    options = [
      "mode=0755"
      "size=1M"
    ];
    neededForBoot = true;
  };

  # Read-only root filesystem — mutable state lives on /persist.
  # nofail: on first boot the partition doesn't exist yet (systemd-repart creates
  # it), and even on subsequent boots it's not essential for basic operation.
  # x-systemd.device-timeout=10s: don't wait 90s if the partition is missing.
  fileSystems."/persist" = {
    device = "/dev/disk/by-partlabel/persist";
    fsType = "f2fs";
    neededForBoot = false;
    options = [
      "nofail"
      "x-systemd.device-timeout=10s"
    ];
  };

  # ── First-boot persist partition creation ───────────────────────────────────
  # systemd-repart runs Before=sysinit.target on every boot. When the persist
  # partition already exists it is a no-op. On first boot (freshly flashed
  # image with no persist partition) it creates the partition, formats it as
  # f2fs, and pre-creates the required directory structure. Zero additional
  # closure cost — the binary is compiled into the systemd package.
  systemd.repart = {
    enable = true;
    partitions."50-persist" = {
      Type = "linux-generic";
      Label = "persist";
      Format = "f2fs";
      MakeDirectories = "/config /config/ssh-authorized-keys /containers /logs";
    };
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
