#!/usr/bin/env bash
# Run one Nix command with the repository-root local build-policy overlay.
set -euo pipefail

if (($# == 0)); then
	echo "usage: $0 <nix arguments...>" >&2
	exit 64
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
override="$repo_root/build.dev.toml"

# Never honor a caller-selected path. The ignored repository-root file is the
# only supported local build-policy input.
unset ATOMIXOS_BUILD_DEV_CONFIG

if [[ -f "$override" ]]; then
	echo "WARNING: applying local build.dev.toml overrides; outputs will be marked -dev." >&2
	export ATOMIXOS_BUILD_DEV_CONFIG="$override"
	exec nix "$@" --impure
fi

exec nix "$@"
