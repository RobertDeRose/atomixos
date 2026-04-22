{
  pkgs,
  self,
  ...
}:

let
  ubootEnvTools = self.packages.${pkgs.system}.uboot-env-tools;
  debugScript = pkgs.writeShellScript "boot-storage-debug" (
    builtins.readFile ../scripts/boot-storage-debug.sh
  );
in
{
  environment.systemPackages = [
    pkgs.coreutils
    pkgs.util-linux
    pkgs.systemd
    pkgs.gnugrep
    ubootEnvTools
    pkgs.rauc
  ];

  systemd.services.boot-storage-debug = {
    description = "Capture boot storage diagnostics";
    wantedBy = [ "multi-user.target" ];
    after = [
      "rauc.service"
    ];

    path = [
      pkgs.coreutils
      pkgs.util-linux
      pkgs.systemd
      pkgs.gnugrep
      ubootEnvTools
      pkgs.rauc
    ];

    serviceConfig = {
      Type = "oneshot";
      ExecStart = debugScript;
      StandardOutput = "journal+console";
      StandardError = "journal+console";
    };
  };
}
