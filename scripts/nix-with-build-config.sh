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

# Never honor a caller-selected path or hash. The ignored repository-root files
# and ATOMIXOS_SERIAL_ROOT_PASSWORD are the only supported inputs.
unset ATOMIXOS_BUILD_DEV_CONFIG ATOMIXOS_SERIAL_ROOT_PASSWORD_HASH
impure=false

if [[ -f "$override" ]]; then
	echo "WARNING: applying local build.dev.toml overrides; outputs will be marked -dev." >&2
	export ATOMIXOS_BUILD_DEV_CONFIG="$override"
	impure=true
fi

sha256_hex() {
	if command -v sha256sum >/dev/null; then
		sha256sum
	else
		shasum -a 256
	fi
}

# The plaintext never reaches Nix: only its yescrypt hash does. The salt comes
# from the password, so the same password always builds the same image.
password="${ATOMIXOS_SERIAL_ROOT_PASSWORD:-}"
unset ATOMIXOS_SERIAL_ROOT_PASSWORD
if [[ -z "$password" && -f "$password_file" ]]; then
	IFS= read -r password <"$password_file" || true
fi
if [[ -n "$password" ]]; then
	salt=$(printf 'atomixos-serial-root:%s' "$password" | sha256_hex | cut -c1-20)
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
