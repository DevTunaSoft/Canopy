#!/usr/bin/env python3
"""Build and deterministically package the Canopy Classic native Plasma 6 baseline.

The tool is deliberately narrow: it consumes a source tree whose content is
pinned by SOURCE_ID.json (generated from an exact git commit by this same
tool), compiles the real Classic C++ target with CMake/Ninja, stages a Plasma
user-scope KPackage with byte-for-byte approved assets, writes an exact SHA-256
manifest and checks that two independent packagings are byte-identical.

Nothing here installs into a desktop, mutates a VM, changes approved artwork,
merges a branch or makes a release/visual-approval claim.

Example (on the Linux reference guest):
    python3 tools/native/build_baseline.py \
        --source /home/canopy/native_build_baseline/source \
        --source-sha ec910d7a7275296ecbc8b5e5c459d356205165d1 \
        --out /home/canopy/native_build_baseline/out
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from baseline_common import (
    APPROVED_WALLPAPER_SHA256,
    LEGACY_WALLPAPER_SHA256,
    PACKAGE_ID,
    PACKAGE_VERSION,
    SOURCE_COMMIT,
    WALLPAPER_NAME,
    canonical_sha256,
    check_manifest_pins,
    collect_files,
    is_hex40,
    make_sha256sums,
    path_string,
    sha256_file,
    write_deterministic_tarball,
)

TOOL_FILES = ("baseline_common.py", "build_baseline.py", "smoke_test.py",
              "guest_smoke.sh", "__init__.py")
TEMPLATES = ("metadata.json.template", "main.qml", "install.sh",
             "uninstall.sh", "verify.sh")


class BuildError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(command, *, cwd=None, env=None, timeout=1800):
    started = utc_now()
    completed = subprocess.run(
        [str(part) for part in command], cwd=str(cwd) if cwd else None,
        env=env, capture_output=True, text=True, errors="replace",
        timeout=timeout,
    )
    return {
        "command": [str(part) for part in command],
        "cwd": path_string(cwd) if cwd else None,
        "started_utc": started,
        "rc": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def command_text(command) -> str:
    return " ".join(str(part) if " " not in str(part) else '"%s"' % part
                    for part in command)


def write_source_id(source: Path, commit: str, tree: str, destination: Path) -> dict:
    """Write content identity of a source tree; SOURCE_ID.json is excluded."""
    source = Path(source).resolve()
    if not (is_hex40(commit) and is_hex40(tree)):
        raise BuildError("source id requires 40-hex commit and tree")
    files = {}
    for relative, path in collect_files(source):
        if relative == "SOURCE_ID.json":
            continue
        files[relative] = sha256_file(path)
    payload = {
        "schema": "canopy.native.source_id/1",
        "commit": commit.lower(),
        "tree": tree.lower(),
        "file_count": len(files),
        "files": files,
        "note": "content identity of the pinned source plus the native tooling; not an approval",
    }
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    return payload


def _verify_source(source: Path, source_sha: str, tree_sha: str | None) -> tuple[dict, list]:
    sidecar_path = source / "SOURCE_ID.json"
    if not sidecar_path.is_file():
        raise BuildError("missing SOURCE_ID.json; generate it with --emit-source-id")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    if sidecar.get("schema") != "canopy.native.source_id/1":
        raise BuildError("unsupported SOURCE_ID schema")
    if sidecar.get("commit") != source_sha.lower():
        raise BuildError("SOURCE_ID commit %r != requested %r"
                         % (sidecar.get("commit"), source_sha))
    if not is_hex40(sidecar.get("tree")):
        raise BuildError("SOURCE_ID tree is not a 40-hex SHA-1")
    if tree_sha is not None and sidecar["tree"].lower() != tree_sha.lower():
        raise BuildError("SOURCE_ID tree != --tree-sha")
    files = sidecar.get("files")
    if not isinstance(files, dict) or not files:
        raise BuildError("SOURCE_ID files must be a non-empty object")
    actual = {relative: sha256_file(path)
              for relative, path in collect_files(source)
              if relative != "SOURCE_ID.json"}
    if actual != files:
        missing = sorted(set(files) - set(actual))
        extra = sorted(set(actual) - set(files))
        changed = sorted(k for k in set(files) & set(actual) if files[k] != actual[k])
        raise BuildError("source content drift: missing=%s extra=%s changed=%s"
                         % (missing[:8], extra[:8], changed[:8]))
    if (source / ".git").exists():
        head = run(["git", "-C", str(source), "rev-parse", "HEAD"], timeout=60)
        tree = run(["git", "-C", str(source), "rev-parse", "HEAD^{tree}"], timeout=60)
        if head["rc"] or head["stdout"].strip().lower() != source_sha.lower():
            raise BuildError("git HEAD does not match the pinned source commit")
        if tree["rc"] or tree["stdout"].strip().lower() != sidecar["tree"].lower():
            raise BuildError("git tree does not match SOURCE_ID tree")
    gates = [
        ("source_commit_pinned", "PASS", sidecar["commit"]),
        ("source_tree_pinned", "PASS", sidecar["tree"]),
        ("source_files_byte_identical", "PASS", "%d files" % len(actual)),
    ]
    return sidecar, gates


def _verify_assets(source: Path) -> tuple[dict, list]:
    approved = source / "prototype/classic/assets/approved"
    manifest_path = approved / "manifest.json"
    if not manifest_path.is_file():
        raise BuildError("missing approved manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    icon_pins = check_manifest_pins(manifest, approved)
    wallpaper = approved / "wallpaper" / WALLPAPER_NAME
    if not wallpaper.is_file():
        raise BuildError("missing approved master wallpaper")
    wallpaper_sha = sha256_file(wallpaper)
    if wallpaper_sha != APPROVED_WALLPAPER_SHA256:
        raise BuildError("approved wallpaper SHA-256 mismatch: %s" % wallpaper_sha)
    legacy = approved / "wallpaper/canopy-wave-preview.png"
    if not legacy.is_file() or sha256_file(legacy) != LEGACY_WALLPAPER_SHA256:
        raise BuildError("legacy wave reference is not byte-identical")
    gates = [
        ("approved_icons_eight_exact", "PASS", "%d icons" % len(icon_pins)),
        ("approved_wallpaper_sha256", "PASS", wallpaper_sha),
        ("legacy_wave_asset_unmodified", "PASS", LEGACY_WALLPAPER_SHA256),
    ]
    return {"manifest": manifest, "icon_pins": icon_pins,
            "wallpaper_sha256": wallpaper_sha}, gates


def _stage(source: Path, tools: Path, out: Path, binary: Path,
           binary_sha: str, assets: dict, logs: list) -> Path:
    stage = out / "stage"
    if stage.exists():
        shutil.rmtree(stage)
    root = stage / PACKAGE_ID
    for directory in ("contents/ui", "contents/bin", "contents/approved/icons",
                      "contents/approved/wallpaper"):
        (root / directory).mkdir(parents=True, exist_ok=True)

    approved = source / "prototype/classic/assets/approved"
    template_text = (tools / "templates/metadata.json.template").read_text(encoding="utf-8")
    for token, value in {
        "@PACKAGE_VERSION@": PACKAGE_VERSION,
        "@SOURCE_SHA@": SOURCE_COMMIT,
        "@TREE_SHA@": assets["tree_sha"],
        "@BINARY_SHA@": binary_sha,
        "@WALLPAPER_SHA@": assets["wallpaper_sha256"],
    }.items():
        template_text = template_text.replace(token, value)
    metadata = json.loads(template_text)
    (root / "metadata.json").write_text(
        json.dumps(metadata, indent=4, sort_keys=True) + "\n", encoding="utf-8")

    shutil.copyfile(tools / "templates/main.qml", root / "contents/ui/main.qml")
    shutil.copyfile(binary, root / "contents/bin/canopy-classic-spike")
    os.chmod(root / "contents/bin/canopy-classic-spike", 0o755)
    shutil.copyfile(approved / "manifest.json", root / "contents/approved/manifest.json")
    for relative in sorted(assets["icon_pins"]):
        shutil.copyfile(approved / relative, root / "contents/approved" / relative)
    for name in (WALLPAPER_NAME, "canopy-wave-preview.png"):
        shutil.copyfile(approved / "wallpaper" / name,
                        root / "contents/approved/wallpaper" / name)
    for script in ("install.sh", "uninstall.sh", "verify.sh"):
        target = root / script
        shutil.copyfile(tools / "templates" / script, target)
        os.chmod(target, 0o755)
    (root / "SHA256SUMS").write_text(make_sha256sums(root), encoding="utf-8")
    logs.append({"step": "stage", "files": len(collect_files(root))})
    return root


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="native path of pinned source tree")
    parser.add_argument("--out", required=True, help="native scratch output directory")
    parser.add_argument("--source-sha", default=SOURCE_COMMIT,
                        help="exact git commit the source tree represents")
    parser.add_argument("--tree-sha", default=None, help="optional pinned git tree SHA-1")
    parser.add_argument("--cmake", default="cmake")
    parser.add_argument("--ninja", default="ninja")
    parser.add_argument("--emit-source-id", metavar="PATH",
                        help="write SOURCE_ID.json for --source and exit")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    out = Path(args.out).resolve()
    try:
        if args.emit_source_id:
            write_source_id(source, args.source_sha, args.tree_sha or SOURCE_COMMIT,
                            Path(args.emit_source_id))
            print("SOURCE_ID_EMITTED: %s" % path_string(Path(args.emit_source_id)))
            return 0

        if not is_hex40(args.source_sha) or args.source_sha.lower() != SOURCE_COMMIT:
            raise BuildError("--source-sha must be the pinned base commit %s"
                             % SOURCE_COMMIT)
        if not source.is_dir() or out == source or source in out.parents or out in source.parents:
            raise BuildError("--out must be a scratch directory outside --source")
        if not (source / "prototype/classic/CMakeLists.txt").is_file():
            raise BuildError("source lacks prototype/classic/CMakeLists.txt")
        tools = Path(__file__).resolve().parent
        for name in TOOL_FILES:
            candidate = tools / name
            if not candidate.is_file() or candidate.is_symlink():
                raise BuildError("missing or linked native tool file: %s" % name)
        for name in TEMPLATES:
            candidate = tools / "templates" / name
            if not candidate.is_file() or candidate.is_symlink():
                raise BuildError("missing or linked native template file: %s" % name)

        sidecar, gates = _verify_source(source, args.source_sha, args.tree_sha)
        assets, asset_gates = _verify_assets(source)
        gates.extend(asset_gates)
        assets["tree_sha"] = sidecar["tree"]

        logs: list = []
        build_dir = out / "build"
        if build_dir.exists():
            shutil.rmtree(build_dir)
        build_dir.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["SOURCE_DATE_EPOCH"] = "0"
        configure = run([args.cmake, "-S", source / "prototype/classic",
                         "-B", build_dir, "-G", "Ninja",
                         "-DCMAKE_BUILD_TYPE=Release"], env=env, timeout=600)
        (out / "configure.log").write_text(
            configure["stdout"] + configure["stderr"], encoding="utf-8")
        logs.append(configure)
        if configure["rc"] != 0:
            raise BuildError("cmake configure failed; see configure.log")
        compile_step = run([args.ninja, "-C", build_dir], env=env, timeout=1500)
        (out / "compile.log").write_text(
            compile_step["stdout"] + compile_step["stderr"], encoding="utf-8")
        logs.append(compile_step)
        if compile_step["rc"] != 0:
            raise BuildError("ninja compile failed; see compile.log")
        binary = build_dir / "canopy-classic-spike"
        if not binary.is_file() or binary.is_symlink():
            raise BuildError("compiled binary missing or linked")
        binary_sha = sha256_file(binary)
        gates.append(("compiled_binary_present", "PASS", binary_sha))

        root = _stage(source, tools, out, binary, binary_sha, assets, logs)
        dist = out / "dist"
        if dist.exists():
            shutil.rmtree(dist)
        dist.mkdir(parents=True, exist_ok=True)
        archive_name = "%s-%s.tar.gz" % (PACKAGE_ID, PACKAGE_VERSION)
        archive = dist / archive_name
        archive_sha = write_deterministic_tarball(root, archive)

        second = out / "rebuild-check" / archive_name
        second_sha = write_deterministic_tarball(root, second)
        if archive_sha != second_sha:
            raise BuildError("package is not byte-identical on rebuild: %s != %s"
                             % (archive_sha, second_sha))
        (out / "rebuild-check/sha256").write_text(second_sha + "\n", encoding="utf-8")
        gates.append(("package_rebuild_byte_identical", "PASS", archive_sha))

        sums = {}
        for line in (root / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
            digest, name = line.split("  ", 1)
            sums[name] = digest
        members = [{"path": name, "sha256": sums[name],
                    "bytes": (root / name).stat().st_size} for name in sorted(sums)]
        if any(canonical_sha256(item["sha256"]) != item["sha256"] for item in members):
            raise BuildError("non-canonical SHA in package SHA256SUMS")

        manifest = {
            "schema": "canopy.native.build_manifest/1",
            "artifact": "canopy-classic-native-plasma6-development-baseline",
            "verdict": "PASS",
            "scope": "DEVELOPMENT_BASELINE_ONLY;NO_RELEASE;NO_VISUAL_APPROVAL;NO_MERGE",
            "generated_utc": utc_now(),
            "host": platform.platform(),
            "source": {
                "commit": sidecar["commit"], "tree": sidecar["tree"],
                "file_count": sidecar["file_count"],
                "source_id_sha256": sha256_file(source / "SOURCE_ID.json"),
            },
            "approved_assets": {
                "wallpaper": {"path": WALLPAPER_NAME,
                              "sha256": assets["wallpaper_sha256"]},
                "icons": assets["icon_pins"],
            },
            "binary": {"path": "contents/bin/canopy-classic-spike",
                       "sha256": binary_sha},
            "package": {
                "id": PACKAGE_ID, "version": PACKAGE_VERSION,
                "structure": "Plasma/Applet", "plasma_api_minimum": "6.0",
                "archive": archive_name, "archive_sha256": archive_sha,
                "archive_bytes": archive.stat().st_size,
                "rebuild_sha256": second_sha,
                "determinism": {"mtime": 0, "uid_gid": 0, "uname_gname": "empty",
                                "tar_format": "GNU", "gzip_mtime": 0,
                                "gzip_filename": "empty", "member_order": "sorted POSIX",
                                "rebuild_byte_identical": True},
                "members": members,
            },
            "gates": gates,
            "commands": {
                "build": command_text([args.cmake, "-S", source / "prototype/classic",
                                       "-B", build_dir, "-G", "Ninja"]),
                "compile": command_text([args.ninja, "-C", build_dir]),
                "install": "install.sh <archive> <state-dir>",
                "verify": "verify.sh <state-dir>",
                "uninstall": "uninstall.sh <state-dir>",
            },
            "note": "SHA-256 values are content identities; SOURCE commit/tree are git SHA-1 identities.",
        }
        (out / "MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        out_sums = ["%s  MANIFEST.json" % sha256_file(out / "MANIFEST.json"),
                    "%s  dist/%s" % (archive_sha, archive_name),
                    "%s  configure.log" % sha256_file(out / "configure.log"),
                    "%s  compile.log" % sha256_file(out / "compile.log")]
        (out / "SHA256SUMS").write_text("\n".join(out_sums) + "\n", encoding="utf-8")
        result = {"verdict": "PASS", "manifest": path_string(out / "MANIFEST.json"),
                  "archive_sha256": archive_sha, "binary_sha256": binary_sha,
                  "wallpaper_sha256": assets["wallpaper_sha256"], "gates": gates}
        (out / "BUILD_RESULT.json").write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        for gate in gates:
            print("GATE|%s|%s|%s" % gate)
        print("BUILD_PASS: archive=%s sha256=%s" % (archive_name, archive_sha))
        return 0
    except (BuildError, ValueError, OSError, json.JSONDecodeError,
            subprocess.SubprocessError) as error:
        print("BUILD_FAIL: %s" % error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
