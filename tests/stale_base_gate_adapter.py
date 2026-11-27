"""Test-only git adapter for the stale-base / sibling-coverage gate.

This is the ONLY place in the PE-112 change that starts a subprocess. It
collects real git facts (ancestry plus byte-derived SHA-256 digests of sibling
test blobs) and builds the bounded snapshot consumed by the pure gate. The
production module ``tools/qa/stale_base_gate.py`` performs no I/O beyond
reading its snapshot file and never mutates a repository.
"""
import hashlib
import os
from pathlib import Path
import subprocess


def _git(repo, *args, check=True):
    """Run git with an argv list (never shell=True) and return CompletedProcess."""
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        check=False,
    )


def _git_ok(repo, *args):
    result = _git(repo, *args)
    if result.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (
            " ".join(args), result.stderr.decode("utf-8", "replace")))
    return result.stdout.decode("utf-8", "replace").strip()


def init_repo(path):
    """Create an isolated local git repository for a fixture."""
    repo = Path(path)
    repo.mkdir(parents=True, exist_ok=True)
    _git_ok(repo, "init", "-q")
    _git_ok(repo, "config", "user.email", "pe112@example.invalid")
    _git_ok(repo, "config", "user.name", "PE-112")
    return repo


def commit_files(repo, files, message):
    """Write fixture files, commit them, and return the exact commit SHA."""
    for rel_path, content in files.items():
        target = repo / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
    _git_ok(repo, "add", "-A")
    _git_ok(repo, "commit", "-q", "-m", message)
    return _git_ok(repo, "rev-parse", "HEAD")


def blob_sha256(repo, rev, path):
    """Return SHA-256 of the raw blob bytes at rev:path, or None if absent."""
    probe = _git(repo, "cat-file", "-e", "%s:%s" % (rev, path))
    if probe.returncode != 0:
        return None
    result = _git(repo, "cat-file", "blob", "%s:%s" % (rev, path))
    if result.returncode != 0:
        raise RuntimeError("could not read blob %s:%s" % (rev, path))
    return hashlib.sha256(result.stdout).hexdigest()


def checkout(repo, rev):
    """Detach the fixture worktree at an exact commit (adapter-only git call)."""
    _git_ok(repo, "checkout", "-q", "--detach", rev)


def merge_base(repo, left, right):
    """Return the merge-base SHA, or None for unrelated histories."""
    result = _git(repo, "merge-base", left, right)
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", "replace").strip()


def collect_snapshot(repo, integration_tip, head, sibling_paths):
    """Build a gate snapshot from real local git objects.

    ``integration_tip`` and ``head`` must be exact 40-hex commit ids already
    resolved by the caller. Sibling digests are computed from blob *bytes*, so
    the gate is independent of the repository hash algorithm.
    """
    siblings = []
    for path in sibling_paths:
        siblings.append({
            "path": path,
            "tip_blob": blob_sha256(repo, integration_tip, path),
            "head_blob": blob_sha256(repo, head, path),
        })
    return {
        "schema": 1,
        "integration_tip": integration_tip,
        "head": head,
        "merge_base": merge_base(repo, head, integration_tip),
        "siblings": siblings,
    }
