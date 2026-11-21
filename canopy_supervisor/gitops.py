"""Git and GitHub operations for the supervisor.

Publishing is deliberately one-way: commit, push, open a DRAFT PR. There is no
merge, force-push, approval or label command in this module.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Iterable

SHA = re.compile(r"^[0-9a-f]{40}$")


class GitError(RuntimeError):
    """A git or gh command failed."""


def run(args: Iterable[str], *, cwd: Path | str | None = None, timeout: int = 120) -> str:
    """Run a git/gh command without a shell and return bounded output."""
    command = [str(arg) for arg in args]
    try:
        result = subprocess.run(
            command, cwd=str(cwd) if cwd else None, capture_output=True,
            text=True, errors="replace", timeout=timeout, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitError(f"command could not run: {type(exc).__name__}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise GitError((detail[-1] if detail else "exit " + str(result.returncode))[:300])
    return (result.stdout or "").strip()


def rev_parse(repo: Path, ref: str) -> str:
    sha = run(["git", "rev-parse", "--verify", ref + "^{commit}"], cwd=repo)
    if not SHA.fullmatch(sha):
        raise GitError("git returned an invalid commit SHA")
    return sha


def branch_exists(repo: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/" + branch],
        cwd=str(repo), capture_output=True, check=False,
    )
    return result.returncode == 0


def worktree_list(repo: Path) -> list[str]:
    output = run(["git", "worktree", "list", "--porcelain"], cwd=repo)
    return [line[len("worktree "):] for line in output.splitlines()
            if line.startswith("worktree ")]


def worktree_add(repo: Path, path: Path, branch: str, base_sha: str) -> Path:
    path = Path(path)
    if path.exists() and any(path.iterdir()):
        raise GitError("refusing to reuse a non-empty worktree directory")
    path.parent.mkdir(parents=True, exist_ok=True)
    if branch_exists(repo, branch):
        raise GitError("branch already exists: " + branch)
    run(["git", "worktree", "add", "-b", branch, str(path), base_sha], cwd=repo, timeout=180)
    return path


def worktree_remove(repo: Path, path: Path) -> None:
    path = Path(path)
    if path.exists() and str(path.resolve()) in {str(Path(item).resolve()) for item in worktree_list(repo)}:
        run(["git", "worktree", "remove", "--force", str(path)], cwd=repo, timeout=120)


def changed_files(worktree: Path, base_sha: str) -> list[str]:
    output = run(["git", "diff", "--name-only", "--no-renames", base_sha + "..HEAD"],
                 cwd=worktree)
    return [line.strip() for line in output.splitlines() if line.strip()]


def pending_files(worktree: Path) -> list[str]:
    """List uncommitted tracked and untracked files in a worker worktree."""
    tracked = run(["git", "diff", "--name-only", "--no-renames"], cwd=worktree)
    untracked = run(["git", "ls-files", "--others", "--exclude-standard"], cwd=worktree)
    return [line.strip() for line in (tracked + "\n" + untracked).splitlines() if line.strip()]


def status_porcelain(worktree: Path) -> list[str]:
    output = run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=worktree)
    return [line for line in output.splitlines() if line.strip()]


def commit_all(worktree: Path, message: str) -> str:
    if not status_porcelain(worktree):
        raise GitError("worktree has no changes to commit")
    run(["git", "add", "-A"], cwd=worktree)
    # Identity is injected via -c so no global git configuration is required.
    run([
        "git", "-c", "user.name=Canopy Supervisor",
        "-c", "user.email=supervisor@canopy.local", "commit", "-m", message[:300],
    ], cwd=worktree)
    sha = run(["git", "rev-parse", "HEAD"], cwd=worktree)
    if not SHA.fullmatch(sha):
        raise GitError("commit did not produce a valid SHA")
    return sha


def push_branch(worktree: Path, branch: str, remote: str = "origin") -> None:
    run(["git", "push", "--set-upstream", remote, branch], cwd=worktree, timeout=240)


def find_open_pr(worktree: Path, *, repo_slug: str, head: str) -> str | None:
    """Return an existing open PR URL for a branch, so retries cannot duplicate it."""
    try:
        output = run([
            "gh", "pr", "list", "--repo", repo_slug, "--head", head,
            "--state", "open", "--json", "number,url", "--limit", "5",
        ], cwd=worktree, timeout=90)
    except GitError:
        return None
    if not output:
        return None
    try:
        rows = json.loads(output)
    except ValueError:
        return None
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        url = rows[0].get("url")
        return str(url) if isinstance(url, str) and url else None
    return None


def create_draft_pr(worktree: Path, *, repo_slug: str, base: str, head: str,
                    title: str, body: str, body_dir: Path) -> str:
    """Create a draft PR. Never passes --merge or any merge flag."""
    body_dir = Path(body_dir)
    body_dir.mkdir(parents=True, exist_ok=True)
    body_path = body_dir / "pr-body.md"
    body_path.write_text(body[:8000] + "\n", encoding="utf-8")
    try:
        output = run([
            "gh", "pr", "create", "--draft",
            "--repo", repo_slug, "--base", base, "--head", head,
            "--title", title[:140], "--body-file", str(body_path),
        ], cwd=worktree, timeout=180)
    finally:
        body_path.unlink(missing_ok=True)
    match = re.search(r"https://github\.com/[^\s]+/pull/\d+", output)
    if not match:
        raise GitError("gh did not return a pull request URL")
    return match.group(0)


def is_pid_alive(pid: int) -> bool:
    """Check liveness without signalling the process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        process = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return False
        try:
            code = ctypes.c_ulong()
            ok = ctypes.windll.kernel32.GetExitCodeProcess(process, ctypes.byref(code))
            return bool(ok) and code.value == 259  # STILL_ACTIVE
        finally:
            ctypes.windll.kernel32.CloseHandle(process)
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


def terminate_pid(pid: int) -> None:
    """Terminate a supervised worker and its children; best effort."""
    if not is_pid_alive(pid):
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, check=False, timeout=30)
    else:
        import signal
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
