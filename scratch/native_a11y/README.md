# Native accessibility verification scratch surface

Owned, bounded evidence surface for the M3/M5 native Plasma accessibility task.
Nothing here contacts the guest VM, starts AT-SPI queries or a screen reader.

- `test_native_role_vocabulary.py` — six RED→GREEN regression checks for the
  native AT-SPI role vocabulary in `screen_reader_metadata.py`.
- `verify_native_a11y.py` — recomputes names, roles, extents, dock labels and
  Alt+F/Escape pixel diffs from already-captured native evidence, scans those
  artifacts for announcement evidence, and probes host VM state to record the
  serialization blocker.
- `native_a11y_verification.json` — generated report (SHA-256 recorded in
  `docs/NATIVE_ACCESSIBILITY.md`).

Run from the worktree root:

```sh
python -m unittest discover -s scratch/native_a11y -p 'test_*.py'
python scratch/native_a11y/verify_native_a11y.py \
  C:/Users/X1/AppData/Local/hermes/cache/scratch \
  scratch/native_a11y/native_a11y_verification.json
```

Scope is `STATIC/CI-SCOPED`. A clean result is not a native run, a
screen-reader announcement, a focus-order pass or visual acceptance.
