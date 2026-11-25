#!/usr/bin/env python3
"""One deterministic Classic build/verification entry point (MSYS2 UCRT64).

Builds the exact pinned integration tip twice from a clean CMake/Ninja tree,
captures real Qt self-test output and three screenshot resolutions, writes a
self-contained evidence bundle with SHA-256 manifest, then runs the fail-closed
gate from tools/qa/classic_build_gate.py.

    python tools/build/classic_release_build.py \
        --source C:/Users/X1/Projects/Canopy \
        --out C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-classic-release

No network access, no main merge, no edits to source files, and no changes
outside the scratch --out directory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SOURCE_SHA = "b31c995a650202b66c08064a7cc3b7b4f0609d2d"
UCRT_BIN = "C:/msys64/ucrt64/bin"
PACMAN = "C:/msys64/usr/bin/pacman.exe"
EXE = {
    "cmake": UCRT_BIN + "/cmake.exe",
    "ninja": UCRT_BIN + "/ninja.exe",
    "qmake6": UCRT_BIN + "/qmake6.exe",
    "g++": UCRT_BIN + "/g++.exe",
}
SIZES = ((1920, 1080), (1200, 750), (760, 500))
REQUIRED_SHOT_MARKERS = (
    "CANOPY_APPROVED_ART_VERIFIED",
    "SELF_TEST_PASS: all eight exact approved dock PNGs loaded",
    "SELF_TEST_PASS: dock icons horizontally/vertically centred",
    "SELF_TEST_PASS: desktop chrome geometry",
    "SELF_TEST_PASS: nonuniform window screenshot captured",
)


def native(path: Path) -> str:
    return str(path).replace("\\", "/")


def run(command, *, env, cwd=None, timeout=900):
    started = time.time()
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                               text=True, timeout=timeout)
    return completed, round(time.time() - started, 2)


def command_line(command) -> str:
    return " ".join(str(part) if " " not in str(part) else '"%s"' % part
                    for part in command)


def first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True,
                        help="native path of the integration-tip worktree")
    parser.add_argument("--out", required=True,
                        help="native scratch path for build and evidence bundle")
    args = parser.parse_args(argv)

    source = Path(args.source).resolve()
    out = Path(args.out).resolve()
    if out == Path(out.anchor) or source == Path(source.anchor):
        print("BUILD_FAIL: source or out is a filesystem root")
        return 1
    if out == source or out in source.parents or source in out.parents:
        print("BUILD_FAIL: out must be scratch, outside the source worktree")
        return 1
    if not (source / "prototype/classic/CMakeLists.txt").is_file():
        print("BUILD_FAIL: source lacks prototype/classic/CMakeLists.txt")
        return 1

    head = run(["git", "-C", native(source), "rev-parse", "HEAD"],
               env=os.environ.copy(), timeout=60)[0]
    if head.returncode != 0 or head.stdout.strip() != SOURCE_SHA:
        print("BUILD_FAIL: source HEAD is %r, expected %s"
              % (head.stdout.strip(), SOURCE_SHA))
        return 1
    tree = run(["git", "-C", native(source), "rev-parse", "HEAD^{tree}"],
               env=os.environ.copy(), timeout=60)[0]
    tracked = run(["git", "-C", native(source), "diff", "--quiet"],
                  env=os.environ.copy(), timeout=60)[0]
    staged = run(["git", "-C", native(source), "diff", "--cached", "--quiet"],
                 env=os.environ.copy(), timeout=60)[0]
    if tracked.returncode or staged.returncode:
        print("BUILD_FAIL: source has modified tracked or staged files")
        return 1

    evidence = out / "evidence"
    build = out / "build"
    (evidence / "binary").mkdir(parents=True, exist_ok=True)
    (evidence / "screenshots").mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = UCRT_BIN + os.pathsep + env.get("PATH", "")
    env.update({
        "MSYSTEM": "UCRT64",
        "SOURCE_DATE_EPOCH": "0",
        "TZ": "UTC",
        "LANG": "C",
        "QT_QPA_PLATFORM": "offscreen",
        "QT_QUICK_BACKEND": "software",
        "QT_QUICK_CONTROLS_STYLE": "Basic",
        "QT_FORCE_STDERR_LOGGING": "1",
        "LIBGL_ALWAYS_SOFTWARE": "1",
    })

    def tool(name, args=()):
        completed, _ = run([EXE[name], *args], env=env, timeout=120)
        if completed.returncode != 0:
            print("BUILD_FAIL: tool query failed: %s" % name)
            return "unavailable"
        return (first_line(completed.stdout) or "unavailable").strip()

    pacman_result, _ = run([PACMAN, "-Q", "msys2-runtime"], env=env, timeout=60)
    toolchain = {
        "cmake": tool("cmake", ["--version"]),
        "ninja": tool("ninja", ["--version"]),
        "qt_version": tool("qmake6", ["-query", "QT_VERSION"]),
        "qt_install_prefix": tool("qmake6", ["-query", "QT_INSTALL_PREFIX"]),
        "qt_install_qml": tool("qmake6", ["-query", "QT_INSTALL_QML"]),
        "compiler": tool("g++", ["--version"]),
        "msys_runtime": (first_line(pacman_result.stdout) if pacman_result.returncode == 0
                         else "unavailable"),
        "source_date_epoch": env["SOURCE_DATE_EPOCH"],
        "qt_qpa_platform": env["QT_QPA_PLATFORM"],
        "qt_quick_backend": env["QT_QUICK_BACKEND"],
        "qt_quick_controls_style": env["QT_QUICK_CONTROLS_STYLE"],
        "qt_force_stderr_logging": env["QT_FORCE_STDERR_LOGGING"],
    }
    (evidence / "toolchain.txt").write_text(
        "\n".join("%s: %s" % (key, value) for key, value in toolchain.items()) + "\n",
        encoding="utf-8")
    print("TOOLCHAIN cmake=%s ninja=%s qt=%s compiler=%s"
          % (toolchain["cmake"], toolchain["ninja"], toolchain["qt_version"],
             toolchain["compiler"]))

    def display(command):
        return command_line(command).replace(EXE["cmake"], "cmake")

    commands = []
    build_hashes = []
    binary_copy = evidence / "binary/canopy-classic-spike.exe"
    for pass_number in (1, 2):
        shutil.rmtree(build, ignore_errors=True)
        build.mkdir(parents=True)
        configure = [EXE["cmake"], "-S", native(source / "prototype/classic"),
                     "-B", native(build), "-G", "Ninja",
                     "-DCMAKE_BUILD_TYPE=Release", "-Wno-author"]
        compile_command = [EXE["cmake"], "--build", native(build), "--parallel", "2"]
        for label, command, timeout in (("configure", configure, 300),
                                        ("build", compile_command, 900)):
            commands.append(display(command))
            completed, elapsed = run(command, env=env, timeout=timeout)
            (evidence / ("%s-pass%d.log" % (label, pass_number))).write_text(
                completed.stdout + completed.stderr, encoding="utf-8")
            print("BUILD pass%d %s rc=%d seconds=%s" %
                  (pass_number, label, completed.returncode, elapsed))
            if completed.returncode != 0:
                print("BUILD_FAIL: %s pass %d failed" % (label, pass_number))
                return 1
            if label == "configure":
                # Qt rcc embeds each resource file's mtime. CMake regenerates
                # qmldir at configure time, so without pinning it the binary
                # differs between otherwise identical clean builds.
                for qmldir in build.rglob("qmldir"):
                    os.utime(qmldir, (0, 0))
                commands.append("# normalize generated qmldir mtimes to SOURCE_DATE_EPOCH=0 before rcc")
        built = build / "canopy-classic-spike.exe"
        if not built.is_file():
            print("BUILD_FAIL: binary missing after pass %d" % pass_number)
            return 1
        build_hashes.append(sha256(built))
        shutil.copy2(built, out / ("pass%d-canopy-classic-spike.exe" % pass_number))
        shutil.copy2(built, binary_copy)
    if build_hashes[0] != build_hashes[1]:
        print("BUILD_FAIL: clean rebuild was not byte-identical: %s vs %s"
              % tuple(build_hashes))
        return 1
    binary_sha = build_hashes[1]
    print("BINARY sha256=%s size=%d reproducible_clean_rebuilds=2"
          % (binary_sha, binary_copy.stat().st_size))

    art = source / "prototype/classic/assets/approved"
    capability_command = [native(binary_copy), "--self-test-system-apps-capability"]
    optin_command = [native(binary_copy), "--enable-system-apps", "--self-test-system-apps"]
    selftests = []
    for name, command, required in (
            ("capability", capability_command, ("CANOPY_GIO_DISABLED",)),
            ("optin", optin_command, ("SYSTEM_APP_LAUNCH_TEST_PASS",))):
        commands.append(command_line(command))
        completed, elapsed = run(command, env=env, cwd=native(out), timeout=120)
        text = completed.stdout + completed.stderr
        log_name = "selftest-capability.log" if name == "capability" else "selftest-optin-refusal.log"
        (evidence / log_name).write_text(text, encoding="utf-8")
        ok = (completed.returncode == 0
              and all(marker in text for marker in required)
              and "FAIL" not in text)
        selftests.append({"name": name, "rc": completed.returncode,
                          "seconds": elapsed, "log": log_name, "pass": ok})
        print("SELFTEST %s rc=%d pass=%s" % (name, completed.returncode, ok))
        if not ok:
            print("BUILD_FAIL: %s self-test failed" % name)
            return 1

    screenshots = []
    for width, height in SIZES:
        size = "%dx%d" % (width, height)
        shot_rel = "screenshots/classic-%s.png" % size
        log_rel = "selftest-%s.log" % size
        command = [native(binary_copy), "--approved-art-dir", native(art),
                   "--self-test-approved", "--self-test-size", size,
                   "--self-test-screenshot", native(evidence / shot_rel)]
        commands.append(command_line(command))
        completed, elapsed = run(command, env=env, cwd=native(out), timeout=150)
        text = completed.stdout + completed.stderr
        (evidence / log_rel).write_text(text, encoding="utf-8")
        shot_path = evidence / shot_rel
        required = REQUIRED_SHOT_MARKERS + (
            "SELF_TEST_PASS: desktop chrome geometry QSize(%d, %d)" % (width, height),)
        ok = (completed.returncode == 0 and shot_path.is_file()
              and all(marker in text for marker in required)
              and "SELF_TEST_FAIL" not in text)
        print("SELFTEST screenshot %s rc=%d pass=%s seconds=%s" %
              (size, completed.returncode, ok, elapsed))
        if not ok:
            print("BUILD_FAIL: screenshot self-test failed at %s" % size)
            return 1
        screenshots.append({
            "path": shot_rel, "log": log_rel, "width": width, "height": height,
            "sha256": sha256(shot_path), "rc": completed.returncode,
            "seconds": elapsed, "pass": ok,
        })

    (evidence / "commands.txt").write_text("\n".join(commands) + "\n", encoding="utf-8")
    bundle = {
        "schema_version": 1,
        "source_sha": SOURCE_SHA,
        "source_tree_sha": tree.stdout.strip(),
        "source_worktree_tracked_clean": True,
        "artifact": "Canopy Classic spike at pinned integration tip",
        "toolchain": toolchain,
        "binary_sha256": binary_sha,
        "binary_size": binary_copy.stat().st_size,
        "binary_relpath": "binary/canopy-classic-spike.exe",
        "reproducibility": {
            "source_date_epoch": "0",
            "clean_builds": 2,
            "build_hashes": build_hashes,
            "byte_identical_rebuild": True,
            "qmldir_mtime_epoch": 0,
            "mtime_normalization": "generated qmldir files set to epoch 0 after each configure",
        },
        "commands": commands,
        "selftests": selftests,
        "screenshots": screenshots,
        "screenshot_hash_policy": (
            "Per-run SHA-256 is recorded in the manifest; pixel bytes are captured "
            "from a live clock-bearing Qt scene and are not pinned across runs. "
            "The gate pins dimensions, PNG structure, visible variation and markers."
        ),
        "platform_limitations": [
            "Windows UCRT64 has no gio-unix-2.0: native app launching compiles as a disabled fallback.",
            "Offscreen Qt platform and software Quick backend are used; this is not a Mint session or compositor test.",
            "Visual approval, installer behaviour and five-minute idle CPU/PSS measurement remain separate gates.",
        ],
    }
    (evidence / "evidence.json").write_text(
        json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    qa_dir = source / "tools/qa"
    sys.path.insert(0, native(qa_dir))
    import classic_build_gate as gate
    manifest = gate.write_manifest(evidence, bundle)
    print("MANIFEST entries=%d" % len(manifest))
    return gate.verify(evidence, SOURCE_SHA)


if __name__ == "__main__":
    sys.exit(main())
