#!/usr/bin/env python3
"""Build and verify one reproducible source+binary development artifact.

The artifact is built ONLY from the pinned git commit plus the exact, already
verified KPackage binary blob in that commit. No wall-clock value enters any
byte of the archive. Nothing here installs into a desktop, mutates a VM,
changes approved artwork, merges a branch or claims a release/approval.

Build (Linux or Windows host, Python 3.10+):

    PYTHONPATH=<worktree> python tools/native/artifact/build_dev_artifact.py \
        --worktree <worktree> --out <worktree>/scratch/native_dev_artifact

Verify an already built artifact without rebuilding:

    PYTHONPATH=<worktree> python tools/native/artifact/build_dev_artifact.py \
        --worktree <worktree> --out <worktree>/scratch/native_dev_artifact --verify-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE_TOOLS = HERE.parent
if str(NATIVE_TOOLS) not in sys.path:
    sys.path.insert(0, str(NATIVE_TOOLS))
import baseline_common as bc  # noqa: E402  (read-only, shared, fail-closed helpers)

WORKTREE_DEFAULT = HERE.parents[2]

SCHEMA_SOURCE_ID = "canopy.native.source_id/1"
SCHEMA_ARTIFACT_ID = "canopy.native.dev_artifact/1"
SCHEMA_EVIDENCE = "canopy.native.dev_artifact_evidence/1"

BRANCH = "integration/native-dev-artifact-20261128"
OWNER_DIRECTIVE_SHA_PREFIX = "79e30d79"
SOURCE_COMMIT = "21c32b61a29f61210fef38c6b9447b49dbfd10bf"
BASELINE_COMMIT = "ec910d7a7275296ecbc8b5e5c459d356205165d1"
BASELINE_TREE = "3c6110a77e9e34be367a4d11b29c3d6a13138bab"
BINARY_REL = (
    "scratch/native_build_baseline/build/dist/"
    "org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz"
)
MANIFEST_REL = "scratch/native_build_baseline/build/MANIFEST.json"
BINARY_SHA256 = "ec9e44cfaa3ba3059aef492b429a6e6c6b94da32a230d4acb6cb28a1ef3ece35"
BINARY_BYTES = 5503210
PACKAGE_VERSION = "0.1.0-dev-baseline"
ARTIFACT_VERSION = "1.0.0"
ARCHIVE_NAME = "canopy-native-dev-artifact-20261128.tar.gz"
STAGE_NAME = "canopy-native-dev-artifact-20261128"
BINARY_STAGE_REL = "binary/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz"
DOC_REL = "docs/NATIVE_DEV_ARTIFACT.md"
SCOPE = ("DEVELOPMENT_ARTIFACT_ONLY;NO_RELEASE;NO_VISUAL_APPROVAL;"
         "NO_MERGE;NO_APPROVAL;NO_CI_CLAIM")
SOURCE_PREFIXES = ("prototype/classic/", "tools/native/")
DOC_INCLUDE = re.compile(
    r"^(?:AGENTS\.md|docs/(?:NATIVE_|CLASSIC_.*NATIVE_|SESSION_CONTROLS_NATIVE_|"
    r"ND041_NATIVE_).*\.md)$"
)


class ArtifactError(RuntimeError):
    """Fail closed on any pin, identity or determinism violation."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(payload: object) -> bytes:
    """Byte-stable JSON: sorted keys, LF line endings, trailing newline."""
    return (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("utf-8")


def git_run(worktree: Path, args: list[str], *, binary: bool = False,
            timeout: int = 600) -> bytes | str:
    """argv-list git call (never shell=True: revision expressions contain ^)."""
    command = ["git", "-C", str(worktree), *args]
    try:
        completed = subprocess.run(command, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   timeout=timeout)
    except subprocess.SubprocessError as error:
        raise ArtifactError("git invocation failed: %s" % error) from error
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise ArtifactError("git %s failed (%d): %s"
                            % (" ".join(args), completed.returncode, detail))
    return completed.stdout if binary else completed.stdout.decode("utf-8", "replace")


def resolve_commit(worktree: Path, commit: str) -> tuple[str, str]:
    """Return (40-hex commit, 40-hex tree) for an object that must be a commit."""
    result = str(git_run(worktree, ["rev-parse", "--verify", commit + "^{commit}"])).strip()
    tree = str(git_run(worktree, ["rev-parse", "--verify", commit + "^{tree}"])).strip()
    if not bc.is_hex40(result) or not bc.is_hex40(tree):
        raise ArtifactError("commit/tree resolution is not 40-hex: %r %r" % (result, tree))
    return result.lower(), tree.lower()


def list_tree(worktree: Path, commit: str) -> list[dict]:
    """Deterministic regular-file inventory of a git commit (blob bytes source)."""
    raw = git_run(worktree, ["ls-tree", "-r", "-z", commit], binary=True)
    entries: list[dict] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        meta, _, path_bytes = record.partition(b"\t")
        if not path_bytes:
            raise ArtifactError("malformed ls-tree record")
        mode, kind, oid = meta.decode("ascii").split()
        path = path_bytes.decode("utf-8")
        if path.startswith("/") or ".." in path.split("/") or "\\" in path:
            raise ArtifactError("unsafe path in git tree: %r" % path)
        entries.append({"mode": mode, "kind": kind, "oid": oid.lower(), "path": path})
    entries.sort(key=lambda item: item["path"])
    return entries


def hash_blobs(worktree: Path, oids: list[str], keep: frozenset[str]) -> dict[str, tuple[str, bytes]]:
    """SHA-256 every blob via one cat-file --batch; retain only requested bytes.

    Object ids are fed from a temporary file and stdout is captured to a
    temporary file: piping a few thousand OIDs inline can deadlock on Windows.
    """
    unique = sorted(set(oids))
    if not unique:
        return {}
    result: dict[str, tuple[str, bytes]] = {}
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="\n") as oid_file:
        oid_file.write("".join(oid + "\n" for oid in unique))
        oid_file.flush()
        oid_file.seek(0)
        with tempfile.TemporaryFile() as output:
            try:
                completed = subprocess.run(
                    ["git", "-C", str(worktree), "cat-file", "--batch"],
                    stdin=oid_file, stdout=output, stderr=subprocess.PIPE, timeout=600)
            except subprocess.SubprocessError as error:
                raise ArtifactError("git cat-file failed: %s" % error) from error
            if completed.returncode != 0:
                raise ArtifactError("git cat-file rc=%d: %s"
                                    % (completed.returncode,
                                       completed.stderr.decode("utf-8", "replace")[:400]))
            output.seek(0)
            stream = output
            for expected in unique:
                header = stream.readline().decode("ascii", "replace").strip()
                parts = header.split()
                if len(parts) != 3 or parts[0].lower() != expected or parts[1] != "blob":
                    raise ArtifactError("unexpected cat-file header for %s: %r" % (expected, header))
                size = int(parts[2])
                data = stream.read(size)
                if len(data) != size or stream.read(1) != b"\n":
                    raise ArtifactError("truncated cat-file payload for %s" % expected)
                digest = bc.sha256_bytes(data)
                result[expected] = (digest, data if expected in keep else b"")
    return result


def collect_source(worktree: Path, commit: str, tree: str, entries: list[dict]
                   ) -> tuple[dict, dict[str, bytes], list[str]]:
    """Build SOURCE_ID payload and the exact source bytes selected for the bundle."""
    included = [item for item in entries
                if item["path"].startswith(SOURCE_PREFIXES) or DOC_INCLUDE.match(item["path"])]
    keep = frozenset(item["oid"] for item in included)
    hashes = hash_blobs(worktree, [item["oid"] for item in entries], keep)
    files: dict[str, str] = {}
    for item in entries:
        if item["kind"] != "blob":
            raise ArtifactError("non-blob entry in tree: %s" % item["path"])
        if item["mode"] == "120000":
            files["%s (symlink)" % item["path"]] = hashes[item["oid"]][0]
            continue
        files[item["path"]] = hashes[item["oid"]][0]
    payload = {
        "schema": SCHEMA_SOURCE_ID,
        "commit": commit,
        "tree": tree,
        "file_count": len(files),
        "files": files,
        "note": ("full candidate tree content identity from git blob bytes (LF); "
                 "the bundle embeds only the paths listed in ARTIFACT_ID.json; "
                 "this is an identity pin, not an approval"),
    }
    selected: dict[str, bytes] = {}
    symlinks: list[str] = []
    for item in included:
        if item["mode"] == "120000":
            symlinks.append(item["path"])
            continue
        if item["mode"] not in ("100644", "100755"):
            raise ArtifactError("unsupported mode %s for %s" % (item["mode"], item["path"]))
        selected[item["path"]] = hashes[item["oid"]][1]
    if symlinks:
        raise ArtifactError("symlink in bundled source set: %s" % ", ".join(symlinks[:5]))
    if BINARY_REL not in files or MANIFEST_REL not in files:
        raise ArtifactError("pinned binary or its manifest is absent from the source commit")
    return payload, selected, sorted(selected)


def verify_binary(data: bytes, manifest_data: bytes) -> tuple[str, str]:
    """Fail closed unless the binary blob matches its own prior build manifest."""
    if len(data) != BINARY_BYTES or bc.sha256_bytes(data) != BINARY_SHA256:
        raise ArtifactError("binary archive bytes do not match the pinned SHA/size")
    try:
        manifest = json.loads(manifest_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ArtifactError("build manifest is not valid JSON: %s" % error) from error
    claimed = manifest.get("package", {}).get("archive_sha256")
    if bc.canonical_sha256(claimed) != BINARY_SHA256:
        raise ArtifactError("binary archive SHA disagrees with MANIFEST.json: %r" % claimed)
    if manifest.get("source", {}).get("commit") != BASELINE_COMMIT:
        raise ArtifactError("binary manifest source commit is not the known-good baseline")
    return BINARY_SHA256, str(claimed)


def stage_bundle(stage: Path, doc_bytes: bytes, source_id: dict,
                 selected: dict[str, bytes], included_paths: list[str],
                 binary_data: bytes, manifest: dict) -> dict:
    """Materialise the deterministic bundle root and return its identity record."""
    if stage.exists():
        import shutil
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    (stage / "source").mkdir()
    (stage / "binary").mkdir()

    def put(relative: str, data: bytes, executable: bool = False) -> None:
        target = stage / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "wb") as stream:
            stream.write(data)
        os.chmod(target, 0o755 if executable else 0o644)

    put("README.md", doc_bytes)
    put("SOURCE_ID.json", canonical_json(source_id))
    put(BINARY_STAGE_REL, binary_data)
    for relative in included_paths:
        put("source/" + relative, selected[relative])

    artifact_id = {
        "schema": SCHEMA_ARTIFACT_ID,
        "artifact": STAGE_NAME,
        "branch": BRANCH,
        "owner_directive_sha_prefix": OWNER_DIRECTIVE_SHA_PREFIX,
        "version": ARTIFACT_VERSION,
        "source": {
            "commit": source_id["commit"],
            "tree": source_id["tree"],
            "full_tree_file_count": source_id["file_count"],
            "embedded_prefixes": list(SOURCE_PREFIXES),
            "embedded_doc_pattern": DOC_INCLUDE.pattern,
            "embedded_file_count": len(included_paths),
            "source_id_path": "SOURCE_ID.json",
        },
        "binary": {
            "path": BINARY_STAGE_REL,
            "sha256": BINARY_SHA256,
            "bytes": BINARY_BYTES,
            "package_id": bc.PACKAGE_ID,
            "package_version": PACKAGE_VERSION,
            "built_from_commit": BASELINE_COMMIT,
            "built_from_tree": BASELINE_TREE,
        },
        "known_good_rollback": {
            "package_archive": BINARY_STAGE_REL,
            "archive_sha256": BINARY_SHA256,
            "binary_in_package": manifest["binary"]["sha256"],
            "baseline_doc": "docs/NATIVE_BUILD_BASELINE.md",
            "rollback_doc": "docs/NATIVE_ROLLBACK.md",
            "candidate_source_commit": SOURCE_COMMIT,
        },
        "scope": SCOPE,
        "verdict": "PASS",
        "builder": "tools/native/artifact/build_dev_artifact.py",
    }
    put("ARTIFACT_ID.json", canonical_json(artifact_id))
    put("SHA256SUMS", bc.make_sha256sums(stage, frozenset({"SHA256SUMS"})).encode("utf-8"))
    return artifact_id


def build(worktree: Path, out: Path, source_commit: str, doc_path: Path) -> dict:
    commit, tree = resolve_commit(worktree, source_commit)
    if commit != SOURCE_COMMIT:
        raise ArtifactError("source commit %s is not the pinned %s" % (commit, SOURCE_COMMIT))
    entries = list_tree(worktree, commit)
    source_id, selected, included_paths = collect_source(worktree, commit, tree, entries)
    pinned = [item["oid"] for item in entries if item["path"] in (BINARY_REL, MANIFEST_REL)]
    if len(pinned) != 2:
        raise ArtifactError("pinned binary and manifest must each appear exactly once")
    blobs = hash_blobs(worktree, pinned, frozenset(pinned))
    binary_data = blobs[next(item["oid"] for item in entries if item["path"] == BINARY_REL)][1]
    manifest_data = blobs[next(item["oid"] for item in entries if item["path"] == MANIFEST_REL)][1]
    binary_sha, manifest_sha = verify_binary(binary_data, manifest_data)
    manifest = json.loads(manifest_data.decode("utf-8"))
    if not doc_path.is_file():
        raise ArtifactError("missing delivery document: %s" % bc.path_string(doc_path))
    doc_bytes = doc_path.read_bytes()
    if b"NO RELEASE" not in doc_bytes:
        raise ArtifactError("delivery document lacks the explicit no-release boundary")

    out.mkdir(parents=True, exist_ok=True)
    stage = out / "stage" / STAGE_NAME
    artifact_id = stage_bundle(stage, doc_bytes, source_id, selected, included_paths,
                               binary_data, manifest)

    archive = out / ARCHIVE_NAME
    first = bc.write_deterministic_tarball(stage, archive)
    second_path = out / "rebuild-check" / ARCHIVE_NAME
    second = bc.write_deterministic_tarball(stage, second_path)
    if first != second:
        raise ArtifactError("artifact is not byte-identical on rebuild: %s != %s" % (first, second))

    sums = bc.parse_sha256sums((stage / "SHA256SUMS").read_text(encoding="utf-8"))
    if "README.md" not in sums or BINARY_STAGE_REL not in sums or "SHA256SUMS" in sums:
        raise ArtifactError("inner SHA256SUMS does not cover the bundle correctly")
    if sums[BINARY_STAGE_REL] != binary_sha:
        raise ArtifactError("inner SHA256SUMS binary digest mismatch")

    (out / "SHA256SUMS.txt").write_text(
        "%s  %s\n" % (first, ARCHIVE_NAME), encoding="utf-8", newline="\n")
    evidence = {
        "schema": SCHEMA_EVIDENCE,
        "generated_utc": utc_now(),
        "verdict": "PASS",
        "scope": SCOPE,
        "owner_directive_sha_prefix": OWNER_DIRECTIVE_SHA_PREFIX,
        "branch": BRANCH,
        "worktree_head": str(git_run(worktree, ["rev-parse", "HEAD"])).strip(),
        "source_commit": commit,
        "source_tree": tree,
        "artifact": {
            "name": ARCHIVE_NAME,
            "sha256": first,
            "rebuild_sha256": second,
            "bytes": archive.stat().st_size,
            "rebuild_byte_identical": True,
        },
        "source_id_sha256": bc.sha256_bytes(canonical_json(source_id)),
        "doc_path": DOC_REL,
        "doc_sha256": bc.sha256_bytes(doc_bytes),
        "binary": {
            "stage_path": BINARY_STAGE_REL,
            "sha256": binary_sha,
            "manifest_archive_sha256": manifest_sha,
            "bytes": BINARY_BYTES,
        },
        "inner_members": len(sums),
        "embedded_source_files": len(included_paths),
        "gates": [
            ["source_commit_pinned", "PASS", commit],
            ["source_tree_pinned", "PASS", tree],
            ["source_id_full_tree", "PASS", "%d files" % source_id["file_count"]],
            ["binary_sha256_matches_manifest", "PASS", binary_sha],
            ["inner_sha256sums_exact", "PASS", "%d members" % len(sums)],
            ["archive_rebuild_byte_identical", "PASS", first],
            ["no_release_no_merge_boundary", "PASS", SCOPE],
        ],
        "commands": {
            "build": ("PYTHONPATH=<worktree> python tools/native/artifact/"
                      "build_dev_artifact.py --worktree <worktree> --out <out>"),
            "verify": ("PYTHONPATH=<worktree> python tools/native/artifact/"
                       "build_dev_artifact.py --worktree <worktree> --out <out> --verify-only"),
        },
        "note": ("Deterministic bytes are SYNTHETIC evidence of reproducibility; "
                 "prior real Plasma guest install/rollback evidence is cited at the "
                 "pinned baseline and is NOT re-executed here. No CI, visual "
                 "acceptance, release or merge claim."),
    }
    (out / "DEV_ARTIFACT.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for key, value in (("archive_sha256", first), ("rebuild_sha256", second)):
        print("%s=%s" % (key, value))
    print("BUILD_PASS: %s sha256=%s" % (ARCHIVE_NAME, first))
    return evidence


def verify_only(out: Path, expected_sha: str | None = None) -> dict:
    """Verify the built artifact against SHA256SUMS.txt and its own inner manifest."""
    archive = out / ARCHIVE_NAME
    if not archive.is_file():
        raise ArtifactError("artifact archive is missing: %s" % bc.path_string(archive))
    lines = (out / "SHA256SUMS.txt").read_text(encoding="utf-8")
    manifest = bc.parse_sha256sums(lines)
    if set(manifest) != {ARCHIVE_NAME}:
        raise ArtifactError("outer SHA256SUMS.txt does not list exactly the artifact")
    actual = bc.sha256_file(archive)
    if manifest[ARCHIVE_NAME] != actual:
        raise ArtifactError("artifact SHA-256 mismatch: %s != %s" % (actual, manifest[ARCHIVE_NAME]))
    if expected_sha and actual != expected_sha:
        raise ArtifactError("artifact SHA-256 differs from the claimed pin")
    with tempfile.TemporaryDirectory() as tmp:
        import tarfile
        with tarfile.open(archive, "r:gz") as bundle:
            bundle.extractall(tmp, filter="data")
        root = Path(tmp)
        if not (root / "ARTIFACT_ID.json").is_file():
            nested = root / STAGE_NAME
            if (nested / "ARTIFACT_ID.json").is_file():
                root = nested
        if not (root / "ARTIFACT_ID.json").is_file():
            raise ArtifactError("archive root lacks ARTIFACT_ID.json (expected %s as root)"
                                % STAGE_NAME)
        inner = bc.parse_sha256sums((root / "SHA256SUMS").read_text(encoding="utf-8"))
        for relative, digest in inner.items():
            target = root / relative
            if not target.is_file() or bc.sha256_file(target) != digest:
                raise ArtifactError("inner SHA256SUMS failure: %s" % relative)
        identity = json.loads((root / "ARTIFACT_ID.json").read_text(encoding="utf-8"))
        if identity.get("schema") != SCHEMA_ARTIFACT_ID or identity.get("verdict") != "PASS":
            raise ArtifactError("ARTIFACT_ID.json schema/verdict is not the expected pin")
        if identity.get("binary", {}).get("sha256") != BINARY_SHA256:
            raise ArtifactError("ARTIFACT_ID.json binary pin mismatch")
        if bc.sha256_file(root / BINARY_STAGE_REL) != BINARY_SHA256:
            raise ArtifactError("embedded binary archive SHA-256 mismatch")
        if not identity["scope"].startswith("DEVELOPMENT_ARTIFACT_ONLY"):
            raise ArtifactError("artifact scope is not development-only")
    result = {"verdict": "PASS", "sha256": actual, "bytes": archive.stat().st_size,
              "inner_members": len(inner), "embedded_binary_sha256": BINARY_SHA256}
    print("VERIFY_PASS: sha256=%s inner_members=%d" % (actual, len(inner)))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worktree", type=Path, default=WORKTREE_DEFAULT)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--source-commit", default=SOURCE_COMMIT)
    parser.add_argument("--doc", type=Path, default=None)
    parser.add_argument("--expected-sha", default=None,
                        help="optional exact artifact SHA-256 required by --verify-only")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args(argv)
    worktree = args.worktree.resolve()
    out = (args.out or worktree / "scratch" / "native_dev_artifact").resolve()
    doc = (args.doc or worktree / DOC_REL).resolve()
    try:
        if args.verify_only:
            verify_only(out, args.expected_sha)
        else:
            build(worktree, out, args.source_commit, doc)
        return 0
    except (ArtifactError, ValueError, OSError, json.JSONDecodeError, KeyError,
            subprocess.SubprocessError, tarfile.TarError) as error:
        print("DEV_ARTIFACT_FAIL: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
