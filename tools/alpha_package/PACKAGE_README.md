# Canopy Classic alpha tarball — quick use

This is an **experimental, user-level application entry**, not a session,
compositor, display manager or desktop replacement. It changes no system
configuration and needs no root.

State at build time is recorded in `MANIFEST.json`:

- `COMPILE_NOT_RUN` — a plan-only artifact. It contains **no compiled binary**
  and `alphactl.py install` refuses it.
- `COMPILED_EVIDENCE_VERIFIED` — a binary was staged only after its SHA-256
  matched the PE-002 compile evidence.

Commands (from the extracted tarball, `python3 3.8+`):

```sh
python3 tools/alpha_package/alphactl.py verify-package --root "$PWD"
python3 tools/alpha_package/alphactl.py plan --root "$PWD" --home "$HOME/.local/share"
python3 tools/alpha_package/alphactl.py install --root "$PWD" --home "$HOME/.local/share" --apply
python3 tools/alpha_package/alphactl.py uninstall --root "$PWD" --home "$HOME/.local/share" --apply
python3 tools/alpha_package/alphactl.py rollback --root "$PWD" --home "$HOME/.local/share" --target before --apply
```

Every mutating command without `--apply` is a dry run. `--home` must be an
absolute, non-traversing, user-level XDG data home. Installed files are only:

- `$XDG_DATA_HOME/applications/org.canopy.ClassicPreview.desktop`
- `$XDG_DATA_HOME/canopy/classic-preview/ownership.json`
- `$XDG_DATA_HOME/canopy-alpha/install-state.json` (small restore record)

Install refuses when any managed path already exists: existing configuration
is never overwritten. Uninstall deletes only byte-exact owned files and, if
marker deletion fails, restores the desktop entry's exact bytes and mode.
`rollback --target before` restores the original desktop state;
`--target after` re-creates the recorded installed state. Modified or
unmanaged files are never deleted automatically.

`CHECKSUMS.sha256` covers every packaged file plus `MANIFEST.json`; verify it
before use. Native Linux Mint session, compositor, accessibility and visual
acceptance are **NOT_RUN** until a real guest run is recorded elsewhere.

See `NOTICE.md` for license and redistribution limits and
`docs/ALPHA_PACKAGE_DESIGN.md` for the full contract and known limitations.
