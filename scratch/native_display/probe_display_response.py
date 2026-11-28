#!/usr/bin/env python3
"""M4 display-response boundedness probe (SYNTHETIC, host-side).

Drives the owned pure-Python display modules through monitor add/remove and
HiDPI scaling scenarios and records each returned plan plus invariant checks.
This is decision-logic evidence only: no Qt, no guest, no hardware access, no
polling, no window resize and no visual claim. Output is deterministic JSON on
stdout; write it to a file with a shell redirect when collecting evidence.
"""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from canopy_features.dock.display_change_response import (  # noqa: E402
    EVENT_DPI_CHANGED, KIND_HOLD, KIND_NO_OP, KIND_RELAYOUT, KIND_SUSPEND,
    MAX_HISTORY, ROOT_HEIGHT, ROOT_WIDTH, DisplayEvent, DisplayChangeResponse,
)
from canopy_features.dock.display_geometry_contract import (  # noqa: E402
    validate_dock_bounds,
)
from canopy_features.reliability.screen_topology_change import (  # noqa: E402
    EVENT_CONNECT, Monitor, ScreenTopologyModel, Topology,
)

ALLOWED_KINDS = frozenset(
    {KIND_RELAYOUT, KIND_HOLD, KIND_SUSPEND, KIND_NO_OP, EVENT_DPI_CHANGED})


def plan_record(label, plan, scale=1.0):
    """Project one plan into a deterministic, checked record."""
    size = tuple(plan.size)
    problems = []
    if plan.kind not in ALLOWED_KINDS:
        problems.append("unknown_kind")
    if (type(size) is not tuple or len(size) != 2
            or any(type(v) is not int or v <= 0 for v in size)):
        problems.append("nonpositive_size")
    else:
        if size[0] > ROOT_WIDTH or size[1] > ROOT_HEIGHT:
            problems.append("above_frozen_root")
        if not validate_dock_bounds(*size, scale=scale).ok:
            problems.append("unsafe_dock_bounds")
    return {
        "label": label,
        "sequence": plan.sequence,
        "kind": plan.kind,
        "size": list(size),
        "reason": plan.reason,
        "scale": scale,
        "invariants": problems or ["bounded", "dock_safe", "frozen_root"],
        "ok": not problems,
    }


def assert_ok(condition, message):
    if not condition:
        raise AssertionError(message)


def scenario_secondary_connect():
    model = ScreenTopologyModel()
    response = DisplayChangeResponse()
    base = Topology([Monitor("eDP-1", 1920, 1080, True)])
    response.handle_recovery_result(model.apply(base))
    expanded = Topology([Monitor("eDP-1", 1920, 1080, True),
                         Monitor("HDMI-1", 2560, 1440, False)])
    plan = response.handle_recovery_result(model.apply(expanded))
    record = plan_record("secondary_monitor_connected", plan)
    assert_ok(record["ok"], "secondary connect plan is unbounded")
    assert_ok(plan.kind == KIND_RELAYOUT, "secondary connect must relayout")
    return [record]


def scenario_secondary_disconnect():
    model = ScreenTopologyModel()
    response = DisplayChangeResponse()
    primary = Monitor("eDP-1", 1920, 1080, True)
    model.apply(Topology([primary]))
    expanded = Topology([primary, Monitor("HDMI-1", 2560, 1440, False)])
    response.handle_recovery_result(model.apply(expanded))
    plan = response.handle_recovery_result(model.apply(Topology([primary])))
    record = plan_record("secondary_monitor_disconnected", plan)
    assert_ok(record["ok"], "secondary disconnect plan is unbounded")
    assert_ok(plan.kind == KIND_RELAYOUT, "surviving primary must relayout")
    assert_ok(plan.size == (ROOT_WIDTH, ROOT_HEIGHT), "unexpected safe size")
    return [record]


def scenario_primary_disconnect_survivor():
    model = ScreenTopologyModel()
    response = DisplayChangeResponse()
    old_primary = Monitor("eDP-1", 1920, 1080, True)
    survivor = Monitor("HDMI-1", 2560, 1440, False)
    model.apply(Topology([old_primary, survivor]))
    result = model.apply(Topology([survivor]))
    assert_ok(result.safe_topology.primary is not None,
              "surviving monitor must be reanchored")
    plan = response.handle_recovery_result(result)
    record = plan_record("primary_disconnected_survivor_reanchors", plan)
    assert_ok(record["ok"], "reanchor plan is unbounded")
    assert_ok(plan.kind != KIND_SUSPEND, "survivor must not suspend desktop")
    return [record]


def scenario_all_disconnected():
    model = ScreenTopologyModel()
    response = DisplayChangeResponse()
    model.apply(Topology([Monitor("eDP-1", 1920, 1080, True)]))
    plan = response.handle_recovery_result(model.apply(Topology(())))
    record = plan_record("all_displays_disconnected", plan)
    assert_ok(record["ok"], "suspend plan is unbounded")
    assert_ok(plan.kind == KIND_SUSPEND, "no display must suspend")
    assert_ok(response.last_safe_size == (ROOT_WIDTH, ROOT_HEIGHT),
              "suspend changed the last safe size")
    return [record]


def scenario_hidpi(physical, scale, label, expected_kind, expected_size):
    response = DisplayChangeResponse()
    plan = response.handle_logical_dpi_change(physical[0], physical[1],
                                              scale, "DP-1")
    record = plan_record(label, plan, scale=scale)
    assert_ok(record["ok"], "HiDPI plan is unbounded")
    assert_ok(plan.kind == expected_kind, "unexpected HiDPI plan kind")
    assert_ok(tuple(plan.size) == expected_size, "unexpected logical size")
    return [record]


def scenario_hidpi_same_logical_size():
    response = DisplayChangeResponse()
    first = response.handle_logical_dpi_change(1920, 1080, 2.0, "DP-1")
    second = response.handle_logical_dpi_change(2880, 1620, 3.0, "DP-1")
    records = [plan_record("hidpi_first", first, scale=2.0),
               plan_record("hidpi_same_logical_size", second, scale=3.0)]
    assert_ok(all(item["ok"] for item in records), "same-logical plan unbounded")
    assert_ok(second.kind == KIND_NO_OP, "same logical size must be a no_op")
    assert_ok(second.reason == "logical_size_unchanged", "wrong no_op reason")
    return records


def scenario_hostile_events():
    response = DisplayChangeResponse()
    hostile = (
        DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080,
                     scale=float("nan")),
        DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=1080, scale=0),
        DisplayEvent(EVENT_DPI_CHANGED, width=True, height=1080, scale=2.0),
        DisplayEvent(EVENT_DPI_CHANGED, width=1920, height=10 ** 9, scale=1.0),
        {"kind": EVENT_DPI_CHANGED, "width": 1920, "height": 1080,
         "scale": "1.5"},
        None,
    )
    records = []
    for index, event in enumerate(hostile):
        plan = response.handle(event)
        record = plan_record("hostile_event_%02d" % index, plan)
        assert_ok(record["ok"], "hostile event produced an unbounded plan")
        assert_ok(plan.kind == KIND_HOLD, "hostile event must be held")
        assert_ok(plan.reason == "invalid_event", "hostile event mislabelled")
        records.append(record)
    return records


def scenario_hostile_changes():
    response = DisplayChangeResponse()
    hostile = (
        DisplayEvent(EVENT_CONNECT, width=1920, height=1080, changes=("x",)),
        DisplayEvent(EVENT_CONNECT, width=1920, height=1080,
                     changes=(("connect", "HDMI-1"),) * 17),
        DisplayEvent(EVENT_CONNECT, width=1920, height=1080,
                     changes=(("connect", "x" * 81),)),
        DisplayEvent(EVENT_CONNECT, width=1920, height=1080,
                     changes=[("connect", "HDMI-1")]),
    )
    records = []
    for index, event in enumerate(hostile):
        plan = response.handle(event)
        record = plan_record("hostile_changes_%02d" % index, plan)
        assert_ok(record["ok"], "hostile changes produced an unbounded plan")
        assert_ok(plan.kind == KIND_HOLD, "hostile changes must be held")
        assert_ok(plan.reason == "invalid_event", "hostile changes mislabelled")
        records.append(record)
    return records


def scenario_duplicate_topology_noop():
    model = ScreenTopologyModel()
    response = DisplayChangeResponse()
    primary = Monitor("eDP-1", 1920, 1080, True)
    topology = Topology([primary, Monitor("HDMI-1", 2560, 1440, False)])
    result = model.apply(topology)
    first = response.handle_recovery_result(result)
    second = response.handle_recovery_result(result)
    records = [plan_record("topology_first", first),
               plan_record("topology_duplicate", second)]
    assert_ok(all(item["ok"] for item in records), "duplicate plan unbounded")
    assert_ok(first.kind == KIND_RELAYOUT, "first snapshot must relayout")
    assert_ok(second.kind == KIND_NO_OP, "duplicate snapshot must be a no_op")
    return records


def scenario_history_bound():
    response = DisplayChangeResponse()
    for index in range(MAX_HISTORY + 20):
        response.handle(DisplayEvent(
            EVENT_DPI_CHANGED, width=1920 + index % 2, height=1080,
            scale=2.0))
    assert_ok(len(response.history) == MAX_HISTORY,
              "history exceeded its bound")
    return [{"label": "history_bound", "limit": MAX_HISTORY,
             "observed": len(response.history), "ok": True}]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def base_sha():
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(ROOT),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=True, text=True).stdout.strip()
    except Exception:
        return "unknown"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", help="optional JSON output path")
    args = parser.parse_args()

    scenarios = []
    for name, func in (
        ("secondary_connect", scenario_secondary_connect),
        ("secondary_disconnect", scenario_secondary_disconnect),
        ("primary_disconnect_survivor", scenario_primary_disconnect_survivor),
        ("all_disconnected", scenario_all_disconnected),
        ("hidpi_150pct", lambda: scenario_hidpi(
            (1920, 1080), 1.5, "hidpi_150pct", KIND_RELAYOUT, (1200, 720))),
        ("hidpi_200pct", lambda: scenario_hidpi(
            (2560, 1440), 2.0, "hidpi_200pct", KIND_RELAYOUT, (1200, 720))),
        ("hidpi_same_logical", scenario_hidpi_same_logical_size),
        ("hostile_events", scenario_hostile_events),
        ("hostile_changes", scenario_hostile_changes),
        ("duplicate_topology_noop", scenario_duplicate_topology_noop),
        ("history_bound", scenario_history_bound),
    ):
        try:
            records = func()
            status = "PASS"
        except Exception as exc:
            records = [{"label": name, "error": repr(exc)}]
            status = "FAIL"
        scenarios.append({"scenario": name, "status": status,
                          "records": records})

    modules = ("canopy_features/dock/display_change_response.py",
               "canopy_features/dock/display_geometry_contract.py",
               "canopy_features/dock/display_scaling_contract.py")
    report = {
        "artifact": "m4_display_response_probe",
        "schema_version": 1,
        "classification": "SYNTHETIC",
        "host_platform": platform.platform(),
        "base_sha": base_sha(),
        "module_sha256": {path: sha256(ROOT / path) for path in modules},
        "native_runtime": "NOT_RUN",
        "scenarios": scenarios,
        "verdict": ("PASS" if all(item["status"] == "PASS"
                                  for item in scenarios) else "FAIL"),
    }
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if report["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
