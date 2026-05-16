#!/usr/bin/env python3
"""Materialize managed users from /data/config/users.json.

Reads the persisted user state written by first-boot-provision and ensures
corresponding local accounts exist with the correct group memberships.
Users present in the previous state but absent from the current config are
locked so they cannot authenticate.

This script is designed to run on every boot (the overlay root starts with
only image-declared users) and after config re-apply.
"""
import grp
import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
from contextlib import suppress
from pathlib import Path


USERS_JSON = Path(os.environ.get("ATOMIXOS_USERS_JSON", "/data/config/users.json"))
MANAGED_STATE = Path(os.environ.get("ATOMIXOS_MANAGED_STATE", "/data/config/managed-users.json"))
SSH_KEYS_DIR = Path(os.environ.get("ATOMIXOS_SSH_KEYS_DIR", "/data/config/ssh-authorized-keys"))

# Users that must never be created, modified, or locked by this script.
PROTECTED_USERS = {"root", "admin", "appsvc"}

# The NixOS-declared admin user that gets its groups updated but is never
# created or deleted by this script.
IMAGE_ADMIN = "admin"


def log(msg: str) -> None:
    print(f"[apply-users] {msg}", file=sys.stderr)


USERNAME_RE = re.compile(r"[a-z_][a-z0-9_-]{0,31}")


def valid_username(name: str) -> bool:
    """Defense-in-depth: reject names that don't match the safe pattern."""
    return bool(USERNAME_RE.fullmatch(name)) and name not in PROTECTED_USERS


def user_exists(name: str) -> bool:
    try:
        pwd.getpwnam(name)
        return True
    except KeyError:
        return False


def group_exists(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def run(cmd: list[str]) -> None:
    log(f"  exec: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        log(f"  command failed ({result.returncode}){detail}")
        raise SystemExit(1)


def ensure_user(name: str, is_admin: bool) -> None:
    """Create or update a managed user account."""
    if name in PROTECTED_USERS:
        # admin is handled separately for group membership only.
        if name == IMAGE_ADMIN:
            ensure_admin_groups(is_admin)
        return

    if user_exists(name):
        # Unlock the account in case it was previously locked.
        # --expiredate= (empty) clears expiry on shadow-utils (NixOS ships shadow).
        run(["usermod", "--unlock", "--expiredate=", "--shell=/bin/sh", name])
    else:
        # Non-admin users are system accounts (no home, system UID range).
        # Account type cannot change after creation on the ephemeral overlay,
        # which resets every boot anyway.
        cmd = [
            "useradd",
            "--system" if not is_admin else "--create-home",
            "--shell", "/bin/sh",
            "--password", "!",  # password-locked
            name,
        ]
        run(cmd)

    # Manage wheel membership.
    if is_admin:
        if group_exists("wheel"):
            run(["usermod", "--append", "--groups", "wheel", name])
    else:
        # Remove from wheel if present.
        try:
            wheel = grp.getgrnam("wheel")
            if name in wheel.gr_mem:
                run(["gpasswd", "--delete", name, "wheel"])
        except KeyError:
            pass


def ensure_authorized_keys_owner(name: str) -> None:
    """Make per-user authorized_keys readable after dynamic user creation."""
    key_path = SSH_KEYS_DIR / name
    if not key_path.exists() or not user_exists(name):
        return
    user = pwd.getpwnam(name)
    os.chown(key_path, user.pw_uid, user.pw_gid)
    key_path.chmod(0o600)


def ensure_admin_groups(is_admin: bool) -> None:
    """Ensure the image-declared admin user has correct wheel membership."""
    if not user_exists(IMAGE_ADMIN):
        return
    if is_admin and group_exists("wheel"):
        # admin is already in wheel from NixOS config; this is a no-op safety net.
        try:
            wheel = grp.getgrnam("wheel")
            if IMAGE_ADMIN not in wheel.gr_mem:
                run(["usermod", "--append", "--groups", "wheel", IMAGE_ADMIN])
        except KeyError:
            pass


def lock_user(name: str) -> None:
    """Lock a managed user that is no longer in the config."""
    if name in PROTECTED_USERS:
        return
    if not user_exists(name):
        return
    log(f"  locking removed user: {name}")
    run(["usermod", "--lock", "--expiredate=1", "--shell=/sbin/nologin", name])


def load_previous_managed() -> set[str]:
    """Load the set of usernames that were previously managed."""
    if not MANAGED_STATE.exists():
        return set()
    try:
        data = json.loads(MANAGED_STATE.read_text())
        if isinstance(data, list):
            return {name for name in data if isinstance(name, str)}
    except (json.JSONDecodeError, OSError):
        pass
    return set()


def save_managed_state(names: set[str]) -> None:
    """Persist the current set of managed usernames atomically."""
    content = json.dumps(sorted(names), indent=2) + "\n"
    fd, tmp_path = tempfile.mkstemp(dir=str(MANAGED_STATE.parent), prefix=".managed-users-")
    try:
        os.write(fd, content.encode())
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        os.close(fd)
        Path(tmp_path).rename(MANAGED_STATE)
    except BaseException:
        with suppress(OSError):
            os.close(fd)
        Path(tmp_path).unlink(missing_ok=True)
        raise


def main() -> None:
    if not USERS_JSON.exists():
        log(f"no users state at {USERS_JSON}; skipping")
        return

    try:
        users = json.loads(USERS_JSON.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log(f"failed to read {USERS_JSON}: {exc}")
        raise SystemExit(1) from exc

    if not isinstance(users, dict):
        log(f"invalid users state in {USERS_JSON}")
        raise SystemExit(1)

    previous = load_previous_managed()
    current: set[str] = set()

    # Create or update declared users.
    for username, user in users.items():
        if not valid_username(username) and username not in PROTECTED_USERS:
            log(f"  skipping invalid username: {username!r}")
            continue
        is_admin = user.get("isAdmin", False)
        log(f"ensuring user: {username} (admin={is_admin})")
        ensure_user(username, is_admin)
        ensure_authorized_keys_owner(username)
        # Only track non-protected users in managed state.
        if username not in PROTECTED_USERS:
            current.add(username)

    # Lock users that were managed before but are no longer declared.
    removed = previous - current
    for name in sorted(removed):
        lock_user(name)

    # Persist the current managed set for next comparison.
    save_managed_state(current)

    log("user apply complete")


if __name__ == "__main__":
    main()
