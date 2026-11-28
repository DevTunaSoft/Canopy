#!/usr/bin/env python3
"""Deterministic A->B->A switching harness for the eight built-in Shell Packs.

LABEL: SYNTHETIC / STATIC_PYTHON_HARNESS. This drives the existing in-process
``canopy_core.shell_host.ShellHost`` with inert presenters. It does NOT run a
compiled Qt shell, a compositor, a Linux Mint guest session or any pack QML,
and it is NOT native desktop acceptance evidence. See docs/NATIVE_SHELL_PACKS.md
for the exact native blocker.

Usage:
    python -m tools.shell_packs.roundtrip_harness --rounds 100 \
        --evidence scratch/native_shell_packs/roundtrip_100.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from canopy_core.registry import PackScan, ShellPackInfo
from canopy_core.shell_host import ShellHost, SwitchBusy
from canopy_features.settings.shell_pack_selection import (
    BUILTIN_IDS,
    BUILTIN_PACKS,
    INCLUDED_TIER,
    MAX_HISTORY,
    PAID_TIERS,
    SHARED_CORE_SERVICES,
    ShellPackSelectionError,
    PackSwitchLedger,
    validate_future_pack,
    validate_pack_id,
)

__all__ = ["run", "run_round_trips", "negative_controls", "self_test"]

HARNESS_SCHEMA = 1
DEFAULT_ROUNDS = 100
HOST_CAPABILITIES = frozenset({
    "app-launcher", "dock", "top-bar", "taskbar", "workspace-list",
    "window-list", "system-status", "settings-panel",
})
PACK_CAPABILITIES = frozenset({"app-launcher", "dock", "top-bar",
                               "workspace-list", "window-list"})
NATIVE_BLOCKER = {
    "code": "NO_COMPILED_SWITCHER_WIRING",
    "detail": (
        "The base tree has only the in-process Python lifecycle prototype "
        "canopy_core.shell_host.ShellHost with inert presenters; no compiled "
        "Qt/host entry point calls ShellHost.switch. "
        "docs/SHELL_PACK_ARCHITECTURE.md states it is not connected to Qt, "
        "compositor/window state or a Mint session. A Mint VM therefore has "
        "no native switcher to exercise."
    ),
    "source": "docs/SHELL_PACK_ARCHITECTURE.md:178-198",
    "vm_observed": "Canopy-Test-Plasma6 registered and running; not used",
    "guest_switch_session": "NOT_RUN",
}


class InjectedFailure(RuntimeError):
    """Bounded test-only presenter failure, never a product exception."""


class LifecycleTracker:
    """Counts inert presenter transitions; proves single active ownership."""

    def __init__(self):
        self.active = 0
        self.max_active = 0
        self.created = 0
        self.disposed = 0

    def activate(self, pack_id):
        if type(pack_id) is not str or not pack_id:
            raise InjectedFailure("presenter has no identity")
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        if self.active > 1:
            # Never leave the duplicate counted: fail closed immediately.
            self.active -= 1
            raise InjectedFailure("duplicate active presenter")

    def deactivate(self):
        self.active -= 1
        if self.active < 0:
            self.active += 1
            raise InjectedFailure("deactivated an inactive presenter")

    def dispose(self):
        self.disposed += 1


class Injection:
    """Bounded, one-shot failure tokens consumed at the lifecycle call site."""

    def __init__(self, failures=None):
        self.queue = {}
        for pack_id, methods in (failures or {}).items():
            self.queue[pack_id] = list(methods)

    def should_fail(self, pack_id, method):
        queued = self.queue.get(pack_id)
        if queued and queued[0] == method:
            queued.pop(0)
            return True
        return False


class InertPresenter:
    """Pure state machine; no QML, process, socket or window is touched."""

    def __init__(self, pack_id, tracker, injection=None, on_prepare=None):
        self.pack_id = pack_id
        self.tracker = tracker
        self.injection = injection
        self.on_prepare = on_prepare
        self.phase = "new"
        self.calls = []
        tracker.created += 1

    def _fails(self, method):
        return self.injection is not None and self.injection.should_fail(
            self.pack_id, method)

    def prepare(self):
        if self._fails("prepare"):
            raise InjectedFailure("injected prepare failure")
        if self.phase != "new":
            raise InjectedFailure("prepare on a used presenter")
        self.calls.append("prepare")
        self.phase = "prepared"
        if self.on_prepare is not None:
            self.on_prepare()

    def activate(self):
        if self._fails("activate"):
            raise InjectedFailure("injected activate failure")
        if self.phase == "active":
            # Idempotent reactivation is what the host's rollback path needs.
            return
        if self.phase != "prepared":
            raise InjectedFailure("activate before prepare")
        self.tracker.activate(self.pack_id)
        self.calls.append("activate")
        self.phase = "active"

    def deactivate(self):
        if self._fails("deactivate"):
            raise InjectedFailure("injected deactivate failure")
        if self.phase in ("prepared", "disposed"):
            return
        if self.phase != "active":
            raise InjectedFailure("deactivate before prepare")
        self.tracker.deactivate()
        self.calls.append("deactivate")
        self.phase = "prepared"

    def dispose(self):
        if self._fails("dispose"):
            raise InjectedFailure("injected dispose failure")
        if self.phase == "disposed":
            return
        if self.phase == "active":
            raise InjectedFailure("dispose of an active presenter")
        self.tracker.dispose()
        self.calls.append("dispose")
        self.phase = "disposed"


class BoundFactory:
    """Bind one trusted factory instance to its reserved pack identity."""

    def __init__(self, shared, pack_id):
        self.shared = shared
        self.pack_id = pack_id

    def __call__(self):
        return self.shared(self.pack_id)


class TrustedFactory:
    """Host-side factory map; never derived from pack metadata or paths."""

    def __init__(self, tracker, injection=None):
        self.tracker = tracker
        self.injection = injection
        self.calls = 0

    def __call__(self, pack_id):
        self.calls += 1
        return InertPresenter(pack_id, self.tracker, injection=self.injection)


def _catalog():
    entries = tuple(
        ShellPackInfo(
            pack_id=pack.pack_id,
            name=pack.name,
            description="reserved built-in; included at no cost",
            directory=Path("builtin") / pack.pack_id,
            entrypoint="ui/Main.qml",
            shell_api=1,
            ui_engine="qt-qml",
            capabilities=PACK_CAPABILITIES,
        )
        for pack in BUILTIN_PACKS
    )
    return PackScan(packs=entries, problems=(), checked_directories=len(entries))


def make_host(failures=None):
    """Build one host with inert, host-registered factories."""
    tracker = LifecycleTracker()
    factory = TrustedFactory(tracker, Injection(failures))
    factories = {pack_id: BoundFactory(factory, pack_id)
                 for pack_id in BUILTIN_IDS}
    host = ShellHost(_catalog(), factories, HOST_CAPABILITIES)
    return host, tracker, factory


def perform_switch(host, ledger, target):
    """Prepare -> attempt -> commit only on verified success; else rollback."""
    token = ledger.prepare(target)
    result = host.switch(target)
    if result.success and result.active_id == target and not host.needs_recovery:
        ledger.commit(token)
    else:
        ledger.rollback(token)
    return result


def run_round_trips(rounds):
    """Return counts for ``rounds`` A->B->A cycles across all eight packs."""
    if type(rounds) is not int or rounds < 1:
        raise ShellPackSelectionError("rounds must be a positive integer")
    host, tracker, factory = make_host()
    first = BUILTIN_IDS[0]
    initial = host.switch(first)
    if not initial.success or host.active_id != first:
        raise AssertionError("initial Classic presentation did not activate")
    ledger = PackSwitchLedger(initial_id=first)

    switches = successes = 0
    results = []
    for index in range(rounds):
        a = BUILTIN_IDS[index % len(BUILTIN_IDS)]
        b = BUILTIN_IDS[(index + 1) % len(BUILTIN_IDS)]
        for target in (b, a):
            result = perform_switch(host, ledger, target)
            switches += 1
            if result.status == "SWITCHED":
                successes += 1
            if host.active_id != target or host.needs_recovery:
                raise AssertionError("host state diverged at switch %d" % switches)
            if ledger.snapshot().committed_id != target:
                raise AssertionError("selection committed at the wrong boundary")
            if tracker.active != 1 or tracker.max_active != 1:
                raise AssertionError("duplicate or missing active presenter")
            results.append(result.status)
    active_during = tracker.active
    dispose_during = tracker.disposed
    stop_result = host.stop()
    final = {
        "round_trips": rounds,
        "switches": switches,
        "switch_successes": successes,
        "factory_calls": factory.calls,
        "presenters_created": tracker.created,
        "presenters_disposed": tracker.disposed,
        "presenters_disposed_during_switching": dispose_during,
        "active_presenter_during_switching": active_during,
        "active_presenter_after_stop": tracker.active,
        "active_presenter_max": tracker.max_active,
        "needs_recovery": host.needs_recovery,
        "committed_id": ledger.snapshot().committed_id,
        "history_bounded": len(ledger.snapshot().history) <= MAX_HISTORY,
        "statuses": sorted(set(results)),
        "stopped": stop_result.status,
    }
    if successes != switches or final["active_presenter_max"] != 1:
        raise AssertionError("round-trip invariants failed")
    if (active_during != 1 or tracker.active != 0
            or tracker.created != tracker.disposed):
        raise AssertionError("inert presenters were not released after stop")
    return final


def negative_controls():
    """Bounded ROLLBACK / REJECTED / RECOVERY controls for one failed switch."""
    source = BUILTIN_IDS[0]
    target = BUILTIN_IDS[1]
    outcomes = {}
    for name, fail in (("prepare", "prepare"), ("activate", "activate"),
                       ("deactivate", "deactivate")):
        # Deactivate failure is injected on the already-active source view;
        # prepare/activate failures are injected on the candidate.
        injected_on = source if name == "deactivate" else target
        host, tracker, _ = make_host({injected_on: [fail]})
        assert host.switch(source).success
        ledger = PackSwitchLedger(initial_id=source)
        result = perform_switch(host, ledger, target)
        state = ledger.snapshot()
        expected = {
            "prepare": "PREPARE_FAILED",
            "activate": "ACTIVATE_FAILED",
            "deactivate": "DEACTIVATE_FAILED",
        }[name]
        if (result.status != expected or host.active_id != source
                or host.needs_recovery or state.committed_id != source
                or tracker.active != 1):
            raise AssertionError("rollback control %s failed" % name)
        outcomes[name] = {
            "status": result.status,
            "active_id": host.active_id,
            "committed_id": state.committed_id,
            "recovery_required": host.needs_recovery,
        }

    # Unrecoverable candidate teardown must require out-of-band recovery,
    # without pretending the original presentation was restored.
    host, tracker, _ = make_host({target: ["activate", "deactivate"]})
    assert host.switch(source).success
    ledger = PackSwitchLedger(initial_id=source)
    result = perform_switch(host, ledger, target)
    if result.status != "RECOVERY_REQUIRED" or not host.needs_recovery:
        raise AssertionError("recovery control failed")
    if ledger.snapshot().committed_id != source:
        raise AssertionError("failed activation changed the persisted selection")
    outcomes["recovery"] = {
        "status": result.status,
        "recovery_required": host.needs_recovery,
        "committed_id": ledger.snapshot().committed_id,
    }

    # Untrusted target IDs and unsupported capabilities are refused before a
    # factory is invoked; no duplicate service or second presenter is built.
    host, tracker, factory = make_host()
    assert host.switch(source).success
    for bad in ("", "org.canopy.fake", "org.example..pack", 7,
                "org.example.pack" * 20):
        result = host.switch(bad)
        if result.status != "REJECTED" or host.active_id != source:
            raise AssertionError("invalid target was not rejected")
    if factory.calls != 1:
        raise AssertionError("rejected targets reached a trusted factory")
    outcomes["rejected_targets"] = {"count": 5, "factory_calls": factory.calls}

    # Synchronous reentrancy must be refused rather than queued.
    reentrant = {}
    state = {}

    def reenter():
        try:
            state["host"].switch(BUILTIN_IDS[2])
        except SwitchBusy:
            reentrant["busy"] = True

    tracker = LifecycleTracker()
    factory = TrustedFactory(tracker)
    factories = {pack_id: BoundFactory(factory, pack_id)
                 for pack_id in BUILTIN_IDS}
    # A fresh host whose target presenter re-enters during prepare.
    re_host = ShellHost(_catalog(), factories, HOST_CAPABILITIES)
    state["host"] = re_host
    assert re_host.switch(source).success
    re_host._factories[target] = lambda: InertPresenter(
        target, tracker, on_prepare=reenter)
    result = re_host.switch(target)
    if not reentrant.get("busy") or not result.success:
        raise AssertionError("reentrant switch was not refused")
    outcomes["reentrancy"] = {"SwitchBusy": True,
                              "outer_status": result.status}
    return outcomes


def self_test():
    """Deterministic contract checks; no external test runner is required."""
    if len(BUILTIN_IDS) != 8 or len(set(BUILTIN_IDS)) != 8:
        raise AssertionError("built-in inventory must hold exactly eight IDs")
    expected = ("org.canopy.classic", "org.canopy.modern",
                "org.canopy.heritage", "org.canopy.flow", "org.canopy.lite",
                "org.canopy.studio", "org.canopy.cloud", "org.canopy.touch")
    if BUILTIN_IDS != expected:
        raise AssertionError("approved built-in identity order changed")
    if any(pack.tier != INCLUDED_TIER for pack in BUILTIN_PACKS):
        raise AssertionError("a built-in pack acquired a tier")
    if PAID_TIERS:
        raise AssertionError("paid tiers are not allowed")
    if len(SHARED_CORE_SERVICES) != 7:
        raise AssertionError("shared core service inventory changed")
    for pack_id in BUILTIN_IDS:
        validate_pack_id(pack_id)
    for bad in (None, True, 7, "", "org.canopy.other", "org.example"):
        try:
            validate_future_pack(bad)
        except (ShellPackSelectionError, TypeError):
            pass
        else:
            raise AssertionError("invalid future identity was accepted")
    # No cap: 64 distinct future identities are all accepted.
    for index in range(64):
        validate_future_pack("org.example.future%d" % index)
    ledger = PackSwitchLedger(initial_id=BUILTIN_IDS[0])
    token = ledger.prepare(BUILTIN_IDS[1])
    if ledger.snapshot().pending_id != BUILTIN_IDS[1]:
        raise AssertionError("prepare did not record a pending target")
    ledger.rollback(token)
    if ledger.snapshot().committed_id != BUILTIN_IDS[0]:
        raise AssertionError("rollback changed the committed selection")
    try:
        ledger.rollback(token)
    except ShellPackSelectionError:
        pass
    else:
        raise AssertionError("a spent token was accepted twice")
    for index in range(40):
        target = BUILTIN_IDS[(index % 7) + 1]
        snapshot = ledger.snapshot()
        if snapshot.committed_id != target:
            token = ledger.prepare(target)
            ledger.commit(token)
    if len(ledger.snapshot().history) != MAX_HISTORY:
        raise AssertionError("selection history exceeded its bound")
    return {"checks": 12, "builtin_count": 8, "future_ids_checked": 64,
            "history_cap": MAX_HISTORY}


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode("utf-8")


def run(rounds=DEFAULT_ROUNDS, evidence_path=None):
    """Execute all checks and return a canonical, hash-labelled report."""
    checks = self_test()
    roundtrips = run_round_trips(rounds)
    controls = negative_controls()
    payload = {
        "schema": HARNESS_SCHEMA,
        "harness": "tools/shell_packs/roundtrip_harness.py",
        "labels": ["SYNTHETIC", "STATIC_PYTHON_HARNESS",
                   "NOT_MINT_RUNTIME", "NO_VISUAL_CHANGE"],
        "claims": {
            "native_mint_round_trip": "NOT_RUN",
            "compiled_qt_switcher": "NOT_RUN",
            "pack_qml_execution": "NOT_RUN",
            "screen_reader": "NOT_RUN",
            "real_hardware_resources": "NOT_RUN",
            "process_or_socket": "NOT_RUN",
        },
        "blocker": NATIVE_BLOCKER,
        "inventory": {
            "builtin_ids": list(BUILTIN_IDS),
            "count": len(BUILTIN_IDS),
            "tier": INCLUDED_TIER,
            "paid_tiers": sorted(PAID_TIERS),
            "future_pack_cap": None,
            "shared_core_services": sorted(SHARED_CORE_SERVICES),
        },
        "contract_checks": checks,
        "round_trips": roundtrips,
        "negative_controls": controls,
        "python": "%d.%d.%d" % sys.version_info[:3],
    }
    payload["sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    text = json.dumps(payload, sort_keys=True, indent=2) + "\n"
    if evidence_path is not None:
        target = Path(evidence_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--evidence", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        payload = run(args.rounds, args.evidence)
    except (AssertionError, ShellPackSelectionError) as exc:
        print("SHELL_PACK_HARNESS_FAIL: %s" % exc, file=sys.stderr)
        return 1
    summary = payload["round_trips"]
    print("SHELL_PACK_HARNESS_PASS rounds=%d switches=%d successes=%d "
          "active_max=%d sha256=%s label=SYNTHETIC/STATIC_PYTHON_HARNESS"
          % (summary["round_trips"], summary["switches"],
             summary["switch_successes"], summary["active_presenter_max"],
             payload["sha256"]))
    if args.evidence is not None:
        print("evidence=%s" % args.evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
