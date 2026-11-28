"""One-shot read-only host-status reader for M4 suspend/resume evidence.

This CLI reads text that a trusted host has *already captured* from the
existing logind, UPower and Plasma host-status interfaces. It runs once,
writes nothing, opens no bus, invokes no command, starts no daemon and polls
nothing. Its verdict is deliberately fail-closed: a file-based observation is
``STATIC SOURCE ONLY`` evidence and can never be reported as a native runtime
PASS.

Usage (capture commands are run by the trusted host, not by this tool):

    python tools/session_recovery/probe_readonly.py \
        --logind-file <captured-loginctl-show-session.txt> \
        --upower-file <captured-upower-info.txt> \
        --plasma-file <captured-host-status.txt>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from canopy_features.session_recovery.contracts import SessionRecoveryError
from canopy_features.session_recovery.logind_upower import (
    parse_logind_show_session, parse_plasma_state, parse_upower_info)
from canopy_features.session_recovery.native_integration import (
    PlasmaRecoveryIntegration)

__all__ = ["build_snapshot", "main"]


def _read(path):
    if path is None:
        return ""
    return Path(path).read_text(encoding="utf-8")


def build_snapshot(*, logind_text="", upower_text="", plasma_text=""):
    """Fold already-captured text into a bounded, read-only JSON report."""
    logind = parse_logind_show_session(logind_text)
    power = parse_upower_info(upower_text)
    plasma = parse_plasma_state(plasma_text)
    integration = PlasmaRecoveryIntegration()
    # ``None`` is not an observation. Desktop visuals were not captured by
    # these read-only interfaces, so they stay unknown here.
    integration.capture("pre", source="host-status-file", interface="logind", facts={
        "shell_active": logind.active,
        "dock_visible": None,
        "launcher_visible": None,
        "window_visible": None,
        "session_present": logind.active,
        "workspace_stable": None,
    })
    snapshot = integration.snapshot()
    return {
        "evidence_label": snapshot.evidence_label,
        "logind": logind.to_dict(),
        "upower": power.to_dict(),
        "plasma": plasma.to_dict(),
        "verdict": snapshot.verdict().to_dict(),
        "fallback": (snapshot.fallback.to_dict()
                     if snapshot.fallback is not None else None),
        "writes": 0,
        "commands_executed": 0,
        "polls": 0,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logind-file", help="captured loginctl show-session text")
    parser.add_argument("--upower-file", help="captured upower -i text")
    parser.add_argument("--plasma-file", help="captured host-status text")
    args = parser.parse_args(argv)
    try:
        report = build_snapshot(
            logind_text=_read(args.logind_file),
            upower_text=_read(args.upower_file),
            plasma_text=_read(args.plasma_file),
        )
    except SessionRecoveryError as exc:
        parser.error(str(exc))
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
