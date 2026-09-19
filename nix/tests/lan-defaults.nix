{ pkgs, self, ... }:

let
  defaults = builtins.fromJSON (builtins.readFile ../../defaults/lan.json);
  systemConfig = self.nixosConfigurations.rock64.config;
  lanNetwork = systemConfig.environment.etc."systemd/network/20-lan.network.d/50-atomixos.conf".text;
  dnsmasq = systemConfig.environment.etc."dnsmasq.d/atomixos-lan.conf".text;
  chrony = systemConfig.environment.etc."atomixos/chrony-lan.conf".text;
in
assert pkgs.lib.hasInfix "Address=${defaults.gateway_cidr}" lanNetwork;
assert pkgs.lib.hasInfix
  "dhcp-range=${defaults.dhcp_start},${defaults.dhcp_end},${defaults.netmask},24h"
  dnsmasq;
assert pkgs.lib.hasInfix "allow ${defaults.subnet_cidr}" chrony;
pkgs.runCommandNoCC "lan-defaults-contract" { } ''
  cmp ${systemConfig.environment.etc."atomixos/lan-defaults.json".source} ${../../defaults/lan.json}
  touch "$out"
''
