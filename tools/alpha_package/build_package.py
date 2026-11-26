#!/usr/bin/env python3
"""Build a deterministic, reproducible Linux Mint alpha tarball.

Two modes:

  plan   Stage docs/scripts plus a MANIFEST.json whose build.status is
         COMPILE_NOT_RUN. No binary is copied and no compiled contents are
         claimed. This is the only mode available until PE-002 publishes the
         exact compiled artifact hash and build evidence.

  build  Require an already-compiled binary, an explicit SHA-256 pin and a
         PE-002 evidence JSON whose digest matches that pin. Only then stage
         payload/canopy-classic and set COMPILED_EVIDENCE_VERIFIED.

Neither mode compiles, downloads, installs, uses root or edits a session.
Staging and tarball output must not already exist: nothing is overwritten.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.alpha_package import alphactl  # noqa: E402

SCHEMA = 1
SOURCE_FILES = (
    "tools/alpha_package/alphactl.py",
    "tools/alpha_package/build_package.py",
    "tools/alpha_package/PACKAGE_README.md",
    "tools/alpha_package/NOTICE.md",
    "docs/ALPHA_PACKAGE_DESIGN.md",
)
PAYLOAD_REL = "payload/canopy-classic"
CHECKSUM_MODES = {"MANIFEST.json": "0644",
                  alphactl.CHECKSUMS_FILE: "0644"}
EVIDENCE_STATUSES = ("COMPILED", "COMPILED_VERIFIED", "PASS")


class BuildError(ValueError):
    """A build safety gate refused to stage or publish the package."""


def _repo_root():
    return Path(__file__).resolve().parents[2]


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _stream_sha(path):
    digest = hashlib.sha256()
    total = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
            total += len(chunk)
    return digest.hexdigest(), total


def _checksum_line(digest, rel):
    return digest + "  " + rel + "\n"


def _prepare_staging(staging):
    target = Path(staging)
    if not target.is_absolute():
        raise BuildError("staging must be an absolute path")
    if target.exists():
        raise BuildError("staging already exists; refusing to overwrite")
    target.mkdir(parents=True)
    return target


def _stage_sources(repo, staging):
    records = {}
    for rel in SOURCE_FILES:
        source = repo / Path(*rel.split("/"))
        if not source.is_file():
            raise BuildError("missing source file: " + rel)
        data = source.read_bytes()
        if len(data) > alphactl.MAX_FILE_BYTES:
            raise BuildError("source file exceeds its byte bound: " + rel)
        destination = staging / Path(*rel.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as handle:
            handle.write(data)
        if os.name != "nt":
            destination.chmod(0o644)
        records[rel] = {"sha256": _sha(data), "size": len(data), "mode": "0644"}
    return records


def _write_manifest(staging, package_id, source_commit, build, payload, files):
    doc = {
        "schema": SCHEMA,
        "package_id": package_id,
        "source_commit": source_commit,
        "build": build,
        "payload": payload,
        "files": files,
        "hash_alg": "sha256",
    }
    raw = (json.dumps(doc, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    path = staging / alphactl.MANIFEST_FILE
    with path.open("xb") as handle:
        handle.write(raw)
    return doc


def _write_checksums(staging, files):
    entries = dict(files)
    entries[alphactl.MANIFEST_FILE] = {
        "sha256": _sha((staging / alphactl.MANIFEST_FILE).read_bytes())}
    lines = "".join(
        _checksum_line(entries[rel]["sha256"], rel) for rel in sorted(entries))
    path = staging / alphactl.CHECKSUMS_FILE
    with path.open("xb") as handle:
        handle.write(lines.encode("utf-8"))
    return path


def _finalize(staging, package_id, source_commit, build, payload, files):
    doc = _write_manifest(staging, package_id, source_commit, build, payload,
                          files)
    _write_checksums(staging, files)
    checked = alphactl.verify_package(staging, doc)
    if checked["verdict"] != "PASS":
        raise BuildError("staged package failed verification: " +
                         "; ".join(checked["reasons"]))
    return doc


def plan_package(staging, source_commit, package_id):
    target = _prepare_staging(staging)
    files = _stage_sources(_repo_root(), target)
    build = {"status": "COMPILE_NOT_RUN", "binary_sha256": None,
             "evidence_sha256": None, "artifact": None}
    payload = {"path": None, "sha256": None, "size": None, "mode": None}
    doc = _finalize(target, package_id, source_commit, build, payload, files)
    if any(path.name == "canopy-classic" for path in target.rglob("*")):
        raise BuildError("plan package must not contain a binary")
    return {"verdict": "PASS", "mode": "plan", "completion": "COMPILE_NOT_RUN",
            "staging": str(target), "manifest_sha256": _sha(
                (target / alphactl.MANIFEST_FILE).read_bytes()),
            "file_count": len(doc["files"])}


def _read_evidence(path, binary_sha, source_commit):
    source = Path(alphactl._text(path, "evidence"))
    raw = alphactl._read_bytes(source, alphactl.MAX_MANIFEST, "evidence")
    try:
        doc = json.loads(raw.decode("utf-8"),
                         object_pairs_hook=alphactl._no_duplicate_keys)
    except alphactl.AlphaPackageError:
        raise
    except (UnicodeError, ValueError) as exc:
        raise BuildError("evidence is not valid JSON") from exc
    if not isinstance(doc, dict):
        raise BuildError("evidence must be a JSON object")
    digest = doc.get("sha256")
    if (not isinstance(digest, str) or not alphactl.HASH64.fullmatch(digest)
            or digest != binary_sha):
        raise BuildError("evidence digest does not pin the supplied binary")
    if "id" in doc and doc["id"] not in ("PE-002", "native-build"):
        raise BuildError("evidence is not from the compile workstream")
    if "status" in doc and doc["status"] not in EVIDENCE_STATUSES:
        raise BuildError("compile evidence is not terminal-success")
    if ("source_commit" in doc and doc["source_commit"] != source_commit):
        raise BuildError("evidence source commit mismatch")
    artifact = doc.get("artifact")
    if artifact is not None and (not isinstance(artifact, str) or not artifact):
        raise BuildError("invalid evidence artifact record")
    return _sha(raw), artifact


def build_package(staging, source_commit, package_id, binary, binary_sha,
                  evidence):
    digest = alphactl._hash64(binary_sha, "binary_sha256")
    evidence_sha, artifact = _read_evidence(evidence, digest, source_commit)
    source = Path(alphactl._text(binary, "binary"))
    alphactl._real_path(source, "binary")
    if not source.is_file() or not os.access(str(source), os.X_OK):
        raise BuildError("binary is missing or not executable")
    actual, size = _stream_sha(source)
    if actual != digest:
        raise BuildError("binary SHA-256 does not match its pin")
    if size > alphactl.MAX_BINARY_BYTES:
        raise BuildError("binary exceeds its byte bound")
    target = _prepare_staging(staging)
    files = _stage_sources(_repo_root(), target)
    destination = target / PAYLOAD_REL
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as handle, destination.open("xb") as out:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            out.write(chunk)
    if os.name != "nt":
        destination.chmod(0o755)
    files[PAYLOAD_REL] = {"sha256": actual, "size": size, "mode": "0755"}
    build = {"status": "COMPILED_EVIDENCE_VERIFIED", "binary_sha256": digest,
             "evidence_sha256": evidence_sha,
             "artifact": artifact or str(source)}
    payload = {"path": PAYLOAD_REL, "sha256": actual, "size": size,
               "mode": "0755"}
    doc = _finalize(target, package_id, source_commit, build, payload, files)
    return {"verdict": "PASS", "mode": "build",
            "completion": "COMPILED_EVIDENCE_VERIFIED",
            "staging": str(target), "binary_sha256": actual,
            "evidence_sha256": evidence_sha,
            "manifest_sha256": _sha((target / alphactl.MANIFEST_FILE).read_bytes()),
            "file_count": len(doc["files"])}


def write_tarball(staging, tarball):
    root = Path(alphactl._text(staging, "staging"))
    if not root.is_dir():
        raise BuildError("staging directory is missing")
    doc = json.loads((root / alphactl.MANIFEST_FILE).read_text(encoding="utf-8"))
    output = Path(alphactl._text(tarball, "tarball"))
    if not output.is_absolute() or output.suffix != ".gz":
        raise BuildError("tarball must be an absolute .gz path")
    if output.exists():
        raise BuildError("tarball already exists; refusing to overwrite")
    entries = {rel: record["mode"] for rel, record in doc["files"].items()}
    entries[alphactl.MANIFEST_FILE] = CHECKSUM_MODES[alphactl.MANIFEST_FILE]
    entries[alphactl.CHECKSUMS_FILE] = CHECKSUM_MODES[alphactl.CHECKSUMS_FILE]
    directories = sorted({"/".join(rel.split("/")[:-1]) for rel in entries
                          if "/" in rel})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw,
                           mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name in sorted(set(directories) | set(entries)):
                    if name in directories:
                        info = tarfile.TarInfo(name + "/")
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        archive.addfile(info)
                        continue
                    rel = name
                    data = (root / Path(*rel.split("/"))).read_bytes()
                    info = tarfile.TarInfo(rel)
                    info.size = len(data)
                    info.mode = int(entries[rel], 8)
                    info.mtime = 0
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    return {"verdict": "PASS", "tarball": str(output),
            "tarball_sha256": _sha(output.read_bytes()),
            "byte_size": output.stat().st_size,
            "build_status": doc["build"]["status"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "build"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--staging", required=True, type=Path)
        cmd.add_argument("--source-commit", required=True)
        cmd.add_argument("--package-id", default="canopy-classic-alpha-90dd463")
        cmd.add_argument("--tarball", type=Path)
        if name == "build":
            cmd.add_argument("--binary", required=True, type=Path)
            cmd.add_argument("--binary-sha256", required=True)
            cmd.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if not alphactl.HASH40.fullmatch(args.source_commit):
            raise BuildError("source-commit must be a 40-hex SHA")
        if not args.package_id or not alphactl.TOKEN.fullmatch(args.package_id):
            raise BuildError("invalid package id")
        if args.command == "plan":
            result = plan_package(args.staging, args.source_commit,
                                  args.package_id)
        else:
            result = build_package(
                args.staging, args.source_commit, args.package_id,
                args.binary, args.binary_sha256, args.evidence)
        if args.tarball is not None:
            result["tarball_result"] = write_tarball(args.staging, args.tarball)
        print("CANOPY_ALPHA_BUILD:", json.dumps(result, sort_keys=True))
        return 0
    except (BuildError, alphactl.AlphaPackageError, OSError, ValueError) as exc:
        print("CANOPY_ALPHA_BUILD_FAIL:", json.dumps(
            {"verdict": "FAIL", "reasons": [str(exc)]}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
