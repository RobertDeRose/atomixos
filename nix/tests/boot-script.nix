# Keep the rootfs partition derived from the selected boot slot.
{
  pkgs,
  ...
}:
pkgs.runCommand "test-boot-script" { } ''
  script=${../../scripts/boot.cmd}

  grep -F 'if test "''${distro_bootpart}" = "1"; then' "$script"
  grep -F 'setenv distro_rootpart 2' "$script"
  grep -F 'elif test "''${distro_bootpart}" = "3"; then' "$script"
  grep -F 'setenv distro_rootpart 4' "$script"
  ! grep -F 'if test -z "''${distro_rootpart}"' "$script"

  touch "$out"
''
