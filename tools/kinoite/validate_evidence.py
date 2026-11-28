#!/usr/bin/env python3
"""Deterministic evidence gate for the Kinoite foundation validation.

Runs on the host (Windows/MSYS). Verifies:
  * every official upstream source was fetched with HTTP 200 and retains its digest;
  * each load-bearing claim is backed by a verbatim (whitespace-normalized)
    quote in the fetched source text;
  * the Canopy user-level planner really emitted a dry-run plan with no
    privileged/system/session writes (host-side execution, NOT Kinoite runtime);
  * no Fedora Kinoite runtime is available here, so all native runtime checks
    are reported NOT_RUN / BLOCKED rather than PASS.

Outputs scratch/kinoite_validation/evidence_matrix.{json,md} and SHA256SUMS.txt.
This is a static-evidence gate, not a Fedora Kinoite acceptance gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

QUOTE_CHECKS = [
    ("E01", "Official deployment path", ["fedora_kinoite_guide", "fedora_installation", "fedora_download"], [
        ("fedora_kinoite_guide", "Fedora Kinoite is a variant of Fedora KDE Plasma Desktop"),
        ("fedora_installation", "We recommend using Fedora Media Writer to make a bootable USB media to install a Fedora Atomic Desktop."),
        ("fedora_download", "Download Fedora Kinoite 45"),
    ]),
    ("E02", "Atomic update commands", ["fedora_updates_rollbacks", "rpm_ostree_handbook"], [
        ("fedora_updates_rollbacks", "$ rpm-ostree upgrade"),
        ("fedora_updates_rollbacks", "$ rpm-ostree upgrade --check"),
        ("rpm_ostree_handbook", "# rpm-ostree status"),
    ]),
    ("E03", "Rollback and pinning commands", ["fedora_updates_rollbacks", "rpm_ostree_handbook"], [
        ("fedora_updates_rollbacks", "Permanent rollbacks: to permanently switch back to the previous deployment, use the rpm-ostree rollback command."),
        ("fedora_updates_rollbacks", "By default, OSTree only keeps the two most recent deployments."),
        ("rpm_ostree_handbook", "# rpm-ostree rollback"),
        ("rpm_ostree_handbook", "# rpm-ostree deploy <version>"),
    ]),
    ("E04", "Major upgrade / rebase path", ["fedora_updates_rollbacks", "rpm_ostree_handbook"], [
        ("fedora_updates_rollbacks", "$ rpm-ostree rebase fedora:fedora/45/x86_64/silverblue"),
        ("fedora_updates_rollbacks", "All your flatpak apps and files in the /home directory will remain persistent between rebases."),
        ("rpm_ostree_handbook", "Like every other rpm-ostree operation, All layered packages and local state will be carried across."),
    ]),
    ("E05", "Kernel/driver and security update path", ["fedora_project_kinoite", "fedora_troubleshooting", "fedora_getting_started"], [
        ("fedora_project_kinoite", "Each version is updated for approximately 13 months, and each update takes effect on your next reboot, keeping your system consistent."),
        ("fedora_troubleshooting", "# rpm-ostree install kmod-nvidia xorg-x11-drv-nvidia"),
        ("fedora_troubleshooting", "# rpm-ostree kargs --append=rd.driver.blacklist=nouveau,nova-core"),
        ("fedora_getting_started", "Good examples of packages to be layered would be:"),
    ]),
    ("E06", "Read-only core behavior", ["fedora_technical", "rpm_ostree_handbook", "ostree_adapting"], [
        ("fedora_technical", "On Fedora Atomic Desktops, the root filesystem (/) is mounted read-only."),
        ("fedora_technical", "The /usr directory and everything below it is also read-only."),
        ("fedora_technical", "The /etc and /var directories are respectively used to store configuration files and runtime state and are thus writable."),
        ("rpm_ostree_handbook", "The only writable directories are /etc and /var. In particular, /usr has a read-only bind mount at all times."),
        ("ostree_adapting", "/home \u2192 /var/home"),
    ]),
    ("E07", "Stock Plasma fallback path", ["fedora_project_kinoite", "sddm_theming", "kde_autostart"], [
        ("fedora_project_kinoite", "Includes the latest versions of the modern and modular desktop, built by the KDE community."),
        ("sddm_theming", "This information is gathered by parsing the desktop files in the `/usr/share/xsessions` directory."),
        ("kde_autostart", "The program scans $HOME/.config/autostart/ for applications and login scripts"),
    ]),
    ("E08", "User-level Canopy extension compatibility", ["systemd_unit", "fedora_technical", "flatpak_using"], [
        ("systemd_unit", "~/.config/systemd/user/*"),
        ("systemd_unit", "$XDG_DATA_HOME/systemd/user or $HOME/.local/share/systemd/user"),
        ("fedora_technical", "/home \u2192 /var/home"),
        ("flatpak_using", "Flatpak commands can be run either system-wide or per-user."),
    ]),
    ("E10", "Flatpak / Flathub independent app updates", ["flatpak_using", "fedora_getting_started"], [
        ("flatpak_using", "$ flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo"),
        ("flatpak_using", "$ flatpak update"),
        ("fedora_getting_started", "Flatpak is the primary way that apps can be installed on Fedora Atomic Desktops."),
    ]),
    ("E11", "DNF path without writing the base OS", ["fedora_toolbox", "fedora_dnf", "fedora_faq"], [
        ("fedora_toolbox", "$ toolbox create"),
        ("fedora_toolbox", "$ toolbox enter"),
        ("fedora_toolbox", "Once inside the toolbox, you can access common command line tools, and install new ones using a package manager (e.g., DNF on Fedora)."),
        ("fedora_dnf", "DNF applies to standard Fedora editions. On image-based variants such as the Fedora Atomic Desktops and Fedora CoreOS, package management works differently."),
    ]),
    ("E12", "No custom image maintenance required", ["fedora_getting_started", "rpm_ostree_handbook", "fedora_project_kinoite"], [
        ("fedora_getting_started", "It’s generally expected that you use package layering sparingly, and use Flatpak and Toolbx whenever possible."),
        ("fedora_project_kinoite", "Graphical applications are installed via Flatpak, and keep themselves separate from the base system."),
        ("rpm_ostree_handbook", "These additional \u201clayered\u201d packages are persistent across upgrades, rebases, and deploys"),
    ]),
]

RUNTIME_COMMANDS = [
    "rpm-ostree status --verbose",
    "findmnt -no OPTIONS /usr",
    "rpm-ostree upgrade --check",
    "sudo rpm-ostree upgrade && sudo systemctl reboot",
    "rpm-ostree rollback && sudo systemctl reboot",
    "sudo rpm-ostree deploy 45.YYYYMMDD.N",
    "flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo",
    "flatpak update",
    "toolbox create && toolbox enter && sudo dnf upgrade",
    "python3 tools/register_classic_preview.py install --dry-run --binary <path>",
]


def norm(text: str) -> str:
    return " ".join(text.split())


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: pathlib.Path) -> dict:
    raw = path.read_text(encoding="utf-8").strip()
    prefix = "CANOPY_INSTALL_RECOVERY: "
    if not raw.startswith(prefix):
        raise AssertionError(f"{path.name}: missing planner prefix")
    return json.loads(raw[len(prefix):])


def probe_runtime() -> dict:
    missing = [name for name in ("rpm-ostree", "ostree", "flatpak", "podman", "docker", "toolbox") if shutil.which(name) is None]
    wsl = ""
    try:
        p = subprocess.run(["wsl.exe", "-l", "-v"], capture_output=True, timeout=30)
        wsl = (p.stdout + p.stderr).decode("utf-8", errors="replace").replace("\x00", "").strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        wsl = f"PROBE_ERROR: {exc}"
    vbox = "VBoxManage ABSENT"
    exe = pathlib.Path("C:/Program Files/Oracle/VirtualBox/VBoxManage.exe")
    if exe.exists():
        try:
            p = subprocess.run([str(exe), "list", "vms"], capture_output=True, timeout=30)
            vbox = (p.stdout + p.stderr).decode("utf-8", errors="replace").strip()
        except (OSError, subprocess.TimeoutExpired) as exc:
            vbox = f"PROBE_ERROR: {exc}"
    kinoite_vm = "kinoite" in vbox.lower()
    return {
        "class": "NATIVE RUNTIME (host probe)",
        "missing_cli": missing,
        "wsl_output": wsl,
        "vbox_vms": vbox,
        "kinoite_vm_present": kinoite_vm,
        "fedora_kinoite_runtime_available": False,
        "reason": "No rpm-ostree/ostree/flatpak/toolbox CLI, no WSL distributions, no Kinoite VM. Shared Ubuntu Plasma VM is not a disposable Kinoite environment.",
    }


def scan_lacos_dependencies(root: pathlib.Path) -> dict:
    p = subprocess.run(
        ["git", "-C", str(root), "ls-files", "canopy_features", "tools", "prototype"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if p.returncode != 0:
        raise AssertionError(f"git ls-files failed: {p.stderr.strip()}")
    files = [rel for rel in p.stdout.splitlines() if not rel.startswith("tools/kinoite/")]
    hits = []
    for rel in files:
        f = root / rel
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if re.search(r"\blacos\b", line, re.IGNORECASE):
                hits.append(f"{rel}:{i}")
    return {"files_scanned": len(files), "code_hits": hits, "count": len(hits), "excluded": "tools/kinoite/** (validation tooling, not product code)"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--worktree", required=True)
    ap.add_argument("--out", required=True, help="scratch/kinoite_validation directory")
    ap.add_argument(
        "--exact-head",
        default=None,
        help="Explicit final head SHA to label the evidence with. Defaults to git HEAD.",
    )
    ap.add_argument(
        "--reviewed-head",
        default=None,
        help="Reviewed head SHA retained as provenance only; never used as exact_head.",
    )
    args = ap.parse_args()
    root = pathlib.Path(args.worktree).resolve()
    out = pathlib.Path(args.out).resolve()

    # Planner stdout is captured through MSYS and can arrive with CRLF; normalize
    # before hashing so digests are host-independent.
    for name in ("planner_install.json", "planner_snapshot.json", "planner_install.err", "planner_snapshot.err"):
        p = out / name
        if p.exists():
            normalized = p.read_bytes().replace(b"\r\n", b"\n")
            p.write_bytes(normalized)

    src_report = json.loads((out / "sources.json").read_text(encoding="utf-8"))
    src_by_key = {r["key"]: r for r in src_report["sources"]}
    text_cache: dict[str, str] = {}
    for key, row in src_by_key.items():
        if row.get("http_code") != 200:
            raise AssertionError(f"{key}: HTTP {row.get('http_code')}")
        p = pathlib.Path(row["text_path"])
        if sha256(p) != row["text_sha256"]:
            raise AssertionError(f"{key}: text digest drift")
        text_cache[key] = norm(p.read_text(encoding="utf-8"))

    rows = []
    for cid, title, sources, quotes in QUOTE_CHECKS:
        unmatched = []
        proof = []
        for key, quote in quotes:
            q = norm(quote)
            if q not in text_cache.get(key, ""):
                unmatched.append({"source": key, "quote": quote})
            else:
                proof.append({"source": key, "source_url": src_by_key[key]["final_url"], "quote": quote,
                              "text_sha256": src_by_key[key]["text_sha256"]})
        rows.append({
            "id": cid,
            "claim": title,
            "evidence_class": "STATIC SOURCE ONLY",
            "verdict": "PASS" if not unmatched else "FAIL",
            "source_keys": sources,
            "proof": proof,
            "unmatched": unmatched,
            "note": "Source text proves documentation/upstream behavior only; it is not a native runtime result.",
        })

    runtime = probe_runtime()

    plan = load_plan(out / "planner_install.json")
    snapshot = load_plan(out / "planner_snapshot.json")
    planner_expectations = {
        "dry_run": plan.get("dry_run") is True,
        "performs_changes": plan.get("performs_changes") is False,
        "privileged": plan.get("privileged") is False,
        "session_changes_empty": plan.get("session_changes") == [],
        "system_paths_written_empty": plan.get("system_paths_written") == [],
        "guest_execution_not_run": plan.get("guest_execution") == "NOT_RUN",
        "snapshot_safe": snapshot.get("safe") is True,
        "snapshot_session_probes_absent": all(
            v.get("kind") == "ABSENT" and v.get("safe") is True
            for v in (snapshot.get("session_entry_probes") or {}).values()
        ),
    }
    local_row = {
        "id": "E09",
        "claim": "User-level Canopy extension and operation without LacOS infrastructure (host-side plan and source scan)",
        "evidence_class": "NATIVE RUNTIME (Windows host, NOT Kinoite)",
        "verdict": "PASS" if all(planner_expectations.values()) else "FAIL",
        "planner_expectations": planner_expectations,
        "planner_sources": {
            "planner_install.json": sha256(out / "planner_install.json"),
            "planner_snapshot.json": sha256(out / "planner_snapshot.json"),
        },
        "local_planner_commands": [
            "python3 -m canopy_features.mint.install_recovery_plan --home <scratch>/empty_home --action snapshot",
            "python3 -m canopy_features.mint.install_recovery_plan --home <scratch>/empty_home --action install --binary <scratch>/canopy-classic-demo",
        ],
        "boundary": "Executed on Windows/MSYS against pure-Python planner only. No Kinoite session, compositor or systemd user manager was exercised.",
    }
    lacos_scan = scan_lacos_dependencies(root)
    local_row["lacos_dependency_scan"] = lacos_scan
    if lacos_scan["count"]:
        local_row["verdict"] = "FAIL"
    rows.append(local_row)

    runtime_row = {
        "id": "E13",
        "claim": "Native Kinoite runtime verification of atomic update/rollback, read-only mount, Plasma fallback, Flatpak/DNF updates",
        "evidence_class": "NATIVE RUNTIME",
        "verdict": "NOT_RUN",
        "blocker": "BLOCKED: no disposable Fedora Kinoite environment on this host",
        "probe": runtime,
        "commands_to_run_in_a_disposable_kinoite_vm": RUNTIME_COMMANDS,
    }
    rows.append(runtime_row)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    head = args.exact_head or subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    report = {
        "generated_utc": timestamp,
        "exact_head": head,
        "scope": "STATIC SOURCE ONLY evidence gate plus host-side planner execution; no native Kinoite runtime",
        "source_count": len(src_by_key),
        "sources_ok": src_report["ok"],
        "checks": rows,
        "overall_static_verdict": "PASS" if all(r["verdict"] == "PASS" for r in rows if r["id"] != "E13") else "FAIL",
        "native_runtime_verdict": "NOT_RUN",
    }
    if args.reviewed_head:
        ordered = {}
        for key, value in report.items():
            ordered[key] = value
            if key == "exact_head":
                ordered["reviewed_head"] = args.reviewed_head
        report = ordered
    (out / "evidence_matrix.json").write_bytes(
        (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    )

    md = [
        "# Kinoite validation evidence matrix",
        "",
        f"Exact head: `{head}`."
        + (f" Reviewed head (provenance only): `{args.reviewed_head}`." if args.reviewed_head else "")
        + f" Generated: {timestamp}.",
        "",
        "| ID | Check | Evidence class | Verdict |",
        "|---|---|---|---|",
    ]
    for r in rows:
        md.append(f"| {r['id']} | {r['claim']} | {r['evidence_class']} | {r['verdict']} |")
    md += [
        "",
        f"Static/host gate: {report['overall_static_verdict']}. Native Kinoite runtime: {report['native_runtime_verdict']} "
        f"({runtime_row['blocker']}).",
        "",
        "Sources are limited to fedoraproject.org, docs.fedoraproject.org, docs.flatpak.org, freedesktop.org, "
        "docs.kde.org, ostreedev.github.io, coreos.github.io and the upstream sddm/sddm repository.",
        "",
    ]
    (out / "evidence_matrix.md").write_bytes(("\n".join(md)).encode("utf-8"))

    sums = []
    for p in sorted(out.glob("sources/*.txt")) + sorted(out.glob("sources/*.html")):
        sums.append((p.relative_to(out).as_posix(), sha256(p)))
    for name in ("sources.json", "planner_install.json", "planner_snapshot.json", "planner_install.err", "planner_snapshot.err", "evidence_matrix.json", "evidence_matrix.md"):
        p = out / name
        if p.exists():
            sums.append((name, sha256(p)))
    (out / "SHA256SUMS.txt").write_text("".join(f"{digest}  {rel}\n" for rel, digest in sums), encoding="utf-8", newline="\n")

    print(f"static_gate={report['overall_static_verdict']} native_runtime={report['native_runtime_verdict']}")
    for r in rows:
        print(f"{r['id']}: {r['verdict']} ({r['evidence_class']})")
        for miss in r.get("unmatched", []):
            print(f"  UNMATCHED {miss['source']}: {miss['quote']}")
    return 0 if report["overall_static_verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
