{ pkgs, ... }:

pkgs.runCommand "e2e-launcher-check"
  {
    nativeBuildInputs = [
      pkgs.bash
      pkgs.coreutils
      pkgs.gnugrep
    ];
  }
  ''
    export TEST_REPO="$TMPDIR/repository with spaces"
    mkdir -p "$TEST_REPO/scripts"
    cp ${../../scripts/run-e2e-check.sh} "$TEST_REPO/scripts/run-e2e-check.sh"
    chmod +x "$TEST_REPO/scripts/run-e2e-check.sh"
    patchShebangs "$TEST_REPO/scripts/run-e2e-check.sh"

    ${pkgs.bash}/bin/bash ${./e2e-launcher.sh}
    mkdir -p "$out"
  ''
