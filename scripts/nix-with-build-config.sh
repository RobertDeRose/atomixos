#!/usr/bin/env bash
# Run one Nix command with the repository-root local build-policy overlay and
# the optional `_RUT_OH_` serial root password.
set -euo pipefail

if (($# == 0)); then
	echo "usage: $0 <nix arguments...>" >&2
	exit 64
fi

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
override="$repo_root/build.dev.toml"
password_file="$repo_root/serial-root.password"
salt_file="$repo_root/serial-root.salt"

# Never honor a caller-selected path or hash. The ignored repository-root files
# and ATOMIXOS_SERIAL_ROOT_PASSWORD are the only supported inputs.
unset ATOMIXOS_BUILD_DEV_CONFIG ATOMIXOS_SERIAL_ROOT_PASSWORD_HASH
impure=false

if [[ -f "$override" ]]; then
	echo "WARNING: applying local build.dev.toml overrides; outputs will be marked -dev." >&2
	export ATOMIXOS_BUILD_DEV_CONFIG="$override"
	impure=true
fi

# The plaintext never reaches Nix: only its yescrypt hash does. The salt is
# random, never derived from the password, and is kept in the ignored salt file
# so rebuilds with the same password reuse the same hash and image.
password="${ATOMIXOS_SERIAL_ROOT_PASSWORD:-}"
unset ATOMIXOS_SERIAL_ROOT_PASSWORD
if [[ -z "$password" && -f "$password_file" ]]; then
	IFS= read -r password <"$password_file" || true
fi
if [[ -n "$password" ]]; then
	if [[ ! -f "$salt_file" ]]; then
		# 15 random bytes are 20 base64 characters; '+' is not a crypt character.
		head -c 15 /dev/urandom | base64 | tr '+' '.' >"$salt_file"
	fi
	IFS= read -r salt <"$salt_file" || true
	if [[ ! "$salt" =~ ^[./0-9A-Za-z]{20}$ ]]; then
		echo "ERROR: $salt_file must hold 20 characters from [./0-9A-Za-z]; delete it to regenerate." >&2
		exit 1
	fi
	hash=$(printf '%s\n' "$password" |
		nix run --inputs-from "$repo_root" nixpkgs#mkpasswd -- --stdin --salt "\$y\$j9T\$$salt")
	unset password
	export ATOMIXOS_SERIAL_ROOT_PASSWORD_HASH="$hash"
	impure=true
fi

if [[ "$impure" == true ]]; then
	exec nix "$@" --impure
fi

exec nix "$@"
