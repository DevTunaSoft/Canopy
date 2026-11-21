# Qt build and Linux Mint acceptance evidence inventory

**Task:** `qt-mint-evidence`
**Branch:** `feat/canopy-supervisor-qt-mint-evidence`
**Commit SHA at inventory time:** `250257df8571d1ce4fa3d736f7072c4bc22dd2c1`
**Host:** Windows (PowerShell 5.1). All checks below are read-only, source-level checks on this Windows host.
**Bytecode control:** `PYTHONDONTWRITEBYTECODE=1` set for every Python invocation; no `__pycache__` was created.

## Scope and honesty statement

This document records prerequisite inventory and local Python test results only.
It does **not** claim a compiled Qt build, a launched Qt window, any screenshot,
or any Linux Mint VM acceptance. No such run was performed and none is
fabricated. No approved artwork, dock design, wallpaper, or Qt GUI file was
modified.

## Commands, results, and output

### 1. Qt-related tracked files

Command:

```
git ls-tree -r --name-only HEAD | findstr /i qt
```

Result: **PASS** (command executed; inventory captured). Output:

```
docs/MINT_CLASSIC_QT_SMOKE.md
docs/QT_PERFORMANCE_EVIDENCE_GATE.md
tests/test_mint_classic_qt_smoke.py
tools/mint_classic_qt_smoke.py
```

These are documentation, a smoke runner, and its unit test. They are not a
compiled Qt binary and do not prove a build exists.

### 2. Build and VM toolchain availability

Command:

```
Get-Command qmake,cmake,VBoxManage -ErrorAction SilentlyContinue
```

Result: **BLOCKED** (prerequisite gate). Output: none — `qmake`, `cmake`, and
`VBoxManage` are not on this Windows host's `PATH`. Without them, a Qt build
and a Linux Mint VM acceptance run cannot be started here.

### 3. Foundation checker

Command:

```
py -3 tools/check_foundation.py
```

Result: **PASS** (exit code 0). Output:

```
PASS: foundation files, tagline, and local Markdown links
```

### 4. Foundation unit tests

Command:

```
py -3 -m unittest tests.test_foundation -v
```

Result: **PASS** (exit code 0). Output:

```
test_broken_local_link (tests.test_foundation.FoundationTests.test_broken_local_link) ... ok
test_missing_file (tests.test_foundation.FoundationTests.test_missing_file) ... ok
test_missing_tagline (tests.test_foundation.FoundationTests.test_missing_tagline) ... ok
test_valid_foundation (tests.test_foundation.FoundationTests.test_valid_foundation) ... ok
test_valid_local_link (tests.test_foundation.FoundationTests.test_valid_local_link) ... ok

----------------------------------------------------------------------
Ran 5 tests in 0.216s

OK
```

### 5. Mint guest preflight unit tests

Command:

```
py -3 -m unittest tests.test_mint_guest_preflight -v
```

Result: **PASS** (exit code 0). Output:

```
test_bad_release_values_ignored (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_bad_release_values_ignored) ... ok
test_missing_desktop_session_identification_is_blocker (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_desktop_session_identification_is_blocker) ... ok
test_missing_each_tool_is_reported (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_each_tool_is_reported) ... ok
test_missing_gui_fails (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_gui_fails) ... ok
test_missing_or_unrecognized_session_does_not_borrow_other_display (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_or_unrecognized_session_does_not_borrow_other_display) ... ok
test_missing_qt_is_blocker (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_qt_is_blocker) ... ok
test_missing_session_type_is_blocker (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_missing_session_type_is_blocker) ... ok
test_no_host_private_data_dumped (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_no_host_private_data_dumped) ... ok
test_non_mint_local_cli_never_claims_acceptance (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_non_mint_local_cli_never_claims_acceptance) ... ok
test_ready_is_not_mint_acceptance (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_ready_is_not_mint_acceptance) ... ok
test_release_parser_only_allows_three_known_fields (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_release_parser_only_allows_three_known_fields) ... ok
test_report_does_not_leak_raw_display_or_desktop_values (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_report_does_not_leak_raw_display_or_desktop_values) ... ok
test_session_display_consistency_negative_controls (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_session_display_consistency_negative_controls) ... ok
test_supported_cinnamon_session_variants (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_supported_cinnamon_session_variants) ... ok
test_ubuntu_is_not_passed_as_mint (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_ubuntu_is_not_passed_as_mint) ... ok
test_wayland_guest_can_be_ready (tests.test_mint_guest_preflight.MintGuestPreflightTests.test_wayland_guest_can_be_ready) ... ok

----------------------------------------------------------------------
Ran 16 tests in 0.496s

OK
```

These tests validate the preflight logic on Windows only. In particular,
`test_non_mint_local_cli_never_claims_acceptance` and
`test_ready_is_not_mint_acceptance` assert that a local non-Mint run and a
`READY_FOR_TESTS` result must **not** be presented as Mint acceptance. Green
here is not evidence of a Mint guest, a Qt build, or visual signoff.

## Result summary

| Check | Result |
| --- | --- |
| Qt files inventory (`git ls-tree ... findstr qt`) | PASS |
| `qmake` / `cmake` / `VBoxManage` availability | BLOCKED (none found) |
| `tools/check_foundation.py` | PASS |
| `tests.test_foundation` | PASS (5 tests) |
| `tests.test_mint_guest_preflight` | PASS (16 tests) |

## NOT RUN (no evidence claimed)

- Compiled Qt build: **NOT RUN** — no `qmake`/`cmake` on this host.
- Qt application launch / runtime smoke: **NOT RUN**.
- Qt screenshots at 760x500, 1200x750, 1920x1080, HiDPI: **NOT RUN**.
- Linux Mint Cinnamon VM boot and in-guest preflight (`tools/mint_guest_preflight.py`): **NOT RUN** — no `VBoxManage` and no Mint guest.
- In-guest Qt smoke runner (`tools/mint_classic_qt_smoke.py`): **NOT RUN**.
- Native app launch, focus, compositor, accessibility, 5-minute resource, and visual signoff gates: **NOT RUN**.

Prerequisites for a real acceptance run are documented in
`docs/MINT_GUEST_PREFLIGHT.md` and `docs/MINT_CLASSIC_QT_SMOKE.md`; they require
a disposable Mint Cinnamon guest and an actual compiled Qt binary with an
engineer-supplied source SHA. None of that was available or performed here.

## Cleanup

`PYTHONDONTWRITEBYTECODE=1` was used for all Python commands. A recursive check
found no `__pycache__` directories in the worktree. No files other than this
document were changed. No commit, push, PR, or branch change was made.
