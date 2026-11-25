"""Normalize already-collected CMake, Ninja and Qt6 compiler probe results.

This module is a pure, offline normalizer. It never runs a subprocess, edits
PATH, touches the filesystem, polls or starts a service. A caller gathers raw
probe evidence with its existing mechanism (for example the read-only
``tools/mint_guest_preflight.py`` probe) and passes that evidence here.

Why normalize: ``cmake --version``, ``ninja --version`` and Qt6 version output
(qmake or pkg-config) use different formats. A bare ``shutil.which`` hit only
proves a file with the right name exists; a stub named ``cmake`` can answer
with another tool's version banner. This module converts heterogeneous output
into one deterministic schema and rejects tools whose name, identity banner or
version cannot be trusted.

Evidence shape (each tool key is optional)::

    {
        "cmake": {"path": "/usr/bin/cmake", "exit_code": 0,
                  "version_output": "cmake version 3.25.1\\n"},
        "ninja": {"path": "C:\\tools\\ninja.exe", "exit_code": 0,
                  "version_output": "1.11.1\\n"},
        "qt6":   {"path": "/usr/bin/qmake", "exit_code": 0,
                  "version_output": "QMake version 3.1\\nUsing Qt version 6.4.2\\n"},
    }

``qt6`` also accepts ``pkg-config`` evidence: set ``"source": "pkg-config"``
and put ``pkg-config --modversion Qt6Core`` output in ``version_output``.

Minimums come from the compiled prototype source, read-only:
``prototype/classic/CMakeLists.txt`` requires CMake 3.21 and Qt6 6.4.

This is probe normalization only. It does not compile Qt, launch a window,
identify Linux Mint or grant visual acceptance; those fields stay NOT_RUN.
"""
import re

SCHEMA_VERSION = 1

# Bounded input: probe output and paths are evidence strings, never executed.
MAX_OUTPUT_CHARS = 4096
MAX_PATH_CHARS = 260

# Derived from prototype/classic/CMakeLists.txt (cmake_minimum_required and
# find_package(Qt6 6.4 REQUIRED COMPONENTS Quick QuickControls2)).
CMAKE_MINIMUM = (3, 21)
QT6_MINIMUM = (6, 4)

# markers: required case-insensitive banner in version output.
# bare_sources: sources whose entire stripped output must be a bare version.
TOOL_RULES = {
    "cmake": {
        "names": ("cmake", "cmake.exe"),
        "markers": ("cmake version",),
        "bare_sources": (),
        "minimum": CMAKE_MINIMUM,
    },
    "ninja": {
        "names": ("ninja", "ninja.exe"),
        "markers": (),
        "bare_sources": ("ninja",),
        "minimum": None,
    },
    "qt6": {
        "names": ("qmake", "qmake6", "pkg-config",
                  "qmake.exe", "qmake6.exe", "pkg-config.exe"),
        "markers": ("using qt version",),
        "bare_sources": ("pkg-config",),
        "minimum": QT6_MINIMUM,
    },
}

_BARE_VERSION = re.compile(r"\d+(?:\.\d+){0,3}\Z")
_AFTER_MARKER = re.compile(r"(\d+(?:\.\d+){0,3})(?![\d.])")


def _binary_name(path):
    """Return the lowercased file name from a POSIX or Windows path string."""
    if not isinstance(path, str):
        return None
    return path.replace("\\", "/").rsplit("/", 1)[-1].strip().lower() or None


def _parse_numbers(token):
    return tuple(int(part) for part in token.split("."))


def _extract_version(output, rule, source):
    """Return (version_tuple, failure_state) for one accepted banner."""
    text = output.strip()
    if source in rule["bare_sources"] or not rule["markers"]:
        if not _BARE_VERSION.fullmatch(text):
            return None, "unusable"
        return _parse_numbers(text), None
    for line in text.splitlines():
        lowered = line.lower()
        for marker in rule["markers"]:
            position = lowered.find(marker)
            if position < 0:
                continue
            tail = line[position + len(marker):].lstrip()
            match = _AFTER_MARKER.match(tail)
            if match is None:
                return None, "unusable"
            return _parse_numbers(match.group(1)), None
    # Output never claimed to be this tool: the executable is not what its
    # name says it is, even when a plausible version number appears.
    return None, "misleading"


def _meets_minimum(version, minimum):
    if minimum is None:
        return True
    padded = version + (0,) * (len(minimum) - len(version))
    return padded >= minimum


def normalize_probe(tool, evidence):
    """Normalize one probe record into a bounded, explicit-state dict."""
    rule = TOOL_RULES[tool]
    record = {
        "tool": tool,
        "state": "missing",
        "version": None,
        "binary_name": None,
        "reason": "no probe evidence for " + tool,
    }
    if not isinstance(evidence, dict):
        return record

    name = _binary_name(evidence.get("path"))
    record["binary_name"] = name
    if name is None:
        return record
    if len(str(evidence.get("path"))) > MAX_PATH_CHARS:
        record["state"] = "unusable"
        record["reason"] = "probe path exceeds length limit"
        return record
    if name not in rule["names"]:
        record["state"] = "misleading"
        record["reason"] = "executable name does not match " + tool
        return record

    exit_code = evidence.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code != 0:
        record["state"] = "unusable"
        record["reason"] = "probe did not exit successfully"
        return record

    output = evidence.get("version_output")
    if not isinstance(output, str) or not output.strip():
        record["state"] = "unusable"
        record["reason"] = "empty or non-text version output"
        return record
    if len(output) > MAX_OUTPUT_CHARS or any(
            ord(char) < 32 and char not in "\n\r\t" for char in output):
        record["state"] = "unusable"
        record["reason"] = "malformed version output"
        return record

    source = evidence.get("source", rule["names"][0])
    if not isinstance(source, str) or source not in rule["names"]:
        record["state"] = "misleading"
        record["reason"] = "unknown probe source for " + tool
        return record

    version, failure = _extract_version(output, rule, _binary_name(source))
    if failure is not None:
        record["state"] = failure
        record["reason"] = (
            "version banner does not identify " + tool
            if failure == "misleading" else "version output could not be parsed"
        )
        return record

    record["version"] = ".".join(str(part) for part in version)
    minimum = rule["minimum"]
    if not _meets_minimum(version, minimum):
        record["state"] = "below_minimum"
        record["reason"] = "version below required " + ".".join(str(p) for p in minimum)
        return record

    record["state"] = "present"
    record["reason"] = "normalized"
    return record


def normalize_capabilities(probes):
    """Normalize a mapping of probe records into one deterministic report."""
    if not isinstance(probes, dict):
        raise TypeError("probes must be a mapping")

    tools = {}
    blockers = []
    for tool, rule in TOOL_RULES.items():
        record = normalize_probe(tool, probes.get(tool))
        tools[tool] = record
        if record["state"] != "present":
            blockers.append(tool + ": " + record["state"] + ": " + record["reason"])

    return {
        "schema_version": SCHEMA_VERSION,
        "probe_only": True,
        "status": "READY" if not blockers else "BLOCKED",
        "tools": tools,
        "blockers": blockers,
        "qt_compiled_acceptance": "NOT_RUN",
        "mint_guest_acceptance": "NOT_RUN",
        "runtime_functional_test": "NOT_RUN",
        "visual_acceptance": "NOT_RUN",
    }
