"""Offline normalizer for already-captured VirtualBox Mint guest evidence.

Consumes data that tools/mint_guest_preflight.py produced inside a guest and,
optionally, an already-captured ``VBoxManage showvminfo --machinereadable``
snapshot from the host. Produces one canonical, privacy-minimized record that
explicitly refuses to claim a VM run, Qt execution, or Linux Mint acceptance.

Pure and bounded by design: no subprocess, no polling, no background service,
no privileged action, no network, and no unbounded input retention. Provenance
and acceptance remain separate manual gates.
"""
import json
from pathlib import Path
import re
import shutil

from tools import mint_classic_qt_smoke as qt
from tools.mint_guest_preflight import NEEDED

SCHEMA_VERSION = 1
KIND = "vbox-guest-preflight-evidence-normalization"
RUN_CLAIM = "NONE"
NOT_RUN = "NOT_RUN"

MAX_INPUT_BYTES = 128_000
MAX_TEXT_FIELD = 160
MAX_BLOCKERS = 24
MAX_NOTES = 8

# Only these machinereadable fields are retained. Paths, MAC addresses,
# snapshots and other host-private data are discarded.
VMINFO_KEYS = ("name", "VMState")
POWEROFF_STATES = frozenset(("poweroff", "poweredoff"))


class EvidenceError(ValueError):
    """Input is not trusted, bounded evidence."""


def _bounded_text(value, label):
    if not isinstance(value, str):
        raise EvidenceError(label + " must be a string")
    if not value or len(value) > MAX_TEXT_FIELD:
        raise EvidenceError(label + " outside safe bounds")
    if any(ord(char) < 32 for char in value):
        raise EvidenceError(label + " contains control characters")
    return value


def _reject_nonstandard(value):
    raise EvidenceError("non-finite JSON number rejected")


def locate_vboxmanage(which=None):
    """Cheap PATH lookup only; never executes VBoxManage. Returns str or None.

    Callers may inject a ``which`` callable for deterministic offline tests.
    """
    finder = shutil.which if which is None else which
    for name in ("VBoxManage", "vboxmanage"):
        try:
            found = finder(name)
        except (OSError, TypeError, ValueError):
            return None
        if found:
            return _bounded_text(str(found), "VBoxManage path")
    return None


def parse_vminfo(text):
    """Parse a bounded showvminfo snapshot into an allowlisted dict.

    Caller-supplied text that cannot be UTF-8 encoded (for example an unpaired
    surrogate) is refused with ``EvidenceError``; the byte bound is measured on
    the encoded form so oversized non-ASCII input is still rejected.
    """
    if text is None or text == "":
        return {}
    if not isinstance(text, str):
        raise EvidenceError("vminfo must be text")
    try:
        encoded_len = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        # Unpaired surrogates are not encodable. Keep the documented domain
        # error instead of leaking a raw UnicodeEncodeError to the caller.
        raise EvidenceError("vminfo snapshot is not encodable text") from None
    if encoded_len > MAX_INPUT_BYTES:
        raise EvidenceError("vminfo snapshot too large")
    result = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in VMINFO_KEYS:
            continue
        if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
            value = value[1:-1]
        try:
            result[key] = _bounded_text(value, "vminfo " + key)
        except EvidenceError:
            # Drop one unsafe field, keep the rest of the bounded snapshot.
            continue
    return result


def load_preflight(path):
    """Read a saved mint-guest-preflight JSON file without following symlinks."""
    with qt._open_regular_file(Path(path)) as source:
        raw = source.read(MAX_INPUT_BYTES + 1)
    if not raw or len(raw) > MAX_INPUT_BYTES:
        raise EvidenceError("preflight evidence missing or oversized")
    try:
        report = json.loads(
            raw.decode("utf-8"), parse_constant=_reject_nonstandard,
        )
    except EvidenceError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise EvidenceError("invalid preflight JSON") from exc
    if type(report) is not dict:
        raise EvidenceError("preflight evidence must be a JSON object")
    return report


def normalize_preflight(report):
    """Return bounded guest facts; never carry over an acceptance claim."""
    if type(report) is not dict:
        raise EvidenceError("preflight evidence must be an object")
    if report.get("probe_only") is not True:
        raise EvidenceError("preflight evidence must be probe-only")
    if report.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceError("unsupported preflight schema")
    status = report.get("status")
    if status not in ("READY_FOR_TESTS", "BLOCKED"):
        raise EvidenceError("unrecognized preflight status")
    mint_identified = report.get("mint_identified")
    if type(mint_identified) is not bool:
        raise EvidenceError("mint_identified must be a bool")
    blockers = report.get("blockers")
    if type(blockers) is not list or len(blockers) > MAX_BLOCKERS:
        raise EvidenceError("preflight blockers outside bounds")
    clean_blockers = [_bounded_text(item, "blocker") for item in blockers]
    commands = report.get("commands_present")
    if type(commands) is not dict:
        raise EvidenceError("commands_present must be an object")
    version = report.get("version_id", "unknown")
    if not isinstance(version, str):
        raise EvidenceError("invalid version_id")
    qt_version = report.get("qt6_core_version")
    if qt_version is not None and (
            not isinstance(qt_version, str) or len(qt_version) > 40):
        raise EvidenceError("invalid Qt version")
    session = report.get("session_type", "other-or-unknown")
    if session not in ("x11", "wayland", "other-or-unknown"):
        raise EvidenceError("invalid session_type")
    return {
        "status": status,
        "mint_identified": mint_identified,
        "version_id": version[:30],
        "cinnamon_identified": bool(report.get("cinnamon_identified", False)),
        "graphical_display_present": bool(
            report.get("graphical_display_present", False)
        ),
        "session_type": session,
        "qt6_core_version": qt_version,
        "commands_present": {
            name: bool(commands.get(name, False)) for name in NEEDED
        },
        "blockers": clean_blockers,
    }


def normalize_vm(vminfo_text=None, vboxmanage_path=None):
    """Describe VM facts from captured evidence only; never start a VM."""
    info = parse_vminfo(vminfo_text)
    present = bool(vboxmanage_path) or bool(vminfo_text)
    state = info.get("VMState")
    name = info.get("name")
    powered_off = state in POWEROFF_STATES if state is not None else None
    notes = []
    if not present:
        notes.append("VBoxManage unavailable; no VM state evidence supplied")
    elif state in POWEROFF_STATES:
        notes.append("VM reported poweroff at capture; no live guest session")
    if len(notes) > MAX_NOTES:  # defensive; currently at most one
        del notes[MAX_NOTES:]
    return {
        "vboxmanage_present": present,
        "vminfo_available": bool(vminfo_text),
        "vm_name": name,
        "vm_state_at_capture": state,
        "vm_powered_off": powered_off,
        "notes": notes,
    }


def build_normalized_evidence(preflight, *, vminfo_text=None,
                              vboxmanage_path=None):
    """Return one canonical, no-claim record from existing evidence.

    ``preflight`` is a dict from tools/mint_guest_preflight.py (or loaded with
    load_preflight). ``vminfo_text`` is captured showvminfo output; absence of
    both it and ``vboxmanage_path`` is the documented "VBoxManage absent" case.
    """
    guest = normalize_preflight(preflight)
    vm = normalize_vm(vminfo_text, vboxmanage_path)
    notes = list(vm["notes"])
    notes.append("evidence normalized offline; no VM, Qt or Mint run performed")
    if len(notes) > MAX_NOTES:
        del notes[MAX_NOTES:]
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "actual_run_performed": False,
        "linux_mint_execution_independently_proven": False,
        "run_claim": RUN_CLAIM,
        "guest": guest,
        "vm": vm,
        "acceptance": {
            "mint_guest_acceptance": NOT_RUN,
            "runtime_functional_test": NOT_RUN,
            "visual_acceptance": NOT_RUN,
            "owner_visual_approval": NOT_RUN,
        },
        "readiness": (
            "READY_FOR_TESTS_EVIDENCE_ONLY"
            if guest["status"] == "READY_FOR_TESTS" else "BLOCKED_EVIDENCE"
        ),
        "notes": notes,
    }
