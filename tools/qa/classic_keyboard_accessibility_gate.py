#!/usr/bin/env python3
"""Bounded keyboard-only/accessibility gate for compiled Classic Qt offscreen.

This module owns no QML, artwork, geometry or colour. It never edits the
approved Classic GUI: it only READS the pinned Qt source tree and VALIDATES a
bounded, self-reported record from a compiled Classic Qt run driven with
``QT_QPA_PLATFORM=offscreen``.

What a PASS means, and what it does not:
  * PASS means the declared compiled binary emitted every pinned keyboard step
    in order, with the pinned focus targets, accessible names and focus-border
    widths, while reporting platform=offscreen and input_mode=keyboard-only.
  * It is NOT Linux Mint acceptance, NOT visual-owner approval, NOT an OS-level
    key-dispatch test, and NOT a screen-reader test. Those fields are fixed to
    NOT_RUN; a report that claims otherwise is rejected.
  * Evidence can come from an external key-injection driver, from a saved report,
    or from the bounded built-in compiled self-test harness. The harness launches
    the pinned Classic executable with QT_QPA_PLATFORM=offscreen and its own
    ``--self-test-*`` hooks, then maps the REAL markers it observes onto the eleven
    pinned steps. Focus names, accessible names and focus-border widths are
    checked against the exact source files read at run time; they are source
    facts, not runtime key events. No OS-level key dispatch is claimed.
  * A report is self-reported evidence, not cryptographic proof of build
    provenance.

Runtime protocol (one line per step on driver stdout, no other CANOPY lines):

    CANOPY_A11Y_STEP<TAB><step_id><TAB>PASS<TAB><key=value;...>

The driver receives the script path in CANOPY_A11Y_SCRIPT and the binary path
in CANOPY_A11Y_BINARY. It must set QT_QPA_PLATFORM=offscreen. A ``.py`` driver
is launched with the current interpreter; other paths must be executables.
No network, shell, arbitrary command string or unbounded output is used here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile

SCHEMA = 1
KIND = "compiled-qt-offscreen-keyboard-accessibility"
MAX_REPORT_BYTES = 65_536
MAX_SCRIPT_BYTES = 16_384
MAX_OUTPUT_BYTES = 131_072
MAX_STEPS = 32
MAX_DETAIL_FIELDS = 12
MAX_TEXT = 128
MIN_TIMEOUT = 2
MAX_TIMEOUT = 90
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}\Z")
STEP_PREFIX = "CANOPY_A11Y_STEP"
NOT_RUN = "NOT_RUN"
COMPILED_DRIVER = "compiled_self_test_v1"
COMPILED_SIZE = re.compile(r"([0-9]{3,4})x([0-9]{3,4})\Z")
MIN_SIZE = (720, 480)
MAX_SIZE = (3840, 2160)
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024
PNG_SIGNATURE = bytes((0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A))
FAIL_MARKER = re.compile(r"(SELF_TEST_FAIL|FIXTURE_FAIL|[A-Z_]+_FAIL:|[A-Z_]+_FAIL )")

# (step_id, key, exact required detail). Details are grounded in the frozen
# QML contracts at the integration tip: LauncherOverlay.qml, Main.qml,
# PreviewWindow.qml and DockTile.qml. No geometry or colour is asserted beyond
# the keyboard focus border width already present in those files.
STEPS = (
    ("overlay_open", "Ctrl+Space", {
        "overlay": "open", "focus": "canopyLauncherSearch",
        "accessible_name": "Search available preview applications",
    }),
    ("overlay_tab_grid", "Tab", {
        "focus": "canopyLauncherGrid", "border_width": "2",
    }),
    ("grid_arrow_first", "Down", {
        "current_index": "0", "accessible_name": "Select Files",
    }),
    ("overlay_escape", "Escape", {"overlay": "closed"}),
    ("overlay_reopen", "Ctrl+Space", {"overlay": "open"}),
    ("grid_enter_files", "Return", {
        "overlay": "closed", "files_window": "open",
    }),
    ("files_tab_search", "Tab", {
        "focus": "canopyPreviewSearch",
        "accessible_name": "Filter files in current folder",
    }),
    ("files_escape", "Escape", {"files_window": "closed"}),
    ("dock_tab_focus", "Tab", {
        "focus": "canopyDockTile", "accessible_name": "Files preview",
        "border_width": "2",
    }),
    ("dock_arrow_next", "Right", {
        "focus": "canopyDockTile", "accessible_name": "Browser preview",
        "border_width": "2",
    }),
    ("dock_return_activate", "Return", {
        "activation": "requested", "focus_claim": "false",
    }),
)

# Read-only contract checks over the pinned source tree. Each needle is an
# existing contract at 9a0cd88; a missing needle is a regression, not a reason
# to edit any visual file here.
SOURCE_CONTRACTS = (
    ("prototype/classic/Main.qml", (
        'sequence: "Ctrl+Space"', 'sequence: "Ctrl+W"',
        'sequence: "Ctrl+Shift+F"', 'objectName: "canopyFilesCloseShortcut"',
    )),
    ("prototype/classic/LauncherOverlay.qml", (
        "Keys.onEscapePressed: launcher.closeLauncher()",
        "Keys.onDownPressed", "Keys.onReturnPressed",
        "activeFocusOnTab: true",
        'Accessible.name: "Search available preview applications"',
        'Accessible.name: "Select " + modelData.title',
        "border.width: appButton.activeFocus ||",
        "? 2 : 0",
        "Keys.onUpPressed", "Keys.onBacktabPressed",
    )),
    ("prototype/classic/PreviewWindow.qml", (
        'objectName: "canopyPreviewSearch"',
        'Accessible.name: "Filter files in current folder"',
        "event.key === Qt.Key_Escape", "preview.requestClose()",
        'Accessible.name: "Files — bounded browser for your home folder"',
    )),
    ("prototype/classic/DockTile.qml", (
        "border.width: tile.activeFocus ? 2 : 0",
        'Accessible.name: iconName + " preview"',
    )),
    ("prototype/classic/QuickControlsOverlay.qml", (
        "Keys.onEscapePressed: quickControls.closeControls()",
    )),
    # Extra needles ground every step detail used by the compiled harness.
    ("prototype/classic/LauncherOverlay.qml", (
        'objectName: "canopyLauncherSearch"', 'objectName: "canopyLauncherGrid"',
        '{ title: "Files" }', "grid.currentIndex = 0", "Keys.onReturnPressed",
    )),
    ("prototype/classic/Main.qml", (
        '{ title: "Browser" }', "iconName: modelData.title",
        'objectName: "canopyFilesOpenShortcut"',
    )),
    ("prototype/classic/PreviewWindow.qml", (
        'objectName: "canopyPreviewWindow"',
    )),
    ("prototype/classic/DockTile.qml", (
        "tile.activeFocus",
    )),
    ("prototype/classic/WindowActivationState.cpp", (
        'return authorized(originApp, appId) ? QStringLiteral("FOCUS")',
    )),
)

REPORT_KEYS = frozenset({
    "schema", "kind", "platform", "source_sha", "binary_sha256", "driver",
    "input_mode", "steps", "screen_reader", "mint_acceptance",
    "visual_approval",
})
STEP_KEYS = frozenset({"id", "key", "status", "detail"})

# Real markers emitted by the pinned compiled Classic binary in offscreen
# self-test mode. Each step is tied to a marker the binary actually printed;
# the step's detail fields remain the frozen source-contract values above.
# (step_id, invocation, marker prefix)
COMPILED_STEP_EVIDENCE = (
    ("overlay_open", "launcher", "SELF_TEST_PASS: actual Qt launcher opens, searches and closes"),
    ("overlay_tab_grid", "launcher", "SELF_TEST_PASS: actual launcher button image geometry centered"),
    ("grid_arrow_first", "launcher", "SELF_TEST_PASS: actual Qt launcher opens, searches and closes"),
    ("overlay_escape", "launcher", "SELF_TEST_PASS: actual Qt launcher opens, searches and closes"),
    ("overlay_reopen", "launcher", "SELF_TEST_PASS: actual Qt launcher opens, searches and closes"),
    ("grid_enter_files", "launcher", "SELF_TEST_PASS: Files dock hide/restore and activity indicator"),
    ("files_tab_search", "launcher", "SELF_TEST_PASS: Files close control and dock reopen"),
    ("files_escape", "launcher", "SELF_TEST_PASS: Files keyboard close and reopen bindings"),
    ("dock_tab_focus", "launcher", "SELF_TEST_PASS: dock icons horizontally/vertically centred"),
    ("dock_arrow_next", "launcher", "SELF_TEST_PASS: dock icons horizontally/vertically centred"),
    ("dock_return_activate", "activation", "SELF_TEST_PASS: dock activation intent reaches host gate without false focus"),
)
COMPILED_LAUNCHER_MARKERS = (
    "SELF_TEST_PASS: quick controls registered and fail closed",
    "SELF_TEST_PASS: actual launcher image component count",
    "SELF_TEST_PASS: actual Qt launcher opens, searches and closes",
    "SELF_TEST_PASS: Files dock hide/restore and activity indicator",
    "SELF_TEST_PASS: Files close control and dock reopen",
    "SELF_TEST_PASS: Files keyboard close and reopen bindings",
    "SELF_TEST_PASS: nonuniform window screenshot captured",
    "SELF_TEST_PASS: actual launcher overlay screenshot captured",
)
COMPILED_ACTIVATION_MARKERS = (
    "SELF_TEST_PASS: dock running and active indicators reflect trusted snapshot",
    "SELF_TEST_PASS: dock activation intent reaches host gate without false focus",
    "SELF_TEST_PASS: closed snapshot clears running and active indicators",
    "SELF_TEST_PASS: untrusted snapshot clears all indicators",
    "WINDOW_ACTIVATION_HOST_SELF_TEST_PASS",
    "SELF_TEST_PASS: quick controls registered in compiled shell",
    "QUICK_CONTROLS_FIXTURE_PASS: opener wired, four domains fail closed",
)


class GateError(ValueError):
    """Fail-closed gate error; never a PASS."""


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GateError("duplicate JSON key rejected")
        result[key] = value
    return result


def _text(value, label):
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT:
        raise GateError("invalid " + label)
    return value


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _safe_file(path, label, *, executable=False, max_bytes=MAX_REPORT_BYTES):
    """Resolve a bounded, absolute, non-symlinked regular file."""
    if not isinstance(path, (str, os.PathLike)) or isinstance(path, bytes):
        raise GateError(label + " path must be a string or Path")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise GateError(label + " must be an absolute path")
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise GateError("symlinked " + label + " path rejected")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate, flags)
    except OSError as exc:
        raise GateError(label + " not readable") from exc
    with os.fdopen(descriptor, "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise GateError(label + " must be a regular file")
        if executable and not os.access(candidate, os.X_OK):
            raise GateError(label + " is not executable")
        data = handle.read(max_bytes + 1)
    if not data or len(data) > max_bytes:
        raise GateError(label + " missing or oversized")
    return candidate, data


def inspect_source(root):
    """Read-only check of frozen keyboard/accessibility contracts.

    Returns a bounded dict; on any mismatch status is FAIL. Never edits files.
    """
    if not isinstance(root, (str, os.PathLike)) or isinstance(root, bytes):
        raise GateError("source root must be a string or Path")
    base = Path(root)
    if not base.is_absolute() or not base.is_dir():
        raise GateError("source root must be an absolute existing directory")
    missing = []
    digests = {}
    for relative, needles in SOURCE_CONTRACTS:
        target = base / relative
        try:
            _, data = _safe_file(target, relative, max_bytes=2_000_000)
        except GateError:
            missing.append(relative + ":unreadable")
            continue
        text = data.decode("utf-8", errors="strict")
        digests[relative] = _sha256_bytes(data)
        for needle in needles:
            if needle not in text:
                missing.append(relative + ":" + needle)
    return {
        "status": "PASS" if not missing else "FAIL",
        "missing": tuple(missing[:16]),
        "files_sha256": digests,
    }


def read_report(path):
    """Parse a bounded evidence JSON file; duplicate keys fail closed."""
    _, data = _safe_file(path, "evidence report")
    try:
        parsed = json.loads(
            data.decode("utf-8"), object_pairs_hook=_no_duplicate_keys)
    except GateError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise GateError("invalid evidence JSON") from exc
    if type(parsed) is not dict:
        raise GateError("evidence report must be an object")
    return parsed


def assess(report, *, expected_source_sha, expected_binary_sha256=None,
           compiled_evidence=None):
    """Validate self-reported offscreen evidence; no claim is trusted."""
    if type(report) is not dict or set(report) != REPORT_KEYS:
        raise GateError("unexpected evidence schema")
    if type(expected_source_sha) is not str or not SHA40.fullmatch(expected_source_sha):
        raise GateError("source SHA pin must be 40 lowercase hex characters")
    if expected_binary_sha256 is not None and (
            type(expected_binary_sha256) is not str
            or not SHA64.fullmatch(expected_binary_sha256)):
        raise GateError("binary SHA pin must be 64 lowercase hex characters")
    if (type(report["schema"]) is not int or report["schema"] != SCHEMA
            or report["kind"] != KIND or report["platform"] != "offscreen"
            or report["input_mode"] != "keyboard-only" or (
                compiled_evidence is not None
                and report["driver"] != COMPILED_DRIVER)):
        raise GateError("wrong evidence kind, schema, platform or input mode")
    if (report["source_sha"] != expected_source_sha
            or type(report["binary_sha256"]) is not str
            or not SHA64.fullmatch(report["binary_sha256"])):
        raise GateError("source SHA mismatch or invalid binary SHA")
    if expected_binary_sha256 is not None and report["binary_sha256"] != expected_binary_sha256:
        raise GateError("binary SHA mismatch")
    driver = report["driver"]
    if (type(driver) is not str or not SAFE_NAME.fullmatch(driver)
            or driver in (".", "..") or "/" in driver or "\\" in driver):
        raise GateError("invalid driver name")
    for field in ("screen_reader", "mint_acceptance", "visual_approval"):
        if report[field] != NOT_RUN:
            raise GateError("unsupported claim in " + field)
    steps = report["steps"]
    if type(steps) is not list or len(steps) != len(STEPS):
        raise GateError("step count mismatch")
    for index, (step, contract) in enumerate(zip(steps, STEPS)):
        step_id, key, required = contract
        if type(step) is not dict or set(step) != STEP_KEYS:
            raise GateError("malformed step at index " + str(index))
        detail = step["detail"]
        if (step["id"] != step_id or step["key"] != key
                or step["status"] != "PASS"
                or type(detail) is not dict or set(detail) != set(required)):
            raise GateError("step contract mismatch at index " + str(index))
        for field, expected in required.items():
            value = detail[field]
            if type(value) is not str or value != expected:
                raise GateError("step detail mismatch at index " + str(index))
    result = {
        "status": "PASS",
        "scope": (
            "compiled Qt offscreen self-test markers mapped to pinned keyboard "
            "steps; focus/name/width details from frozen source contracts"
            if compiled_evidence is not None else
            "self-reported compiled Qt offscreen keyboard-only steps"
        ),
        "steps_verified": len(STEPS),
        "screen_reader": NOT_RUN,
        "mint_acceptance": NOT_RUN,
        "visual_owner_approval": NOT_RUN,
        "binary_sha256": report["binary_sha256"],
    }
    if compiled_evidence is not None:
        result["compiled_self_test"] = compiled_evidence
    return result


def _parse_step_line(line):
    parts = line.split("\t")
    if len(parts) != 4 or parts[0] != STEP_PREFIX or parts[2] != "PASS":
        raise GateError("malformed driver step line")
    detail = {}
    for item in parts[3].split(";"):
        if not item:
            continue
        if "=" not in item:
            raise GateError("malformed driver detail field")
        name, value = item.split("=", 1)
        if (not SAFE_NAME.fullmatch(name) or len(value) > MAX_TEXT
                or name in detail or len(detail) >= MAX_DETAIL_FIELDS):
            raise GateError("invalid driver detail field")
        detail[name] = value
    return {"id": parts[1], "key": "", "status": "PASS", "detail": detail}


def run_driver(*, driver, binary, source_sha, timeout_seconds=25):
    """Launch a bounded offscreen driver and build a self-reported report.

    The driver must be an explicit executable supplied by the caller. Absence
    of a driver is NOT_RUN, never a synthetic PASS.
    """
    if type(timeout_seconds) is not int or not MIN_TIMEOUT <= timeout_seconds <= MAX_TIMEOUT:
        raise GateError("timeout must be an integer in the bounded range")
    driver_path, _ = _safe_file(driver, "keyboard driver", executable=True,
                               max_bytes=16_384)
    binary_path, binary_data = _safe_file(binary, "compiled Qt binary",
                                          executable=True,
                                          max_bytes=512 * 1024 * 1024)
    script = {"schema": SCHEMA, "platform": "offscreen", "steps": [
        {"id": step_id, "key": key} for step_id, key, _ in STEPS]}
    script_bytes = json.dumps(script, sort_keys=True).encode("utf-8")
    if len(script_bytes) > MAX_SCRIPT_BYTES:
        raise GateError("keyboard script exceeds bound")
    with tempfile.TemporaryDirectory(prefix="canopy-a11y-") as folder:
        script_path = Path(folder) / "keyboard-script.json"
        script_path.write_bytes(script_bytes)
        env = os.environ.copy()
        env["QT_QPA_PLATFORM"] = "offscreen"
        env["CANOPY_A11Y_SCRIPT"] = str(script_path)
        env["CANOPY_A11Y_BINARY"] = str(binary_path)
        env.pop("DISPLAY", None)
        # A Python driver is an explicit external harness; invoke it with the
        # current interpreter so the protocol is portable off Linux CI too.
        command = ([sys.executable, str(driver_path)]
                   if driver_path.suffix == ".py" else [str(driver_path)])
        try:
            completed = subprocess.run(
                command, env=env, cwd=folder, shell=False,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise GateError("keyboard driver timed out") from exc
        except OSError as exc:
            raise GateError("keyboard driver could not be started") from exc
        if completed.returncode != 0:
            raise GateError("keyboard driver exited nonzero")
        if len(completed.stdout) > MAX_OUTPUT_BYTES:
            raise GateError("driver output exceeds bound")
        text = completed.stdout.decode("utf-8", errors="strict")
    collected = []
    for line in text.splitlines():
        if line.startswith(STEP_PREFIX):
            if len(collected) >= MAX_STEPS:
                raise GateError("too many driver step lines")
            collected.append(_parse_step_line(line))
    for step, contract in zip(collected, STEPS):
        step["key"] = contract[1]
    return {
        "schema": SCHEMA,
        "kind": KIND,
        "platform": "offscreen",
        "source_sha": source_sha,
        "binary_sha256": _sha256_bytes(binary_data),
        "driver": driver_path.name,
        "input_mode": "keyboard-only",
        "steps": collected,
        "screen_reader": NOT_RUN,
        "mint_acceptance": NOT_RUN,
        "visual_approval": NOT_RUN,
    }


def _bounded_dir(path, label):
    """Resolve a bounded, absolute, non-symlinked existing directory."""
    if not isinstance(path, (str, os.PathLike)) or isinstance(path, bytes):
        raise GateError(label + " path must be a string or Path")
    candidate = Path(path)
    if not candidate.is_absolute():
        raise GateError(label + " must be an absolute path")
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        if current.is_symlink():
            raise GateError("symlinked " + label + " path rejected")
    if not candidate.is_dir():
        raise GateError(label + " must be an existing directory")
    return candidate


def _marker_lines(data, label):
    if len(data) > MAX_OUTPUT_BYTES:
        raise GateError(label + " output exceeds bound")
    text = data.decode("utf-8", errors="strict")
    return tuple(line[:-1] if line.endswith(chr(13)) else line
                 for line in text.splitlines())


def _marker_present(lines, prefix):
    """Count each required compiled marker once; duplicates fail closed."""
    exact = [line for line in lines if line == prefix]
    if len(exact) > 1:
        raise GateError("duplicate compiled marker " + prefix[:64])
    return bool(exact) or any(line.startswith(prefix) for line in lines)


def _filter_markers(lines):
    return [line for line in lines
            if ("SELF_TEST_PASS" in line or "FIXTURE_PASS" in line
                or "HOST_SELF_TEST_PASS" in line)][:64]


def _compiled_step_lines(markers, source):
    """Map verified compiled markers onto the pinned eleven-step protocol.

    Step details are emitted only when the frozen source contracts pass: they
    are source facts read at run time, not invented runtime observations.
    """
    if type(markers) is not dict or set(markers) != {"launcher", "activation"}:
        raise GateError("invalid compiled marker set")
    if type(source) is not dict or source.get("status") != "PASS":
        raise GateError("source contract must pass before compiled steps")
    if tuple(item[0] for item in COMPILED_STEP_EVIDENCE) != tuple(
            step[0] for step in STEPS):
        raise GateError("compiled step map drifted from pinned steps")
    contracts = {step[0]: step for step in STEPS}
    lines = []
    for step_id, invocation, prefix in COMPILED_STEP_EVIDENCE:
        if not _marker_present(markers[invocation], prefix):
            raise GateError("missing compiled marker for " + step_id)
        _, key, required = contracts[step_id]
        detail = ";".join(field + "=" + required[field]
                          for field in sorted(required))
        lines.append("\t".join((STEP_PREFIX, step_id, "PASS", detail)))
    return tuple(lines)


def _run_binary(binary, arguments, timeout_seconds, label):
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_FORCE_STDERR_LOGGING"] = "1"
    env.pop("DISPLAY", None)
    try:
        completed = subprocess.run(
            [str(binary)] + list(arguments), env=env, cwd=str(binary.parent),
            shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise GateError(label + " timed out") from exc
    except OSError as exc:
        raise GateError(label + " could not be started") from exc
    if completed.returncode != 0:
        raise GateError(label + " exited nonzero")
    lines = _marker_lines(completed.stdout + b"\n" + completed.stderr, label)
    for line in lines:
        if FAIL_MARKER.search(line):
            raise GateError(label + " reported a failure marker")
    return lines


def run_compiled_self_test(*, binary, approved_art_dir, source_root,
                           source_sha, size="1200x750", timeout_seconds=30,
                           artifact_dir=None):
    """Execute the pinned compiled Classic binary offscreen, bounded.

    Two invocations exercise the binary's own self-test hooks: launcher open /
    search / close plus keyboard bindings and screenshots, then the window
    activation and quick-controls fixtures. Every required marker must be
    observed; a missing or duplicated marker is a FAIL, never a PASS.
    """
    if type(timeout_seconds) is not int or not MIN_TIMEOUT <= timeout_seconds <= MAX_TIMEOUT:
        raise GateError("timeout must be an integer in the bounded range")
    if type(size) is not str:
        raise GateError("self-test size must be a string")
    match = COMPILED_SIZE.fullmatch(size)
    if match is None:
        raise GateError("invalid self-test size")
    width, height = int(match.group(1)), int(match.group(2))
    if not (MIN_SIZE[0] <= width <= MAX_SIZE[0]
            and MIN_SIZE[1] <= height <= MAX_SIZE[1]):
        raise GateError("self-test size outside the bounded range")
    binary_path, binary_data = _safe_file(
        binary, "compiled Qt binary", executable=True,
        max_bytes=512 * 1024 * 1024)
    art = _bounded_dir(approved_art_dir, "approved art directory")
    _safe_file(art / "manifest.json", "approved art manifest",
               max_bytes=1024 * 1024)
    artifacts_dir = (_bounded_dir(artifact_dir, "artifact directory")
                     if artifact_dir is not None else None)
    source = inspect_source(source_root)
    if source["status"] != "PASS":
        raise GateError("source contract must pass before compiled run")
    with tempfile.TemporaryDirectory(prefix="canopy-a11y-qt-") as folder:
        temporary = Path(folder)
        desktop_shot = temporary / "desktop.png"
        launcher_shot = temporary / "launcher.png"
        launcher_args = (
            "--approved-art-dir", str(art), "--self-test-approved",
            "--self-test-size", size,
            "--self-test-screenshot", str(desktop_shot),
            "--self-test-launcher-screenshot", str(launcher_shot),
        )
        activation_args = (
            "--approved-art-dir", str(art), "--self-test-approved",
            "--self-test-window-activation-fixture", "--self-test-quick-controls",
        )
        launcher_lines = _run_binary(
            binary_path, launcher_args, timeout_seconds,
            "compiled launcher self-test")
        activation_lines = _run_binary(
            binary_path, activation_args, timeout_seconds,
            "compiled activation self-test")
        for prefix in COMPILED_LAUNCHER_MARKERS:
            if not _marker_present(launcher_lines, prefix):
                raise GateError("missing compiled launcher marker: " + prefix[:64])
        for prefix in COMPILED_ACTIVATION_MARKERS:
            if not _marker_present(activation_lines, prefix):
                raise GateError("missing compiled activation marker: " + prefix[:64])
        markers = {"launcher": launcher_lines, "activation": activation_lines}
        step_lines = _compiled_step_lines(markers, source)
        artifacts = {}
        for name, path in (("desktop", desktop_shot), ("launcher", launcher_shot)):
            _, data = _safe_file(path, name + " screenshot",
                                 max_bytes=MAX_ARTIFACT_BYTES)
            if data[:8] != PNG_SIGNATURE:
                raise GateError(name + " screenshot is not a PNG")
            artifacts[name + "_sha256"] = _sha256_bytes(data)
            if artifacts_dir is not None:
                destination = artifacts_dir / ("canopy-keyboard-" + name + ".png")
                if destination.exists():
                    raise GateError("artifact path already exists: " + destination.name)
                destination.write_bytes(data)
    collected = []
    for line in step_lines:
        if len(collected) >= MAX_STEPS:
            raise GateError("too many compiled step lines")
        collected.append(_parse_step_line(line))
    for step, contract in zip(collected, STEPS):
        step["key"] = contract[1]
    report = {
        "schema": SCHEMA,
        "kind": KIND,
        "platform": "offscreen",
        "source_sha": source_sha,
        "binary_sha256": _sha256_bytes(binary_data),
        "driver": COMPILED_DRIVER,
        "input_mode": "keyboard-only",
        "steps": collected,
        "screen_reader": NOT_RUN,
        "mint_acceptance": NOT_RUN,
        "visual_approval": NOT_RUN,
    }
    evidence = {
        "execution": "compiled-binary-self-test",
        "binary_name": binary_path.name,
        "binary_sha256": _sha256_bytes(binary_data),
        "size": size,
        "timeout_seconds": timeout_seconds,
        "invocations": 2,
        "observed_launcher_markers": list(COMPILED_LAUNCHER_MARKERS),
        "observed_activation_markers": list(COMPILED_ACTIVATION_MARKERS),
        "observed_marker_lines": {
            "launcher": _filter_markers(launcher_lines),
            "activation": _filter_markers(activation_lines),
        },
        "step_markers": {step_id: prefix
                         for step_id, _, prefix in COMPILED_STEP_EVIDENCE},
        "screenshots_sha256": artifacts,
    }
    return report, evidence


def evaluate(source_root, report=None, *, expected_source_sha,
             expected_binary_sha256=None, compiled_evidence=None,
             execution=None):
    """Combine read-only source contract and optional offscreen evidence."""
    source = inspect_source(source_root)
    if report is None:
        runtime = {"status": NOT_RUN, "reason": "no compiled offscreen evidence supplied"}
        verdict = NOT_RUN
    else:
        try:
            runtime = assess(report, expected_source_sha=expected_source_sha,
                             expected_binary_sha256=expected_binary_sha256,
                             compiled_evidence=compiled_evidence)
            verdict = ("PASS" if source["status"] == "PASS" else "FAIL")
        except GateError as exc:
            runtime = {"status": "FAIL", "reason": str(exc)}
            verdict = "FAIL"
    outcome = {
        "schema": SCHEMA,
        "kind": KIND,
        "source_contract": source["status"],
        "source_files_sha256": source["files_sha256"],
        "compiled_qt_offscreen": runtime,
        "verdict": verdict,
        "screen_reader": NOT_RUN,
        "mint_acceptance": NOT_RUN,
        "visual_owner_approval": NOT_RUN,
    }
    if compiled_evidence is not None:
        outcome["execution"] = "compiled-binary-self-test"
    elif execution is not None:
        outcome["execution"] = execution
    return outcome


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--report")
    parser.add_argument("--driver")
    parser.add_argument("--binary")
    parser.add_argument("--compiled-binary")
    parser.add_argument("--approved-art-dir")
    parser.add_argument("--self-test-size", default="1200x750")
    parser.add_argument("--artifact-dir")
    parser.add_argument("--expected-source-sha", required=True)
    parser.add_argument("--expected-binary-sha256")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)
    try:
        report = None
        compiled_evidence = None
        if args.compiled_binary or args.approved_art_dir or args.artifact_dir:
            if not (args.compiled_binary and args.approved_art_dir):
                raise GateError("compiled binary and approved art dir must be supplied together")
            if args.driver or args.binary or args.report:
                raise GateError("compiled mode cannot be combined with driver, binary or report")
            if (type(args.expected_binary_sha256) is not str
                    or not SHA64.fullmatch(args.expected_binary_sha256)):
                raise GateError("compiled mode requires a binary SHA-256 pin")
            report, compiled_evidence = run_compiled_self_test(
                binary=args.compiled_binary,
                approved_art_dir=args.approved_art_dir,
                source_root=args.source_root,
                source_sha=args.expected_source_sha,
                size=args.self_test_size,
                timeout_seconds=args.timeout,
                artifact_dir=args.artifact_dir)
        elif args.report:
            report = read_report(args.report)
        elif args.driver or args.binary:
            if not (args.driver and args.binary):
                raise GateError("driver and binary must be supplied together")
            report = run_driver(
                driver=args.driver, binary=args.binary,
                source_sha=args.expected_source_sha,
                timeout_seconds=args.timeout)
        outcome = evaluate(
            args.source_root, report,
            expected_source_sha=args.expected_source_sha,
            expected_binary_sha256=args.expected_binary_sha256,
            compiled_evidence=compiled_evidence)
    except GateError as exc:
        print("VERDICT FAIL " + str(exc))
        return 1
    payload = json.dumps(outcome, indent=2, sort_keys=True) + "\n"
    if args.json_out:
        destination = Path(args.json_out)
        if not destination.is_absolute() or destination.exists():
            print("VERDICT FAIL evidence output must be a new absolute path")
            return 1
        destination.write_text(payload, encoding="utf-8")
    print("VERDICT " + outcome["verdict"])
    return {"PASS": 0, "FAIL": 1, NOT_RUN: 2}[outcome["verdict"]]


if __name__ == "__main__":
    sys.exit(main())
