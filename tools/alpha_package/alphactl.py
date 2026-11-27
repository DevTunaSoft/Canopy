#!/usr/bin/env python3
"""Standalone lifecycle controller for the Canopy Classic alpha tarball.

This is the only mutating script in the alpha package. It is stdlib-only so an
extracted tarball needs no repository checkout. It writes only two user-level
desktop-entry files and one small state file under XDG_DATA_HOME; it never
touches /etc, /usr, a session, a display manager or the compiled binary.

Install:
  * refuses to overwrite *any* existing managed path (no unrelated config is
    ever replaced);
  * records exact pre-install state, exact bytes and mode before writing;
  * creates owned files exclusively (O_EXCL), verifies them, and unwinds only
    files it created if any step fails.

Uninstall:
  * deletes only files whose exact bytes match the recorded marker;
  * if marker deletion fails, restores the desktop entry's exact bytes/mode;
  * reports whether the original desktop state was restored.

Rollback:
  * reconciles current state against a recorded before/after state, restoring
    or deleting only files it can prove it owns; never deletes a modified file.

No command claims Linux Mint session acceptance: that is always NOT_RUN and
requires a real guest run. A COMPILE_NOT_RUN package cannot be installed.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

SCHEMA = 1
DESKTOP = "org.canopy.ClassicPreview.desktop"
MANIFEST_FILE = "MANIFEST.json"
CHECKSUMS_FILE = "CHECKSUMS.sha256"
STATE_REL = "canopy-alpha/install-state.json"
OWNED_KEYS = ("desktop", "manifest")
SNAPSHOT_KEYS = OWNED_KEYS + ("xdg_autostart", "xdg_session")
MAX_ENTRY = 8192
MAX_MARKER = 4096
MAX_STATE = 1 << 16
MAX_MANIFEST = 1 << 16
MAX_FILE_BYTES = 64 << 20
MAX_BINARY_BYTES = 250_000_000
CHUNK = 64 * 1024
HEX = frozenset("0123456789abcdef")
MODES = frozenset((0o600, 0o644, 0o755))
NATIVE_MINT = "NOT_RUN"
# This label claims only that a PE-002-labelled evidence record's digest
# matched the staged binary. It does not claim an independent compile audit.
PE002_DIGEST_EVIDENCE_MATCHED = "PE002_DIGEST_EVIDENCE_MATCHED"
BUILD_STATUSES = ("COMPILE_NOT_RUN", PE002_DIGEST_EVIDENCE_MATCHED)
PROTECTED = (
    "/etc", "/usr", "/var", "/opt", "/boot", "/proc", "/sys", "/dev",
    "/snap", "/root", "C:\\Windows", "C:\\Program Files",
    "C:\\Program Files (x86)", "C:\\ProgramData",
)
TOKEN = re.compile(r"[A-Za-z0-9._-]{1,80}\Z")
HASH64 = re.compile(r"[0-9a-f]{64}\Z")
HASH40 = re.compile(r"[0-9a-f]{40}\Z")
# Conservative unquoted Exec characters. Anything outside this set is quoted
# per the freedesktop Desktop Entry spec (reserved characters, spaces, etc.).
EXEC_UNQUOTED = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789/:._+-")
# Inside a quoted Exec field these four characters must be backslash-escaped.
EXEC_ESCAPE = frozenset('"\\$`')
# Exec field codes are expanded by launchers and cannot be escaped safely.
EXEC_FORBIDDEN = frozenset("%")


class AlphaPackageError(ValueError):
    """A safety gate refused the requested operation."""


def _text(value, name):
    if isinstance(value, bool) or not isinstance(value, (str, os.PathLike)):
        raise AlphaPackageError(name + " must be a path string or PathLike")
    try:
        text = os.fspath(value)
    except Exception as exc:
        raise AlphaPackageError(name + " must be a readable path string") from exc
    if not isinstance(text, str) or not text or "\x00" in text:
        raise AlphaPackageError(name + " must be a nonempty path string")
    if any(not char.isprintable() for char in text):
        raise AlphaPackageError(name + " contains a control character")
    return text


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _hash64(value, name, *, allow_none=False):
    if value is None and allow_none:
        return None
    if (not isinstance(value, str) or not HASH64.fullmatch(value)
            or any(char not in HEX for char in value)):
        raise AlphaPackageError(name + " must be a lowercase SHA-256")
    return value


def _int(value, name, *, allow_none=False):
    if value is None and allow_none:
        return None
    if type(value) is not int or value < 0:
        raise AlphaPackageError(name + " must be a nonnegative integer")
    return value


def _no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AlphaPackageError("duplicate JSON key: " + str(key))
        result[key] = value
    return result


def _safe_rel(value, name):
    raw = _text(value, name)
    if "\\" in raw or raw.startswith("/") or os.path.isabs(raw):
        raise AlphaPackageError(name + " must be a relative POSIX path")
    parts = tuple(raw.split("/"))
    for part in parts:
        if part in ("", ".", ".."):
            raise AlphaPackageError(name + " has an unsafe component")
        if len(part) >= 2 and part[1] == ":" and part[0].isalpha():
            raise AlphaPackageError(name + " is drive-qualified")
    return raw


def _real_path(path, message):
    """Reject traversal and symlinks in every *existing* path component."""
    raw = _text(path, message)
    if not os.path.isabs(raw) or ".." in Path(raw).parts:
        raise AlphaPackageError(message + ": absolute non-traversing path required")
    parts = Path(os.path.abspath(raw)).parts
    if not parts:
        raise AlphaPackageError(message + ": empty path")
    current = Path(parts[0])
    for part in parts[1:]:
        current = current / part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise AlphaPackageError(message + ": unreadable path") from exc
        if stat.S_ISLNK(mode):
            raise AlphaPackageError(message + ": symlinked component")
    return str(path)


def _data_home(home):
    raw = _real_path(home, "data home")
    normalized = os.path.normcase(os.path.abspath(raw))
    for prefix in PROTECTED:
        probe = os.path.normcase(prefix).rstrip("\\/")
        if normalized == probe or any(
                normalized.startswith(probe + sep) for sep in ("/", "\\")):
            raise AlphaPackageError("system-owned data home is not user-level")
    return raw


def _owned(home):
    data = Path(home)
    return {
        "desktop": data / "applications" / DESKTOP,
        "manifest": data / "canopy" / "classic-preview" / "ownership.json",
        "xdg_autostart": data / ".config" / "autostart" / DESKTOP,
        "xdg_session": data / ".local" / "share" / "xsessions" / DESKTOP,
    }


def _state_path(home):
    return Path(home) / STATE_REL


def _read_bytes(path, limit, name):
    source = Path(_text(path, name))
    try:
        info = os.lstat(source)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AlphaPackageError(name + " must be a regular non-symlink file")
        if info.st_size > limit:
            raise AlphaPackageError(name + " exceeds its byte bound")
        with source.open("rb") as handle:
            data = handle.read(limit + 1)
    except AlphaPackageError:
        raise
    except OSError as exc:
        raise AlphaPackageError(name + " could not be read") from exc
    if len(data) > limit:
        raise AlphaPackageError(name + " exceeds its byte bound")
    return data


def _stream_sha(path, limit):
    digest = hashlib.sha256()
    total = 0
    source = Path(path)
    try:
        info = os.lstat(source)
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise AlphaPackageError("package entry is not a regular file")
        if info.st_size > limit:
            raise AlphaPackageError("package entry exceeds its byte bound")
        with source.open("rb") as handle:
            for chunk in iter(lambda: handle.read(CHUNK), b""):
                total += len(chunk)
                if total > limit:
                    raise AlphaPackageError("package entry exceeds its byte bound")
                digest.update(chunk)
    except AlphaPackageError:
        raise
    except OSError as exc:
        raise AlphaPackageError("package entry could not be read") from exc
    return digest.hexdigest(), total


def _path_state(path, limit, name):
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {"kind": "ABSENT", "size": None, "mode": None, "sha256": None,
                "payload_base64": None, "safe": True, "reason": None}
    except (OSError, ValueError):
        return {"kind": "UNREADABLE", "size": None, "mode": None, "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " could not be inspected"}
    if stat.S_ISLNK(info.st_mode):
        return {"kind": "SYMLINK", "size": info.st_size, "mode": None,
                "sha256": None, "payload_base64": None, "safe": False,
                "reason": name + " is a symlink"}
    if not stat.S_ISREG(info.st_mode):
        return {"kind": "OTHER", "size": info.st_size, "mode": None,
                "sha256": None, "payload_base64": None, "safe": False,
                "reason": name + " is not a regular file"}
    if info.st_size > limit:
        return {"kind": "OVERSIZE", "size": info.st_size,
                "mode": stat.S_IMODE(info.st_mode), "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " exceeds its byte bound"}
    try:
        data = _read_bytes(path, limit, name)
    except AlphaPackageError:
        return {"kind": "UNREADABLE", "size": info.st_size,
                "mode": stat.S_IMODE(info.st_mode), "sha256": None,
                "payload_base64": None, "safe": False,
                "reason": name + " could not be read"}
    return {"kind": "REGULAR_FILE", "size": len(data),
            "mode": stat.S_IMODE(info.st_mode), "sha256": _sha(data),
            "payload_base64": base64.b64encode(data).decode("ascii"),
            "safe": True, "reason": None}


def _payload(state, limit, name):
    if not isinstance(state, dict):
        raise AlphaPackageError(name + " state is not an object")
    encoded = state.get("payload_base64")
    if encoded is None:
        return None
    if not isinstance(encoded, str) or len(encoded) > 4 * limit + 8:
        raise AlphaPackageError(name + " payload is not bounded base64")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise AlphaPackageError(name + " payload is invalid base64") from exc
    if len(data) > limit:
        raise AlphaPackageError(name + " payload exceeds its byte bound")
    return data


def _snapshot(home):
    owned = _owned(home)
    return {
        "desktop": _path_state(owned["desktop"], MAX_ENTRY, "desktop entry"),
        "manifest": _path_state(
            owned["manifest"], MAX_MARKER, "ownership marker"),
        "xdg_autostart": _path_state(
            owned["xdg_autostart"], MAX_ENTRY, "xdg autostart entry"),
        "xdg_session": _path_state(
            owned["xdg_session"], MAX_ENTRY, "xdg session entry"),
    }


def _same_state(actual, expected):
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    for field in ("kind", "size", "mode", "sha256", "payload_base64"):
        if actual.get(field) != expected.get(field):
            return False
    return True


def _projected(path, data, mode):
    # Windows chmod cannot represent POSIX 0644/0755; record the achievable
    # mode there instead of inventing a mismatch against a real install.
    effective = 0o666 if os.name == "nt" else mode
    return {"kind": "REGULAR_FILE", "size": len(data), "sha256": _sha(data),
            "mode": effective, "payload_base64": (
                base64.b64encode(data).decode("ascii")),
            "safe": True, "reason": None, "target": str(path)}


def _absent(path):
    return {"kind": "ABSENT", "size": None, "mode": None, "sha256": None,
            "payload_base64": None, "safe": True, "reason": None,
            "target": str(path)}


def _exec_field(raw):
    """Return a spec-conforming Exec field for one executable path."""
    if any(char in EXEC_FORBIDDEN for char in raw):
        raise AlphaPackageError("binary path contains an Exec field code")
    if all(char in EXEC_UNQUOTED for char in raw):
        return raw
    escaped = []
    for char in raw:
        if char in EXEC_ESCAPE:
            escaped.append("\\")
        escaped.append(char)
    return '"' + "".join(escaped) + '"'


def _entry(binary):
    raw = _text(binary, "binary")
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Canopy Classic (alpha)\n"
        "Comment=Canopy Classic alpha preview - user-level reversible entry\n"
        "Exec=" + _exec_field(raw) + "\n"
        "Terminal=false\n"
        "Categories=Utility;\n"
    ).encode("utf-8")


def _marker(entry):
    return json.dumps({"schema": SCHEMA, "sha256": _sha(entry)},
                      sort_keys=True).encode("utf-8")


def load_manifest(root):
    base = Path(_text(root, "package root"))
    if not base.is_absolute() or not base.is_dir():
        raise AlphaPackageError("package root must be an absolute directory")
    _real_path(base, "package root")
    data = _read_bytes(base / MANIFEST_FILE, MAX_MANIFEST, "manifest")
    try:
        doc = json.loads(data.decode("utf-8"),
                         object_pairs_hook=_no_duplicate_keys)
    except AlphaPackageError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise AlphaPackageError("manifest is not valid JSON") from exc
    if not isinstance(doc, dict) or set(doc) != {
            "schema", "package_id", "source_commit", "build", "payload",
            "files", "hash_alg"}:
        raise AlphaPackageError("unexpected manifest shape")
    if type(doc["schema"]) is not int or doc["schema"] != SCHEMA:
        raise AlphaPackageError("unsupported manifest schema")
    if doc["hash_alg"] != "sha256":
        raise AlphaPackageError("unsupported manifest hash algorithm")
    if (not isinstance(doc["package_id"], str)
            or not TOKEN.fullmatch(doc["package_id"])):
        raise AlphaPackageError("invalid package id")
    if not isinstance(doc["source_commit"], str) or not HASH40.fullmatch(
            doc["source_commit"]):
        raise AlphaPackageError("source_commit must be a 40-hex SHA")
    build = doc["build"]
    if not isinstance(build, dict) or set(build) != {
            "status", "binary_sha256", "evidence_sha256", "artifact"}:
        raise AlphaPackageError("unexpected build record")
    if build["status"] not in BUILD_STATUSES:
        raise AlphaPackageError("unknown build status")
    payload = doc["payload"]
    if not isinstance(payload, dict) or set(payload) != {
            "path", "sha256", "size", "mode"}:
        raise AlphaPackageError("unexpected payload record")
    files = doc["files"]
    if not isinstance(files, dict):
        raise AlphaPackageError("manifest files must be an object")
    normalized = {}
    for rel, record in files.items():
        safe = _safe_rel(rel, "manifest file path")
        if safe in (MANIFEST_FILE, CHECKSUMS_FILE):
            raise AlphaPackageError("checksum files cannot be manifest entries")
        if not isinstance(record, dict) or set(record) != {"sha256", "size", "mode"}:
            raise AlphaPackageError("unexpected file record for " + safe)
        digest = _hash64(record["sha256"], safe + " sha256")
        size = _int(record["size"], safe + " size")
        mode = record["mode"]
        if not isinstance(mode, str) or mode not in ("0600", "0644", "0755"):
            raise AlphaPackageError("unsupported mode for " + safe)
        normalized[safe] = {"sha256": digest, "size": size, "mode": mode}
    if build["status"] == "COMPILE_NOT_RUN":
        if (build["binary_sha256"] is not None
                or build["evidence_sha256"] is not None
                or build["artifact"] is not None
                or any(value is not None for value in payload.values())
                or any(rel.startswith("payload/") for rel in normalized)):
            raise AlphaPackageError(
                "COMPILE_NOT_RUN manifest cannot claim binary contents")
    else:
        digest = _hash64(build["binary_sha256"], "build binary_sha256")
        _hash64(build["evidence_sha256"], "evidence_sha256")
        if (not isinstance(build["artifact"], str)
                or not build["artifact"]):
            raise AlphaPackageError("compiled build has no artifact record")
        rel = _safe_rel(payload["path"], "payload path")
        if not rel.startswith("payload/") or rel not in normalized:
            raise AlphaPackageError("payload is not a manifest file entry")
        if (_hash64(payload["sha256"], "payload sha256") != digest
                or _int(payload["size"], "payload size") != normalized[rel]["size"]
                or payload["mode"] != "0755"):
            raise AlphaPackageError("payload record contradicts the manifest")
    return doc


def verify_package(root, manifest=None):
    base = Path(_text(root, "package root"))
    doc = manifest if manifest is not None else load_manifest(base)
    reasons = []
    checksum_path = base / CHECKSUMS_FILE
    try:
        raw = _read_bytes(checksum_path, MAX_MANIFEST, "checksums file")
        lines = raw.decode("utf-8").splitlines()
        declared = {}
        for line in lines:
            if not line.strip():
                continue
            parts = line.split("  ")
            if len(parts) != 2:
                raise AlphaPackageError("malformed checksum line")
            digest, rel = parts
            _hash64(digest, "checksum digest")
            safe = _safe_rel(rel, "checksum path")
            if safe in declared:
                raise AlphaPackageError("duplicate checksum path")
            declared[safe] = digest
    except (AlphaPackageError, UnicodeError) as exc:
        return {"verdict": "FAIL", "reasons": ["checksums:" + str(exc)]}
    expected_paths = set(doc["files"]) | {MANIFEST_FILE}
    if set(declared) != expected_paths:
        return {"verdict": "FAIL", "reasons": ["checksum_path_set_mismatch"]}
    if declared.get(MANIFEST_FILE) != _sha(
            _read_bytes(base / MANIFEST_FILE, MAX_MANIFEST, "manifest")):
        reasons.append("manifest_checksum_mismatch")
    for rel, record in sorted(doc["files"].items()):
        target = base.joinpath(*rel.split("/"))
        try:
            _real_path(target.parent, "package directory")
            digest, size = _stream_sha(target, MAX_BINARY_BYTES)
        except AlphaPackageError as exc:
            reasons.append(rel + ":" + str(exc))
            continue
        if digest != record["sha256"] or size != record["size"]:
            reasons.append("checksum_mismatch:" + rel)
        if declared[rel] != digest:
            reasons.append("checksums_file_mismatch:" + rel)
        if os.name != "nt":
            try:
                mode = stat.S_IMODE(os.lstat(target).st_mode)
            except OSError:
                reasons.append("mode_unreadable:" + rel)
                continue
            if mode != int(record["mode"], 8):
                reasons.append("mode_mismatch:" + rel)
    return {"verdict": "FAIL" if reasons else "PASS", "reasons": reasons,
            "build_status": doc["build"]["status"],
            "file_count": len(doc["files"])}


def _common(operation, home, snapshot):
    return {
        "schema": SCHEMA,
        "operation": operation,
        "dry_run": True,
        "performs_changes": False,
        "privileged": False,
        "native_mint_session_acceptance": NATIVE_MINT,
        "guest_execution": NATIVE_MINT,
        "session_changes": [],
        "system_paths_written": [],
        "home": home,
        "before": {key: snapshot[key] for key in SNAPSHOT_KEYS},
        "after_expected": None,
        "steps": [],
        "rollback": [],
        "auto_action_allowed": False,
        "safety": "DRY_RUN_ONLY",
        "not_proven": [
            "No Linux Mint guest was contacted; session acceptance is " + NATIVE_MINT,
            "Screen-reader behavior: " + NATIVE_MINT,
            "No system-wide configuration or service was changed.",
        ],
    }


def _steps(*entries):
    result = []
    for order, entry in enumerate(entries, 1):
        item = dict(entry)
        item["order"] = order
        result.append(item)
    return result


def _assert_clean(home, snapshot, *, require_state_absent=True):
    reasons = []
    for key in SNAPSHOT_KEYS:
        state = snapshot[key]
        if not state["safe"] or state["kind"] != "ABSENT":
            reasons.append("unexpected_path:" + key)
    if require_state_absent and _path_state(
            _state_path(home), MAX_STATE, "state file")["kind"] != "ABSENT":
        reasons.append("state_file_exists")
    return reasons


def _install_inputs(root):
    """Re-read and fully verify the package before any install mutation.

    Returns exactly the values used to derive both the plan and the state so
    that a manifest/payload swap between the two cannot be trusted.
    """
    doc = load_manifest(root)
    checked = verify_package(root, doc)
    if checked["verdict"] != "PASS":
        raise AlphaPackageError("package verification failed: " +
                                "; ".join(checked["reasons"]))
    if doc["build"]["status"] != PE002_DIGEST_EVIDENCE_MATCHED:
        raise AlphaPackageError("COMPILE_NOT_RUN: no exact binary evidence; "
                                "install refused")
    base = Path(_text(root, "package root"))
    payload = doc["payload"]
    binary = base.joinpath(*payload["path"].split("/"))
    _real_path(binary, "payload binary")
    if not binary.is_file() or not os.access(str(binary), os.X_OK):
        raise AlphaPackageError("payload binary is missing or not executable")
    digest, size = _stream_sha(binary, MAX_BINARY_BYTES)
    if digest != payload["sha256"] or size != payload["size"]:
        raise AlphaPackageError("payload binary does not match its pinned hash")
    entry = _entry(str(binary))
    marker = _marker(entry)
    return {
        "doc": doc, "binary": binary, "digest": digest, "size": size,
        "entry": entry, "marker": marker,
        "package_sha256": _sha(_read_bytes(
            base / MANIFEST_FILE, MAX_MANIFEST, "manifest")),
    }


def _confirm_install_inputs(inputs, plan):
    if (inputs["package_sha256"] != plan["package_sha256"]
            or str(inputs["binary"]) != plan["binary_path"]
            or inputs["digest"] != plan["binary_sha256"]
            or inputs["size"] != plan["binary_size"]
            or _sha(inputs["entry"]) != plan["after_expected"]["desktop"]["sha256"]
            or _sha(inputs["marker"]) != plan["after_expected"]["manifest"]["sha256"]):
        raise AlphaPackageError("package changed before install")


def plan_install(root, home):
    inputs = _install_inputs(root)
    binary = inputs["binary"]
    digest = inputs["digest"]
    entry = inputs["entry"]
    marker = inputs["marker"]
    normalized = _data_home(home)
    owned = _owned(normalized)
    snapshot = _snapshot(normalized)
    reasons = _assert_clean(normalized, snapshot)
    if reasons:
        raise AlphaPackageError("install refused: " + "; ".join(reasons))
    if len(entry) > MAX_ENTRY or len(marker) > MAX_MARKER:
        raise AlphaPackageError("projected entry exceeds its byte bound")
    plan = _common("install", normalized, snapshot)
    plan["after_expected"] = {
        "status": "INSTALLED",
        "desktop": _projected(owned["desktop"], entry, 0o644),
        "manifest": _projected(owned["manifest"], marker, 0o600),
    }
    plan["package_sha256"] = inputs["package_sha256"]
    plan["binary_path"] = str(binary)
    plan["binary_sha256"] = digest
    plan["binary_size"] = inputs["size"]
    plan["steps"] = _steps(
        {"phase": "snapshot", "description": "Recheck all managed paths."},
        {"phase": "verify-package", "description": "Recheck exact file hashes.",
         "sha256": plan["package_sha256"]},
        {"phase": "write-state", "description": "Exclusively record pre-install state.",
         "target": str(_state_path(normalized))},
        {"phase": "write-desktop", "description": "Exclusively create the user entry.",
         "target": str(owned["desktop"]), "sha256": _sha(entry)},
        {"phase": "write-marker", "description": "Exclusively create the ownership marker.",
         "target": str(owned["manifest"]), "sha256": _sha(marker)},
        {"phase": "verify", "description": "Recheck exact bytes, mode and status.",
         "verdict": NATIVE_MINT},
    )
    plan["rollback"] = [
        {"order": 1, "action": "unlink_created_file",
         "target": str(owned["manifest"]), "bytes_bound": MAX_MARKER},
        {"order": 2, "action": "unlink_created_file",
         "target": str(owned["desktop"]), "bytes_bound": MAX_ENTRY},
        {"order": 3, "action": "unlink_created_file",
         "target": str(_state_path(normalized)), "bytes_bound": MAX_STATE},
    ]
    return plan


def _ensure_parents(paths):
    """Create only the owned directories needed by the files we will create."""
    for path in paths:
        parent = Path(_text(path, "target")).parent
        _real_path(parent, "target parent")
        try:
            parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            raise AlphaPackageError("could not create owned directory") from exc
        _real_path(parent, "target parent after creation")


def _write_exclusive(path, data, mode):
    target = Path(_text(path, "write target"))
    _real_path(target.parent, "write target parent")
    # Windows chmod only maps the owner write bit: 0644 and 0600 both end up
    # visible as 0666. Use the same effective mode the snapshots project.
    effective = 0o666 if os.name == "nt" else mode
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(str(target), flags, effective)
    except OSError as exc:
        raise AlphaPackageError("could not exclusively create " + str(target)) from exc
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        try:
            target.unlink()
        except OSError:
            pass
        raise
    try:
        os.chmod(str(target), effective)
    except OSError as exc:
        target.unlink(missing_ok=True)
        raise AlphaPackageError("could not set mode on " + str(target)) from exc


def _make_state(doc, home, binary, snapshot, entry, marker):
    return {
        "schema": SCHEMA,
        "package_id": doc["package_id"],
        "source_commit": doc["source_commit"],
        "home": str(home),
        "binary_path": str(binary),
        "binary_sha256": doc["build"]["binary_sha256"],
        "before": {key: snapshot[key] for key in OWNED_KEYS},
        "after": {
            "desktop": _projected(
                _owned(home)["desktop"], entry, 0o644),
            "manifest": _projected(
                _owned(home)["manifest"], marker, 0o600),
        },
        "entry_sha256": _sha(entry),
        "marker_sha256": _sha(marker),
    }


def _state_bytes(state):
    text = json.dumps(state, sort_keys=True, ensure_ascii=False) + "\n"
    raw = text.encode("utf-8")
    if len(raw) > MAX_STATE:
        raise AlphaPackageError("state record exceeds its byte bound")
    return raw


def load_state(home):
    normalized = _data_home(home)
    raw = _read_bytes(_state_path(normalized), MAX_STATE, "state file")
    try:
        state = json.loads(raw.decode("utf-8"),
                           object_pairs_hook=_no_duplicate_keys)
    except AlphaPackageError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise AlphaPackageError("state file is not valid JSON") from exc
    if not isinstance(state, dict) or set(state) != {
            "schema", "package_id", "source_commit", "home", "binary_path",
            "binary_sha256", "before", "after", "entry_sha256",
            "marker_sha256"}:
        raise AlphaPackageError("unexpected state record")
    if type(state["schema"]) is not int or state["schema"] != SCHEMA:
        raise AlphaPackageError("unsupported state schema")
    if state["home"] != normalized:
        raise AlphaPackageError("state home mismatch")
    _hash64(state["binary_sha256"], "state binary_sha256")
    _hash64(state["entry_sha256"], "state entry_sha256")
    _hash64(state["marker_sha256"], "state marker_sha256")
    for phase in ("before", "after"):
        if (not isinstance(state[phase], dict)
                or set(state[phase]) != set(OWNED_KEYS)):
            raise AlphaPackageError("unexpected " + phase + " state map")
    for key in OWNED_KEYS:
        limit = MAX_ENTRY if key == "desktop" else MAX_MARKER
        before = state["before"][key]
        if not isinstance(before, dict) or before.get("kind") != "ABSENT":
            raise AlphaPackageError("unsafe recorded before state: " + key)
        # apply_install can only record ABSENT before paths: any claim of a
        # pre-existing file is inconsistent and must refuse before deletions.
        if any(before.get(field) is not None for field in (
                "size", "mode", "sha256", "payload_base64")):
            raise AlphaPackageError("inconsistent recorded before state: " + key)
        after = state["after"][key]
        if not isinstance(after, dict) or after.get("kind") not in (
                "ABSENT", "REGULAR_FILE"):
            raise AlphaPackageError("unsafe recorded after state: " + key)
        if after["kind"] == "ABSENT":
            if any(after.get(field) is not None for field in (
                    "size", "mode", "sha256", "payload_base64")):
                raise AlphaPackageError(
                    "inconsistent recorded after state: " + key)
        else:
            data = _payload(after, limit, key)
            if (data is None
                    or _hash64(after.get("sha256"), key + " after sha256")
                    != _sha(data) or _int(after.get("size"), key + " after size")
                    != len(data)):
                raise AlphaPackageError(
                    "inconsistent recorded after state: " + key)
    return state


def apply_install(root, home):
    plan = plan_install(root, home)
    normalized = plan["home"]
    fresh = _snapshot(normalized)
    for key in SNAPSHOT_KEYS:
        if not _same_state(fresh[key], plan["before"][key]):
            raise AlphaPackageError("managed state changed before install")
    inputs = _install_inputs(root)
    _confirm_install_inputs(inputs, plan)
    doc = inputs["doc"]
    binary = inputs["binary"]
    entry = inputs["entry"]
    marker = inputs["marker"]
    state = _make_state(doc, normalized, binary, fresh, entry, marker)
    owned = _owned(normalized)
    created = []
    try:
        _ensure_parents([_state_path(normalized), owned["desktop"],
                         owned["manifest"]])
        _write_exclusive(_state_path(normalized), _state_bytes(state), 0o600)
        created.append(_state_path(normalized))
        _write_exclusive(owned["desktop"], entry, 0o644)
        created.append(owned["desktop"])
        _write_exclusive(owned["manifest"], marker, 0o600)
        created.append(owned["manifest"])
    except BaseException:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        raise
    observed = _snapshot(normalized)
    for key in OWNED_KEYS:
        if not _same_state(observed[key], plan["after_expected"][key]):
            for path in reversed(created):
                path.unlink(missing_ok=True)
            raise AlphaPackageError("post-install verification failed")
    return {
        "verdict": "PASS",
        "operation": "install",
        "performed_changes": True,
        "privileged": False,
        "native_mint_session_acceptance": NATIVE_MINT,
        "package_sha256": plan["package_sha256"],
        "binary_sha256": plan["binary_sha256"],
        "desktop_sha256": _sha(entry),
        "marker_sha256": _sha(marker),
        "original_desktop_state": "ABSENT",
        "managed_paths": [str(owned[key]) for key in OWNED_KEYS],
    }


def _load_and_check(root, home):
    doc = load_manifest(root)
    checked = verify_package(root, doc)
    if checked["verdict"] != "PASS":
        raise AlphaPackageError("package verification failed: " +
                                "; ".join(checked["reasons"]))
    state = load_state(home)
    if state["binary_sha256"] != doc["build"]["binary_sha256"]:
        raise AlphaPackageError("state binary hash contradicts package")
    return doc, state


def plan_uninstall(root, home):
    _doc, state = _load_and_check(root, home)
    normalized = _data_home(home)
    snapshot = _snapshot(normalized)
    reasons = []
    for key in SNAPSHOT_KEYS:
        if key in OWNED_KEYS:
            if not _same_state(snapshot[key], state["after"][key]):
                reasons.append("not_exact_owned:" + key)
        elif not snapshot[key]["safe"] or snapshot[key]["kind"] != "ABSENT":
            reasons.append("unexpected_path:" + key)
    if reasons:
        raise AlphaPackageError("uninstall refused: " + "; ".join(reasons))
    plan = _common("uninstall", normalized, snapshot)
    plan["after_expected"] = {
        "status": "NOT_INSTALLED",
        "desktop": _absent(_owned(normalized)["desktop"]),
        "manifest": _absent(_owned(normalized)["manifest"]),
    }
    plan["steps"] = _steps(
        {"phase": "snapshot", "description": "Recheck exact owned state."},
        {"phase": "verify-ownership", "description": "Match marker to entry.",
         "sha256": state["entry_sha256"]},
        {"phase": "unlink-desktop", "description": "Delete the exact owned entry.",
         "target": str(_owned(normalized)["desktop"])},
        {"phase": "unlink-marker", "description": "Delete the exact owned marker.",
         "target": str(_owned(normalized)["manifest"])},
        {"phase": "restore-original", "description": "Confirm the original desktop state.",
         "verdict": NATIVE_MINT},
    )
    plan["rollback"] = [
        {"order": 1, "action": "restore_exact_bytes_and_mode",
         "target": str(_owned(normalized)["desktop"]),
         "payload_base64": state["after"]["desktop"]["payload_base64"],
         "mode": state["after"]["desktop"]["mode"],
         "bytes_bound": MAX_ENTRY},
    ]
    return plan


def _delete_exact(path, state, name):
    current = _path_state(path, MAX_STATE, name)
    if not _same_state(current, state):
        raise AlphaPackageError(name + " changed during removal")
    try:
        Path(path).unlink()
    except OSError as exc:
        raise AlphaPackageError(name + " could not be removed") from exc


def apply_uninstall(root, home):
    plan = plan_uninstall(root, home)
    _doc, state = _load_and_check(root, plan["home"])
    normalized = plan["home"]
    fresh = _snapshot(normalized)
    for key in SNAPSHOT_KEYS:
        if key in OWNED_KEYS:
            if not _same_state(fresh[key], state["after"][key]):
                raise AlphaPackageError("managed state changed before uninstall")
    owned = _owned(normalized)
    entry_bytes = _payload(state["after"]["desktop"], MAX_ENTRY, "desktop")
    try:
        _delete_exact(owned["desktop"], state["after"]["desktop"], "desktop entry")
    except AlphaPackageError as exc:
        return {"verdict": "FAIL", "operation": "uninstall",
                "performed_changes": False, "reasons": [str(exc)]}
    try:
        _delete_exact(owned["manifest"], state["after"]["manifest"], "marker")
    except AlphaPackageError as exc:
        restored = False
        try:
            if _path_state(owned["desktop"], MAX_ENTRY, "desktop")["kind"] == "ABSENT":
                mode = state["after"]["desktop"]["mode"]
                _write_exclusive(owned["desktop"], entry_bytes,
                                 mode if mode else 0o644)
                restored = True
        except (AlphaPackageError, OSError):
            restored = False
        return {"verdict": "FAIL", "operation": "uninstall",
                "performed_changes": not restored,
                "rollback_restored": restored,
                "native_mint_session_acceptance": NATIVE_MINT,
                "reasons": [str(exc)]}
    observed = _snapshot(normalized)
    for key in OWNED_KEYS:
        if not _same_state(observed[key], state["before"][key]):
            return {"verdict": "FAIL", "operation": "uninstall",
                    "performed_changes": True,
                    "native_mint_session_acceptance": NATIVE_MINT,
                    "reasons": ["original_desktop_not_restored:" + key]}
    try:
        _state_path(normalized).unlink()
    except OSError as exc:
        return {"verdict": "FAIL", "operation": "uninstall",
                "performed_changes": True,
                "native_mint_session_acceptance": NATIVE_MINT,
                "reasons": ["state_file_not_removed:" + type(exc).__name__]}
    return {
        "verdict": "PASS",
        "operation": "uninstall",
        "performed_changes": True,
        "privileged": False,
        "native_mint_session_acceptance": NATIVE_MINT,
        "original_desktop_restored": True,
        "restored_state_sha256": _sha(_state_bytes({
            key: state["before"][key] for key in OWNED_KEYS})),
    }


def plan_rollback(root, home, target):
    if target not in ("before", "after"):
        raise AlphaPackageError("rollback target must be before or after")
    _doc, state = _load_and_check(root, home)
    normalized = _data_home(home)
    snapshot = _snapshot(normalized)
    for key in SNAPSHOT_KEYS:
        if key not in OWNED_KEYS and (
                not snapshot[key]["safe"] or snapshot[key]["kind"] != "ABSENT"):
            raise AlphaPackageError("rollback refused: unexpected_path:" + key)
    owned = _owned(normalized)
    actions = []
    for key in OWNED_KEYS:
        desired = state[target][key]
        current = snapshot[key]
        if _same_state(current, desired):
            continue
        other = state["after" if target == "before" else "before"][key]
        if desired["kind"] == "ABSENT":
            if current["kind"] == "REGULAR_FILE" and _same_state(current, other):
                actions.append({"action": "delete", "key": key,
                                "target": str(owned[key])})
                continue
            raise AlphaPackageError("rollback refused: unproven file at " + key)
        if current["kind"] == "ABSENT":
            actions.append({"action": "restore", "key": key,
                            "target": str(owned[key])})
            continue
        raise AlphaPackageError("rollback refused: modified file at " + key)
    if not actions:
        raise AlphaPackageError("rollback refused: already at target state")
    plan = _common("rollback", normalized, snapshot)
    plan["target"] = target
    plan["after_expected"] = {
        "status": "INSTALLED" if target == "after" else "NOT_INSTALLED",
        "desktop": dict(
            state["after"]["desktop"] if target == "after"
            else state["before"]["desktop"], target=str(owned["desktop"])),
        "manifest": dict(
            state["after"]["manifest"] if target == "after"
            else state["before"]["manifest"], target=str(owned["manifest"])),
    }
    plan["actions"] = actions
    plan["steps"] = _steps(
        {"phase": "snapshot", "description": "Recheck exact recorded state."},
        {"phase": "reconcile", "description": "Act only on provably owned paths."},
        {"phase": "verify", "description": "Compare exact bytes to the target state.",
         "verdict": NATIVE_MINT},
    )
    return plan


def apply_rollback(root, home, target):
    plan = plan_rollback(root, home, target)
    _doc, state = _load_and_check(root, plan["home"])
    normalized = plan["home"]
    owned = _owned(normalized)
    for action in plan["actions"]:
        key = action["key"]
        expected = state[target][key]
        current = state["after" if target == "before" else "before"][key]
        if action["action"] == "delete":
            try:
                _delete_exact(owned[key], current, key)
            except AlphaPackageError as exc:
                return {"verdict": "FAIL", "operation": "rollback",
                        "performed_changes": True, "reasons": [str(exc)]}
        else:
            data = _payload(expected,
                            MAX_ENTRY if key == "desktop" else MAX_MARKER, key)
            mode = expected["mode"] or (0o644 if key == "desktop" else 0o600)
            try:
                _ensure_parents([owned[key]])
                _write_exclusive(owned[key], data, mode)
            except AlphaPackageError as exc:
                return {"verdict": "FAIL", "operation": "rollback",
                        "performed_changes": True, "reasons": [str(exc)]}
    observed = _snapshot(normalized)
    for key in OWNED_KEYS:
        wanted = state[target][key]
        probe = dict(wanted)
        probe.pop("target", None)
        if not _same_state(observed[key], probe):
            return {"verdict": "FAIL", "operation": "rollback",
                    "performed_changes": True,
                    "reasons": ["target_state_mismatch:" + key]}
    if target == "before":
        try:
            _state_path(normalized).unlink()
        except OSError as exc:
            return {"verdict": "FAIL", "operation": "rollback",
                    "performed_changes": True,
                    "reasons": ["state_file_not_removed:" + type(exc).__name__]}
    return {"verdict": "PASS", "operation": "rollback",
            "performed_changes": True, "privileged": False,
            "target": target, "actions": plan["actions"],
            "native_mint_session_acceptance": NATIVE_MINT,
            "original_desktop_restored": target == "before"}


def _emit(result):
    print("CANOPY_ALPHA:", json.dumps(result, sort_keys=True))
    return 0 if result.get("verdict", "PASS") == "PASS" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("install", "uninstall", "plan"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", required=True, type=Path)
        cmd.add_argument("--home", required=True, type=Path)
        cmd.add_argument("--apply", action="store_true")
    rb = sub.add_parser("rollback")
    rb.add_argument("--root", required=True, type=Path)
    rb.add_argument("--home", required=True, type=Path)
    rb.add_argument("--target", choices=("before", "after"), default="before")
    rb.add_argument("--apply", action="store_true")
    ver = sub.add_parser("verify-package")
    ver.add_argument("--root", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-package":
            return _emit(verify_package(args.root))
        if args.command == "plan":
            return _emit(plan_install(args.root, args.home))
        if args.command == "install":
            if not args.apply:
                return _emit(plan_install(args.root, args.home))
            return _emit(apply_install(args.root, args.home))
        if args.command == "uninstall":
            if not args.apply:
                return _emit(plan_uninstall(args.root, args.home))
            return _emit(apply_uninstall(args.root, args.home))
        if args.command == "rollback":
            if not args.apply:
                return _emit(plan_rollback(args.root, args.home, args.target))
            return _emit(apply_rollback(args.root, args.home, args.target))
        raise AlphaPackageError("unknown command")
    except AlphaPackageError as exc:
        return _emit({"verdict": "FAIL", "operation": args.command,
                      "performed_changes": False, "reasons": [str(exc)]})


if __name__ == "__main__":
    raise SystemExit(main())
