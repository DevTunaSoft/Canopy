"""Bounded OpenCode worker launch, monitoring and log hygiene."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Callable

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
SECRETS = (
    re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{16,}|st_[0-9a-fA-F-]{20,}|"
               r"rt_[0-9a-fA-F-]{20,}|sk-[A-Za-z0-9_-]{16,})\b"),
    re.compile(r"(?i)(OPENCODE_API_KEY|GH_TOKEN|GITHUB_TOKEN|Bearer)\s*[:=]?\s+\S+"),
)


class WorkerError(RuntimeError):
    """Worker could not be started or configured."""


def redact(text: str) -> str:
    """Remove ANSI escapes and known credential shapes from worker output."""
    clean = ANSI.sub("", text)
    for pattern in SECRETS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def evidence_path(state_root: Path, task_id: str) -> Path:
    """Supervisor-owned, durable evidence (never writable by a worker)."""
    return Path(state_root) / "evidence" / task_id / "evidence.json"


def worker_evidence_path(worktree: Path) -> Path:
    """Temporary evidence within the worker's permitted Git worktree."""
    return Path(worktree) / ".canopy-worker-evidence.json"


def build_prompt(task: dict, worktree: Path, evidence: Path, protected: tuple[str, ...]) -> str:
    """Share only this task's context, not repository history."""
    scope = ", ".join(task["scope"])
    banned = ", ".join(protected)
    tests = ("Run relevant tests for your changed files." if task.get("tests_required", True)
             else "Report NOT RUN with a reason if no tests apply.")
    return "\n".join([
        f"Canopy supervisor task {task['id']}: {task['title']}",
        f"Objective: {task['objective']}",
        f"Worktree (only workspace): {worktree}",
        f"Owned paths you may edit: {scope}",
        f"Assigned branch: {task['branch']}",
        "",
        "Rules:",
        "1. Read AGENTS.md and docs/QUALITY.md once. Do not load full git history or all open PRs.",
        "2. Stay inside owned paths. Do not edit approved artwork, dock icons, wallpaper, "
        "Qt GUI files or these protected paths: " + banned + ".",
        "3. Do not git commit, push, create a PR, merge, or change branch. The supervisor publishes.",
        f"4. {tests} Use real commands and report PASS/FAIL/BLOCKED/NOT RUN with short output excerpts. "
        "Never invent evidence.",
        f"5. Write evidence JSON ONLY to {evidence} inside your current worktree, "
        "using keys: task_id, branch, commit_sha (use \"PENDING\"), tests (list of "
        "{command,result,output_excerpt}), changed_files, draft (true), notes. "
        "This temporary JSON is not a project artifact. Never write outside "
        "your assigned worktree or into the supervisor's sibling evidence "
        "directory. The trusted supervisor will copy it after you exit.",
        "6. If blocked, mark this task BLOCKED with the exact missing dependency. "
        "Do not fabricate assets or approval. The supervisor owns task rollover; "
        "do not stall or keep retrying this task indefinitely.",
        ("7. For implementation tasks, include artifacts in evidence.json as an array "
         "of {path, sha256} objects for every required authored file; compute actual "
         "SHA-256 after writing files. Do not report PASS with missing artifacts."
         if task.get("kind") == "implementation" else
         "7. Report any next independent follow-up candidates in notes."),
        "8. End with a one-line factual summary; other workers will continue independent tasks.",
    ])


class WorkerLauncher:
    """Launches `opencode run` with isolated state and a concise task prompt."""

    def __init__(self, config: dict, state_root: Path,
                 credential: Callable[[], str], opencode_exe: str | None = None,
                 spawner: Callable | None = None):
        self.config = config
        self.root = Path(state_root)
        self.credential = credential
        self.exe = opencode_exe or config.get("opencode_exe") or "opencode"
        self.spawner = spawner or subprocess.Popen
        self._processes: dict[int, object] = {}

    def build_env(self, worker_id: str) -> dict:
        environment = dict(os.environ)
        environment["OPENCODE_API_KEY"] = self.credential()
        data_home = self.root / "worker-data" / worker_id
        data_home.mkdir(parents=True, exist_ok=True)
        environment["XDG_DATA_HOME"] = str(data_home)
        return environment

    def launch(self, task: dict, worker_id: str, worktree: Path, log_path: Path) -> int:
        worktree, log_path = Path(worktree), Path(log_path)
        if not worktree.is_dir():
            raise WorkerError("worktree missing: " + str(worktree))
        log_path.parent.mkdir(parents=True, exist_ok=True)
        protected = tuple(self.config.get("protected_paths", ()))
        prompt = build_prompt(task, worktree, worker_evidence_path(worktree), protected)
        arguments = [
            self.exe, "--pure", "run",
            "--model", str(self.config.get("model", "opencode-go/hy4-flash-free")),
            "--dir", str(worktree), prompt,
        ]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
        with log_path.open("a", encoding="utf-8", newline="\n") as log:
            log.write(redact(f"LAUNCH task={task['id']} worker={worker_id} "
                             f"model={self.config.get('model')}\n"))
            log.flush()
            try:
                process = self.spawner(
                    arguments, cwd=str(worktree), env=self.build_env(worker_id),
                    stdout=log, stderr=subprocess.STDOUT, creationflags=flags,
                )
            except (OSError, ValueError) as exc:
                raise WorkerError(f"cannot start OpenCode worker: {type(exc).__name__}") from exc
        self._processes[process.pid] = process
        return process.pid

    def knows(self, pid: int) -> bool:
        return pid in self._processes

    def poll(self, pid: int) -> int | None:
        """Return the real exit code for a process launched by this instance.

        After a restart the OS handle is gone. Returning None is deliberate:
        the supervisor requeues such tasks instead of guessing their result.
        """
        process = self._processes.get(pid)
        if process is None:
            return None
        code = process.poll()
        if code is not None:
            self._processes.pop(pid, None)
        return code


def progress_signature(worktree: Path, log_path: Path) -> tuple:
    """Detect real progress: log growth or changing worktree files."""
    worktree, log_path = Path(worktree), Path(log_path)
    log_size = log_path.stat().st_size if log_path.exists() else 0
    count = 0
    latest = 0.0
    for root, dirs, files in os.walk(worktree):
        dirs[:] = [name for name in dirs if name != ".git"]
        for name in files:
            count += 1
            try:
                latest = max(latest, (Path(root) / name).stat().st_mtime)
            except OSError:
                continue
    return (log_size, count, int(latest))


def read_evidence(state_root: Path, task_id: str) -> dict:
    path = evidence_path(state_root, task_id)
    if not path.is_file():
        raise WorkerError("worker did not write evidence JSON")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise WorkerError("worker evidence is not valid JSON") from exc
    if not isinstance(data, dict):
        raise WorkerError("worker evidence must be an object")
    return data
