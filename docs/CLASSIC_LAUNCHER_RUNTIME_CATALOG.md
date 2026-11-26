## CURRENT TIP CORRECTION — exact tip `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` (PR #651 merge; supersedes every earlier "live tip" claim below, including `84684a0` and `dd079d4`)

Current integration tip: `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` — merge of PR #651 from `docs/current-tip-84684a0` on `integration/canopy-classic-20261123` at 2026-11-26T09:55:37Z, with parents `2d6b5affe4ff50fbb9b5db5a28cef0d1aebf6ce4` (PR #650 merge) and `96686334ce00a2eecd8f11f4a044416ef652254f`. `git rev-parse HEAD` in this isolated worktree and `git ls-remote --heads origin refs/heads/integration/canopy-classic-20261123` both resolve to that exact SHA. The former tip `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` (PR #647 merge) is an **archived ancestor** whose pin-specific claims are preserved and scoped below. #279 remains **PROTECTED — OPEN DRAFT, HOLD** at head `17bb473e9b9740481f0269440391ab92e528139d`; it is a visual-lock guard only and never merge authorization. Nothing merges to `main`; no self-approval, promotion or merge is performed by this change.

Former integration tip (archived ancestor): `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` — merge of PR #647 from head `564056da378377a9dae567f874e46f3df2a2836d` on `integration/canopy-classic-20261123`, merged 2026-11-26T07:25:07Z; parent 1 is `d617453569ab23afe076fc58e56f2c94a4e6b97a` (PR #646 merge, head `2e1d4c04e7e107177290564315354674949a8563`). Verified in this isolated worktree with `git rev-parse HEAD` (= the exact pin), `git ls-remote origin refs/heads/integration/canopy-classic-20261123` (= the exact pin at verification), `git diff --name-only dd079d4 84684a0f77c81cb0e84d9a679ec57a429dc5c1db` (only the three owned docs), `git diff --quiet dd079d4 84684a0f77c81cb0e84d9a679ec57a429dc5c1db -- prototype/classic` (exit 0), and fresh `gh pr view 647` / `gh pr view 646` (both MERGED with the exact heads above). `origin/main` remains `65a9e0de107355e04f91356db7358debf751760a`; nothing merges to `main`. #279 remains **PROTECTED — OPEN DRAFT, HOLD** at head `17bb473e9b9740481f0269440391ab92e528139d` (re-queried live: OPEN, draft, no merge commit); it is a visual-lock guard only and never merge authorization. No self-approval, promotion or merge is performed by this change.

Every `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` claim below is **ARCHIVED / SCOPED TO THAT ANCESTOR**. That includes the terminal full suite `Ran 3772 tests in 1400.814s`, `OK (skipped=48)`, exit 0, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-645-closure/full-discover.log`, SHA-256 `bb42b0225a3aa7b34ad6718b9e368cf4d896a0b37ce47b75251b7560e851e995`. That suite ran at `dd079d4` only: it is **NOT** a suite result at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`, is not re-attributed to `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`, and is not re-attributed to earlier pins. The full suite at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` was **REAL_HOST_RUN_SCOPED** at that pin (archived/scoped to that ancestor): `python -m unittest discover -s tests` (Python 3.14.10) in a clean isolated worktree pinned to that exact tip returned `Ran 3772 tests in 1269.363s`, `OK (skipped=46)`, exit 0, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_84684a0_artifacts/full.log`, SHA-256 `72bb1ea46b04cd605883b7fa83a009e5fc4eba1d780fa81646289432855bbee6`, with zero `FAIL:`/`ERROR:` summary names (empty-set SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`); report `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_84684a0.json`, SHA-256 `2efec701f7711ebc001b0d7a551d57abf21873e93c78a151cb1ba1ea9c9dc3b8`, independently verified in `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_independent_verification_84684a0.json`. This run belongs to the exact integration tip only, not to this docs-only correction head; no test code differs between `dd079d4` and `84684a0`. Its skip count (46) differs from the archived `dd079d4` run (48), and no skip-name identity is claimed because the exact-tip log is non-verbose. This is a real host run scoped to that tip, not Mint, desktop, visual, owner or release acceptance. All older suite counts, screenshot hashes and scoped verdicts below remain pinned to their own historical SHAs. The only gates re-run for this correction are the two documentation gates recorded in the PR body.

The authoritative full-suite record at `20fb694f2b4a0ea44e2f3032f316ac8c7e65a23a` comes only from the two terminal artifacts below (no suite was run for this docs PR). The first terminal run, artifact `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_20fb694.json` (SHA-256 `1ee77b94b6c48c11e70242d4d117e539943fa15708cee31ebbabd2d88e219388`), ran `python -m unittest discover -s tests` (Python 3.14.10) in a clean private worktree at that exact SHA and returned `Ran 3774 tests in 1666.718s`, `FAILED (errors=1, skipped=48)`, exit 1, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_20fb694_artifacts/full.log` SHA-256 `c974a9032bb4b764315abb7f4bc3de707a29e9adc25eeea765ce60f8681d2316`, with one normalized failure name `test_cli_failure_marker (test_c100_perf_artifact_bundle_gate.CliTests.test_cli_failure_marker)` (set SHA-256 `b2b3623648c8d07d84f74ca35c5c87790c58e3d9367fce23dff225759e6982ac`) that the artifact attributes to a 60-second host-load `subprocess.TimeoutExpired`, not a product assertion failure; that first run is reported as FAILED and is not claimed as PASS. The serialized authoritative rerun at the same exact SHA, artifact `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_20fb694_rerun.json`, returned `Ran 3774 tests in 1332.755s`, `OK (skipped=48)`, exit 0, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_suite_20fb694_rerun_artifacts/full.log` SHA-256 `fe659f5d62bf23330d193b43ef9a5cf45f8a18da7992ba434d45d850bfe52670` (sidecar matches), with zero normalized FAIL/ERROR names (empty-set SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`); the isolated check log `C:/Users/X1/AppData/Local/hermes/cache/scratch/perf_cli_rerun_20fb694.log` SHA-256 `bc9b6104b24eaf1be191837ce9b12421f064bc5baa170865f63984fd1f8e03f3` records the flag-checked test passing 4/4 in isolation. Ran and skipped counts are identical across both runs; no new FAIL/ERROR name appears in the rerun and the first-run timeout name is absent. The scoped baseline remains the archived `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` run `Ran 3772 tests in 1269.363s`, `OK (skipped=46)`, log SHA-256 `72bb1ea46b04cd605883b7fa83a009e5fc4eba1d780fa81646289432855bbee6`; the +2 test-count delta is attributed in the artifacts to PR #649. Labels remain `REAL_HOST_RUN_SCOPED` for both runs and `NOT_RUN` for visual acceptance, `main` merge and any further suite re-run. No Mint acceptance, owner visual approval or release readiness is claimed.

Exact-tip compiled candidate (verified, scoped): the source worktree at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` was clean; two clean UCRT64 / Qt 6.12.0 Release offscreen builds produced byte-identical `canopy-classic-spike.exe` SHA-256 `bfeecaedf1e5cb5b6f9bf6acfa2290390c06ea046174413bf9c5c1cbebbb7824` (3,458,593 bytes; pass1, pass2 and `evidence/binary/canopy-classic-spike.exe` recomputed from disk). `python tools/qa/classic_build_gate.py verify --evidence C:/Users/X1/AppData/Local/hermes/cache/scratch/consolidated-compiled-84684a0/evidence --source-sha 84684a0f77c81cb0e84d9a679ec57a429dc5c1db` reported `VERDICT PASS`, `checks=12 pass=12 fail=0` (log `C:/Users/X1/AppData/Local/hermes/cache/scratch/consolidated-compiled-84684a0/gate.log`, SHA-256 `cd6eab1665a53e5dc0f6edcb5a2747bd0d250d526737bc2a57ce3414546e3efd`). Three approved-art offscreen self-test logs each recorded 21 `SELF_TEST_PASS` markers at 1920x1080 (`99dfb131a2caf4bf106dcf3aeaa55fb3b344c18a96463c7e1708182f0d7f39a6`), 1200x750 (`ca861a4df87988fb91bd0f697ac46bace1e6772eff29922836cfeab962b5aef3`) and 760x500 (`d36c03375c4c6c7e79e6cd89a83700e2d8aec01cbd36d5fde52e0eb4420222f9`). Ledger: `C:/Users/X1/AppData/Local/hermes/cache/scratch/consolidated-compiled-84684a0/ledger.md`. This is **SYNTHETIC** software-rendered offscreen evidence with GIO unavailable on Windows: not Mint acceptance, live desktop launch, real native GIO launch, screen-reader verification, owner visual signoff or release readiness (all `NOT_RUN`; Mint acceptance `NOT_ESTABLISHED`). Resource impact: `SYNTHETIC` bounded offscreen captures and gate fixtures only; five-minute shell-owned PSS/CPU/GPU/wakeup profiling and screen-reader behavior are `NOT_RUN`. No stability, security, accessibility or approved-visual trade-off is made for any performance gain.

For the launcher catalogue specifically, the compiled bridge remains opt-in (`--launcher-catalog`), fail-closed and SYNTHETIC; approved default ordering stays `8 : 6` and no approved visual byte changed at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`. This change owns exactly `docs/CLASSIC_LAUNCHER_RUNTIME_CATALOG.md`, `docs/GUI_ENGINEERING_DOSSIER.md`, `docs/PRODUCT_COMPLETION_MATRIX.md`, `docs/AGENTS_WORKFORCE.md`, `docs/ROADMAP.md`, `README.md`, `CONTRIBUTING.md`, `docs/ARCHITECTURE.md`, `docs/QUALITY.md` and `.github/PULL_REQUEST_TEMPLATE.md`. No source, QML, artwork, asset, workflow, test or tool path is touched, and no visual or asset byte changes.

---

# Classic launcher desktop-entry catalogue: compiled-runtime bridge record

## ARCHIVED TIP CORRECTION — exact tip `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` (superseded at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`; all evidence below is scoped to this ancestor)

Archived integration tip at that time: `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` — merge of PR #645 from head `7f58777ef7beb4c2fd128be5785c0a8a99018691` on `integration/canopy-classic-20261123`. Verified at that time in that isolated worktree with `git rev-parse HEAD`, `git ls-remote origin refs/heads/integration/canopy-classic-20261123` (returned `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` at that time; the current re-query returns `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`) and a fresh `gh pr view` for every PR below. `origin/main` remains `65a9e0de107355e04f91356db7358debf751760a`; nothing merges to `main`. That historical docs-only change was pinned to that exact tip and owns only the three files named in the task; no source, QML, artwork, asset or test path is touched. The earlier `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (#637), `128c973e8dc64b5ce1b3c1a3e06fe1e55ed64366` (#625) and `dcb41bde55f37a4a433a0fa4b473f32ea6cc0055` (#624) pins below are **merged ancestors / archived evidence pins only**: every log hash, screenshot hash, suite count and scoped verdict there is preserved verbatim and is **not re-attributed** to `dd079d4a60c3fd0fa5cf975ce26af27215e77b55`. None of this `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` evidence, including its terminal full suite below, is attributed to `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`. In particular, the `Ran 3660 tests in 861.683s`, `OK (skipped=46)` full-suite result, the `Ran 12 tests` docs-gate result and the deterministic launcher-model compile probe belong **only** to exact tip `af97e116b59620b7e9c0e51b7b042dc40e5cb77d`. The completed full suite at `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` is **REAL PASS**: `Ran 3772 tests in 1400.814s`, `OK (skipped=48)`, exit 0, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy-645-closure/full-discover.log`, SHA-256 `bb42b0225a3aa7b34ad6718b9e368cf4d896a0b37ce47b75251b7560e851e995`, zero `FAIL:`/`ERROR:` lines. This result belongs only to `dd079d4` and is not attributed to earlier pins or to `84684a0`.

Merged chain after `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (all ten re-queried with `gh pr view` as `MERGED`; exact heads and merge SHAs recorded verbatim):

| PR | Exact head SHA | Exact merge SHA | What landed |
|---|---|---|---|
| #638 | `0e944444134ef686b3fdd99d398370e306997a7a` | `d2876cc7766ea10a29fc3cfd06f6517f710b331c` | Governance/workforce/PR-lifecycle reconciliation docs |
| #639 | `67a7a60cc0ad560479ac53c631242d8936b805b2` | `c11e508e469b56e12828b9cf73693184f3a2bbb3` | Bounded native catalog producer |
| #640 | `733e20235d3f8f1ce620f401a4c5c307e8549dcc` | `97a151b7c5fec512245b308eb4cc3b13ee21da64` | Read-only Linux resource probe |
| #641 | `488278e3f862fe6b3eb193ac9bf84b4cad2e64b6` | `f47b48d5c3f14af2ac238b14b132b1222f3f1c16` | Bounded trusted quick-controls host status producer |
| #642 | `5a3c9c0a75616825ddf28b819d1323cc38a3df76` | `0b82f0dfeea9ef23aa874d1cad225498dedcbab9` | Bounded read-only notification host snapshot producer |
| #643 | `f0131c2072fb9a77d2f587fbb6078b75029a20a8` | `721cba08c282a7f90739c3bae042d6b9077a6396` | Prior stale-docs correction at `af97e11` |
| #644 | `34770419158281bfb0d4d36307d74ef2fb54248c` | `f3555d89b7f0325ed2b67fb47946d5e0cde9fd51` | Fix for #639 native catalog bounded directory enumeration |
| #645 | `7f58777ef7beb4c2fd128be5785c0a8a99018691` | `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` | Fix for #640 real `smaps_rollup` parsing and confined proc reads |
| #646 | `2e1d4c04e7e107177290564315354674949a8563` | `d617453569ab23afe076fc58e56f2c94a4e6b97a` | Docs-only stale-claim correction at archived `dd079d4` (superseded at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`) |
| #647 | `564056da378377a9dae567f874e46f3df2a2836d` | `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` | Docs-only correction recording the terminal `dd079d4` suite (now archived/scoped, never re-attributed to `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`) |

**Fixes applied at the archived `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` tip (not merely proposed; still present at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` with byte-identical compiled inputs):** #644 (`f3555d8…`, head `34770419…`) bounds native catalog directory enumeration by counting `os.scandir` entries one at a time and refusing at 513 before materializing names or reading file bodies, and skips invalid desktop-id names before `lstat`; its `SYNTHETIC` negative control produced `1000 != 513` on the untouched base and passed at the fix head (16 targeted tests `OK`). #645 (`dd079d4…`, head `7f58777e…`) parses real `smaps_rollup` files by skipping exactly the three known unitless non-memory fields (`THPeligible`, `ProtectionKey`, `VmFlags`) while keeping strict `name: N kB` and 1 MiB-bound fail-closed behavior for every other line, confines each proc read to `--proc-root` by checking every intermediate path component for symlinks, and translates invalid UTF-8 to `MeasurementError`; its realistic rollup and symlink/UTF-8 negative controls are fixture-scoped (`LINUX_PROC_SCOPED`), **not** a real five-minute shell-owned PSS/CPU/wakeup measurement. Both fixes are already in the source tree at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` (no compiled-input delta from `dd079d4a60c3fd0fa5cf975ce26af27215e77b55`); this docs PR does not change their code.

#279 remains **PROTECTED — OPEN DRAFT, HOLD** at head `17bb473e9b9740481f0269440391ab92e528139d`; it is a visual-lock guard only and never merge authorization. No self-approval, no promotion and no merge is performed by this change. A separate queued job re-audits these corrected docs for zero stale claims; that job is also barred from self-approval and merge.

Historical gates re-run on the exact corrected docs tree at `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` (Windows 11 host, `PYTHONDONTWRITEBYTECODE=1`): `python3 tools/check_foundation.py` **PASS**, exit 0, output `PASS: foundation files, tagline, and local Markdown links`, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_docs_gates_dd079d4/foundation.log`, SHA-256 `cd7ce3ea44ff12d436ec0af5e64de94b552f5bdfd4b210f14372c29537f937ad`; `python3 -m unittest tests.test_foundation tests.test_foundation_link_scope_guard -v` **PASS**, exit 0, `Ran 12 tests`, `OK`, log `C:/Users/X1/AppData/Local/hermes/cache/scratch/final_docs_gates_dd079d4/docs_tests.log`. Both historical gates were executed on that exact corrected docs tree; they are documentation gates only and do not re-run or re-attribute the 3660-test suite at `af97e11`.

Acceptance labels remain unchanged at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`: `SYNTHETIC` for compile probes, synthetic fixtures and scoped rollup/catalog evidence; `NOT_RUN` for real Mint session acceptance, live desktop launch, live screen-reader announcement, five-minute shell-owned PSS/CPU/GPU/wakeup profiling, owner visual signoff, release readiness; Mint acceptance remains `NOT_ESTABLISHED` (the #620 report gate is internal `evidence-consistency PASS` only); owner visual acceptance remains `NOT_RUN` for every build, the v2 preview remains pending owner signoff, and no merged PR is described as owner-accepted. No false Mint or owner acceptance is claimed anywhere in this correction.

---

Status: **APPLIED and FIXED at exact archived integration tip `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` — compiled host injection wired by merged #637; #644 bounded native-catalog enumeration and #645 real `smaps_rollup` parsing / confined proc reads applied in later merges and still present at `84684a0f77c81cb0e84d9a679ec57a429dc5c1db`; still opt-in and SYNTHETIC, with no owner visual or Mint acceptance.**
Correction record: the earlier `128c973` base, the `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` wiring tip and the BLOCKED wiring note below are retained as archived historical context only; #635 made the compile probe deterministic, #637 applied the wiring at `af97e116b59620b7e9c0e51b7b042dc40e5cb77d`, and #644/#645 fixes are applied at the archived tip `dd079d4a60c3fd0fa5cf975ce26af27215e77b55`.

Base at task start: `128c973e8dc64b5ce1b3c1a3e06fe1e55ed64366`; corrected to archived tip `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (merge of PR #637, head `9777dfafa6c84e2a8bcd883f736586a74198db00`), which contains the applied wiring. Archived ancestor tip: `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` (merge of #645); PRs #638–#645 are MERGED with exact heads and merge SHAs in the CURRENT TIP CORRECTION and ARCHIVED TIP CORRECTION sections above; #644/#645 fixes are applied there. No governance file is touched by this docs-only change. Visual lock: no approved asset, dock, theme, main-window, icon-provider
or geometry file is touched by this change.

## Audit finding

- `prototype/classic/LauncherOverlay.qml` supplies a hard-coded eight-item
  catalogue in approved mode (`Browser, Mail, Files, Calendar, Photos, Music,
  Terminal, Settings`) and six items in legacy preview mode.
- `prototype/classic/main.cpp` self-test asserts exactly `8 : 6` catalog items
  and ready icons, so any unguarded catalogue replacement would fail the
  compiled screenshot gate and change the approved appearance.
- Pure-Python discovery/contract code already exists and is tested:
  - `canopy_features/launcher/desktop_entry_parser.py` — offline `.desktop`
    parse from bytes; no process, poll or shell.
  - `canopy_features/launcher/desktop_entry_tryexec.py` — bounded TryExec gate.
  - `canopy_features/launcher/launcher_catalog_ingest.py` —
    `compose_launcher_catalog()` returns an immutable, bounded snapshot with
    fixed negative claims; hidden/NoDisplay entries and duplicate ids are
    skipped; no filesystem, process or visual side effects.
  - `canopy_features/launcher/app_categories.py`, `launcher_search_view.py` —
    category and search contracts.
- Before this change there was **no compiled-host consumer** of that catalog
  contract: Python records stayed outside the Qt runtime. Event topics such as
  `app.catalog.changed` are transport/QA observability only, not compiled
  wiring. At `af97e11` that gap is closed: PR #637 added the compiled-host consumer described below.

## What this change adds (owned paths only)

- `prototype/classic/LauncherModel.h` / `.cpp` (new implementation file):
  `LauncherCatalogModel`, a plain C++ (no `Q_OBJECT`) read-only value that
  consumes one already-produced snapshot. It is bounded (64 KiB file, 1024
  rows, 256-character titles), validates ids against the Python `DESKTOP_ID`
  grammar, rejects control/format/surrogate/private-use/unassigned/line/
  paragraph scalars, collapses duplicate ids first-wins, validates the whole
  input before committing, and leaves the previous state untouched on any
  refusal. It exposes `applications()` as `[{"title": ...}, ...]` plus
  `browse()` / `filter()` over the same `LauncherModel` bounds. No XDG walk,
  network, process, daemon, timer or privileged write.
- The wire format is headerless, LF-terminated `app_id<TAB>title`; one explicit
  read-only file path is supplied by a trusted host, never discovered by
  globbing. UTF-8 is decoded strictly.
- `prototype/classic/LauncherOverlay.qml`: `applications` now checks a guarded
  context property and uses `canopyLauncherCatalog.applications()` only when
  `active` is true; otherwise the original approved eight-item order (or the
  legacy six-item order) is returned unchanged. No colour, font, icon source,
  anchor, cell size, accessibility string or keyboard handler changed.
- `tests/test_c100_launcher_runtime_catalog.py`: Python-side parity tests and
  a real g++/Qt6 compile-and-run probe of the model. The probe consumes the
  exact bytes produced by `compose_launcher_catalog()` and proves hostile
  snapshots fail closed without replacing a prior snapshot.
- This document carries the owner-locked integration fragment (below).

## Contract mapping (Python → compiled host)

| Pure contract | Compiled mirror |
| --- | --- |
| `MAX_ENTRIES = 1024` | `LauncherCatalogModel::MaxRows = 1024` |
| `MAX_TITLE_CHARS = 256` | `MaxTitleChars = 256` |
| `DESKTOP_ID = [A-Za-z0-9][A-Za-z0-9._-]*\.desktop` | `validAppId()` manual full match |
| `_UNSAFE_UNICODE_CATEGORIES` (Cc, Cf, Cs, Co, Cn, Zl, Zp) | `validTitle()` `QChar::category()` denylist + surrogate/C0/DEL guard |
| hidden / NoDisplay skipped upstream | never present in the produced snapshot |
| duplicate id, first wins | `seenIds` skip, first wins |
| immutable ordered snapshot | commit-only-after-full-validation `QVector` copy |
| no filesystem/process/visual claims | one explicit read-only file; no launch, no geometry change |

Intentional scope boundary: the compiled host does not parse `.desktop` files
or scan XDG directories. The Python contract remains the parser/ingest owner;
the compiled model is the bounded consumer. This keeps the bridge opt-in,
read-only and free of privileged or network paths.

## APPLIED — compiled host injection wired by merged PR #637 at `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (archived tip; still applied at `dd079d4a60c3fd0fa5cf975ce26af27215e77b55`)

At `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` the equivalent of the fragment below is **APPLIED** by merged PR #637: `prototype/classic/CMakeLists.txt` builds `LauncherModel.cpp/.h` and `prototype/classic/main.cpp` registers the read-only `canopyLauncherCatalog` bridge with the opt-in `--launcher-catalog` snapshot path and fail-closed rejection. PR #635 made the compile probe deterministic. Default approved ordering stays `8 : 6` and no visual path changed. The historical prose below records the original proposal; the verification and owner gates remain:

1. The exact patch below is the historical proposal; its equivalent is already APPLIED at `af97e11` by #637 (do not rebase across an owner branch).
2. Build once, then run the default approved screenshot self-test; it must
   still report `8` items and `CANOPY_APPROVED_ART_VERIFIED`.
3. Run the opt-in self-test with a host-produced fixture; expect
   `CANOPY_LAUNCHER_CATALOG_CONNECTED`, `SELF_TEST_PASS: opt-in desktop-entry
   catalogue reached QML`, and no `SELF_TEST_FAIL`.
4. Keep owner visual approval separate: the opt-in catalogue can render
   arbitrary desktop titles whose icons are not in the approved set; that is
   an experimental, non-approved mode and needs owner review before any
   default promotion.

### Exact patch fragment for `main.cpp` and `CMakeLists.txt`

```diff
diff --git a/prototype/classic/CMakeLists.txt b/prototype/classic/CMakeLists.txt
--- a/prototype/classic/CMakeLists.txt
+++ b/prototype/classic/CMakeLists.txt
@@ -9,7 +9,7 @@ if(PkgConfig_FOUND)
     pkg_check_modules(GIO_UNIX QUIET IMPORTED_TARGET gio-unix-2.0)
 endif()
 qt_standard_project_setup()
-qt_add_executable(canopy-classic-spike main.cpp WindowActivationState.cpp WindowActivationState.h RoundedDockIconProvider.cpp RoundedDockIconProvider.h SystemAppLauncher.cpp SystemAppLauncher.h)
+qt_add_executable(canopy-classic-spike main.cpp LauncherModel.cpp LauncherModel.h WindowActivationState.cpp WindowActivationState.h RoundedDockIconProvider.cpp RoundedDockIconProvider.h SystemAppLauncher.cpp SystemAppLauncher.h)
 qt_add_qml_module(canopy-classic-spike
     URI Canopy.Classic
     VERSION 1.0
diff --git a/prototype/classic/main.cpp b/prototype/classic/main.cpp
--- a/prototype/classic/main.cpp
+++ b/prototype/classic/main.cpp
@@ -1,6 +1,7 @@
 #include "RoundedDockIconProvider.h"
 #include "SystemAppLauncher.h"
 #include "WindowActivationState.h"
+#include "LauncherModel.h"
 
 #include <QGuiApplication>
 #include <QQmlApplicationEngine>
@@ -494,6 +495,30 @@ public:
     Q_INVOKABLE QVariantList snapshot() const { return QVariantList(); }
 };
 
+// Read-only QML face of the opt-in desktop-entry catalogue. The model is a
+// plain bounded C++ value owned by main(): no Q_OBJECT on it, no signals,
+// timers, sockets, process calls or privileged paths. QML sees only the
+// already-validated snapshot and its row count.
+class LauncherCatalogBridge final : public QObject {
+    Q_OBJECT
+    Q_PROPERTY(bool active READ active CONSTANT)
+    Q_PROPERTY(int rowCount READ rowCount CONSTANT)
+public:
+    explicit LauncherCatalogBridge(const LauncherCatalogModel &model,
+                                   QObject *parent = nullptr)
+        : QObject(parent), m_model(model) {}
+
+    bool active() const { return m_model.active(); }
+    int rowCount() const { return m_model.rowCount(); }
+    Q_INVOKABLE QVariantList applications() const
+    {
+        return m_model.applications();
+    }
+
+private:
+    const LauncherCatalogModel &m_model;
+};
+
 // A Repeater can give its delegates QObject owners different from their
 // visual parents. Traverse the actual QQuickItem scene tree for UI assertions.
@@ -1242,6 +1267,10 @@ int main(int argc, char *argv[]) {
     // Declared before the QQmlApplicationEngine below so this trusted controller
     // outlives the engine, the context property and every QML object using it.
     QuickControlsHostStateController hostStateController;
+    // Opt-in desktop-entry catalogue: inactive unless --launcher-catalog is
+    // given with a valid, bounded snapshot. Both objects outlive the engine.
+    LauncherCatalogModel launcherCatalog;
+    LauncherCatalogBridge launcherCatalogBridge(launcherCatalog);
     const QString activationBackend = activationBackendId();
     activationState.applySnapshot(
         hostActivationSnapshot(systemLauncher, activationBackend, 1));
@@ -1262,6 +1291,25 @@ int main(int argc, char *argv[]) {
     } else if (activationBackend.isEmpty()) {
         qWarning() << "CANOPY_ACTIVATION_BACKEND_UNKNOWN_FAIL_CLOSED";
     }
+    if (args.contains(QStringLiteral("--self-test-launcher-catalog-model")))
+        return LauncherCatalogModel::selfTest() ? 0 : 1;
+    // Opt-in host bridge: one explicit, read-only snapshot file. Absence,
+    // wrong arguments or any malformed row leaves the approved catalogue and
+    // all visuals untouched. No XDG walk, network or privileged operation.
+    const int launcherCatalogIndex = args.indexOf(
+        QStringLiteral("--launcher-catalog"));
+    if (launcherCatalogIndex >= 0) {
+        if (launcherCatalogIndex + 1 >= args.size()
+            || args.at(launcherCatalogIndex + 1).startsWith(QLatin1Char('-'))) {
+            qWarning() << "CANOPY_LAUNCHER_CATALOG_REJECTED_FAIL_CLOSED: missing path";
+        } else if (launcherCatalog.loadFromFile(
+                       args.at(launcherCatalogIndex + 1))) {
+            qInfo() << "CANOPY_LAUNCHER_CATALOG_CONNECTED: opt-in rows"
+                    << launcherCatalog.rowCount();
+        } else {
+            qWarning() << "CANOPY_LAUNCHER_CATALOG_REJECTED_FAIL_CLOSED";
+        }
+    }
     const bool launcherFixture = args.contains(QStringLiteral("--self-test-launcher-launch-fixture"));
     if (args.contains(QStringLiteral("--self-test-system-apps-capability"))) {
@@ -1596,6 +1644,11 @@ int main(int argc, char *argv[]) {
     NotificationHostSource notificationSource;
     engine.rootContext()->setContextProperty(
         QStringLiteral("canopyNotificationSource"), &notificationSource);
+    // The read-only catalogue bridge is always registered so QML can use a
+    // plain typeof guard; it reports active=false unless a valid opt-in
+    // snapshot was loaded above.
+    engine.rootContext()->setContextProperty(
+        QStringLiteral("canopyLauncherCatalog"), &launcherCatalogBridge);
     // Real in-process host-state injection: the trusted shell delivers one
     // bounded, already-produced payload on an existing host-event topic. No
     // bus, transport, process or privileged write is created. The controller
@@ -2541,6 +2594,13 @@ int main(int argc, char *argv[]) {
     }
     const bool quickSettingsExpected =
         enableSystemApps && systemLauncher.canLaunch(QStringLiteral("Settings"));
+    // The opt-in catalogue changes only the result set; default approved
+    // ordering and geometry stay exactly as before.
+    const bool launcherCatalogActive = launcherCatalog.active();
+    const int expectedLauncherCount = launcherCatalogActive
+        ? launcherCatalog.rowCount() : (approvedMode ? 8 : 6);
+    const QStringList expectedLauncherTitles = launcherCatalogActive
+        ? launcherCatalog.titles() : QStringList();
     const int screenshotIndex = args.indexOf(QStringLiteral("--self-test-screenshot"));
     if (screenshotIndex >= 0) {
         if (screenshotIndex + 1 >= args.size()) {
@@ -2553,6 +2613,7 @@ int main(int argc, char *argv[]) {
         QTimer::singleShot(1000, window,
             [window, screenshotPath, launcherScreenshotPath, approvedMode, landscapeMode,
              framingReviewMode, quickSettingsExpected, settingsOverlay,
+             launcherCatalogActive, expectedLauncherCount, expectedLauncherTitles,
              settingsOpen = args.contains(QStringLiteral("--self-test-settings-open")),
              terminalCandidateMode = !terminalCandidatePath.isEmpty()]() {
             auto *bar = window->findChild<QQuickItem *>(QStringLiteral("canopyTopBar"));
@@ -2636,7 +2697,7 @@ int main(int argc, char *argv[]) {
                 window->contentItem(), QStringLiteral("canopyLauncherSearch"));
             if (!applicationLauncher || !launcherSearch
                 || applicationLauncher->property("catalogCount").toInt() !=
-                    (approvedMode ? 8 : 6)
+                    expectedLauncherCount
                 || !QMetaObject::invokeMethod(applicationLauncher, "openLauncher",
                                                Qt::DirectConnection)
                 || !applicationLauncher->isVisible() || !dock->isVisible()) {
@@ -2648,7 +2709,7 @@ int main(int argc, char *argv[]) {
             QCoreApplication::processEvents();
             const int launcherImageCount = countVisualItems(
                 applicationLauncher, QStringLiteral("canopyLauncherIcon"));
-            if (launcherImageCount != (approvedMode ? 8 : 6)
+            if (launcherImageCount != expectedLauncherCount
                  || countReadyLauncherImages(applicationLauncher) != launcherImageCount) {
                 qCritical() << "SELF_TEST_FAIL: incomplete launcher image catalogue"
                             << launcherImageCount;
@@ -2678,16 +2739,33 @@ int main(int argc, char *argv[]) {
             const bool restoredMatch =
                 applicationLauncher->setProperty("searchQuery", QString())
                 && applicationLauncher->property("filteredCount").toInt() ==
-                    (approvedMode ? 8 : 6);
+                    expectedLauncherCount;
+            // Compiled proof that the host snapshot, not a copied QML list,
+            // reached the actual launcher: titles must match in order.
+            bool catalogMatches = true;
+            if (launcherCatalogActive) {
+                const QVariantList actual =
+                    applicationLauncher->property("applications").toList();
+                catalogMatches = actual.size() == expectedLauncherTitles.size();
+                for (int i = 0; catalogMatches && i < actual.size(); ++i) {
+                    catalogMatches =
+                        actual.at(i).toMap().value(QStringLiteral("title")).toString()
+                        == expectedLauncherTitles.at(i);
+                }
+            }
             const bool closed = QMetaObject::invokeMethod(
                 applicationLauncher, "closeLauncher", Qt::DirectConnection)
                 && !applicationLauncher->isVisible() && dock->isVisible();
-            if (!selectedMatch || !emptyMatch || !restoredMatch || !closed) {
+            if (!selectedMatch || !emptyMatch || !restoredMatch || !catalogMatches
+                || !closed) {
                 qCritical() << "SELF_TEST_FAIL: launcher search or dismissal inconsistent";
                 QCoreApplication::exit(1);
                 return;
             }
             qInfo() << "SELF_TEST_PASS: actual Qt launcher opens, searches and closes";
+            if (launcherCatalogActive)
+                qInfo() << "SELF_TEST_PASS: opt-in desktop-entry catalogue reached QML"
+                        << expectedLauncherCount;
             if (framingReviewMode)
                 qInfo() << "SELF_TEST_PASS: launcher-only Qt frame review enabled; dock frozen";
```

## On-disk reproducible targeted log (included in this PR)

Captured after reverting the then owner-locked files at historical base head `128c973e8dc64b5ce1b3c1a3e06fe1e55ed64366`; the wiring is applied at `af97e116b59620b7e9c0e51b7b042dc40e5cb77d`. Logged with
`PYTHONHASHSEED` default, Qt 6 UCRT64 toolchain and
`QT_QPA_PLATFORM=offscreen`. Full raw log (including Qt style warnings):
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_launcher_targeted_evidence.txt`.
Its SHA-256 is
`7638bd5159caa2c1e7dc1cd397b34b9d19fe87666e1957eaf81b112154942407`.

```text
COMMAND: python -m unittest tests.test_c100_launcher_runtime_catalog tests.test_classic_launcher_search -v
EXIT: 0
test_compiled_model_consumes_python_snapshot_and_fails_closed (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogCompiledTests.test_compiled_model_consumes_python_snapshot_and_fails_closed) ... ok
test_bounded_readonly_model_source_contract (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogSourceTests.test_bounded_readonly_model_source_contract) ... ok
test_bridge_format_never_carries_control_or_path_ids (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogSourceTests.test_bridge_format_never_carries_control_or_path_ids) ... ok
test_hidden_and_duplicate_entries_never_reach_the_bridge (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogSourceTests.test_hidden_and_duplicate_entries_never_reach_the_bridge) ... ok
test_python_contract_feeds_an_ordered_bounded_snapshot (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogSourceTests.test_python_contract_feeds_an_ordered_bounded_snapshot) ... ok
test_qml_bridge_is_guarded_and_approved_order_is_preserved (tests.test_c100_launcher_runtime_catalog.RuntimeCatalogSourceTests.test_qml_bridge_is_guarded_and_approved_order_is_preserved) ... ok
test_compiled_header_filter_and_selection (tests.test_classic_launcher_search.LauncherSearchCompiledTests.test_compiled_header_filter_and_selection) ... ok
test_compiled_qml_filter_keyboard_and_accessible_count (tests.test_classic_launcher_search.LauncherSearchCompiledTests.test_compiled_qml_filter_keyboard_and_accessible_count) ... ok
test_model_header_mirrors_bounded_fail_closed_contract (tests.test_classic_launcher_search.LauncherSearchSourceTests.test_model_header_mirrors_bounded_fail_closed_contract) ... ok
test_qml_exposes_accessible_result_count (tests.test_classic_launcher_search.LauncherSearchSourceTests.test_qml_exposes_accessible_result_count) ... ok
test_qml_filter_is_bounded_case_insensitive_and_fail_closed (tests.test_classic_launcher_search.LauncherSearchSourceTests.test_qml_filter_is_bounded_case_insensitive_and_fail_closed) ... ok
test_qml_preserves_frozen_keyboard_and_accessibility_contracts (tests.test_classic_launcher_search.LauncherSearchSourceTests.test_qml_preserves_frozen_keyboard_and_accessibility_contracts) ... ok
test_qml_selection_is_bounded_and_keyboard_driven (tests.test_classic_launcher_search.LauncherSearchSourceTests.test_qml_selection_is_bounded_and_keyboard_driven) ... ok
Ran 13 tests in 75.035s
OK

COMMAND: python tools/check_foundation.py
EXIT: 0
PASS: foundation files, tagline, and local Markdown links

COMMAND: canopy-classic-spike.exe --approved-art-dir <repo>/prototype/classic/assets/approved --self-test-approved --self-test-size 1920x1080 --self-test-screenshot <scratch>/canopy_launcher_default_head_shot.png
EXIT: 0
CANOPY_APPROVED_ART_VERIFIED: eight exact PNG icons and legacy blue wave
SELF_TEST_PASS: actual launcher image component count 8
SELF_TEST_PASS: actual launcher button image geometry centered 8
SELF_TEST_PASS: actual Qt launcher opens, searches and closes
SELF_TEST_PASS: desktop chrome geometry QSize(1920, 1080)

SUMMARY: unittest_exit=0 foundation_exit=0 screenshot_exit=0
         foundation_pass=True screenshot_eight_item_pass=True screenshot_chrome_pass=True
screenshot_sha256=7b70ed55e5cb3d378c21d1f4794ab2d7940640c1edefce9113d37d146a8441bd
```

Final confirmation after the doc was completed (same files, plus the read-only
visual-lock tests): `python -m unittest tests.test_c100_launcher_runtime_catalog
tests.test_classic_launcher_search tests.test_check_visual_lock -v` → `Ran 22
tests`, `OK`, exit 0; raw log SHA-256
`4ed040fbd4439e7105ef404b53527d14c5bdcd5f3e73c7a8ba85b3df33007f79`.

Compiled artifact actually executed for the head-state run:
`C:/Users/X1/AppData/Local/hermes/cache/scratch/canopy_launcher_catalog_build/canopy-classic-spike.exe`,
SHA-256 `8250e8a44733cf3c781ec7ccdfe8ad529ee6513127c7859b144cb2e9884008a0`.
The binary is a build artifact, not a repository file; the commands above and
the owned source paths make the run reproducible.

## Evidence and labels

- `COMPILED (SYNTHETIC, applied at af97e11)` — PR #635 made the g++/Qt6 launcher-model probe deterministic; PR #637 applied the compiled wiring. At `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` three bounded repeats of `test_compiled_model_consumes_python_snapshot_and_fails_closed` returned `Ran 1 test ... OK` (log SHA-256s `3d3696833787c160782dd10c063fc5297cb7517032e23c9878b1a4c1ad779e6b`, `9353cf016ed924e917f2bfa0ef8296afcb8d1c4c76c0e7e2bf018e20dd1f0082`, `8d0a3022c75a01ae4e8f86c79c3d60732b490555f7340b907c3dcaccc419a0f9`), and the full suite at the same tip is `Ran 3660 tests in 861.683s`, `OK (skipped=46)` (log SHA-256 `b274d360caa2b026ea8446073c549976b77fd2b2a5dd1c08427be72987345b94`). This is a local offscreen compile/run against a Python-generated fixture: **SYNTHETIC**, not Mint, visual or release acceptance. An exact-tip full GUI binary build and real desktop launch remain **NOT_RUN**.
- `COMPILED (historical, offscreen, local scaffolding, not at the original PR head)` — before the
- `SYNTHETIC` — Python contract tests and the offscreen g++/Qt6 model probe;
  no desktop, Mint guest or real user session.
- `COMPILED (offscreen, local scaffolding, not at PR head)` — before the
  ownership correction, the patch above was applied locally and the full
  Classic binary was built with CMake/Ninja. It reported
  `CANOPY_LAUNCHER_CATALOG_CONNECTED: opt-in rows 3`,
  `SELF_TEST_PASS: actual launcher image component count 3`,
  `SELF_TEST_PASS: opt-in desktop-entry catalogue reached QML 3`, exit 0,
  with no `SELF_TEST_FAIL`. Fixture SHA-256
  `8d5b73bafd69f1d4506e7bc5907846ff718ae4de1a2c7ed59ba4f5583a58e262`
  (three Python-produced rows), raw log SHA-256
  `eef3fe72f30842bf9e5c097e0e00f89db199512a3b6b97956ba1fd82bc8f5991`.
  This proves the fragment and QML guard work together; it is **not** evidence
  that this PR's head activates the bridge, because the owner-locked files were
  reverted before commit.
- `COMPILED (offscreen, at PR head)` — default approved screenshot self-test
  still reports the frozen eight-item launcher and the approved icon set.
- `NOT_RUN` — real Mint desktop acceptance, real desktop-entry discovery on a
  user machine, real PSS/CPU profile, screen-reader session. No visual or
  automatic-CI-on-guest verdict is claimed.

Resource impact: `SYNTHETIC` bounded allocations only — at most one 64 KiB
read, 1024 small rows and one QVariantList conversion, performed once and only
when the opt-in flag is present; no polling, timers, caches or background
wakeups. Real-runtime RSS and CPU are `NOT_RUN`; the change adds no continuous
work and does not trade stability, security, accessibility or approved visuals
for a minor gain. Screen-reader behaviour is unchanged in approved mode; in
opt-in mode the existing `Accessible.name`/`description` bindings derive from
the same validated titles, and no new announcement is emitted.

Remaining blockers: **NOT_RUN** — owner visual review before any opt-in catalogue becomes a default, real Mint desktop acceptance and real desktop launch. The wiring itself is **APPLIED** at archived `af97e116b59620b7e9c0e51b7b042dc40e5cb77d` (#637) and still applied at archived `dd079d4a60c3fd0fa5cf975ce26af27215e77b55` and at current tip `84684a0f77c81cb0e84d9a679ec57a429dc5c1db` (no compiled-input delta); #644/#645 fixes are applied there; no further source integration is pending.
