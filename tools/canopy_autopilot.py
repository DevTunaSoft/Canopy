#!/usr/bin/env python3
"""One-time, opt-in per-user Windows Task Scheduler recovery for Canopy.

Install only when explicitly invoked. The Task Scheduler runs this script
every five minutes, using an unprivileged interpreter and a separate checkout.
The existing supervisor still owns all queues, validation and draft PRs.
No automatic merge, visual/artwork edit or privileged system change.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

# The dedicated checkout is automatically refreshed. Never contaminate it
# with untracked Python cache files during scheduled imports.
sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

BRANCH = "feat/windows-multi-agent-supervisor-20261121"
REPO = "DevTunaSoft/Canopy"
WORKERS = 3
REQUIRED_BACKLOG = 100
TASK_INTERVAL_MINUTES = 5


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def state_path(root: Path) -> Path:
    return Path(root) / "autopilot-status.json"


def write_status(root: Path, status: str, detail: str = "", *,
                 counts: dict | None = None) -> None:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    record = {"at": utc_now(), "status": status,
              "detail": str(detail)[:320]}
    if counts is not None:
        record["counts"] = counts
    path = state_path(root)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)
    log = root / "autopilot-history.jsonl"
    with log.open("a", encoding="utf-8") as out:
        out.write(json.dumps(record, sort_keys=True) + "\n")


def task_name(root: Path) -> str:
    digest = hashlib.sha256(str(Path(root).resolve()).casefold().encode()).hexdigest()[:12]
    return "Canopy-Autopilot-" + digest


def expected_pythonw(executable: Path) -> Path:
    executable = Path(executable).resolve()
    path = executable.with_name("pythonw.exe")
    if not path.is_file():
        raise ValueError("Python Windows launcher pythonw.exe not found")
    return path


def scheduled_command(pythonw: Path, entry: Path, settings: Path) -> str:
    """Create a Windows-safe /TR value; no cmd.exe, shell or expansions."""
    if not all(Path(p).is_absolute() for p in (pythonw, entry, settings)):
        raise ValueError("scheduled paths must be absolute")
    return subprocess.list2cmdline(
        [str(pythonw), str(entry), "service", "--settings", str(settings)]
    )


def scheduler_create(task: str, action: str, *, replace_existing: bool = False,
                     runner=subprocess.run) -> None:
    # No /RU password, /RP, /RL HIGHEST or admin permission.
    args = ["schtasks.exe", "/Create", "/TN", task, "/SC", "MINUTE",
            "/MO", str(TASK_INTERVAL_MINUTES), "/RL", "LIMITED",
            "/TR", action]
    if replace_existing:
        # Only an installer-owned task with a verified settings record may
        # be replaced. Never overwrite an unrelated Task Scheduler entry.
        args.append("/F")
    result = runner(args, capture_output=True, text=True, timeout=45)
    if result.returncode != 0:
        raise RuntimeError("Task Scheduler refused per-user registration"
                           f" (exit={result.returncode}); no elevation attempted")


def scheduler_delete(task: str, *, runner=subprocess.run) -> None:
    result = runner(["schtasks.exe", "/Delete", "/TN", task, "/F"],
                    capture_output=True, text=True, timeout=45)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to remove owned task (exit={result.returncode})")


@contextmanager
def single_owner(path: Path):
    """OS-backed nonblocking lock; released automatically when a process dies."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as fp:
        if fp.tell() == 0:
            fp.write(b"0")
            fp.flush()
        fp.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(fp.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError("another Canopy process owns the lock") from exc
        else:
            import fcntl
            try:
                fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise RuntimeError("another Canopy process owns the lock") from exc
        try:
            yield
        finally:
            fp.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fp.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fp.fileno(), fcntl.LOCK_UN)


def runner_is_active(root: Path) -> bool:
    try:
        with single_owner(root / "locks" / "runner.lock"):
            return False
    except RuntimeError:
        return True


def refresh_checkout(checkout: Path, *, runner=subprocess.run) -> str:
    """Update an isolated, clean checkout only when no supervisor owns it."""
    checkout = Path(checkout)
    if not (checkout / ".git").exists():
        raise ValueError("dedicated autopilot Git checkout missing")
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    state = runner(["git", "-C", str(checkout), "status", "--porcelain"],
                   capture_output=True, text=True, timeout=35, env=env)
    if state.returncode != 0 or state.stdout.strip():
        raise ValueError("autopilot checkout has changes; keeping files untouched")
    fetched = runner(["git", "-C", str(checkout), "fetch", "--quiet", "origin", BRANCH],
                     capture_output=True, text=True, timeout=120, env=env)
    if fetched.returncode == 0:
        switched = runner(["git", "-C", str(checkout), "switch", "--detach",
                           "origin/" + BRANCH],
                          capture_output=True, text=True, timeout=40, env=env)
        if switched.returncode != 0:
            raise RuntimeError("safe checkout update failed; no forced reset")
        return "updated"
    # A network outage does not erase a usable checkout or its task ledger.
    head = runner(["git", "-C", str(checkout), "rev-parse", "HEAD"],
                  capture_output=True, text=True, timeout=20, env=env)
    if head.returncode != 0:
        raise RuntimeError("network unavailable and existing checkout invalid")
    return "offline-existing-checkout"


def load_settings(path: Path) -> dict:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise ValueError("invalid autopilot settings")
    root = Path(data["state_root"])
    checkout = Path(data["checkout"])
    if not root.is_absolute() or not checkout.is_absolute():
        raise ValueError("settings paths must be absolute")
    if data["task"] != task_name(root):
        raise ValueError("scheduled task identity mismatch")
    return data


def get_queue_summary(root: Path, *, prefix="c100-") -> dict:
    from canopy_supervisor.state import TaskStore
    ledger = TaskStore(root).load()
    selected = [t for t in ledger["tasks"] if t["id"].startswith(prefix)]
    summary: dict[str, int] = {}
    for t in selected:
        status = t["status"]
        summary[status] = summary.get(status, 0) + 1
    return summary


def ensure_backlog(root: Path) -> None:
    """Append the missing backlog safely without overwriting existing work."""
    from canopy_supervisor import state
    from tools import canopy_backlog_100
    store = state.TaskStore(root)
    path = root / "roadmap.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("roadmap is not an array")
        if len({t["id"] for t in data if isinstance(t, dict)
                and str(t.get("id", "")).startswith("c100-")}) == REQUIRED_BACKLOG:
            return
    with state.exclusive_lock(store.lock_path):
        current = store.load()
        active = [t["id"] for t in current["tasks"] if t.get("status") in
                  ("assigned", "running", "verifying", "publishing", "interrupted")]
        if active:
            # Resuming the previous task state takes precedence; the next
            # scheduled run loads missing backlog when it becomes idle.
            return
        store.set_paused(True)
    try:
        canopy_backlog_100.prepare(root)
    finally:
        with state.exclusive_lock(store.lock_path):
            store.set_paused(False)


def execute_service(settings: Path, *, runner=subprocess.run) -> int:
    data = load_settings(settings)
    root = Path(data["state_root"])
    checkout = Path(data["checkout"])
    # No task runs under a second supervisor or a second scheduled instance.
    try:
        with single_owner(root / "locks" / "autopilot.lock"):
            if runner_is_active(root):
                write_status(root, "deferred", "another supervisor is already active")
                return 0
            if (root / "PAUSED").exists():
                write_status(root, "paused", "explicit user pause preserved")
                return 0
            try:
                refresh = refresh_checkout(checkout, runner=runner)
                write_status(root, "starting", "checkout=" + refresh)
                sys.path.insert(0, str(checkout))
                from canopy_supervisor import state
                from canopy_supervisor.cli import build_supervisor, load_config

                store = state.TaskStore(root)
                config = load_config(root)
                if config.get("max_workers", 3) > WORKERS:
                    raise ValueError("too many workers configured")
                ensure_backlog(root)
                supervisor = build_supervisor(config, store)
                write_status(root, "running", "supervisor active",
                             counts=get_queue_summary(root))
                results = supervisor.run(until_idle=True, progress_every=6)
                statuses = get_queue_summary(root)
                recorded = sum(statuses.values())
                bad = ("blocked", "failed", "queued", "assigned",
                       "running", "verifying", "publishing", "interrupted",
                       "cancelled")
                if recorded != REQUIRED_BACKLOG or any(statuses.get(s) for s in bad):
                    write_status(root, "incomplete",
                                 f"{recorded}/{REQUIRED_BACKLOG} recorded; "
                                 "recover or review blockers on next run",
                                 counts=statuses)
                    return 2
                write_status(root, "complete",
                             f"{recorded}/{REQUIRED_BACKLOG} recorded",
                             counts=statuses)
                return 0
            except Exception as exc:
                write_status(root, "error",
                             f"{type(exc).__name__}: {str(exc)[:200]}")
                return 2
    except RuntimeError:
        # Another scheduled copy is already servicing this state. This is not
        # an error and never starts additional OpenCode workers.
        return 0


def install(root: Path, checkout: Path, *,
            runner=subprocess.run, popen=subprocess.Popen,
            pythonexe: Path | None = None, appdata: Path | None = None) -> Path:
    if os.name != "nt" and pythonexe is None:
        raise ValueError("Task Scheduler installation is available on Windows only")
    root, checkout = Path(root).resolve(), Path(checkout).resolve()
    if not (root / "config.json").is_file():
        raise ValueError("existing Canopy supervisor config missing; nothing overwritten")
    if not (checkout / ".git").exists():
        raise ValueError("dedicated supervisor checkout does not exist")
    if runner_is_active(root):
        raise ValueError("supervisor currently running; refusing competing installation")
    pythonw = Path(pythonexe) if pythonexe else expected_pythonw(Path(sys.executable))
    app = Path(appdata) if appdata else Path(os.environ["LOCALAPPDATA"]) / "CanopyAutopilot"
    app = app.resolve()
    app.mkdir(parents=True, exist_ok=True)
    entry = app / "Canopy-Watchdog.pyw"
    settings = app / "autopilot.json"
    task = task_name(root)
    stored = {
        "schema": 1, "state_root": str(root), "checkout": str(checkout),
        "task": task, "installed_at": utc_now(), "model": "existing-supervisor",
    }
    owned_task = settings.exists()
    if owned_task:
        old = load_settings(settings)
        if (old["state_root"], old["checkout"], old["task"]) != (
                str(root), str(checkout), task):
            raise ValueError("existing autostart belongs to a different checkout")
    # Copy a stable watchdog entry so git updates never replace code running
    # under Task Scheduler, and never delete the user's prior Git files.
    source = Path(__file__).resolve()
    if source != entry:
        shutil.copy2(source, entry)
    settings.write_text(json.dumps(stored, indent=2) + "\n", encoding="utf-8")
    scheduler_create(task, scheduled_command(pythonw, entry, settings),
                     replace_existing=owned_task, runner=runner)
    # An explicit initial installation authorizes resuming the idle queue.
    sys.path.insert(0, str(checkout))
    from canopy_supervisor import state
    store = state.TaskStore(root)
    with state.exclusive_lock(store.lock_path):
        store.set_paused(False)
        store.event("-", "autopilot_installed",
                    "per-user 5-minute restart task; no elevated rights")
    write_status(root, "installed", "scheduled recovery every 5 minutes")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | \
        getattr(subprocess, "DETACHED_PROCESS", 0)
    popen([str(pythonw), str(entry), "service", "--settings", str(settings)],
          cwd=str(app), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
          stderr=subprocess.DEVNULL, creationflags=flags)
    return settings


def uninstall(settings: Path, *, runner=subprocess.run) -> None:
    record = load_settings(settings)
    scheduler_delete(record["task"], runner=runner)
    # Uninstall never deletes the workspace, task history, logs or branches.
    Path(settings).unlink(missing_ok=True)
    write_status(Path(record["state_root"]), "uninstalled",
                 "scheduled restart removed; task history retained")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    add = commands.add_parser("install", help="one-time Windows non-admin autostart")
    add.add_argument("--state-root", type=Path, required=True)
    add.add_argument("--checkout", type=Path, required=True)
    service = commands.add_parser("service", help="scheduled watchdog invocation")
    service.add_argument("--settings", type=Path, required=True)
    remove = commands.add_parser("uninstall", help="remove only owned scheduled task")
    remove.add_argument("--settings", type=Path, required=True)
    status = commands.add_parser("status", help="inspect latest watchdog state")
    status.add_argument("--state-root", type=Path, required=True)
    args = p.parse_args(argv)
    try:
        if args.command == "install":
            settings = install(args.state_root, args.checkout)
            print("CANOPY_AUTOPILOT_INSTALLED " + str(settings), flush=True)
            return 0
        if args.command == "service":
            return execute_service(args.settings)
        if args.command == "uninstall":
            uninstall(args.settings)
            print("CANOPY_AUTOPILOT_UNINSTALLED", flush=True)
            return 0
        result = state_path(args.state_root)
        print(result.read_text(encoding="utf-8") if result.exists()
              else '{"status":"not-installed"}')
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(f"CANOPY_AUTOPILOT_BLOCKED: {type(exc).__name__}: {exc}",
              file=sys.stderr, flush=True)
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"CANOPY_AUTOPILOT_BLOCKED: scheduled action timed out: {exc.cmd}",
              file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
