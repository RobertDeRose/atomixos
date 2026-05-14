# Base NixOS configuration shared between Rock64 hardware and QEMU targets.
# Contains all service configuration, networking, firewall, and application setup.
# Hardware-specific settings (kernel, DTB, device paths) are in separate modules.
{
  config,
  developmentMode ? false,
  lib,
  pkgs,
  self,
  ...
}:

{
  options.atomixos.serialRootDebug.enable = lib.mkOption {
    type = lib.types.bool;
    default = false;
    description = ''
      Enable the Rock64 serial-only root debug escape hatch triggered by the
      `_RUT_OH_` U-Boot environment variable.
    '';
  };

  imports = [
    ./logging.nix
    ./networking.nix
    ./firewall.nix
    ./lan-gateway.nix
    ./openvpn.nix
    ./rauc.nix
    ./first-boot.nix
    ./os-verification.nix
    ./os-upgrade.nix
    ./boot-storage-debug.nix
    ./watchdog.nix
  ];

  config = {

    # ── Base system ──────────────────────────────────────────────────────────────

    system.stateVersion = "25.11";

    # Login banner — shows build identity on serial console so we always know
    # which image is running. Uses git rev when available, dirty rev otherwise.
    environment.etc.issue.text =
      let
        rev = self.shortRev or self.dirtyShortRev or "unknown";
      in
      ''

        AtomixOS (NixOS ${config.system.nixos.release}) — build ${rev}

      '';

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

    # Keep only the filesystem tooling we actually need. In particular, the
    # systemd initrd uses system.fsPackages to populate mkfs/fsck helpers, and
    # initrd systemd-repart now needs mkfs.vfat for boot-b and mkfs.f2fs for
    # /data on first boot.
    system.fsPackages = lib.mkForce [
      pkgs.dosfstools
      pkgs.f2fs-tools
    ];

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

    # ── OverlayFS sandboxing compatibility ─────────────────────────────────────
    # systemd's mount-namespace sandboxing (ProtectSystem, PrivateTmp, etc.)
    # creates bind-mounts that can fail on an OverlayFS root. Specifically,
    # ProtectSystem="strict" tries to remount / read-only inside a mount
    # namespace, which doesn't work reliably on overlay. Relax sandboxing for
    # affected services so they start correctly on the overlay root.

    # nsncd: upstream sandboxing (ProtectSystem, ProtectHome, etc.) creates
    # mount namespaces that fail on an OverlayFS root. Permission denied on
    # socket bind at /var/run/nscd/socket. Disable all namespace sandboxing
    # since nsncd is the critical path — its failure cascades to every service
    # that needs name resolution (chronyd, dnsmasq, sshd login, etc.).
    systemd.services.nscd.serviceConfig = {
      ProtectSystem = lib.mkForce false;
      ProtectHome = lib.mkForce false;
      PrivateTmp = lib.mkForce false;
      NoNewPrivileges = lib.mkForce false;
      RestrictSUIDSGID = lib.mkForce false;
      # TEMP: run as root to diagnose if "Permission denied" is user-related
      User = lib.mkForce "root";
      Group = lib.mkForce "root";
      DynamicUser = lib.mkForce false;
    };

    # chronyd: disable all mount-namespace sandboxing. Upstream sets
    # PrivateMounts, PrivateTmp, ProtectSystem, ProtectHome, and several
    # ProtectKernel* options — each creates bind-mounts that fail on overlay.
    systemd.services.chronyd.serviceConfig = {
      ProtectSystem = lib.mkForce false;
      ProtectHome = lib.mkForce false;
      PrivateTmp = lib.mkForce false;
      PrivateMounts = lib.mkForce false;
      ProtectKernelTunables = lib.mkForce false;
      ProtectKernelModules = lib.mkForce false;
      ProtectKernelLogs = lib.mkForce false;
      ProtectControlGroups = lib.mkForce false;
      ProtectHostname = lib.mkForce false;
    };

    # dnsmasq: disable mount-namespace sandboxing. Upstream sets ProtectSystem,
    # ProtectHome, and PrivateTmp. Its preStart also runs chown which needs
    # NSS resolution (provided by nsncd).
    systemd.services.dnsmasq.serviceConfig = {
      ProtectSystem = lib.mkForce false;
      ProtectHome = lib.mkForce false;
      PrivateTmp = lib.mkForce false;
    };

    # systemd-remount-fs is not needed — the overlay root is already writable
    # and there's no meaningful remount to perform. The fstab entry for / says
    # "overlay" which systemd-remount-fs handles as a no-op anyway, but we
    # disable it explicitly to avoid any edge cases.
    systemd.services.systemd-remount-fs.serviceConfig.ExecStart = lib.mkForce [
      "" # clear upstream ExecStart
      "${pkgs.coreutils}/bin/true"
    ];

    # FUSE filesystem support is not needed on this embedded device. Suppress
    # the upstream systemd unit that tries to load the fuse kernel module
    # (which isn't built) and mount /sys/fs/fuse/connections.
    systemd.suppressedSystemUnits = [ "sys-fs-fuse-connections.mount" ];

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
      "d /var/lib/appsvc 0750 appsvc appsvc -"
      "d /var/lib/appsvc/.config 0750 appsvc appsvc -"
      "d /var/lib/appsvc/.config/containers 0750 appsvc appsvc -"
      "d /var/lib/appsvc/.config/containers/systemd 0750 appsvc appsvc -"
      "d /var/cache 0755 root root -"
      "d /var/cache/nscd 0755 nscd nscd -"
      "d /var/log 0755 root root -"
      "d /var/log/journal 2755 root systemd-journal -"
      "d /var/db 0755 root root -"
      "d /run/chrony 0750 chrony chrony -"
    ];

    # ── OverlayFS root over read-only squashfs ──────────────────────────────────
    # U-Boot selects the active rootfs slot and passes it on the kernel command
    # line. Initrd systemd mounts the real root from fileSystems."/", which is an
    # overlay composed from:
    #   lower = selected squashfs slot mounted at /run/rootfs-base
    #   upper = tmpfs-backed /run/overlay-root/upper
    #   work  = tmpfs-backed /run/overlay-root/work
    #
    # Keeping the lower and upper/work directories under /run matches the NixOS
    # overlayfs initrd support and avoids mutating /sysroot after other initrd
    # units have started depending on it.
    fileSystems."/" = {
      overlay = {
        lowerdir = [ "/run/rootfs-base" ];
        upperdir = "/run/overlay-root/upper";
        workdir = "/run/overlay-root/work";
        useStage1BaseDirectories = false;
      };
      # The overlay backing paths are prepared explicitly by initrd services.
      # Leaving NixOS's auto-generated overlay depends list enabled for / causes
      # sysroot.mount -> sysroot-run.mount -> sysroot.mount cycles in initrd.
      depends = lib.mkForce [ ];
    };

    # Mount the selected squashfs slot before sysroot.mount composes the overlay.
    # The boot script passes the slot device as atomixos.lowerdev=... so initrd
    # systemd can keep using fstab-driven root mounting.
    boot.initrd.systemd.services.initrd-prepare-overlay-lower = {
      description = "Prepare overlay lower squashfs";
      requiredBy = [ "sysroot.mount" ];
      before = [ "sysroot.mount" ];
      after = [ "initrd-root-device.target" ];
      wants = [ "initrd-root-device.target" ];
      unitConfig.DefaultDependencies = false;
      serviceConfig = {
        Type = "oneshot";
        RemainAfterExit = true;
      };
      path = [
        pkgs.coreutils
        pkgs.util-linux
      ];
      script = ''
        set -euo pipefail

        lower_device=
        lower_fstype=squashfs

        for arg in $(</proc/cmdline); do
          case "$arg" in
            atomixos.lowerdev=*)
              lower_device=''${arg#atomixos.lowerdev=}
              ;;
            atomixos.lowerfstype=*)
              lower_fstype=''${arg#atomixos.lowerfstype=}
              ;;
          esac
        done

        if [ -z "$lower_device" ]; then
          echo "initrd-prepare-overlay-lower: missing atomixos.lowerdev= kernel parameter" >&2
          exit 1
        fi

        /bin/mkdir -p /run/rootfs-base
        /bin/mount -t "$lower_fstype" -o ro "$lower_device" /run/rootfs-base
      '';
    };

    # NixOS already exports SYSTEMD_SYSROOT_FSTAB via the initrd manager
    # environment. Avoid also embedding the generated initrd-fstab store path in
    # the initrd-parse-etc unit.
    boot.initrd.systemd.services.initrd-parse-etc.environment = lib.mkForce { };

    # Persistent state lives on /data (f2fs partition, created on first boot).
    # The tmpfs upper layer is intentionally ephemeral: every boot starts clean
    # from the verified squashfs image, which is ideal for A/B OTA updates.
    fileSystems."/data" = {
      device = "/dev/disk/by-partlabel/data";
      fsType = "f2fs";
      neededForBoot = false;
      options = [
        "nofail"
        "noatime"
        "x-systemd.device-timeout=60s"
      ];
    };

    # Create slot B and /data in the initrd so GPT changes happen before
    # switch_root and before any live mounts are active. The flash image only
    # carries slot A; initrd systemd-repart provisions the inactive A/B slot and
    # the persistent data partition from the remaining eMMC space on first boot.
    boot.initrd.systemd.enable = true;
    # Keep initrd emergency mode usable on the serial console while we are
    # validating early-boot storage changes on hardware.
    boot.initrd.systemd.emergencyAccess = true;
    # Custom initrd services do not automatically get their `path` entries copied
    # into the initrd image, so include the probe tools they invoke explicitly.
    boot.initrd.systemd.initrdBin = [
      pkgs.gnugrep
      pkgs.util-linux
    ];
    boot.initrd.systemd.repart = {
      enable = true;
      empty = "allow";
    };

    boot.initrd.systemd.services.atomixos-detect-fresh-flash = {
      description = "Detect fresh flash before repartitioning";
      before = [ "systemd-repart.service" ];
      wantedBy = [ "systemd-repart.service" ];
      requires =
        lib.optional ((config.boot.initrd.systemd.repart.device or null) != null)
          "${
            lib.replaceStrings [ "/" ] [ "-" ] (lib.removePrefix "/" config.boot.initrd.systemd.repart.device)
          }.device";
      after =
        lib.optional ((config.boot.initrd.systemd.repart.device or null) != null)
          "${
            lib.replaceStrings [ "/" ] [ "-" ] (lib.removePrefix "/" config.boot.initrd.systemd.repart.device)
          }.device";
      unitConfig.DefaultDependencies = false;
      serviceConfig = {
        Type = "oneshot";
      };
      path = [
        pkgs.coreutils
        pkgs.systemd
      ];
      script = ''
        set -euo pipefail
        mkdir -p /run/atomixos

        # Detect against the repart target directly instead of relying on
        # /dev/disk/by-partlabel/boot-b, which can lag behind early initrd udev
        # on subsequent boots and falsely keep the system in fresh-flash mode.
        repart_device=${lib.escapeShellArg (config.boot.initrd.systemd.repart.device or "")}
        has_boot_b=1

        udevadm settle --timeout=10 || true

        if [ -n "$repart_device" ] && [ -b "$repart_device" ]; then
          if ${pkgs.util-linux}/bin/lsblk -nrpo PARTLABEL "$repart_device" | ${pkgs.gnugrep}/bin/grep -Fxq boot-b; then
            has_boot_b=0
          fi
        elif [ -e /dev/disk/by-partlabel/boot-b ]; then
          has_boot_b=0
        fi

        if [ "$has_boot_b" -ne 0 ]; then
          : > /run/atomixos/fresh-flash
        else
          rm -f /run/atomixos/fresh-flash
        fi
      '';
    };

    boot.initrd.systemd.services.atomixos-persist-fresh-flash-marker = {
      description = "Persist fresh-flash marker for switched root";
      before = [ "initrd-switch-root.target" ];
      wantedBy = [ "initrd-switch-root.target" ];
      after = [ "sysroot.mount" ];
      requires = [ "sysroot.mount" ];
      unitConfig.DefaultDependencies = false;
      serviceConfig = {
        Type = "oneshot";
      };
      path = [ pkgs.coreutils ];
      script = ''
        set -euo pipefail
        mkdir -p /sysroot/etc/atomixos
        if [ -f /run/atomixos/fresh-flash ]; then
          : > /sysroot/etc/atomixos/fresh-flash
        else
          rm -f /sysroot/etc/atomixos/fresh-flash
        fi
      '';
    };

    # systemd-repart matches existing partitions by GPT type, not by label.
    # Declare the slot-A partitions too so the later slot-B entries become the
    # second xbootldr/root-arm64 partitions instead of matching p1/p2.
    systemd.repart.partitions."10-boot-a" = {
      Type = "xbootldr";
      Label = "boot-a";
      SizeMinBytes = "128M";
      SizeMaxBytes = "128M";
    };

    systemd.repart.partitions."20-rootfs-a" = {
      Type = "root-arm64";
      Label = "rootfs-a";
      SizeMinBytes = "1024M";
      SizeMaxBytes = "1024M";
    };

    systemd.repart.partitions."30-boot-b" = {
      Type = "xbootldr";
      Label = "boot-b";
      Format = "vfat";
      SizeMinBytes = "128M";
      SizeMaxBytes = "128M";
    };

    systemd.repart.partitions."40-rootfs-b" = {
      Type = "root-arm64";
      Label = "rootfs-b";
      SizeMinBytes = "1024M";
      SizeMaxBytes = "1024M";
    };

    systemd.repart.partitions."50-data" = {
      Type = "linux-generic";
      Label = "data";
      Format = "f2fs";
      SizeMinBytes = "64M";
      MakeDirectories = [
        "/config"
        "/config/quadlet"
        "/config/ssh-authorized-keys"
        "/containers"
        "/logs"
      ];
    };

    # ── Users ────────────────────────────────────────────────────────────────────

    users.mutableUsers = false;
    # This appliance intentionally ships without any built-in login credential.
    # The admin SSH key is provisioned onto /data on first boot, and Rock64 has
    # a separate physical serial recovery path via `_RUT_OH_`.
    users.allowNoPasswordLogin = true;

    # Root stays locked by default. Rock64 can still expose a physical
    # serial-only root recovery path separately via `_RUT_OH_`.
    users.users.root = {
      hashedPassword = "!";
    };

    users.users.admin = {
      isNormalUser = true;
      extraGroups = [
        "wheel"
        "podman"
      ];

      # Normal operator access is SSH-key-only. The password stays locked even
      # after provisioning; break-glass serial root recovery is handled
      # separately on supported hardware.
      hashedPassword = "!";
    };

    users.users.appsvc = {
      isSystemUser = true;
      group = "appsvc";
      home = "/var/lib/appsvc";
      createHome = false;
      extraGroups = [ "podman" ];
      subUidRanges = [
        {
          startUid = 200000;
          count = 65536;
        }
      ];
      subGidRanges = [
        {
          startGid = 200000;
          count = 65536;
        }
      ];
    };
    users.groups.appsvc = { };

    # Disable sudo and doas — use systemd's run0 for privilege escalation instead.
    # run0 is already part of systemd 258.5 (zero additional closure cost) and
    # doesn't require suid binaries or PAM configuration.
    security.sudo.enable = false;
    security.polkit = {
      enable = true;

      # Headless run0 elevation needs a non-interactive policy because the admin
      # account is intentionally password-locked and there is no desktop auth
      # agent on the appliance.
      extraConfig = ''
        polkit.addRule(function(action, subject) {
          if (subject.isInGroup("wheel")) {
            return polkit.Result.YES;
          }
        });
      '';
    };

    # Disable X11 auth forwarding in su's PAM config — shadow.nix defaults this
    # to true, which drags xauth + 9 X11 libraries (~6.5 MB) into the closure.
    # Completely unnecessary on a headless embedded gateway.
    security.pam.services.su.forwardXAuth = lib.mkForce false;

    # ── Core services ────────────────────────────────────────────────────────────

    # Podman remains the device application runtime even though the local
    # Cockpit/Traefik management path has been removed.
    virtualisation.podman = {
      enable = true;
      dockerCompat = true; # Provides `docker` CLI alias
      defaultNetwork.settings.dns_enabled = true;
    };

    # Persist container image/layer storage on /data for application workloads.
    virtualisation.containers.storage.settings = {
      storage = {
        graphroot = "/data/containers/storage";
        runroot = "/run/containers/storage";
      };
    };

    # OpenSSH for remote access
    services.openssh = {
      enable = true;
      settings = {
        PasswordAuthentication = false;
        PermitRootLogin = "no";
      };
      # Load SSH public keys from /data — written during device provisioning.
      # Uses %u (username) so each user gets their own key file.
      authorizedKeysFiles = [ "/data/config/ssh-authorized-keys/%u" ];
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
      python3
      f2fs-tools
      kmod # modprobe — systemd needs this for loading kernel modules
    ];
  };
}
