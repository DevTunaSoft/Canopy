"""Explicit inert caller for the read-only ShellHost capability report.

Usage: python -m canopy_core.capability_cli

This module does not read files, environment variables, stdin or clock; it
starts no process and imports no feature module. It feeds eight fixed,
evidence-free records to ``ShellHost.capability_report`` and prints only the
frozen report's schema, counts, fixed component tokens and negative claims.
Nothing here approves a release, Mint acceptance, visual approval, process
launch, I/O or capability activation.
"""
import json

from .registry import PackScan
from .shell_host import HostCapabilityReport, ShellHost

NEGATIVE_CLAIMS = (
    "release_approved", "linux_mint_acceptance_proven", "owner_visual_approval",
    "process_launched", "io_performed", "capability_activated",
    "desktop_session_started", "measurement_performed", "real_hardware_measured",
    "desktop_claim", "window_geometry_read",
)
OUTPUT_KEYS = ("status", "schema", "component_count", "component_tokens") + NEGATIVE_CLAIMS


def inert_records():
    """Return eight fixed, zero-count, fixed-token records (no raw values)."""
    switcher = {"active": False, "current": "", "selected": "",
                "window_count": 0, "order": ()}
    workspace = {"workspace_count": 0, "identifiers": (),
                 "problem_count": 0, "problem_reasons": ()}
    delivery = {"sent": 0, "received": 0, "delivered": 0, "duplicates": 0,
                "reordered": 0, "gaps": 0, "missed": 0, "dropped": 0,
                "rejected": 0, "notice_count": 0, "last_policy": ""}
    startup = {"action": "none", "safe_to_start": False,
               "needs_rollback": False, "completed_count": 0,
               "unwind_count": 0, "reason": ""}
    return {
        "schema": 1,
        "reliability": {
            "schema": 1, "status": "BLOCKED", "acceptance": "NOT_ESTABLISHED",
            "startup": dict(startup), "delivery": dict(delivery),
            "switcher": dict(switcher)},
        "readiness": {
            "status": "READINESS_SNAPSHOT", "schema": 1, "component_count": 5,
            "component_tokens": ["SNAPSHOT", "OK", "VALID", "PLAN_SNAPSHOT", "OK"],
            "release_approved": False, "linux_mint_acceptance_proven": False,
            "owner_visual_approval": False, "desktop_session_started": False,
            "shell_running": False, "process_launched": False,
            "measurement_performed": False, "real_hardware_measured": False,
            "installation_attempted": False},
        "security": {
            "status": "SNAPSHOT", "schema": 1, "uri_status": "REJECTED",
            "privilege_status": "DENIED", "privilege_reason": "",
            "metadata_status": "", "metadata_capability_count": 0,
            "launch_authorized": False, "process_launched": False,
            "release_approved": False, "linux_mint_acceptance_proven": False,
            "real_hardware_measured": False, "owner_visual_approval": False,
            "measurement_performed": False},
        "launch": {
            "status": "IDLE", "reason": "no_events", "event_count": 0,
            "relevant_count": 0, "success_count": 0, "failure_count": 0,
            "retry_count": 0, "claims": []},
        "focus": {
            "schema": 1, "status": "BLOCKED", "acceptance": "NOT_ESTABLISHED",
            "observation": "NOT_PERFORMED",
            "focus": {"live_windows": 0, "grant_count": 0, "decision_count": 0,
                      "statuses": (), "target_apps": (), "reasons": ()},
            "workspace": dict(workspace), "switcher": dict(switcher)},
        "session": {
            "schema": 1, "status": "BLOCKED", "acceptance": "NOT_ESTABLISHED",
            "switcher": dict(switcher), "workspace": dict(workspace),
            "portal": {"capability_count": 0, "denied": (), "missing": (),
                       "session_type": "", "unknown_permission": (),
                       "usable": False, "wayland": False,
                       "window_enumeration": ""},
            "negotiation": {"backend": "", "granted": False, "status": "",
                            "supported": False}},
        "recovery": {
            "schema": 1, "status": "BLOCKED", "acceptance": "NOT_ESTABLISHED",
            "observation": "NOT_PERFORMED", "startup": dict(startup),
            "session": {"accepted": False, "label": "", "locked": False,
                        "recent_statuses": (), "suspended": False},
            "delivery": dict(delivery)},
        "desktop": {
            "status": "DENIED", "reason": "invalid_input", "declared_count": 0,
            "action_count": 0, "argv_length": 0, "claims": []},
    }


def build_report():
    """Compose the frozen report from inert records on a fresh empty host."""
    host = ShellHost(PackScan((), (), 1), {}, frozenset())
    return host.capability_report(inert_records())


def main(argv=None):
    """Print a filtered, bounded view of the frozen report to stdout."""
    if argv:
        return 2
    report = build_report()
    if not isinstance(report, HostCapabilityReport):
        return 2
    data = report.as_dict()
    output = {key: data[key] for key in OUTPUT_KEYS}
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
