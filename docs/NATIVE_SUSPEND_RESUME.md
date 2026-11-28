# M4 native suspend/resume — fail-closed contract and real Plasma guest evidence

Owner directive: `Canopy_LacOS_Integrated_Execution_Directive_2026-11-27.md`
SHA-256 `79e30d79a580bd05cf9d6cb09a45cbbb7887c0c35c5116a34bb6a0ace6042083` (section 11 evidence vocabulary, section M4 deployment and recovery).
Base: `integration/canopy-plasma6-20261127` at `ec910d7a7275296ecbc8b5e5c459d356205165d1`.
Branch: `product/native-suspend-resume-20261127`. Draft PR only; no merge and no self-approval.

## Contract (pure decision layer, unchanged behavior)

- `canopy_features/reliability/suspend_resume_contracts.py` folds already-delivered protocol-v2 `session.state.changed` host events or an existing `SessionState` into an immutable snapshot. Nothing is available until a confirmed active observation; `suspended`, `locked`, `resume_pending` and `unknown` all deny. A resume event alone never re-enables anything: `resume_ready()` must acknowledge a re-observed desktop. No D-Bus, process, window, network or filesystem I/O; no thread, timer or poll loop.
- `canopy_features/reliability/suspend_resume_native.py` is the bounded intake adapter: hard ceilings (`MAX_PENDING=32`, `MAX_DRAIN=16`), fail-closed boundary loss, bounded `submit_many`, stable caller-independent disclosures, and no host action.
- Additive M4 API: `EVIDENCE_LABELS` and `OUTCOMES` (the exact directive vocabulary), a frozen `RuntimeOutcome` and pure `runtime_outcome(observation)`. It maps only already-collected facts to an outcome. `None` means *not observed* and yields `NOT RUN`; an explicitly false fact yields `FAIL`; a non-`NATIVE RUNTIME` report yields `BLOCKED` and can never be promoted to a native PASS. The function performs no host access and reads no host state.
- No protocol version, topic or payload field was added; no protected visual, QML, C++, asset or workflow path was touched.

## Real guest procedure

The dedicated guest `Canopy-Test-Plasma6` (Ubuntu, X11 Plasma 6.6.4 / KWin 6.6.4, 1920×1080, headless, SSH `127.0.0.1:2223` with the on-disk key `g1_ubuntu_evidence/ssh/g1_ed25519`) was running and the VM work was serialized (no other VM-process probe was active at launch).

Reproducible sequence from the worktree root (host orchestration only; no credential typed, guest sudo used with `-n`):

```sh
python scratch/native_suspend/probe_plasma_guest.py pre
python scratch/native_suspend/probe_plasma_guest.py suspend
python scratch/native_suspend/probe_plasma_guest.py during
python scratch/native_suspend/probe_plasma_guest.py wake
python scratch/native_suspend/probe_plasma_guest.py post
python scratch/native_suspend/verify_runtime.py
```

`pre`/`during`/`post` use `VBoxManage controlvm screenshotpng` and read-only SSH observations; `suspend` launches `sudo -n systemctl suspend` detached in the guest; `wake` sends a host `VBoxManage controlvm … acpipowerbutton`. No guest file, connection, brightness, inhibition or power setting was changed outside that one suspend action and the wake button.

Facts recomputed from `scratch/native_suspend/evidence/probe.jsonl`:

| UTC | Observation | Label |
| --- | --- | --- |
| 06:16:42–49 | Pre-suspend PNG SHA-256 `592b23a5…9514`; X11 session 65 `Active=yes`, `State=active`, `LockedHint=no`; `/usr/bin/plasmashell` PID 5422, `/usr/bin/kwin_x11` PID 5384; `/proc/uptime` 8127.59; `CanSuspend` = `challenge`; `wmctrl -l` rc=124 | NATIVE RUNTIME (session), BLOCKED (X clients) |
| 06:16:58 | Guest suspend launched, rc=0, `M4_SUSPEND_LAUNCHED` | NATIVE RUNTIME |
| 06:17:13–35 | VM still `VMState="running"` (normal for guest S3); framebuffer PNG byte-identical; two SSH probes rc=255 with `Connection timed out during banner exchange` | NATIVE RUNTIME |
| 06:17:45–53 | Host ACPI power button rc=0; SSH reachable on attempt 1 | NATIVE RUNTIME |
| 06:18:06–14 | Post-resume PNG byte-identical; same session 65 active/unlocked; same PIDs 5422/5384; `/proc/uptime` 8212.32 (no reboot); `wmctrl -l` rc=124 | NATIVE RUNTIME (session), BLOCKED (X clients) |

Visual review of the exact pre-suspend PNG (`scratch/native_suspend/evidence/visual_review.json`) confirms dock with six tiles and active indicator, launcher and an open Files window at 1920×1080 — functional presence only, not visual approval. The post-resume PNG is byte-identical to the pre-suspend frame, and the guest X server did not answer new X clients before **or** after the cycle (`wmctrl`/`xdpyinfo` rc=124). It therefore cannot prove a fresh post-resume dock/launcher/window render.

## Verdict and exact blocker

`scratch/native_suspend/evidence/runtime_verdicts.json` SHA-256 `dc939be1c241a3fdf66fb903f2c307c6062367de2062d00aaf6af50bf0c5130f` reports:

- Overall contract outcome: **`NOT RUN`** — `desktop-state-not-reobserved`; evidence label `NATIVE RUNTIME` for the facts that were actually observed.
- Sub-outcome **`PASS` / `NATIVE RUNTIME`**: real guest S3 suspend and session recovery (SSH stopped and returned on the first wake, unchanged compositor/shell PIDs, active unlocked session, continuous uptime).
- Sub-outcome **`NOT RUN` / `NATIVE RUNTIME`**: fresh post-resume dock/launcher/window re-observation. Exact blocker: `guest X clients fail before and after suspend (wmctrl/xdpyinfo rc=124); post-resume PNG is byte-identical to the pre-suspend frozen frame`. This is an observed guest-X condition, not a claim that the desktop failed to recover.
- `BLOCKED`: X-client window enumeration in this guest.
- `NOT RUN`: screen-reader/AT-SPI behavior, multi-monitor and HiDPI suspend/resume, real PSS/CPU across the cycle, owner final visual acceptance.
- No release readiness, merge authorization, self-approval or compiled-shell wiring claim.

## Verification (exact worktree)

- 8 synthetic `runtime_outcome` tests — OK, rc=0 (`scratch/native_suspend/evidence/synthetic_tests.log` SHA-256 `12f22ad8…7981a`).
- 34 existing PE-057 and PE-081 targeted tests — OK, rc=0 (`…/targeted_tests.log` SHA-256 `93bba4c9…d4a4a`).
- Full suite `python -m unittest discover -s tests -v` — 4671 tests, `OK (skipped=49)`, rc=0 (`…/full_suite.log` SHA-256 `686455d5…e82`).
- `python tools/check_foundation.py` — PASS, rc=0 (`…/foundation.log` SHA-256 `cd7ce3ea…f37ad`).
- `scratch/native_suspend/evidence/SHA256SUMS.txt` recomputed and verified with `sha256sum -c`.

## Resource impact

`SYNTHETIC` pure-Python tests plus bounded host-side probe commands (one PNG capture per phase, six short SSH batches). No idle PSS/CPU, timing win, polling loop, thread, cache or daemon; at most one frozen decision record per observation. Screen-reader behavior is `NOT RUN`/unchanged: this change emits no UI or announcement. No stability, security, accessibility or approved-visual trade-off.

No merge, approval, release or visual acceptance is claimed.
