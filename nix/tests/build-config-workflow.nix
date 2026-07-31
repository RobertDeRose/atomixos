{
  pkgs,
  ...
}:

pkgs.runCommand "build-config-workflow-check"
  {
    nativeBuildInputs = [
      pkgs.bash
      pkgs.coreutils
      pkgs.gnugrep
    ];
  }
  ''
    export TEST_REPO="$TMPDIR/repository with spaces"
    mkdir -p "$TEST_REPO/scripts" "$TEST_REPO/.mise"
    cp ${../../mise.toml} "$TEST_REPO/mise.toml"
    cp -R ${../../.mise/tasks} "$TEST_REPO/.mise/tasks"
    cp ${../../scripts/nix-with-build-config.sh} "$TEST_REPO/scripts/nix-with-build-config.sh"
    cp ${../../scripts/build.sh} "$TEST_REPO/scripts/build.sh"
    chmod +x "$TEST_REPO/scripts/"*.sh
    patchShebangs "$TEST_REPO/scripts"

    ${pkgs.bash}/bin/bash ${./build-config-workflow.sh}
    mkdir -p "$out"
  ''
