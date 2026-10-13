# Runs scripts/os-upgrade.sh against stub rauc/curl/systemctl to check the
# update query carries the board's RAUC compatible and that another board's
# bundle is never downloaded.
{
  pkgs,
  ...
}:

pkgs.runCommand "os-upgrade-query-check"
  {
    nativeBuildInputs = [
      pkgs.bash
      pkgs.coreutils
      pkgs.gnugrep
      pkgs.jq
    ];
  }
  ''
    export OS_UPGRADE_SCRIPT=${../../scripts/os-upgrade.sh}
    ${pkgs.bash}/bin/bash ${./os-upgrade-query.sh}
    mkdir -p "$out"
  ''
