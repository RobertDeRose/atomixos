#!/usr/bin/env bash
# Remove and re-apply the dynamic SSH-on-WAN nftables rule.
# Used for runtime toggling without reboot.
#
# Dependencies (must be on PATH): nft, awk
set -euo pipefail

# Remove any existing dynamic SSH rule
HANDLE=$(nft -a list chain inet filter input 2>/dev/null | grep 'SSH-WAN-dynamic' | awk '{print $NF}')
if [ -n "$HANDLE" ]; then
	nft delete rule inet filter input handle "$HANDLE"
fi

# Re-add if flag exists
if [ -f /persist/config/ssh-wan-enabled ]; then
	echo "Re-adding SSH-on-WAN rule"
	nft add rule inet filter input iifname "eth0" tcp dport 22 accept comment \"SSH-WAN-dynamic\"
else
	echo "SSH-on-WAN disabled"
fi
