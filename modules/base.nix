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

  # Root filesystem — at runtime U-Boot selects the active slot via kernel cmdline
  # (root=/dev/mmcblk2pN). This declaration satisfies NixOS assertions and provides
  # the fallback device; the actual root is overridden by the bootloader.
  fileSystems."/" = {
    device = "/dev/disk/by-label/rootfs-a";
    fsType = "squashfs";
    options = [ "ro" ];
  };

  # Read-only root filesystem — mutable state lives on /persist
  fileSystems."/persist" = {
    device = "/dev/disk/by-label/persist";
    fsType = "f2fs";
    neededForBoot = false;
  };

  # ── Users ────────────────────────────────────────────────────────────────────

  users.mutableUsers = false;

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

  # ── Essential packages ───────────────────────────────────────────────────────

  environment.systemPackages = with pkgs; [
    nano
    htop
    curl
    jq
    f2fs-tools
    python3Minimal # Required by Cockpit (pod) for systemd D-Bus interaction
  ];
}
