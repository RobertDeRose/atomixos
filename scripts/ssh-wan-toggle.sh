#!/usr/bin/env bash
# Conditionally enable SSH on WAN (eth0) based on a flag file.
# Run at boot by ssh-wan-toggle.service.
#
# Dependencies (must be on PATH): nft
set -euo pipefail

remove_dynamic_rules() {
	nft -a list chain inet filter input 2>/dev/null \
		| awk 'match($0, /comment "SSH-WAN-dynamic"/) {print $NF}' \
		| while IFS= read -r handle; do
			[ -n "$handle" ] || continue
			nft delete rule inet filter input handle "$handle"
		done
}

remove_dynamic_rules

if [ -f /data/config/ssh-wan-enabled ]; then
	echo "SSH-on-WAN flag detected, adding firewall rule"
	nft add rule inet filter input iifname "eth0" tcp dport 22 accept comment \"SSH-WAN-dynamic\"
else
	echo "SSH-on-WAN flag not present, SSH on WAN remains blocked"
fi
