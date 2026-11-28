#!/usr/bin/env python3
"""Build the allowlist-patched Classic launcher in guest scratch on Canopy-Test-Plasma6.

No repository, PR, branch, package, setting, desktop entry or VM control mutation.
All guest writes are confined to /home/canopy/native_terminal_launch_20261127.
"""
import os
import shlex
import subprocess
import sys
import time

SCRATCH = "C:/Users/X1/AppData/Local/hermes/cache/scratch"
KEY = SCRATCH + "/g1_ubuntu_evidence/ssh/g1_ed25519"
LOCAL_CPP = ("C:/Users/X1/AppData/Local/hermes/cache/scratch/"
             "wt-native-terminal-launch-20261127/prototype/classic/SystemAppLauncher.cpp")
HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "build_guest.log")
GUEST = "/home/canopy/native_terminal_launch_20261127"
SSH = ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "-p", "2223", "canopy@127.0.0.1"]
SCP = ["scp", "-i", KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-P", "2223"]


def stamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def run(label, cmd, timeout=600):
    printable = cmd if isinstance(cmd, str) else " ".join(shlex.quote(x) for x in cmd)
    # String commands are remote shell commands; argv lists are local tools
    # (ssh/scp) that already carry their own remote command/arguments.
    argv = SSH + [cmd] if isinstance(cmd, str) else cmd
    p = subprocess.run(argv, capture_output=True, timeout=timeout)
    out = (p.stdout or b"").decode("utf-8", "replace")
    err = (p.stderr or b"").decode("utf-8", "replace")
    text = ("\n=== %s [%s] rc=%d ===\n$ %s\n%s%s\n"
            % (label, stamp(), p.returncode, printable, out, err))
    with open(LOG, "a", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(text)
    if p.returncode:
        raise SystemExit("%s failed rc=%d" % (label, p.returncode))
    return out


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("prepare", "build", "compile"):
        raise SystemExit("usage: build_guest.py prepare|build|compile")
    phase = sys.argv[1]
    do_build = False
    if phase == "prepare":
        run("guest_stage_mkdir",
            "mkdir -p %s && test ! -e %s/src && cp -a "
            "/home/canopy/pr728_build_39a9fd/src %s/src && echo STAGE_COPIED"
            % (GUEST, GUEST, GUEST), timeout=240)
        run("base_source_sha",
            "sha256sum %s/src/prototype/classic/SystemAppLauncher.cpp" % GUEST)
    elif phase == "compile":
        out = run("patched_source_sha",
            "for i in 1 2 3 4 5; do out=$(sha256sum "
            "%s/src/prototype/classic/SystemAppLauncher.cpp 2>&1); "
            "case \"$out\" in b397916b*) echo \"$out\"; exit 0;; esac; sleep 2; "
            "done; echo \"$out\"; exit 1" % GUEST)
        if "b397916b6e2b2dc2664972722a7a77185d80be7f52bc28325d3fc62f816e6a03" not in out:
            raise SystemExit("patched source SHA mismatch")
        do_build = True
    else:
        run("scp_patched_source", SCP + [LOCAL_CPP,
            "canopy@127.0.0.1:" + GUEST + "/src/prototype/classic/SystemAppLauncher.cpp"],
            timeout=120)
        out = run("patched_source_sha",
                  "sha256sum %s/src/prototype/classic/SystemAppLauncher.cpp" % GUEST)
        if "b397916b6e2b2dc2664972722a7a77185d80be7f52bc28325d3fc62f816e6a03" not in out:
            raise SystemExit("patched source SHA mismatch")
        do_build = True
    if do_build:
        run("cmake_configure",
            "rm -rf %s/build && cmake -S %s/src/prototype/classic -B %s/build -G Ninja "
            "-DCMAKE_BUILD_TYPE=Release -Wno-dev"
            % (GUEST, GUEST, GUEST), timeout=300)
        run("cmake_build", "cmake --build %s/build --parallel 2" % GUEST, timeout=900)
        run("binary_and_capability",
            "sha256sum %s/build/canopy-classic-spike; "
            "%s/build/canopy-classic-spike --self-test-system-apps-capability; "
            "echo CAPABILITY_RC=$?"
            % (GUEST, GUEST), timeout=180)


if __name__ == "__main__":
    main()
