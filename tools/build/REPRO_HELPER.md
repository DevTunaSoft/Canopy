# Classic UCRT64 reproducible-build helper (RI-011)

RI-003 attributed two non-identical UCRT64 release binaries to source **EOL
conversion** and **file mtimes**, not to a source defect. This helper makes
those two inputs explicit and stable without editing the tracked worktree.

```sh
# Stage pinned sources from git blobs in scratch (never from the CRLF worktree):
python tools/build/repro_build_helper.py prepare \
  --source <repo-root> \
  --source-sha <exact-40-hex-commit> \
  --out private-evidence/temp/canopy-repro-stage

# Re-derive every staged byte and mtime from the same pin:
python tools/build/repro_build_helper.py verify \
  --source <repo-root> \
  --source-sha <exact-40-hex-commit> \
  --stage private-evidence/temp/canopy-repro-stage
```

`prepare` writes `repro_stage_report.json` with per-file blob/stage SHA-256,
byte-identity and EOL-normalization flags, observed `core.autocrlf`, and the
stable timestamp inputs (`SOURCE_DATE_EPOCH`, `TZ`, `LANG`). EOL rewriting is
limited to compiler/rcc inputs; binaries and hash-pinned documentation/sidecar
artifacts are staged byte-for-byte. All staged files,
including the report, get mtime `0` by default. `verify` fails closed on a
changed byte, a changed mtime, an unexpected staged path or a wrong pin.

The helper does **not** change git config, assets, QML, C++, product behavior or
the existing `classic_release_build.py` flow. Generated Qt `qmldir` files still
need the epoch pin that `classic_release_build.py` already applies after
configure; `normalize_generated_mtimes()` exposes that input for reuse and for
regression tests. No binary rebuild is implied by running this helper.

Verification is local, synthetic (`SYNTHETIC`): the tests use a temporary git
fixture with `core.autocrlf=true`; a real UCRT64 binary hash is `NOT_RUN` here
and remains the authority of `classic_release_build.py`.
