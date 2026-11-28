"""M4 native-session recovery verification harness (bounded, offline logic).

Each invocation is a fresh Python process. It reads/writes only a caller-owned
state root inside a temporary directory, except for the ``probe`` mode which
makes no state writes. All results are JSON on stdout so host and guest runs
can be compared byte-for-byte.

This is a SYNTHETIC process-restart model of logout/restart and crash
recovery. It does not terminate a desktop session, launch a compositor, or
claim visual/acceptance behavior. A real Plasma host may run it unchanged;
see docs/NATIVE_SESSION_RECOVERY.md for the evidence boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from canopy_features.reliability import lock_session_events as lock
from canopy_features.reliability import session_lifecycle_snapshot as snapshot
from canopy_features.reliability import startup_checkpoints as checkpoints
from canopy_features.reliability import theme_transition_rollback as theme
from canopy_features.settings import persisted_preferences as preferences
from canopy_features.windows import focus_intents as focus

USER = "alice"
STEPS = ("dock", "menu", "search")
LEGACY_RAW = b'{"reduced_motion":"reduce"}'


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _root(arg: str) -> Path:
    root = Path(arg).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _store(root: Path):
    return preferences.PersistedPreferences.for_user(root, USER)


def _emit(mode: str, root: Path, **fields):
    print(json.dumps({
        "mode": mode,
        "verdict": "PASS",
        "python": sys.version.split()[0],
        "root": str(root),
        **fields,
    }, sort_keys=True, separators=(",", ":")))


def write(root: Path, value: str = "reduce"):
    store = _store(root)
    assert store.set("reduced_motion", value) is True
    path = store.path
    _emit("write", root, value=value, state_sha256=_sha(path))


def read(root: Path, expected=None):
    store = _store(root)
    value = store.view("reduced_motion").value
    assert value in preferences.KEYS["reduced_motion"]["values"]
    if expected is not None:
        assert value == expected, "stored preference did not survive restart"
    _emit("read", root, value=value, state_sha256=_sha(store.path))


def legacy_read(root: Path):
    store = _store(root)
    path = store.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(LEGACY_RAW)
    # Fresh instance: no in-memory state survives from the writer.
    reopened = _store(root)
    value = reopened.view("reduced_motion").value
    assert value == "reduce", value
    assert path.read_bytes() == LEGACY_RAW, "read migrated a file without a write"
    _emit("legacy_read", root, value=value, state_sha256=_sha(path),
          legacy_source_sha256=hashlib.sha256(LEGACY_RAW).hexdigest())


def legacy_commit(root: Path):
    store = _store(root)
    path = store.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(LEGACY_RAW)
    reopened = _store(root)
    assert reopened.view("reduced_motion").value == "reduce"
    assert reopened.set("reduced_motion", "full") is True
    committed = json.loads(path.read_text(encoding="utf-8"))
    assert committed == {"version": 1, "values": {"reduced_motion": "full"}}
    quarantine = Path(str(path) + preferences.CORRUPT_SUFFIX)
    assert quarantine.read_bytes() == LEGACY_RAW, "legacy bytes were lost"
    after_restart = _store(root)
    assert after_restart.view("reduced_motion").value == "full"
    _emit("legacy_commit", root, value="full", state_sha256=_sha(path),
          quarantine_sha256=_sha(quarantine))


def crash(root: Path):
    directory = root / "startup"
    journal = checkpoints.StartupCheckpoints(directory, STEPS)
    journal.begin()
    journal.complete("dock")
    journal.complete("menu")
    decided = checkpoints.StartupCheckpoints(directory, STEPS).recover()
    assert decided.action == checkpoints.ROLLBACK, decided
    assert decided.completed == ("dock", "menu")
    assert decided.unwind == ("menu", "dock")
    assert decided.safe_to_start is False
    assert decided.needs_rollback is True
    durable = journal.path.read_bytes()
    again = checkpoints.StartupCheckpoints(directory, STEPS).recover()
    assert again == decided
    assert journal.path.read_bytes() == durable
    _emit("crash", root, action=decided.action,
          completed=list(decided.completed), unwind=list(decided.unwind),
          target=decided.target, safe_to_start=decided.safe_to_start,
          state_sha256=_sha(journal.path), repeat_decision_stable=True)


def crash_corrupt(root: Path):
    directory = root / "startup"
    journal = checkpoints.StartupCheckpoints(directory, STEPS)
    journal.begin()
    raw = b'{"schema":1,"steps":["dock"'
    journal.path.write_bytes(raw)
    decided = checkpoints.StartupCheckpoints(directory, STEPS).recover()
    assert decided.action == checkpoints.FAIL_CLOSED, decided
    assert decided.completed == ()
    assert decided.safe_to_start is False
    assert journal.path.read_bytes() == raw, "untrusted bytes were overwritten"
    _emit("crash_corrupt", root, action=decided.action,
          safe_to_start=decided.safe_to_start, state_sha256=_sha(journal.path),
          raw_preserved=True)


def safe_state(root: Path):
    directory = root / "startup"
    journal = checkpoints.StartupCheckpoints(directory, STEPS)
    journal.begin()
    journal.complete("dock")
    decision = checkpoints.StartupCheckpoints(directory, STEPS).recover()
    locked = lock.Reconciler(initial_locked=True)
    record = snapshot.compose(
        locked, theme.ThemeTransitionRollback(),
        focus.FocusBroker(lambda *_: True))
    assert record.status == snapshot.STATUS_BLOCKED
    assert record.acceptance == snapshot.ACCEPTANCE_NOT_ESTABLISHED
    assert record.event_observation == snapshot.EVENT_OBSERVATION_NOT_PERFORMED
    assert decision.safe_to_start is False
    _emit("safe_state", root, recovery_action=decision.action,
          recovery_safe_to_start=decision.safe_to_start,
          session_status=record.status,
          acceptance=record.acceptance,
          event_observation=record.event_observation)


def probe(root: Path):
    _emit("probe", root, modules=[
        preferences.__name__, checkpoints.__name__, snapshot.__name__])


MODES = {
    "write": write, "read": read, "legacy_read": legacy_read,
    "legacy_commit": legacy_commit, "crash": crash,
    "crash_corrupt": crash_corrupt, "safe_state": safe_state,
    "probe": probe,
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=sorted(MODES))
    parser.add_argument("root")
    parser.add_argument("--expected", default=None,
                        help="required preference value for the read mode")
    args = parser.parse_args(argv)
    target = _root(args.root)
    if args.mode == "read":
        read(target, args.expected)
    else:
        MODES[args.mode](target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
