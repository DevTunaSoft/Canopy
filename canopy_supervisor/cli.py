"""Command line interface for the Canopy multi-agent supervisor."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

from . import credentials, policy, state
from .supervisor import DEFAULT_CONFIG, Supervisor
from .worker import WorkerLauncher


def default_state_root() -> Path:
    override = os.environ.get("CANOPY_SUPERVISOR_STATE_ROOT")
    if override:
        return Path(override)
    return Path.cwd() / ".canopy-supervisor"


def resolve_opencode_exe(configured: str) -> str:
    if configured:
        return configured
    from_env = os.environ.get("OPENCODE_EXE", "")
    if from_env:
        return from_env
    candidates = [
        shutil.which("opencode.exe"),
        Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" /
        "opencode-ai" / "bin" / "opencode.exe",
        shutil.which("opencode"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return "opencode"


def load_config(state_root: Path) -> dict:
    config = state.TaskStore(state_root).config_path
    if not config.is_file():
        raise ValueError("supervisor not initialized; run: init --repo <path>")
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("corrupt supervisor config") from exc
    if not isinstance(data, dict):
        raise ValueError("supervisor config must be an object")
    return {**DEFAULT_CONFIG, **data, "state_root": str(state_root)}


def build_supervisor(config: dict, store: state.TaskStore, *, spawner=None) -> Supervisor:
    launcher = WorkerLauncher(
        config, store.root,
        credential=lambda: credentials.get_opencode_api_key(data_home=Path(
            config.get("opencode_data_home") or "") if config.get("opencode_data_home") else None),
        opencode_exe=resolve_opencode_exe(config.get("opencode_exe", "")),
        spawner=spawner,
    )
    return Supervisor(config, store, launcher)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="canopy-supervisor",
        description="Bounded Git-worktree coordinator for OpenCode coding workers. Never merges.",
    )
    parser.add_argument("--state-root", type=Path, default=None,
                        help="state directory (default: ./.canopy-supervisor)")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create or update supervisor state")
    init.add_argument("--repo", type=Path, required=True)
    init.add_argument("--max-workers", type=int, default=3)
    init.add_argument("--model", default="opencode-go/hy4-flash-free")
    init.add_argument("--opencode-exe", default="")
    init.add_argument("--repo-slug", default="DevTunaSoft/Canopy")
    init.add_argument("--task-timeout-minutes", type=int, default=45)
    init.add_argument("--stall-minutes", type=int, default=6)
    init.add_argument("--force", action="store_true", help="overwrite existing config")

    add = commands.add_parser("add-task", help="append a task to the persistent queue")
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--objective", required=True)
    add.add_argument("--scope", action="append", required=True,
                     help="owned relative path or pattern; repeatable")
    add.add_argument("--depends-on", action="append", default=[])
    add.add_argument("--base", default="main")
    add.add_argument("--branch", default=None)

    commands.add_parser("run", help="dispatch and monitor workers").add_argument(
        "--once", action="store_true", help="run a single coordination step")
    commands.add_parser("status", help="print the Markdown dashboard").add_argument(
        "--json", action="store_true", help="print raw task state instead")
    commands.add_parser("check", help="validate queue invariants without launching workers")
    commands.add_parser("stop", help="request clean shutdown after the current step")
    commands.add_parser("pause", help="stop dispatching new tasks")
    commands.add_parser("resume", help="allow new task dispatch")
    commands.add_parser("recover", help="requeue tasks with lost leases")
    commands.add_parser("prune", help="remove worktrees of finished tasks")
    return parser


def _state_root(args) -> Path:
    return Path(args.state_root) if args.state_root else default_state_root()


def _locked_action(store, action):
    with state.exclusive_lock(store.lock_path):
        return action()


def main(argv=None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    root = _state_root(args)
    try:
        if args.command == "init":
            repo = Path(args.repo).resolve()
            if not (repo / ".git").exists():
                raise ValueError("--repo must point at an existing Git repository")
            store = state.TaskStore(root)
            if store.config_path.exists() and not args.force:
                raise ValueError("config already exists; use --force to replace it")
            config = dict(DEFAULT_CONFIG)
            config.update({
                "repo": str(repo), "state_root": str(root),
                "max_workers": args.max_workers, "model": args.model,
                "opencode_exe": resolve_opencode_exe(args.opencode_exe),
                "repo_slug": args.repo_slug,
                "task_timeout_minutes": args.task_timeout_minutes,
                "stall_minutes": args.stall_minutes,
            })
            Supervisor(config, store, object())._validate_config()
            state.atomic_write(store.config_path, json.dumps(config, indent=2, sort_keys=True) + "\n")
            state.atomic_write(store.tasks_path, json.dumps(
                {"version": state.STATE_VERSION, "tasks": [], "updated_at": state.utcnow()},
                indent=2) + "\n")
            store.event("-", "initialized", f"repo={repo} workers={args.max_workers}")
            store.write_dashboard(store.load(), config)
            print(f"INITIALIZED {root}")
            return 0

        config = load_config(root)
        store = state.TaskStore(root)

        if args.command == "add-task":
            definition = policy.validate_task({
                "id": args.id, "title": args.title, "objective": args.objective,
                "scope": args.scope, "depends_on": args.depends_on,
                "base": args.base,
                **({"branch": args.branch} if args.branch else {}),
            }, config.get("protected_paths"))
            def action():
                data = store.load()
                if any(task["id"] == definition["id"] for task in data["tasks"]):
                    raise ValueError("duplicate task id: " + definition["id"])
                data["tasks"].append(state.new_task(definition, config["max_attempts"]))
                store.save(data)
                store.event(definition["id"], "task_added", definition["title"])
                store.write_dashboard(data, config)
            _locked_action(store, action)
            print(f"ADDED {definition['id']}")
            return 0

        if args.command == "status":
            data = store.load()
            print(json.dumps(data, indent=2, sort_keys=True) if args.json
                  else store.dashboard(data, config))
            return 0

        if args.command == "check":
            Supervisor(config, store, object())._validate_config()
            data = store.load()
            seen = set()
            for task in data["tasks"]:
                definition = policy.validate_task(task, config.get("protected_paths"))
                if definition["id"] in seen:
                    raise ValueError("duplicate task id in queue: " + definition["id"])
                seen.add(task["id"])
            for task in data["tasks"]:
                for dependency in task.get("depends_on", []):
                    if dependency not in seen:
                        raise ValueError(f"unknown dependency {dependency} on {task['id']}")
            print(f"CHECK_PASS tasks={len(data['tasks'])}")
            return 0

        if args.command == "stop":
            state.atomic_write(store.stop_path, state.utcnow() + "\n")
            print("STOP_REQUESTED")
            return 0

        if args.command == "pause":
            store.set_paused(True)
            store.event("-", "paused")
            print("PAUSED")
            return 0

        if args.command == "resume":
            store.set_paused(False)
            store.event("-", "resumed")
            print("RESUMED")
            return 0

        if args.command == "recover":
            def action():
                supervisor = build_supervisor(config, store)
                data = store.load()
                count = supervisor.recover(data)
                store.save(data)
                store.write_dashboard(data, config)
                return count
            print(f"RECOVERED {_locked_action(store, action)}")
            return 0

        if args.command == "prune":
            supervisor = build_supervisor(config, store)
            print(f"PRUNED {supervisor.prune()}")
            return 0

        if args.command == "run":
            supervisor = build_supervisor(config, store)
            data = supervisor.run(once=args.once)
            active = sum(task.get("status") in state.ACTIVE_STATUSES for task in data["tasks"])
            print(f"RUN_DONE active={active} dashboard={store.dashboard_path}")
            return 0
    except (ValueError, policy.PolicyError, state.LockBusy, credentials.CredentialError) as exc:
        print(f"SUPERVISOR_FAIL: {exc}", file=sys.stderr)
        return 2
    return 2
