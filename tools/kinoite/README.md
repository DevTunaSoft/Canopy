# Kinoite validation tools

Two stdlib-only scripts support `docs/LACOS_KINOITE_VALIDATION.md`:

```sh
python3 tools/kinoite/fetch_sources.py --out scratch/kinoite_validation
python3 tools/kinoite/validate_evidence.py --worktree . --out scratch/kinoite_validation
```

`fetch_sources.py` retrieves only official upstream URLs (Fedora, Flatpak,
freedesktop.org, KDE, libostree, rpm-ostree and the upstream SDDM repository),
stores each response with LF-normalized line endings and builds a whitespace-normalized text projection
plus `sources.json` with HTTP status, final URL and digests.

`validate_evidence.py` checks verbatim quotes for every load-bearing claim,
re-executes the host-side Canopy planner dry-runs, probes for a Fedora Kinoite
runtime, scans tracked code for LacOS dependencies, and writes
`evidence_matrix.{json,md}` and `SHA256SUMS.txt`. It never starts a VM, changes a
system file or claims a native Kinoite result. A `PASS` from this gate means the
static/host evidence is intact; native runtime checks remain `NOT RUN` when no
disposable Kinoite environment is available.

`--exact-head SHA` stamps the single authoritative final-head field
(`exact_head`) on the evidence; without it the gate defaults to `git HEAD`.
`--reviewed-head SHA` retains the earlier reviewed head as `reviewed_head`
provenance only and is never used as `exact_head`. Regenerate after any commit
that changes the owned evidence paths, then verify `sha256sum -c SHA256SUMS.txt`
(47 artifacts).
