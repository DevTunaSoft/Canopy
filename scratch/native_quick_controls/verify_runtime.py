"""Map fresh Plasma probe evidence through the M3 control planner (no I/O to host).

Reads only the read-only probe logs in ``scratch/native_quick_controls/evidence``,
normalises them into bounded ``ProbeFacts`` and writes ``runtime_verdicts.json``.
It never contacts the VM, opens D-Bus, executes a control or writes a guest file.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "scratch" / "native_quick_controls" / "evidence"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from canopy_features.quick_controls.native_controls import (  # noqa: E402
    NativeControls, ProbeFacts,
)


def read(name):
    path = EVIDENCE / name
    return path.read_text(encoding="utf-8"), sha256(path.read_bytes()).hexdigest()


def output_after(text, marker):
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("$ ") and marker in line:
            for candidate in lines[index + 1:]:
                if candidate.startswith("[exit="):
                    return ""
                if candidate.startswith("$ "):
                    return ""
                return candidate
    return None


def blocker_lines(text, needle):
    return [line for line in text.splitlines() if needle in line]


def main():
    env_text, env_sha = read("env.txt")
    bright_text, bright_sha = read("brightness.txt")
    net_text, net_sha = read("network.txt")
    power_text, power_sha = read("power.txt")

    nm_permission = None
    perms_output = output_after(net_text, "GetPermissions") or ""
    match = re.search(
        r"'org\.freedesktop\.NetworkManager\.network-control':\s*'([a-z]+)'",
        perms_output,
    )
    if match and match.group(1) in {"yes", "no", "auth"}:
        nm_permission = match.group(1)

    def uint_after(text, marker):
        output = output_after(text, marker) or ""
        match = re.search(r"uint32 (\d+)", output)
        return int(match.group(1)) if match else None

    state = uint_after(net_text, "Properties.Get org.freedesktop.NetworkManager State")
    connectivity = uint_after(net_text, "Properties.Get org.freedesktop.NetworkManager Connectivity")
    check_available_output = output_after(
        net_text, "Properties.Get org.freedesktop.NetworkManager ConnectivityCheckAvailable") or ""
    check_available = (True if "<true>" in check_available_output else
                       False if "<false>" in check_available_output else None)

    backlight_entries = []
    lines = bright_text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("$ ") and "ls -la /sys/class/backlight/" in line:
            for candidate in lines[index + 1:]:
                if candidate.startswith("[exit=") or candidate.startswith("$ "):
                    break
                if candidate.startswith("total ") or candidate.rstrip().endswith(" .") \
                        or candidate.rstrip().endswith(" .."):
                    continue
                if candidate.strip():
                    backlight_entries.append(candidate.strip())

    can_suspend_output = output_after(power_text, "CanSuspend") or ""
    can_suspend_match = re.search(r"\('([a-z]+)',\)", can_suspend_output)
    can_suspend = can_suspend_match.group(1) if can_suspend_match else None
    list_jobs_denied = bool(blocker_lines(power_text, "ListJobs") and
                            any("AccessDenied" in line for line in power_text.splitlines()))

    facts = ProbeFacts(
        source="plasma-probe",
        brightness_supported=(output_after(bright_text, "NameHasOwner") == "(true,)"),
        backlight_device=bool(backlight_entries),
        connectivity_check_available=check_available,
        network_control_permission=nm_permission,
        network_state=state,
        connectivity=connectivity,
        power_can_suspend=can_suspend,
        power_list_jobs_allowed=not list_jobs_denied,
    )

    verdicts = {
        "brightness": NativeControls.brightness_step(5, facts).to_dict(),
        "network": NativeControls.network_recheck(facts).to_dict(),
        "power": NativeControls.power_capability(facts).to_dict(),
        "power_suspend_transition": NativeControls.refuse_transition("suspend").to_dict(),
    }

    report = {
        "schema_version": 1,
        "purpose": "M3 bounded native quick controls — real Plasma probe to verdict mapping",
        "session_context": {
            "probe_user": "canopy (uid 1000)",
            "bus": "unix:path=/run/user/1000/bus",
            "note": "Guest had rebooted; SDDM greeter and SSH session were present, "
                    "no graphical user shell during the fresh probe. Earlier "
                    "logged-in-Plasma evidence is preserved in "
                    "native_controls_readonly_addendum.md. Device/permission "
                    "blockers were re-observed fresh here.",
        },
        "probe_sha256": {
            "env.txt": env_sha,
            "brightness.txt": bright_sha,
            "network.txt": net_sha,
            "power.txt": power_sha,
        },
        "normalised_facts": {
            key: value for key, value in facts.__dict__.items()
        },
        "exact_observed_blockers": {
            "brightness": blocker_lines(bright_text, "BrightnessControl"),
            "network": blocker_lines(net_text, "PermissionDenied"),
            "power": blocker_lines(power_text, "AccessDenied"),
        },
        "verdicts": verdicts,
        "mutation_performed": False,
        "controls_executed_by_planner": False,
        "release_ready": False,
        "visual_acceptance": "AWAITING_OWNER",
    }
    target = EVIDENCE / "runtime_verdicts.json"
    target.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n",
                      encoding="utf-8")
    for domain, verdict in verdicts.items():
        print(domain, verdict["execution"], verdict["reason"])
    print("wrote", target)


if __name__ == "__main__":
    main()
