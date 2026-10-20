"""Exercise release promotion against real local Git remotes."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release-refs.sh"


@pytest.fixture
def repository(tmp_path, monkeypatch):
    # Never inherit signing, hooks, credentials, or push policy from the developer.
    for name in list(os.environ):
        if name.startswith("GIT_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    git_path = shutil.which("git")
    bash_path = shutil.which("bash")
    assert git_path is not None
    assert bash_path is not None
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    subprocess.run([git_path, "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run([git_path, "init", "-b", "dev", str(work)], check=True, capture_output=True)

    def git(*args, bare=False):
        return subprocess.run(
            [git_path, "-C", str(remote if bare else work), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("config", "user.name", "Release test")
    git("config", "user.email", "release@example.test")
    git("remote", "add", "origin", str(remote))
    git("commit", "--allow-empty", "-m", "feat(repo): initial capability")
    first = git("rev-parse", "HEAD")
    git("push", "origin", "dev")

    def promote(sha, tag="v0.1.0"):
        return subprocess.run([bash_path, str(SCRIPT), sha, tag], cwd=work, capture_output=True, text=True, check=False)

    return git, promote, first, remote


def test_first_release_and_rerun_preserve_dev_and_tag(repository):
    git, promote, first, _ = repository
    assert promote(first).returncode == 0
    assert git("rev-parse", "refs/heads/main", bare=True) == first
    assert git("rev-parse", "v0.1.0^{commit}", bare=True) == first
    assert git("cat-file", "-t", "v0.1.0", bare=True) == "tag"
    tag_object = git("rev-parse", "v0.1.0", bare=True)
    assert promote(first).returncode == 0
    assert git("rev-parse", "v0.1.0", bare=True) == tag_object
    assert git("rev-parse", "refs/heads/dev", bare=True) == first


def test_release_uses_validated_commit_when_dev_has_advanced(repository):
    git, promote, first, _ = repository
    assert promote(first).returncode == 0
    git("commit", "--allow-empty", "-m", "fix(repo): selected release")
    selected = git("rev-parse", "HEAD")
    git("commit", "--allow-empty", "-m", "feat(repo): later development")
    later = git("rev-parse", "HEAD")
    git("push", "origin", "dev")
    assert promote(selected, "v0.1.1").returncode == 0
    assert git("rev-parse", "refs/heads/main", bare=True) == selected
    assert git("rev-parse", "v0.1.1^{commit}", bare=True) == selected
    assert git("rev-parse", "refs/heads/dev", bare=True) == later


def test_conflicting_tag_does_not_advance_main(repository):
    git, promote, first, _ = repository
    assert promote(first).returncode == 0
    git("commit", "--allow-empty", "-m", "fix(repo): next release")
    result = promote(git("rev-parse", "HEAD"))
    assert result.returncode != 0
    assert "already identifies a different commit" in result.stderr
    assert git("rev-parse", "refs/heads/main", bare=True) == first
    assert git("rev-parse", "v0.1.0^{commit}", bare=True) == first


def test_diverged_main_is_not_rewritten(repository):
    git, promote, first, _ = repository
    assert promote(first).returncode == 0
    git("switch", "-c", "other")
    git("commit", "--allow-empty", "-m", "fix(repo): other history")
    divergent = git("rev-parse", "HEAD")
    git("push", "origin", "HEAD:main")
    git("switch", "dev")
    git("commit", "--allow-empty", "-m", "fix(repo): development history")
    result = promote(git("rev-parse", "HEAD"), "v0.1.1")
    assert result.returncode != 0
    assert "main is not an ancestor" in result.stderr
    assert git("rev-parse", "refs/heads/main", bare=True) == divergent
    assert git("tag", "--list", "v0.1.1", bare=True) == ""


def test_rejected_tag_push_leaves_main_unchanged(repository):
    git, promote, first, remote = repository
    assert promote(first).returncode == 0
    git("commit", "--allow-empty", "-m", "fix(repo): next release")
    # Simulate a remote ruleset that accepts main but rejects new tags.
    hook = remote / "hooks" / "update"
    hook.write_text('#!/bin/sh\ncase "$1" in refs/tags/*) exit 1 ;; esac\n')
    hook.chmod(0o755)
    result = promote(git("rev-parse", "HEAD"), "v0.1.1")
    assert result.returncode != 0
    assert git("rev-parse", "refs/heads/main", bare=True) == first
    assert git("tag", "--list", "v0.1.1", bare=True) == ""


def test_unreachable_remote_does_not_create_local_tag(repository):
    git, promote, first, remote = repository
    git("remote", "set-url", "origin", str(remote / "missing"))
    assert promote(first).returncode != 0
    assert git("tag", "--list", "v0.1.0") == ""
