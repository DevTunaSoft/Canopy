#!/usr/bin/env python3
"""Prepare 100 distinct, bounded Canopy engineering jobs (3 worker slots).

The backlog is additive and idempotent. This script does not execute code from
GitHub, install software, modify approved artwork, or merge any pull requests.
It requires the existing supervisor to be paused before changing its roadmap.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from canopy_supervisor import gitops, policy, state  # noqa: E402
from canopy_supervisor.cli import build_supervisor, load_config  # noqa: E402

BASE = "feat/classic-qt-port-buildable-20261121"
MAX_BACKLOG = 128

# Every row is a specific, bounded, independently testable engineering problem,
# not a generic "write another document" instruction. No task owns the Classic
# approved art, frozen dock geometry, source QML/C++, or GitHub workflows.
# Format: (component slug, engineering contract, required negative/edge check)
AREAS = {
    "launcher": [
        ("desktop-entry-parser", "parse freedesktop Desktop Entry application metadata", "malformed files, duplicates and invalid encoding"),
        ("desktop-entry-visibility", "apply Hidden, NoDisplay and OnlyShowIn/NotShowIn visibility semantics", "conflicting visibility flags and unknown desktops"),
        ("desktop-entry-tryexec", "evaluate TryExec availability without running binaries", "missing executables, absolute paths and spoofed executables"),
        ("app-search-casefold", "perform bounded Unicode-aware application name matching", "very long queries and casefold collisions"),
        ("app-search-ranking", "rank exact-prefix and fuzzy application matches deterministically", "ties, large catalogs and empty queries"),
        ("app-categories", "represent freedesktop application categories and ordering", "unknown categories and duplicate category IDs"),
        ("desktop-exec-fields", "parse Desktop Entry Exec field codes into safe argv without shell expansion", "unsupported field codes and metacharacter injection"),
        ("icon-theme-resolution", "resolve freedesktop icon theme names without silently replacing locked assets", "path escape, missing icons and cyclic inheritance"),
        ("launcher-favorites", "manage bounded persistent application favorites with stable IDs", "duplicates, deleted apps and corrupt state"),
        ("launcher-keyboard-navigation", "model grid focus movement and search selection", "empty results, compact grids and out-of-range focus"),
    ],
    "dock": [
        ("pinned-items", "maintain ordered pinned application IDs as immutable state transitions", "duplicate or missing application IDs"),
        ("running-indicators", "derive running-state indicators from trusted application events", "out-of-order events and stale process IDs"),
        ("window-grouping", "group multiple trusted windows by desktop application ID", "missing mappings and duplicated windows"),
        ("click-intents", "map dock activation to safe launch or focus intents", "untrusted IDs, missing targets and repeated clicks"),
        ("keyboard-navigation", "model accessible dock focus order without modifying locked dock geometry", "empty dock, wrapping and reduced motion"),
        ("pin-order-rollback", "validate/revert interrupted pin reordering transactions", "partially written state and conflict recovery"),
        ("notification-badges", "bound unread badge counts per trusted application", "negative, huge or malformed notification counts"),
        ("autohide-state", "represent optional user-controlled dock visibility as a pure state machine", "focus loss, modal windows and edge transitions"),
        ("display-geometry-contract", "validate dock bounds against scaling and screen dimensions without editing UI", "tiny, HiDPI and fractional scaling"),
        ("active-window-mapping", "map focused window IDs to trusted dock tiles", "focus races and unknown window owners"),
    ],
    "apps": [
        ("launch-argv", "produce shell-free argv for validated application launches", "shell metacharacters and empty commands"),
        ("safe-uri-open", "validate portal-backed opening requests for URI schemes", "javascript, file traversal and malformed URIs"),
        ("terminal-intent", "prepare explicit terminal app intents without implicit elevated execution", "missing terminal and injection attempts"),
        ("file-manager-intent", "form safe file manager launch intents for real user directories", "symlink escapes and missing directories"),
        ("desktop-actions", "parse and validate desktop action entries and IDs", "missing references and duplicated action names"),
        ("working-directory-policy", "validate application launch working-directory policies", "relative paths, missing dirs and unsafe inheritance"),
        ("environment-allowlist", "build minimal subprocess environments without credentials", "token leakage and disallowed variables"),
        ("process-exit-events", "represent application process lifecycle as bounded events", "PID reuse and crash loops"),
        ("launch-error-contract", "classify actionable process-launch errors without inventing success", "timeouts, denied launch and missing app"),
        ("app-capability-probe", "probe executability and session capabilities read-only", "unavailable tools and unsupported sessions"),
    ],
    "windows": [
        ("session-backend-detect", "detect X11/Wayland runtime capabilities without assuming compositor control", "headless, missing env and invalid displays"),
        ("x11-window-inventory", "normalize read-only X11 window inventory inputs behind an optional adapter", "malformed IDs, stale windows and unavailable display"),
        ("wayland-portal-capabilities", "describe Wayland portal capabilities without unauthorized window enumeration", "denied permissions and missing portals"),
        ("focus-intents", "model window focus requests with explicit backend authorization checks", "cross-app permissions and stale targets"),
        ("window-close-intents", "model non-destructive close request semantics", "unknown windows and disallowed ownership"),
        ("window-state-capabilities", "represent minimize/maximize support with backend feature negotiation", "unsupported compositors and invalid transitions"),
        ("workspace-inventory", "normalize workspace names and identifiers from permitted sources", "reordered, removed and duplicate workspaces"),
        ("window-title-sanitizer", "bound and sanitize labels derived from external window titles", "control characters and overlong strings"),
        ("window-roles", "map trusted window role types for dock grouping and switching", "ambiguous role and missing parent window"),
        ("switcher-state", "implement deterministic keyboard window-switch selection state", "window death during selection and wraparound"),
    ],
    "mint": [
        ("release-detect", "read Linux Mint version and distro compatibility read-only", "missing, forged and malformed release files"),
        ("dependency-probe", "report required Qt packages without attempting installation", "missing tools, old Qt and untrusted package names"),
        ("vbox-guest-readiness", "normalize existing VirtualBox guest preflight evidence without claiming an actual run", "powered-off VM and absent VBoxManage"),
        ("ssh-noninteractive", "validate safe guest SSH command construction without credentials", "host key failure, timeout and injection"),
        ("qt-plugin-discovery", "inspect available Qt image/platform plugin evidence without changing environment", "missing Qt SVG plugin and incompatible version"),
        ("compiler-capabilities", "normalize CMake/Ninja/Qt compiler probes", "missing toolchains and misleading executable names"),
        ("display-backends", "probe safe X11/Wayland availability for Mint testing", "no display and software-render fallback"),
        ("qt-log-diagnostics", "classify actual runtime QML/Qt logs and missing readiness markers", "crash, warnings and truncated logs"),
        ("screenshot-capture-manifest", "build reproducible screenshot evidence manifests from real existing captures only", "hash mismatch, absent binary and corrupt PNG"),
        ("guest-acceptance-summary", "compose fail-closed Linux Mint guest test evidence from true command results", "skipped guest execution and incomplete evidence"),
    ],
    "installer": [
        ("xdg-user-paths", "validate user-level XDG target paths without root or global changes", "symlinks and path traversal"),
        ("desktop-entry-staging", "stage escaped desktop launch entries with ownership records", "existing user entries and malformed Exec fields"),
        ("preview-install-plan", "produce a dry-run Linux Mint preview installation plan", "missing Qt executable and unauthorized output"),
        ("rollback-ownership", "reconcile reversals of partially installed owned files only", "foreign files and interrupted transaction"),
        ("upgrade-ownership", "verify old/new installation ownership before user-level upgrades", "tampered manifests and version rollback"),
        ("uninstall-integrity", "plan reversible uninstallation without deleting unrelated paths", "missing files and ownership mismatch"),
        ("icon-cache-optin", "describe optional icon cache refresh without invoking privileged tools", "missing cache tool and forced root action"),
        ("autostart-consent", "model opt-in-only session autostart registration", "disabled consent and duplicate autostart entries"),
        ("session-entry-validation", "validate user-level session entry metadata without replacing login manager", "unsafe Exec and missing session binary"),
        ("mint-dependency-contract", "check installed package constraints against stable Mint versions", "version mismatch and unknown packages"),
    ],
    "reliability": [
        ("startup-checkpoints", "model startup steps with durable no-corruption rollback decisions", "crash during initialization and partial state"),
        ("event-delivery-loss", "test bounded event delivery and overflow fallback contracts", "missed, repeated and reordered notifications"),
        ("app-launch-backoff", "implement bounded application relaunch backoff after failures", "repeated crash and rate-limit saturation"),
        ("focus-reconciliation", "recover focus selection when the current window disappears", "window death and repeated shortcuts"),
        ("configuration-recovery", "validate versioned config backup and safe recovery paths", "corrupt JSON and interrupted writes"),
        ("theme-transition-rollback", "model no-duplication theme switching rollback state", "interrupted transition and abandoned resources"),
        ("lock-session-events", "reconcile suspend/lock/resume event order without persistent polling", "duplicate unlock and backwards timestamps"),
        ("screen-topology-change", "model display connect/disconnect recovery events", "no monitors and unsupported resolutions"),
        ("runtime-error-ledger", "record bounded, redacted and structured shell fault records", "token leakage and unbounded log growth"),
        ("single-instance-guard", "validate lock and takeover policy for shell-owned user processes", "stale PID and competing instance"),
    ],
    "security": [
        ("path-jail-checks", "enforce canonical containment for user-selected file paths", "unicode traversal and absolute escape"),
        ("symlink-component-defense", "reject symlinked directory components before privileged actions", "nested links and race conditions"),
        ("desktop-exec-injection", "reject unsafe executable field expansion and shell calls", "quotes, redirects, pipes and substitutions"),
        ("untrusted-uri-schemes", "limit URI launch intents to permitted schemes", "javascript schemes and newline payloads"),
        ("launch-env-redaction", "redact secrets in environment diagnostics and failure reports", "API keys and credential-like fields"),
        ("log-size-caps", "bound diagnostic buffers and JSON report output lengths", "giant payloads and invalid unicode"),
        ("ipc-message-schema", "validate versioned, bounded trusted shell IPC payloads", "unknown schema and giant collections"),
        ("pack-manifest-metadata", "enforce data-only untrusted pack metadata handling", "executable-looking fields and path traversal"),
        ("privilege-boundary", "deny root/system-level actions from preview and desktop helpers", "sudo injection and inherited elevation"),
        ("plugin-trust-policy", "define non-executing integrity contracts for optional extensions", "unknown signer and mismatched digest"),
    ],
    "performance": [
        ("cpu-idle-samples", "calculate idle CPU percentages using monotonic bounded samples", "counter reset and zero duration"),
        ("pss-samples", "parse Linux /proc PSS evidence without estimating missing values", "malformed totals and disappeared process"),
        ("memory-delta", "report memory growth across repeated app interactions from real samples", "missing start/end and negative deltas"),
        ("launch-latency", "compute cold and warm startup timing summaries with explicit provenance", "clock jumps and missing timestamps"),
        ("queue-latency", "analyze bounded event queue latency evidence", "out-of-order timestamps and empty traces"),
        ("frame-pacing", "parse frame time distributions without claiming real GPU measurements", "dropped samples and unknown backend"),
        ("screenshot-limits", "enforce image size/dimension limits before Qt screenshot inspection", "oversized and truncated PNG"),
        ("effects-budget", "encode policy for optional effects with hard low-resource defaults", "infinite animation and invalid effect toggles"),
        ("feature-overrides", "validate resource-profile feature override precedence", "conflicts and invalid profile values"),
        ("cold-warm-benchmark", "summarize actual cold/warm startup runs with environment metadata", "unpaired runs and bogus performance claims"),
    ],
    "accessibility": [
        ("keyboard-action-map", "define screen-independent keyboard action intents", "duplicate shortcuts and inaccessible actions"),
        ("focus-order-contract", "verify deterministic focus navigation for menus and launcher", "modal traps and empty views"),
        ("reduced-motion-contract", "model reduced-motion preference propagation without rendering changes", "unset preference and contradictory overrides"),
        ("screen-reader-metadata", "validate accessible roles, labels and names in UI metadata", "missing labels and empty button names"),
        ("contrast-audit", "calculate WCAG contrast metrics from authored UI color references", "transparent and malformed colors"),
        ("high-contrast-options", "validate accessible high-contrast tokens without changing approved art", "missing labels and invalid hex colors"),
        ("shortcut-conflict-check", "detect collisions between user and shell shortcut registration", "reserved combos and duplicate actions"),
        ("tooltip-focus-contract", "describe keyboard-triggered tooltip visibility/accessibility semantics", "focus lost and absent hover"),
        ("text-scale-bounds", "validate text scaling/fallback policy for compact and HiDPI layouts", "extreme scales and font fallback"),
        ("resize-reflow-evidence", "check QML layout contracts for reduced window width using existing code", "760x500 clipped content and overflow"),
    ],
}


def tasks() -> list[dict]:
    result = []
    for area, specs in AREAS.items():
        for slug, contract, negatives in specs:
            task_id = "c100-" + area + "-" + slug
            source = f"canopy_features/{area}/{slug.replace('-', '_')}.py"
            test = f"tests/test_c100_{area}_{slug.replace('-', '_')}.py"
            objective = (
                f"Implement a genuine, small, independently useful engineering "
                f"component to {contract}. Read the actual compiled Canopy Classic "
                f"Qt source, existing tests and engineering requirements before "
                f"starting; reuse existing capabilities rather than duplicating "
                f"them. Work only in {source} and {test}. Include meaningful "
                f"offline unit tests, explicitly exercising {negatives}. Do not "
                f"introduce continuous polling, new background services, "
                f"privileged actions, paid APIs or unbounded memory. Verify "
                f"Windows-host and Linux-Mint behavior where feasible; never "
                f"claim a test of real Mint or compiled Qt unless it actually ran. "
                f"Do not modify frozen dock geometry, source artwork, QML, C++, "
                f"wallpaper, GitHub workflows or main. If a genuinely useful "
                f"implementation is impossible within the owned paths, report "
                f"BLOCKED with exact root cause instead of producing empty "
                f"stubs or duplicate test-only wrappers. Run py -3 -m unittest "
                f"tests.test_c100_{area}_{slug.replace('-', '_')} -v, record "
                f"actual output and SHA-256 of each new file in the in-worktree "
                f".canopy-worker-evidence.json, and prepare a draft PR only "
                f"after real green tests. Note any future integration still "
                f"needed: this modular component does not prove a working "
                f"desktop until wired into the compiled Qt application."
            )
            result.append(policy.validate_task({
                "id": task_id, "title": f"{area}: {contract[:108]}",
                "objective": objective,
                "scope": [source, test],
                "artifacts": [source, test],
                "kind": "implementation",
                "base": BASE,
                "tests_required": True,
            }))
    return result


def prepare(root: Path) -> tuple[int, int]:
    store = state.TaskStore(root)
    config = load_config(root)
    with state.exclusive_lock(store.lock_path):
        if not store.paused:
            raise ValueError("pause supervisor before preparing 100-task backlog")
        data = store.load()
        active = [item["id"] for item in data["tasks"]
                  if item.get("status") in
                  ("assigned", "running", "verifying", "publishing", "interrupted")]
        if active:
            raise ValueError("active worker tasks must stop first: " + ", ".join(active))
        repo = Path(config["repo"])
        gitops.run(["git", "fetch", config["remote"]], cwd=repo, timeout=180)
        gitops.rev_parse(repo, config["remote"] + "/" + BASE)
        path = store.root / "roadmap.json"
        catalog = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        if not isinstance(catalog, list):
            raise ValueError("roadmap must be an array; no task state changed")
        validated = [policy.validate_task(item, config["protected_paths"])
                     for item in catalog]
        by_id = {}
        for item in validated:
            if item["id"] in by_id:
                raise ValueError("duplicate existing roadmap ID: " + item["id"])
            by_id[item["id"]] = item
        existing = {item["id"] for item in data["tasks"]}
        new = tasks()
        if len(new) != 100 or len({item["id"] for item in new}) != 100:
            raise ValueError("backlog must contain exactly 100 unique tasks")
        new_paths = set()
        for item in new:
            for scoped in item["scope"]:
                if scoped in new_paths:
                    raise ValueError("overlapping backlog path: " + scoped)
                new_paths.add(scoped)
        additions = []
        for item in new:
            old = by_id.get(item["id"])
            if old is not None:
                if old != item:
                    raise ValueError("existing task contract has changed: " + item["id"])
                continue
            if item["id"] in existing:
                continue
            if any(policy.scope_conflict(item["scope"], previous["scope"])
                   for previous in validated):
                raise ValueError("scope conflicts with approved roadmap: " + item["id"])
            if any(policy.scope_conflict(item["scope"], record["scope"])
                   for record in data["tasks"]):
                raise ValueError("scope conflicts with old task: " + item["id"])
            additions.append(item)
        if len(validated) + len(additions) > MAX_BACKLOG:
            raise ValueError("backlog exceeds 128 task safety cap")
        if additions:
            state.atomic_write(path, json.dumps(validated + additions, indent=2) + "\n")
            store.event("-", "backlog_100_loaded",
                        f"added={len(additions)} from 100 validated assignments")
        return len(additions), len(validated) + len(additions)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--start", action="store_true")
    args = parser.parse_args(argv)
    try:
        added, total = prepare(args.state_root)
        print(f"CANOPY_100_READY added={added} roadmap_total={total}", flush=True)
        if args.start:
            store = state.TaskStore(args.state_root)
            config = load_config(args.state_root)
            with state.exclusive_lock(store.lock_path):
                store.set_paused(False)
                store.event("-", "backlog_100_started", "three workers; bounded recovery")
            sup = build_supervisor(config, store)
            # Emit a factual snapshot every six five-second coordination
            # steps so the single terminal never looks stuck during long runs.
            results = sup.run(until_idle=True, progress_every=6)
            ids = {item["id"] for item in tasks()}
            statuses = {}
            for item in results["tasks"]:
                if item["id"] in ids:
                    statuses[item["status"]] = statuses.get(item["status"], 0) + 1
            print("CANOPY_100_FINISHED " + json.dumps(statuses, sort_keys=True), flush=True)
            counted = sum(statuses.values())
            if counted != 100:
                print(f"CANOPY_100_INCOMPLETE: only {counted}/100 tasks reached the ledger; "
                      "inspect roadmap dependencies and supervisor dashboard",
                      file=sys.stderr)
                return 1
            if any(statuses.get(key) for key in ("blocked", "failed", "queued",
                                                 "assigned", "running", "interrupted")):
                return 1
        return 0
    except (ValueError, OSError, TypeError, gitops.GitError,
            policy.PolicyError, state.LockBusy) as exc:
        print("CANOPY_100_BLOCKED: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
