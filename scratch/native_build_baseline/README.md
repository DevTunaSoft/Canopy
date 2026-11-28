# Native build baseline — executed evidence index

Scope: `DEVELOPMENT_BASELINE_ONLY;NO_RELEASE;NO_VISUAL_APPROVAL;NO_MERGE`.

Base pin: commit `ec910d7a7275296ecbc8b5e5c459d356205165d1`, tree
`3c6110a77e9e34be367a4d11b29c3d6a13138bab` on
`origin/integration/canopy-plasma6-20261127`.

Reference guest: `Canopy-Test-Plasma6` (Ubuntu 26.04 LTS Kubuntu desktop,
Plasma 6.6.4, KWin X11 session 65, `DISPLAY=:0`, 1920x1080). The VM was already
running and is shared; the driver did not start, stop, save, revert or snapshot
it. The package was installed at user scope and removed again; the stock Plasma
config was restored byte-for-byte (`UNINSTALL_PASS: stock Plasma config restored
byte-for-byte`).

Final executed run: `2026-11-28T05:00:30Z`–`2026-11-28T05:03:52Z`, verdict
`PASS` in `SMOKE_RESULT.json`. Every final check is `PASS`; no check is `FAIL`
or `BLOCKED` in the executed set. `SHA256SUMS` in this directory is the exact
SHA-256 manifest of the committed evidence (all rows are recomputed from the
bytes in this directory; `SHA256SUMS` itself is excluded).

## Files

- `SMOKE_RESULT.json` — host-side verdict, every check and its detail.
- `HOST_COMMANDS.json` — exact host commands with rc/start time (SSH key path
  appears as a command argument; no credential or password is stored).
- `build/MANIFEST.json` — exact source/tree/tool/asset/binary/package SHAs,
  package member inventory and determinism record.
- `build/BUILD_RESULT.json` — guest build gate output.
- `build/configure.log`, `build/compile.log` — real CMake/Ninja output.
- `build/SHA256SUMS` — SHA-256 manifest of the build output.
- `build/org.kde.plasma.canopyclassic-0.1.0-dev-baseline.tar.gz` — the exact
  deterministic KPackage archive that was installed in the guest.
- `smoke/checks.txt`, `smoke/commands.log` — guest-side checks and command log.
- `smoke/package_hash_check.log` — in-guest `sha256sum -c SHA256SUMS`.
- `smoke/classic_runtime.log` — real binary launch output with approved-art and
  wallpaper verification markers.
- `smoke/plasma_session_with_classic.png` — 1920x1080 real desktop capture with
  the Classic window live.
- `smoke/plasma_session.png` — real desktop capture after cleanup.
- `smoke/SHA256SUMS` — guest-side hash manifest of the smoke outputs.
- `source_baseline.tar.gz`, `source_archive.sha256` — exact `git archive` of the
  pinned base commit uploaded to the guest before the tool overlay.
- `build_stdout.log`, `smoke_stdout.log` — driver transcripts.

## Labels not covered by the executed set

- `NOT_RUN`: full `--self-test-approved` fidelity suite, CI check runs, owner
  visual approval, release approval, merge/approval of any PR.
- `BLOCKED`: nothing in the final executed run. An earlier exploratory run of
  the full self-test at this base emitted `SELF_TEST_FAIL: Files folder grid
  clipped or unbalanced`; it was superseded by the runtime-launch smoke gate
  and is not part of the final PASS evidence.
- `FAIL`: nothing in the final executed run.

No screenshot in this directory is an approval artifact; captures prove a real
render only.
