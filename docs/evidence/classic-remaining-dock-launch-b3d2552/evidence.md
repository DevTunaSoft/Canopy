# Classic remaining dock launches: verification evidence

Base: `b3d2552db0205e2f7821cb3bd7955453347051a0` (`integration/canopy-classic-20261123`).
Scope: Calendar, Photos and Terminal dock tiles join Files, Browser and Mail on the existing host-owned `SystemAppLauncher`; no QML, artwork, wallpaper, dock geometry or colour byte was changed.
Correction applied at integration tip `ec4ccc65a07071f85c0ce627447bc06c0dc3e0ad`; only this evidence note was corrected (self-citation removed, SHA citations recomputed from raw committed blob bytes).

## What was verified
- Source contracts: 6 tests pass on the candidate; the same file fails on the pristine base with 8 failures across 6 tests (RED then GREEN).
- Full `unittest discover -s tests` on the pristine base: 3399 tests, OK (skipped=45), 486.291s.
- Full `unittest discover -s tests` on the candidate: 3405 tests, OK (skipped=45), 176.032s; the +6 are this PR's contract tests, with no FAIL/ERROR on either side.
- Foundation contract check: PASS.
- Qt: MSYS2 UCRT64 Qt 6 CMake/Ninja configure and compile succeeded (52 build steps). `gio-unix-2.0` is absent on this Windows host, so the launcher compiles as its documented disabled fallback; no GIO-enabled native launch is claimed locally.
- Compiled runtime: 63 `SELF_TEST_PASS` markers across three approved-art self-test runs; three valid PNG screenshots at 1920x1080, 1200x750 and 760x500, each checked with `tools/check_screenshot.py`.
- Compiled fail-closed disclosure: `CALENDAR_`, `PHOTOS_` and `TERMINAL_DOCK_STATUS_FIXTURE_PASS` each emitted with rc=0 on the disabled-backend build; hostile `Name;echo bad` activation was refused before the launcher was touched.

## Artifact SHA-256

- `.gitattributes` `705fd4d6451a31d36b3df7de96f83f30ac976c9b4a6d1e51671d8e2f33e2d0da`
- `classic-1200x750.png` `dd13497b3d232b68ede1fbecc09a4086ad71de331328a8449471edfd14049ce4`
- `classic-1920x1080.png` `b844754d864525b9e737b79cdc5324536953b855a1ff616c9f2f29b3aaacc6db`
- `classic-760x500.png` `710b1d8c6da8abac1f77def58ed4d1928f1fd1f3d8f600d9bc86119a766f6515`
- `cmake-config.log` `fb46615a646a6c5bfe3fe5be9b5ed7a0b8b6edd7fa6cc0a7c492947c0aa14726`
- `compile.log` `68159a79ddf6f06729e7dd6d454a2206ec86f937f323a151acdf1005a5b41a9c`
- `compiled-qt.log` `aad4cc6e248064a4fa4a550a53b663f155abf511bb76b42c287731ca69e5ffc6`
- `evidence.md` - no self-hash; verify externally (git blob ID / raw-byte SHA-256, see normalization note)
- `foundation-check.txt` `129871f6cc021e47dda115aa0fd87eb66c0d65ce785dab53a4bff19dd0af606f`
- `recompile.log` `66d2325af77174fe1ef857d27f05e27247c5658b52c3fbff81b1eb02fbb9f19b`
- `red-proof.txt` `e5e162513bf41cd048a2706b775c6972a077b7546d84614235f84c294e71c8e8`
- `sha256.txt` - self-referential manifest; final digest recorded in the
  ND-050 remediation evidence ledger outside this bundle
- `status-fixtures.log` `850ab89a33b8c39e655698faa78f3ad84070f9b6dcec140352c0fc5f7df2ace5`
- `suite-baseline.txt` `4a4cce3d783d776a70d5130347d301daee0a5af59b02ae599f0154276759f980`
- `suite-candidate.txt` `e7c09f008a4d20b30036c98481f52cb03a8da530036e06f0e4bf68066ca6170a`
- `target-test.txt` `065c7d15facfd20f14fb9182747be315f3349fa1d5e1a0e966047509f4bfa9b1`

Normalization note: every SHA-256 in the table is over the exact committed blob bytes. The evidence directory pins `* -text`, so CRLF bytes are authoritative (`git ls-files --eol`: `i/crlf w/crlf attr/-text`); an LF-normalized copy hashes differently and is not authoritative. No SHA-256 is recorded for `evidence.md` itself: a file cannot contain its own final digest, so the previous self-citation was stale by construction (it named the pre-#610 blob `f2f25394...`). Verify this file externally with `git rev-parse <commit>:docs/evidence/classic-remaining-dock-launch-b3d2552/evidence.md` (git blob ID) and `git cat-file blob <commit>:<path> | sha256sum` (raw-byte SHA-256). The `sha256.txt` citation above is the raw SHA-256 of that manifest's committed blob, `cde85a8b...`, not the stale `5b2ac034...` and not the LF-normalized `939e4f6a...`. The manifest's own `evidence.md` row still records the historical pre-#610 blob `f2f25394...`; it is not a claim about the current bytes of this file. The frozen manifest and all logs/screenshots were left untouched.

## Resource / evidence note
- Measured: Windows 11 host, MSYS2 UCRT64 Qt 6, `QT_QPA_PLATFORM=offscreen`, software rendering, three approved-art captures (1920x1080, 1200x750, 760x500); source-contract and full-suite wall-clock counts above are `SYNTHETIC` host evidence, not Linux Mint acceptance.
- NOT_RUN: GIO-enabled launch fixtures (Ubuntu Xvfb CI owns them), real Linux Mint guest acceptance, real desktop/window-activation focus, idle CPU/PSS sampling, GPU-backed rendering and owner visual approval.
- Screen-reader: no accessibility metadata or QML was edited. Refusals reuse the existing `canopyLauncherStatus` Label already present in the launcher overlay; screen-reader behaviour was NOT_RUN locally.
- No stability, security, accessibility or approved-visual trade was made for a performance gain; the change only forwards one frozen dock label to the already-reviewed launcher and discloses refusal.
