"""Task dispatch, stall recovery and verified publishing for Canopy workers."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from . import gitops
from . import policy
from . import roadmap
from . import state as state_module
from .policy import PolicyError
from .worker import (WorkerError, evidence_path, worker_evidence_path,
                     progress_signature, read_evidence)

DEFAULT_CONFIG = {
    "repo": "",
    "state_root": "",
    "max_workers": 3,
    "model": "opencode-go/hy4-flash-free",
    "opencode_exe": "",
    "task_timeout_minutes": 45,
    "stall_minutes": 6,
    "lease_minutes": 10,
    "max_attempts": 2,
    "base_branch": "main",
    "remote": "origin",
    "repo_slug": "DevTunaSoft/Canopy",
    "protected_paths": list(policy.PROTECTED_PATHS),
    "poll_seconds": 5,
    "auto_queue": True,
}

SUCCESS_STATES = ("awaiting_review", "done")


class Supervisor:
    """Single-owner coordinator. All mutations happen under the state lock."""

    def __init__(self, config: dict, store: state_module.TaskStore, launcher,
                 *, git=gitops, now_fn=time.time):
        self.config = {**DEFAULT_CONFIG, **config}
        self.store = store
        self.launcher = launcher
        self.git = git
        self.now = now_fn
        self._stop = threading.Event()
        self._validate_config()

    def _validate_config(self) -> None:
        repo = Path(self.config.get("repo", ""))
        if not repo.is_dir() or not (repo / ".git").exists():
            raise ValueError("config.repo must be an existing Git repository")
        for key in ("max_workers", "task_timeout_minutes", "stall_minutes",
                    "lease_minutes", "max_attempts", "poll_seconds"):
            value = self.config[key]
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"config.{key} must be a positive integer")
        if self.config["max_workers"] > 3:
            raise ValueError("max_workers cannot exceed 3 for this supervisor")
        if self.config["stall_minutes"] >= self.config["task_timeout_minutes"]:
            raise ValueError("stall_minutes must be shorter than task_timeout_minutes")
        if not isinstance(self.config.get("model"), str) or not self.config["model"].startswith("opencode-go/"):
            raise ValueError("config.model must use the authenticated opencode-go provider")

    # ---------- scheduling ----------

    def _dependencies_met(self, task: dict, tasks: list[dict]) -> bool:
        by_id = {item["id"]: item for item in tasks}
        for dependency in task.get("depends_on", []):
            owner = by_id.get(dependency)
            if not owner or owner.get("status") not in SUCCESS_STATES:
                return False
        return True

    def assignable(self, task: dict, tasks: list[dict]) -> bool:
        if task.get("status") != "queued":
            return False
        if self.now() < float(task.get("next_attempt_at", 0)):
            return False
        if task.get("attempts", 0) >= task.get("max_attempts", self.config["max_attempts"]):
            return False
        if not self._dependencies_met(task, tasks):
            return False
        for other in tasks:
            if other is task or other.get("status") not in state_module.ACTIVE_STATUSES:
                continue
            if other.get("branch") == task.get("branch"):
                return False
            if policy.scope_conflict(task.get("scope", []), other.get("scope", [])):
                return False
        return True

    def free_worker(self, tasks: list[dict]) -> str | None:
        used = {task.get("owner") for task in tasks
                if task.get("status") in state_module.ACTIVE_STATUSES}
        for number in range(1, self.config["max_workers"] + 1):
            worker = f"worker-{number}"
            if worker not in used:
                return worker
        return None

    def active_count(self, tasks: list[dict]) -> int:
        return sum(task.get("status") in state_module.ACTIVE_STATUSES for task in tasks)

    @staticmethod
    def backoff(attempts: int) -> float:
        """Exponential delay, capped at five minutes."""
        return min(300.0, 30.0 * (2 ** max(0, attempts - 1)))

    # ---------- worktree and recovery ----------

    def _norm_path(self, path: Path) -> str:
        return str(Path(path).resolve()).replace("\\", "/").lower()

    def prepare_worktree(self, task: dict) -> Path:
        repo = Path(self.config["repo"])
        path = Path(task["worktree"]) if task.get("worktree") else \
            Path(self.config["state_root"]) / "worktrees" / task["id"]
        registered = {self._norm_path(item) for item in self.git.worktree_list(repo)}
        if self._norm_path(path) in registered:
            current = self.git.run(["git", "branch", "--show-current"], cwd=path)
            if current != task["branch"]:
                raise WorkerError("reused worktree is on an unexpected branch")
            return path
        if self.git.branch_exists(repo, task["branch"]):
            path.parent.mkdir(parents=True, exist_ok=True)
            self.git.run(["git", "worktree", "add", str(path), task["branch"]],
                         cwd=repo, timeout=180)
            return path
        return self.git.worktree_add(repo, path, task["branch"], task["base_sha"])

    def _collect_worker_evidence(self, task: dict) -> bool:
        """Ingest a bounded, local-only report after the worker has exited.

        Worker tools may write only inside their worktree. Only this trusted
        supervisor writes the durable state/evidence directory. Never stage
        symlinks, out-of-scope paths, or mismatched task identities.
        """
        worktree = task.get("worktree")
        if not worktree:
            return False
        source = worker_evidence_path(Path(worktree))
        if not source.is_file() and not source.is_symlink():
            return False
        try:
            if source.is_symlink():
                raise WorkerError("worktree evidence cannot be a symlink")
            with source.open("rb") as handle:
                raw = handle.read(131073)
            if len(raw) > 131072:
                raise WorkerError("worktree evidence exceeds 128 KiB limit")
            report = json.loads(raw.decode("utf-8"))
            if not isinstance(report, dict):
                raise WorkerError("worktree evidence must be a JSON object")
            if report.get("task_id") != task["id"] or report.get("branch") != task["branch"]:
                raise WorkerError("worktree evidence task or branch mismatch")
            target = evidence_path(self.store.root, task["id"])
            state_module.atomic_write(target, json.dumps(report, sort_keys=True) + "\n")
            source.unlink()
        except (WorkerError, OSError, ValueError, UnicodeError) as exc:
            self.store.event(task["id"], "evidence_collection_failed",
                             type(exc).__name__, level="ERROR")
            return False
        self.store.event(task["id"], "evidence_collected",
                         "worktree report moved to supervisor state")
        return True

    def recover(self, data: dict) -> int:
        """Requeue tasks whose supervisor lease has expired."""
        recovered = 0
        now = self.now()
        for task in data["tasks"]:
            if task.get("status") == "interrupted":
                self._collect_worker_evidence(task)
                has_evidence = evidence_path(self.store.root, task["id"]).is_file()
                attempts = task.get("attempts", 0)
                limit = task.get("max_attempts", self.config["max_attempts"])
                if has_evidence:
                    status, stage = "verifying", "recovered-evidence"
                elif attempts >= limit:
                    status, stage = "blocked", "recovery-limit"
                else:
                    status, stage = "queued", "recovered"
                state_module.advance(task, status, stage,
                                     "checkpoint replayed after restart",
                                     owner=None, pid=None, lease_expires_at=0.0,
                                     next_attempt_at=0.0)
                self.store.event(task["id"], "recovered", f"replayed {stage}", level="WARN")
                recovered += 1
                continue
            if task.get("status") not in state_module.ACTIVE_STATUSES:
                continue
            if task.get("status") in ("verifying", "publishing"):
                # These stages are durable checkpoints, not live worker
                # processes. A child may have exited already; verify() owns
                # the result even after a supervisor restart.
                continue
            pid = task.get("pid")
            expired = now >= float(task.get("lease_expires_at", 0))
            # On the current supervisor instance, Popen is authoritative for
            # exit status. A process may have finished between loop ticks:
            # checking raw PID liveness first would discard its exit code,
            # skip evidence verification and consume a retry incorrectly.
            knows = getattr(self.launcher, "knows", lambda value: False)(pid)
            if task.get("status") == "running" and knows and not expired:
                continue  # monitor() will call poll() and verify the exit
            alive = bool(pid) and self.git.is_pid_alive(pid)
            if not expired and (not pid or alive):
                continue
            if not alive:
                self._collect_worker_evidence(task)
            if not alive and evidence_path(self.store.root, task["id"]).is_file():
                # Worker finished between supervisor restarts. Let verification
                # inspect the evidence and the real diff before any decision.
                continue
            if alive:
                self.git.terminate_pid(pid)
            message = "worker process lost or lease expired; task recovered"
            if task.get("attempts", 0) >= task.get("max_attempts", self.config["max_attempts"]):
                state_module.advance(task, "blocked", "recovery-limit", message,
                                     owner=None, pid=None, lease_expires_at=0.0)
            else:
                state_module.advance(
                    task, "queued", "recovered", message, owner=None, pid=None,
                    lease_expires_at=0.0,
                    next_attempt_at=self.now() + self.backoff(task.get("attempts", 0)),
                )
            self.store.event(task["id"], "recovered", message, level="WARN", worker=task.get("owner"))
            recovered += 1
        return recovered

    def dispatch(self, data: dict) -> int:
        if self.store.paused:
            return 0
        started = 0
        for task in data["tasks"]:
            if self.active_count(data["tasks"]) >= self.config["max_workers"]:
                break
            if not self.assignable(task, data["tasks"]):
                continue
            worker = self.free_worker(data["tasks"])
            if not worker:
                break
            # A stacked Qt QA task must branch from the actual compiled Qt
            # prototype PR, not old main (which contains no Qt prototype).
            # Resolve feature bases from a fetched remote-tracking ref.
            base = task.get("base") or self.config["base_branch"]
            base_ref = (base if base == self.config["base_branch"]
                        else f"{self.config['remote']}/{base}")
            try:
                base_sha = self.git.rev_parse(Path(self.config["repo"]), base_ref)
            except gitops.GitError as exc:
                self.store.event(task["id"], "dispatch_blocked",
                                 f"base ref unavailable: {base_ref}: {exc}", level="ERROR")
                continue
            state_module.advance(
                task, "assigned", "assigned", "", owner=worker,
                lease_expires_at=self.now() + self.config["lease_minutes"] * 60,
                base_sha=base_sha, last_error="",
            )
            # Reserve the worker slot on disk before any slow worktree operation.
            self.store.save(data)
            self.store.event(task["id"], "assigned", "reserved worker slot", worker=worker)
            try:
                worktree = self.prepare_worktree(task)
                task["worktree"] = str(worktree)
                # A retry cannot accidentally reuse a partial report from a
                # previous worker attempt. Source files remain untouched.
                worker_evidence_path(worktree).unlink(missing_ok=True)
                evidence_path(self.store.root, task["id"]).unlink(missing_ok=True)
                log = Path(self.config["state_root"]) / "logs" / (task["id"] + ".log")
                pid = self.launcher.launch(task, worker, worktree, log)
                state_module.advance(
                    task, "running", "launched", "", owner=worker, pid=pid, worktree=str(worktree),
                    heartbeat_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    started_at=self.now(), last_progress_at=self.now(), progress_signature=[],
                    lease_expires_at=self.now() + self.config["lease_minutes"] * 60,
                    attempts=task.get("attempts", 0) + 1,
                )
                self.store.event(task["id"], "launched", f"pid={pid}", worker=worker)
                started += 1
            except (WorkerError, PolicyError, gitops.GitError, OSError, ValueError) as exc:
                message = f"dispatch failed: {type(exc).__name__}: {exc}"
                state_module.advance(
                    task, "failed", "dispatch-error", message, owner=None, pid=None,
                    lease_expires_at=0.0,
                    next_attempt_at=self.now() + self.backoff(task.get("attempts", 0)),
                )
                self.store.event(task["id"], "failed", message, level="ERROR", worker=worker)
            self.store.save(data)
        return started

    # ---------- monitoring ----------

    def _interrupt(self, task: dict, reason: str) -> None:
        pid = task.get("pid")
        if pid:
            self.git.terminate_pid(pid)
        attempts = task.get("attempts", 0)
        limit = task.get("max_attempts", self.config["max_attempts"])
        status = "blocked" if attempts >= limit else "queued"
        state_module.advance(
            task, status, "interrupted", reason, owner=None, pid=None,
            lease_expires_at=0.0,
            next_attempt_at=self.now() + self.backoff(attempts) if status == "queued" else 0.0,
        )
        self.store.event(task["id"], "interrupted", reason, level="WARN")

    def monitor(self, data: dict) -> int:
        finished = 0
        now = self.now()
        for task in data["tasks"]:
            if task.get("status") != "running":
                continue
            task["lease_expires_at"] = now + self.config["lease_minutes"] * 60
            task["heartbeat_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            pid = task.get("pid")
            code = self.launcher.poll(pid) if pid else 0
            knows = getattr(self.launcher, "knows", lambda value: False)(pid)
            if code is None and pid and not knows and not self.git.is_pid_alive(pid) and \
                    evidence_path(self.store.root, task["id"]).is_file():
                self.store.event(task["id"], "orphan_exit",
                                 "worker exited before supervisor reattached; verifying evidence",
                                 level="WARN")
                code = 0
            if code is not None:
                self._collect_worker_evidence(task)
                state_module.advance(task, "verifying", "worker-exit", "",
                                     exit_code=code, lease_expires_at=now + self.config["lease_minutes"] * 60)
                self.store.event(task["id"], "worker_exit", f"exit={code}")
                finished += 1
                continue
            worktree = Path(task.get("worktree", ""))
            log = Path(self.config["state_root"]) / "logs" / (task["id"] + ".log")
            signature = list(progress_signature(worktree, log)) if worktree.is_dir() else []
            if signature != task.get("progress_signature"):
                task["progress_signature"] = signature
                task["last_progress_at"] = now
                continue
            last = float(task.get("last_progress_at", now))
            if now - last > self.config["stall_minutes"] * 60:
                self._interrupt(task, "worker stalled: no log or file progress")
            elif now - float(task.get("started_at", now)) > self.config["task_timeout_minutes"] * 60:
                self._interrupt(task, "worker exceeded task time limit")
        return finished

    # ---------- verification and publishing ----------

    def _pr_body(self, task: dict, evidence: dict, sha: str) -> str:
        tests = "\n".join(
            f"- `{row.get('command', '')}` — {row.get('result', '')} "
            f"{str(row.get('output_excerpt', ''))[:200]}"
            for row in evidence.get("tests", [])
        )
        return "\n".join([
            "Draft PR opened by the Canopy supervisor for human integration review.",
            "",
            f"Task: {task['id']} — {task['title']}",
            f"Commit: `{sha}`",
            f"Scope: {', '.join(task['scope'])}",
            f"Review base: {task.get('base') or self.config['base_branch']} (stacked PRs must not merge before their base)",
            "",
            "## Reported test evidence",
            tests or "- NOT RUN",
            "",
            f"Notes: {str(evidence.get('notes', ''))[:600]}",
            "",
            "No merge is authorized. Existing Canopy CI remains the source of check results; "
            "this PR does not add or duplicate a workflow. Owner visual signoff and real Mint "
            "evidence remain separate gates.",
        ])

    @staticmethod
    def _evidence_outcome(evidence: dict) -> str:
        """BLOCKED and NOT RUN are never successful campaign completions."""
        results = {row.get("result") for row in evidence.get("tests", [])
                   if isinstance(row, dict)}
        if "FAIL" in results:
            return "failed"
        if "BLOCKED" in results or "NOT RUN" in results:
            return "blocked"
        return "success"

    def _verify_artifacts(self, task: dict, evidence: dict, worktree: Path) -> None:
        """Implementation tasks must name real files with matching SHA-256."""
        if task.get("kind") != "implementation":
            return
        artifacts = evidence.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise PolicyError("implementation task has no verifiable artifacts")
        for item in artifacts:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                raise PolicyError("invalid artifact entry")
            path = worktree / item["path"]
            if not path.is_file():
                raise PolicyError("artifact missing: " + item["path"])
            expected = item.get("sha256")
            if isinstance(expected, str):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != expected:
                    raise PolicyError("artifact SHA-256 mismatch: " + item["path"])

    def publish(self, task: dict) -> None:
        """Verify claims, commit, push and open a draft PR. Never merge."""
        worktree = Path(task["worktree"])
        base_sha = task["base_sha"]
        try:
            evidence = read_evidence(Path(self.config["state_root"]), task["id"])
            outcome = self._evidence_outcome(evidence)
            pending = self.git.pending_files(worktree)
            if outcome == "blocked":
                # Preserve incomplete edits in the worker's local worktree.
                # Never commit or push a BLOCKED/NOT RUN task: its diff has
                # not passed the scope, artifact and test evidence gates.
                state_module.advance(
                    task, "blocked", "prerequisites-blocked",
                    str(evidence.get("notes", ""))[:500], owner=None, pid=None,
                    lease_expires_at=0.0,
                )
                self.store.event(task["id"], "blocked_no_pr",
                                 "unverified edits preserved locally; no push or PR",
                                 level="WARN")
                return
            if outcome == "failed":
                raise PolicyError("worker reported FAIL")
            if not pending or task.get("publish") is False:
                state_module.advance(task, "done", "no-publish", "",
                                     owner=None, pid=None, lease_expires_at=0.0)
                self.store.event(task["id"], "no_publish",
                                 "no worktree diff or publish disabled; evidence retained")
                return
            self._verify_artifacts(task, evidence, worktree)
            policy.validate_evidence(evidence, task, pending, pending_allowed=True)
            sha = self.git.commit_all(worktree, f"feat(supervisor): {task['title']}")
            changed = self.git.changed_files(worktree, base_sha)
            evidence["commit_sha"] = sha
            self._verify_artifacts(task, evidence, worktree)
            policy.validate_evidence(evidence, task, changed)
            self.git.push_branch(worktree, task["branch"], self.config["remote"])
            url = self.git.find_open_pr(worktree, repo_slug=self.config["repo_slug"],
                                        head=task["branch"])
            if not url:
                url = self.git.create_draft_pr(
                    worktree, repo_slug=self.config["repo_slug"],
                    base=task.get("base") or self.config["base_branch"], head=task["branch"],
                    title="DRAFT: " + task["title"],
                    body=self._pr_body(task, evidence, sha),
                    body_dir=Path(self.config["state_root"]) / "evidence" / task["id"],
                )
            number = url.rstrip("/").rsplit("/", 1)[-1]
            task["evidence"] = evidence
            task["pr"] = {"number": number, "url": url, "draft": True}
            state_module.advance(task, "awaiting_review", "draft-pr-opened", "",
                                 sha=sha, owner=None, pid=None, lease_expires_at=0.0)
            self.store.event(task["id"], "draft_pr", url, data={"sha": sha, "pr": number})
        except (WorkerError, PolicyError, gitops.GitError, OSError, ValueError) as exc:
            message = f"verification failed: {type(exc).__name__}: {exc}"
            state_module.advance(
                task, "failed", "verification-error", message, owner=None, pid=None,
                lease_expires_at=0.0,
                next_attempt_at=self.now() + self.backoff(task.get("attempts", 0)),
            )
            self.store.event(task["id"], "verification_failed", message, level="ERROR")

    # ---------- autonomous roadmap ----------

    def auto_queue(self, data: dict) -> int:
        """Refill the pipeline from the approved roadmap under the state lock."""
        if not self.config.get("auto_queue", True) or self.store.paused:
            return 0
        try:
            additions = roadmap.select(
                data["tasks"], self.config["max_workers"], self.store.root,
                protected=self.config.get("protected_paths"), now=self.now(),
            )
        except (roadmap.RoadmapError, policy.PolicyError, OSError, ValueError) as exc:
            self.store.event("-", "roadmap_error", str(exc), level="ERROR")
            return 0
        for definition in additions:
            task = state_module.new_task(definition, self.config["max_attempts"])
            data["tasks"].append(task)
            self.store.event(task["id"], "auto_queued",
                             "selected from approved roadmap", data={"scope": task["scope"]})
        return len(additions)

    # ---------- loop ----------

    def step(self) -> dict:
        data = self.store.load()
        self.recover(data)
        self.auto_queue(data)
        self.dispatch(data)
        self.monitor(data)
        self.verify(data)
        data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self.store.save(data)
        self.store.write_dashboard(data, self.config)
        return data

    def verify(self, data: dict) -> int:
        count = 0
        for task in data["tasks"]:
            if task.get("status") != "verifying":
                continue
            self._collect_worker_evidence(task)
            self.publish(task)
            self.store.save(data)
            count += 1
        return count

    def stop(self) -> None:
        self._stop.set()

    def run(self, *, once: bool = False, until_idle: bool = False,
            max_steps: int | None = None, interval: float | None = None) -> dict:
        """Loop with a per-step lock so operators can feed tasks between steps."""
        interval = float(interval if interval is not None else self.config["poll_seconds"])
        steps = 0
        with state_module.exclusive_lock(self.store.lock_path):
            self.store.event("-", "supervisor_start", "model=" + self.config["model"])
        try:
            while not self._stop.is_set() and not self.store.stop_path.exists():
                with state_module.exclusive_lock(self.store.lock_path):
                    data = self.step()
                steps += 1
                if once or (max_steps is not None and steps >= max_steps):
                    break
                # Explicit bounded-wave mode ends only after the approved
                # roadmap has no more assignments and all workers are done.
                # Normal run remains continuous for other workflows.
                if until_idle and not any(
                    task.get("status") in ("queued", "assigned", "running",
                                           "verifying", "publishing", "interrupted")
                    for task in data["tasks"]
                ):
                    break
                self._stop.wait(interval)
        except KeyboardInterrupt:
            self.stop()
        finally:
            stop_requested = self._stop.is_set() or self.store.stop_path.exists()
            # A one-shot diagnostic step must not kill live workers.
            if stop_requested:
                with state_module.exclusive_lock(self.store.lock_path):
                    self.shutdown()
                self.store.stop_path.unlink(missing_ok=True)
        return self.store.load()

    def shutdown(self) -> None:
        """Checkpoint active tasks so a restart can recover them safely."""
        data = self.store.load()
        for task in data["tasks"]:
            if task.get("status") in state_module.ACTIVE_STATUSES:
                if task.get("pid"):
                    self.git.terminate_pid(task["pid"])
                state_module.advance(task, "interrupted", "clean-shutdown",
                                     "supervisor stopped before task finished",
                                     owner=None, pid=None, lease_expires_at=0.0)
                self.store.event(task["id"], "shutdown", "checkpoint saved", level="WARN")
        self.store.save(data)
        self.store.write_dashboard(data, self.config)
        self.store.event("-", "supervisor_stop")

    def prune(self) -> int:
        """Remove worktrees of terminal tasks; never deletes task history."""
        repo = Path(self.config["repo"])
        data = self.store.load()
        removed = 0
        for task in data["tasks"]:
            path = task.get("worktree")
            if path and task.get("status") in state_module.TERMINAL_STATUSES:
                self.git.worktree_remove(repo, Path(path))
                removed += 1
        return removed
