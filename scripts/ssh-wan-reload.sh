#!/usr/bin/env bash
# Remove and re-apply the dynamic SSH-on-WAN nftables rule.
# Used for runtime toggling without reboot.
#
# Dependencies (must be on PATH): nft, awk
set -euo pipefail

WAN_INTERFACE="${ATOMIXOS_WAN_INTERFACE:-wan}"

# Remove all existing dynamic SSH rules before optionally adding one.
nft -a list chain inet filter input 2>/dev/null |
	awk 'match($0, /comment "SSH-WAN-dynamic"/) {print $NF}' |
	while IFS= read -r handle; do
		[ -n "$handle" ] || continue
		nft delete rule inet filter input handle "$handle"
	done

# Re-add if flag exists
if [ -f /data/config/ssh-wan-enabled ]; then
	echo "Re-adding SSH-on-WAN rule"
	nft add rule inet filter input iifname "$WAN_INTERFACE" tcp dport 22 accept comment \"SSH-WAN-dynamic\"
else
	echo "SSH-on-WAN disabled"
fi
