# Mint Test Lab integration checkpoint — 2026-11-18

## Scope

This integration branch unifies the previously isolated VM-test foundations on top of `feat/mint-testlab-visual-evidence` (draft PR #17), **without merging anything into main**. It preserves the Classic GTK prototype and includes:

| Source PRs | Consolidated capability |
|---|---|
| #18, #21 | User-owned Linux process RSS/HWM and CPU samplers |
| #19, #22 | PNG screenshot structural validation and required GTK CI check |
| #20, #23, #26 | Immutable approved-commit plan, clean-checkout gate and bounded execution |
| #25, #27 | Linux Mint preflight and Windows host prerequisite inspection |
| #28 | GTK/Xvfb probe to prevent skipped GUI tests reporting PASS |
| #29 | Read-only PR dependency graph auditor |
| #30, #31 | Fail-closed independent report consistency and multi-oracle scenario matrix |
| #32 | Deliberately failing subprocess negative control, required by CI |
| #33, #34 | Restricted named VirtualBox host controller and Mint acceptance contract |
| #35 | One-command Windows **preparation only**, with Windows-hosted self-test |
| #36, #37 | Host-owned run ledger, bounded retries and explicitly untrusted guest evidence envelope |

## Verification

CI is configured to execute combined Python unit tests, GTK/Xvfb smoke tests, deliberate failure detection, screenshot capture/structure validation, Windows bootstrap self-test and Windows preflight self-test. **Do not mark PASS without inspecting GitHub Actions on this branch's exact SHA.** This is a first integration gate, not end-to-end unattended Mint proof.

## Unfinished before hands-free Mint testing

1. **One-click provisioning** must actually detect/install VirtualBox and obtain Linux Mint using exact official verified SHA/signatures, create an isolated guest, perform noninteractive OS install, install dependencies and create a clean snapshot. The current script only writes a plan. Windows admin authorization remains explicit.
2. **Trusted host supervisor** must schedule approved commits and create host-side challenge IDs, control the named VM with validated identities, and receive results without granting guest access to host secrets. The available host controller supports limited manual status/start/snapshot restore; it is not a service.
3. **Guest transport/execution** must be approved-commit-only, bounded, isolated and equipped for graphical Cinnamon input, screen observation and real user-session testing. Existing Xvfb GTK tests are not Cinnamon acceptance tests.
4. **Independent host observability** must verify actual process exits, host VM state, artifact hashes and fresh guest boot identity; no guest self-report is independent evidence.
5. **Recovery** must collect diagnostics before any destructive restore, cap retries, reset disposable snapshots with user-approved local policy, and check Mint boot/login after reset.
6. **Evidence** must include cold/warm boot, keyboard/focus/accessibility, screenshot/geometry, 320px/HiDPI/multimonitor, settings corruption, install/uninstall rollback, security, CPU/RAM and repeated stability checks. Declare missing evidence BLOCKED/NOT_RUN.

## Engineering constraints

Clean modular memory-efficient code, zero background services unless justified, no shells or tokens in guest, no untrusted public PR workflow on a self-hosted machine. Two synthetic oracles do not certify a desktop. Complete PR stack still needs explicit code diff review and decision whether/when to merge; this integration PR is draft and does not retarget or merge other PRs.

## Reproduce checks (on suitable Linux developer/CI environment)

```bash
python3 -m unittest discover -s tests -v
python3 -m scripts.negative_controls
CANOPY_ISOLATED_DISPLAY=1 PYTHONPATH=. xvfb-run -a /usr/bin/python3 scripts/capture_classic.py --output-dir test-results/visual
python3 -m scripts.validate_visual --directory test-results/visual
```

A Windows GitHub Actions runner separately executes `Install-Canopy-TestLab.ps1 -SelfTest` and `Test-CanopyHost.ps1 -SelfTest`.

## Pending decisions

Separate Classic design reference PR #24 is intentionally **not** combined: it starts from main and needs a compatibility/design integration review. Original Classic code changes PR #1–#17 stay preserved as base ancestry; none have been merged into main.
