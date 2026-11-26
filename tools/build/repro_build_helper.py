#!/usr/bin/env python3
"""Offline reproducibility helper for the Classic MSYS2 UCRT64 build.

RI-003 attributed non-identical release binaries to EOL conversion and file
mtimes, not to a source defect. This helper makes those two inputs explicit
and stable without editing the tracked worktree, assets, QML or C++:

* staged source bytes are taken from git blobs (never from a worktree whose
  ``core.autocrlf=true`` checkout may have rewritten LF to CRLF);
* pinned compiled-source blobs (C/C++, QML, CMake, Qt project files) are
  canonicalized to LF; binary blobs and hash-pinned docs/artifacts are copied
  byte-for-byte;
* staged files and generated ``qmldir`` inputs get a stable mtime, and the
  build environment carries ``SOURCE_DATE_EPOCH``.

It is tooling only: it never changes git config, product code or build output.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys

STABLE_EPOCH = 0
REPORT_NAME = "repro_stage_report.json"
HEX_CHARS = frozenset("0123456789abcdefABCDEF")
COMPILED_SOURCE_SUFFIXES = frozenset((
    ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx",
    ".qml", ".cmake", ".pri", ".pro", ".qrc", ".ui",
))
COMPILED_SOURCE_NAMES = frozenset(("CMakeLists.txt",))
GENERATED_INPUT_NAMES = ("qmldir",)
AUTOCRLF_SAFE = frozenset(("false", "input"))
AUTOCRLF_KNOWN = frozenset(("true", "false", "input"))


def normalize_eol(data: bytes):
    """Return ``(canonical_bytes, changed)``; binary data is never rewritten."""
    if not isinstance(data, bytes):
        raise TypeError("normalize_eol requires bytes")
    if b"\x00" in data:
        return data, False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return data, False
    canonical = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return canonical, canonical != data


def is_compiled_source(path) -> bool:
    """Only compiler/rcc inputs get EOL rewriting; hash-pinned artifacts do not."""
    if not isinstance(path, (str, PurePosixPath)):
        raise TypeError("is_compiled_source requires a path string")
    parsed = PurePosixPath(path)
    return (parsed.name in COMPILED_SOURCE_NAMES
            or parsed.suffix.lower() in COMPILED_SOURCE_SUFFIXES)


def staged_bytes(blob: bytes, path):
    """Return the canonical staged bytes for a pinned blob at ``path``."""
    if not is_compiled_source(path):
        return blob, False
    return normalize_eol(blob)


def canonical_autocrlf(value):
    """Canonical git ``core.autocrlf`` token, or None for an unknown value."""
    if value is None:
        return "false"  # git's default on the build host
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    return token if token in AUTOCRLF_KNOWN else None


def autocrlf_is_safe(value) -> bool:
    """True only when a checkout cannot turn LF source bytes into CRLF."""
    return canonical_autocrlf(value) in AUTOCRLF_SAFE


def _check_epoch(epoch):
    if type(epoch) is not int or epoch < 0:
        raise ValueError("epoch must be a non-negative int")


def stable_env(base=None, *, epoch=STABLE_EPOCH):
    """Copy ``base`` with deterministic time/locale inputs; never mutate it."""
    _check_epoch(epoch)
    if base is None:
        base = {}
    if not isinstance(base, dict):
        raise ValueError("base must be a dict")
    env = dict(base)
    env.update({"SOURCE_DATE_EPOCH": str(epoch), "TZ": "UTC", "LANG": "C"})
    return env


def normalize_mtimes(root, *, epoch=STABLE_EPOCH):
    """Pin mtimes of all regular files below ``root``; skip symlinks."""
    _check_epoch(epoch)
    directory = Path(root)
    if not directory.is_dir():
        raise ValueError("root must be an existing directory")
    count = 0
    for path in directory.rglob("*"):
        if path.is_symlink() or not path.is_file():
            continue
        os.utime(path, (epoch, epoch))
        count += 1
    return count


def normalize_generated_mtimes(build_dir, *, epoch=STABLE_EPOCH,
                               names=GENERATED_INPUT_NAMES):
    """Pin CMake/Qt generated inputs (qmldir) that rcc embeds as mtimes."""
    _check_epoch(epoch)
    directory = Path(build_dir)
    if not directory.is_dir():
        raise ValueError("build_dir must be an existing directory")
    wanted = frozenset(names)
    count = 0
    for path in directory.rglob("*"):
        if path.is_symlink() or not path.is_file() or path.name not in wanted:
            continue
        os.utime(path, (epoch, epoch))
        count += 1
    return count


def native(path: Path) -> str:
    return str(path).replace("\\", "/")


def canonical_sha(value):
    """40-hex SHA-256 lowercase, or None for anything else (fail closed)."""
    if not isinstance(value, str) or len(value) != 40:
        return None
    if any(char not in HEX_CHARS for char in value):
        return None
    return value.lower()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(source, *args):
    return subprocess.run(["git", "-C", native(source), *args],
                          capture_output=True, timeout=180)


def _validate_source(source, expected_sha):
    """Return the pinned tree SHA only for a clean, exactly pinned worktree."""
    head = git(source, "rev-parse", "HEAD")
    if head.returncode != 0 or canonical_sha(head.stdout.decode().strip()) != expected_sha:
        raise ValueError("source HEAD is %r, expected %s"
                         % (head.stdout.decode().strip(), expected_sha))
    tree = git(source, "rev-parse", "HEAD^{tree}")
    if tree.returncode != 0:
        raise ValueError("source tree could not be resolved")
    dirty = git(source, "diff", "--quiet")
    staged = git(source, "diff", "--cached", "--quiet")
    if dirty.returncode or staged.returncode:
        raise ValueError("source worktree dirty or staged")
    return tree.stdout.decode().strip()


def _tracked_entries(source):
    """List ``(mode, blob_oid, repo_path)`` for every regular tracked file."""
    result = git(source, "ls-files", "-s", "-z")
    if result.returncode != 0:
        raise ValueError("tracked file list could not be read")
    entries = []
    for raw in result.stdout.split(b"\0"):
        if not raw:
            continue
        meta, path_bytes = raw.split(b"\t", 1)
        mode, oid, stage = meta.split()
        if stage != b"0":
            raise ValueError("unmerged index entry")
        mode_text = mode.decode()
        if mode_text not in ("100644", "100755"):
            raise ValueError("unsupported tracked mode %s" % mode_text)
        path = path_bytes.decode("utf-8")
        parts = PurePosixPath(path).parts
        if (not path or path.startswith("/") or "\\" in path
                or any(part in ("..", ".", ".git") for part in parts)):
            raise ValueError("unsafe tracked path %r" % path)
        entries.append((mode_text, oid.decode(), path))
    return entries


def _read_blobs(source, oids):
    """Read pinned blob bytes in one git batch (worktree EOL is never used)."""
    unique = list(dict.fromkeys(oids))
    if not unique:
        return {}
    payload = ("\n".join(unique) + "\n").encode("ascii")
    result = subprocess.run(
        ["git", "-C", native(source), "cat-file", "--batch"],
        input=payload, capture_output=True, timeout=300)
    if result.returncode != 0:
        raise ValueError("git cat-file --batch failed")
    data = result.stdout
    position = 0
    blobs = {}
    for oid in unique:
        end = data.find(b"\n", position)
        if end < 0:
            raise ValueError("truncated git cat-file header")
        fields = data[position:end].decode("ascii").split()
        position = end + 1
        if len(fields) != 3 or fields[0] != oid or fields[1] != "blob":
            raise ValueError("unexpected git cat-file header")
        size = int(fields[2])
        blob = data[position:position + size]
        position += size + 1
        if len(blob) != size:
            raise ValueError("truncated git cat-file payload")
        blobs[oid] = blob
    return blobs


def _core_autocrlf(source):
    result = git(source, "config", "--get", "core.autocrlf")
    observed = result.stdout.decode().strip() if result.returncode == 0 else "unset"
    canonical = "false" if observed == "unset" else canonical_autocrlf(observed)
    return {
        "observed": observed,
        "canonical": canonical,
        "safe": autocrlf_is_safe(observed),
        "policy": ("source bytes come from git blobs; worktree EOL and git "
                   "config are reported but never modified"),
    }


def _stage_path(stage, path):
    target = stage.joinpath(*PurePosixPath(path).parts).resolve()
    root = stage.resolve()
    if not target.is_relative_to(root):
        raise ValueError("staged path escapes scratch root")
    return target


def _check_out(source, out):
    source = Path(source).resolve()
    out = Path(out).resolve()
    if (out == Path(out.anchor) or source == Path(source.anchor)
            or out == source or out in source.parents or source in out.parents):
        raise ValueError("out must be scratch, outside the source worktree")
    if out.exists() and any(out.iterdir()):
        raise ValueError("out must be a fresh or empty scratch directory")
    out.mkdir(parents=True, exist_ok=True)
    return out


def prepare(source, source_sha, out, *, epoch=STABLE_EPOCH):
    """Materialize pinned, LF-canonical, epoch-pinned sources in scratch."""
    expected = canonical_sha(source_sha)
    if expected is None:
        raise ValueError("--source-sha must be a 40-character hex string")
    tree = _validate_source(source, expected)
    out = _check_out(source, out)
    entries = _tracked_entries(source)
    blobs = _read_blobs(source, [oid for _, oid, _ in entries])
    files = []
    byte_identical = 0
    eol_normalized = 0
    for mode, oid, path in entries:
        blob = blobs[oid]
        canonical, changed = staged_bytes(blob, path)
        target = _stage_path(out, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(canonical)
        os.chmod(target, 0o755 if mode == "100755" else 0o644)
        identical = canonical == blob
        byte_identical += int(identical)
        eol_normalized += int(changed)
        files.append({
            "path": path, "mode": mode,
            "blob_sha256": sha256_bytes(blob),
            "stage_sha256": sha256_bytes(canonical),
            "byte_identical": identical, "eol_normalized": changed,
        })
    env = stable_env({}, epoch=epoch)
    autocrlf = _core_autocrlf(source)
    report = {
        "schema_version": 1,
        "source_sha": expected,
        "source_tree_sha": tree,
        "source_worktree_tracked_clean": True,
        "core_autocrlf": autocrlf,
        "stable_timestamp": {
            "epoch": epoch,
            "env": env,
            "generated_input_policy": ("CMake/Qt generated qmldir files must be "
                                       "pinned with normalize_generated_mtimes "
                                       "before rcc, as in classic_release_build.py"),
        },
        "counts": {
            "files": len(files),
            "byte_identical": byte_identical,
            "eol_normalized": eol_normalized,
        },
        "files": files,
    }
    report_path = out / REPORT_NAME
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    normalized = normalize_mtimes(out, epoch=epoch)
    print("SOURCE sha=%s tree=%s" % (expected, tree))
    print("AUTOCRLF observed=%s canonical=%s safe=%s"
          % (autocrlf["observed"], autocrlf["canonical"], autocrlf["safe"]))
    print("STAGE files=%d byte_identical=%d eol_normalized=%d"
          % (len(files), byte_identical, eol_normalized))
    print("MTIME normalized=%d epoch=%d" % (normalized, epoch))
    print("ENV SOURCE_DATE_EPOCH=%s TZ=%s"
          % (env["SOURCE_DATE_EPOCH"], env["TZ"]))
    print("REPORT path=%s sha256=%s"
          % (REPORT_NAME, sha256_bytes(report_path.read_bytes())))
    print("HELPER_PASS")
    return 0


def verify(source, stage, source_sha, *, epoch=STABLE_EPOCH):
    """Re-derive every staged byte and mtime from the pinned tree."""
    expected = canonical_sha(source_sha)
    if expected is None:
        raise ValueError("--source-sha must be a 40-character hex string")
    _validate_source(source, expected)
    stage = Path(stage).resolve()
    if not stage.is_dir():
        raise ValueError("stage must be an existing directory")
    report_path = stage / REPORT_NAME
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("source_sha") != expected:
        print("VERIFY_FAIL: source_sha")
        return 1
    entries = _tracked_entries(source)
    blobs = _read_blobs(source, [oid for _, oid, _ in entries])
    by_path = {path: (mode, oid) for mode, oid, path in entries}
    reported = report.get("files")
    if not isinstance(reported, list) or {e["path"] for e in reported} != set(by_path):
        print("VERIFY_FAIL: file set")
        return 1
    failures = []
    for entry in reported:
        path = entry["path"]
        target = _stage_path(stage, path)
        if not target.is_file():
            failures.append(path)
            continue
        actual = target.read_bytes()
        canonical, _ = staged_bytes(blobs[by_path[path][1]], path)
        if (actual != canonical
                or sha256_bytes(actual) != entry["stage_sha256"]
                or target.stat().st_mtime_ns != epoch * 1_000_000_000):
            failures.append(path)
    extra = {str(path.relative_to(stage)).replace("\\", "/")
             for path in stage.rglob("*")
             if path.is_file() and path.name != REPORT_NAME} - set(by_path)
    if failures or extra:
        for path in failures[:8]:
            print("VERIFY_FAIL: %s" % path)
        if extra:
            print("VERIFY_FAIL: unexpected staged paths=%d" % len(extra))
        return 1
    print("VERIFY files=%d pass=%d epoch=%d" % (len(by_path), len(by_path), epoch))
    print("VERIFY_PASS")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--source", required=True,
                             help="native path of the pinned source worktree")
        command.add_argument("--source-sha", required=True,
                             help="exact 40-hex commit the caller trusts")
        command.add_argument("--out" if name == "prepare" else "--stage",
                             required=True, help="native scratch path")
        command.add_argument("--epoch", type=int, default=STABLE_EPOCH,
                             help="non-negative stable mtime / SOURCE_DATE_EPOCH")
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            return prepare(args.source, args.source_sha, args.out, epoch=args.epoch)
        return verify(args.source, args.stage, args.source_sha, epoch=args.epoch)
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        print("HELPER_FAIL: %s" % exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
