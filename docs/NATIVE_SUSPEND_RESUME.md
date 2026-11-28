# M4 native suspend/resume recovery contract

**Status: `BLOCKED_NOT_RUN` for real suspend/resume.** This is a source and
verification contract for a bounded, read-only host integration. No real
suspend, resume, lock/unlock, Plasma/KWin session, D-Bus call, UPower event,
guest, compiled Qt binary or screen-reader was exercised. There is no native
runtime PASS in this change.

- Controlling directive: Rev3 SHA-256 `1fba4b1e…` (owner file
  `C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`).
- Base: `integration/canopy-plasma6-20261127` @ `ec910d7a`.
- Branch: `product/native-suspend-resume-20261128`.
- Owned paths only: `canopy_features/session_recovery/**`,
  `tools/session_recovery/**`, `scratch/native_suspend_resume/**`, this file.
  No reliability, event, QML, C++, asset, test-discovery or workflow path is
  modified. The sibling suspend/resume verdict work owns
  `canopy_features/reliability/**`; this change does not touch it.
- Draft PR only: no merge, no approval, no self-approval, no base or main
  change.

## Boundary

`canopy_features.session_recovery` adds a read-only composition layer over
contracts that already exist at `ec910d7a`:

- `canopy_features.reliability.suspend_resume_contracts` and
  `canopy_features.reliability.suspend_resume_native` provide the fail-closed
  phase model and bounded host-event intake; this layer composes
  `SuspendResumeNativePath` and never modifies or forks it.
- `canopy_features.quick_controls.host_status_producer.TRUSTED_SOURCES`
  supplies the only accepted capture sources (`host-events`,
  `host-status-file`).
- `canopy_features.system.quick_controls_state.STATUS_TOKENS` supplies the
  session-state vocabulary.
- logind and UPower are **reused** as existing read-only host-status sources.
  `logind_upower.py` parses text a trusted host has already captured from
  `loginctl show-session` and `upower -i`; it does not invoke them.

No new protocol version, topic, payload field, service, daemon, bus client,
socket, subprocess, thread, timer or poll loop is introduced.
`NO_NEW_SERVICE = True`, `DAEMON = False`, `POLL_INTERVAL_SECONDS = None`.
`tools/session_recovery/probe_readonly.py` is a one-shot reader: it reads
captured files, writes nothing, executes no command and polls nothing.

## Capture and checkpoints

Pre/post captures hold six fixed facts (`shell_active`, `dock_visible`,
`launcher_visible`, `window_visible`, `session_present`, `workspace_stable`).
Each fact is `True`, `False` or `None`; `None` means *not observed*, never
*observed absent*. Facts are reordered to a canonical key order, exposed as
immutable mappings, and JSON-serializable.

| Checkpoint | Meaning |
| --- | --- |
| `pre-state-captured` | pre-suspend desktop state supplied by a trusted host |
| `session-preserved` | session identity still stable after resume |
| `work-preserved` | work area and restored windows still stable |
| `suspend-confirmed` | suspend was already observed by the host |
| `resume-confirmed` | resume was already observed by the host |
| `post-state-captured` | post-resume desktop state supplied by a trusted host |
| `desktop-reobserved` | trusted caller acknowledged a re-observed desktop |
| `fallback-ready` | safe stock-Plasma fallback declared, never executed |

The checkpoint tuple is bounded to eight records. Every observation creates a
new immutable record; published records are never mutated.

## Verdict rules (fail-closed)

| Condition | Outcome / reason |
| --- | --- |
| anything other than `NATIVE RUNTIME` evidence | `BLOCKED` / `native-evidence-absent` |
| suspend or resume not confirmed | `NOT RUN` / `suspend-not-observed`, `resume-not-observed` |
| no explicit desktop re-observation | `NOT RUN` / `desktop-not-reobserved` |
| missing pre/post capture or unknown fact | `NOT RUN` / `pre-post-state-missing`, `pre-post-facts-incomplete` |
| a confirmed desktop/work fact is `False` | `FAIL` / `desktop-state-not-restored`, `session-or-work-not-preserved` |
| preserved-work facts unknown | `NOT RUN` / `preservation-incomplete` |
| native evidence, all checkpoints confirmed | `PASS` / `native-suspend-resume-recovery-verified` |

A `PASS` is impossible to construct with a non-native evidence label, and a
lost host boundary (explicitly marked unavailable, overflow or close) downgrades
the snapshot to `STATIC SOURCE ONLY` and declares fallback. A resume event by
itself never re-enables anything: re-observation must be explicitly acknowledged.

## Honest fallback

`Fallback(reason)` is a declaration with `target = stock-plasma`,
`action = none`, `executed = False`. Declaring fallback performs no switch,
logout, restart, process action or configuration change. The host owns any
later decision to use stock Plasma.

## Verification (SYNTHETIC / static only)

- `PYTHONPATH=<repo> python -m unittest discover -s tools/session_recovery -p
  'test_*.py' -v`: **33 tests, OK** (`SYNTHETIC`, in-process Python). The suite
  lives in `tools/session_recovery/` because `tests/**` is not an owned path;
  CI's `unittest discover -s tests` does not collect it. This is recorded, not
  hidden.
- `PYTHONPATH=<worktree> python tools/check_foundation.py`: **PASS**
  (foundation files, tagline and local Markdown links).
- Real CLI execution of `probe_readonly.py` against captured sample text
  returned `evidence_label = STATIC SOURCE ONLY` and
  `verdict = BLOCKED / native-evidence-absent`, with
  `writes = commands_executed = polls = 0`.
- Static AST scan: zero imports of `subprocess`, `socket`, `threading`,
  `asyncio`, `dbus`, `time`, `os` and zero calls to `sleep`, `poll`, `select`,
  `spawn`, `Popen`, `system`, `exec`, `eval` in the three production modules.
- Evidence (exact command, counts and hashes): `scratch/native_suspend_resume/`.

## Resource impact

- Measured (`SYNTHETIC`, in-process): at most eight checkpoint records, six
  facts per capture and 16 KiB of parser input per captured text; bounds are
  enforced by construction and asserted by the targeted tests. No allocation
  depends on an unbounded iterator or on host uptime.
- `NOT_RUN`: real-desktop incremental PSS, average CPU/GPU cost, scheduler
  wakeups, 24-hour stability, real suspend/resume and multi-monitor/HiDPI
  behavior. No Mint guest or compiled Qt run was performed here.
- `screen-reader`: `NOT_RUN`. The module emits no UI, announcement or visual
  change; it only returns immutable records.
- No stability, security, accessibility or approved-visual trade-off is made
  for a resource gain. No visual, QML, C++, asset or workflow path is touched.

## Non-claims

`BLOCKED_NOT_RUN`: real suspend, resume, lock/unlock, D-Bus/logind/UPower
runtime delivery, Plasma/KWin behavior, Mint acceptance, compiled Qt behavior,
screen-reader announcements, visual approval, release readiness and merge
approval. A `PASS` produced by the pure contract in a synthetic fixture is a
logic result only; it is not evidence of a working desktop session.
