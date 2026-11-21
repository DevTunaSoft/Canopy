# Original approved icon verification — attempt 1

**Result: BLOCKED.** The eight owner-approved PNG masters are not present in
this checkout, so read-only hash verification could not be performed. The
SHA manifest was located only as a reference in a remote branch; it does not
contain the artwork bytes required to compute hashes. No artwork was
regenerated, replaced, or modified.

## Context

- Branch: `feat/canopy-supervisor-original-icon-verification-attempt-1`
- Commit: `80b8dcb711ba80ac7eee9b1187156ae900251069`
- `git status --short`: clean
- Audit tool inspected: `tools/audit_approved_icon_optics.py`
  - Requires `--approved-art-dir` containing `icons/<name>.png` for exactly
    eight icons and a `--manifest` JSON with a `sha256` per icon.
  - Pure stdlib; decodes bounded 8-bit RGBA PNGs and compares SHA-256 of the
    original file bytes. It never writes artwork.

## Lookup commands and exact output

All commands were run from the worktree root.

### 1. Worktree state

```
$ git branch --show-current; git rev-parse HEAD; git status --short
feat/canopy-supervisor-original-icon-verification-attempt-1
80b8dcb711ba80ac7eee9b1187156ae900251069
```

### 2. Tracked files matching icon/master patterns

```
$ git ls-files | Select-String -Pattern 'manifest.json|approved|icons/|\.png$|classic/prototype'

examples/shell-pack-starter/manifest.json
tests/test_approved_icon_optics.py
tools/audit_approved_icon_optics.py
```

`examples/shell-pack-starter/manifest.json` is a shell-pack metadata example
(`org.example.canopy.minimal`), not the icon manifest.

### 3. Filesystem search for masters, manifest, and directories

```
$ Get-ChildItem -Recurse -File -Filter 'manifest.json' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
C:\Users\X1\AppData\Local\Temp\opencode\supervisor-canopy-state\worktrees\original-icon-verification-attempt-1\examples\shell-pack-starter\manifest.json
$ Get-ChildItem -Recurse -File -Filter '*.png' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName
(no output — zero PNG files in checkout)
$ Get-ChildItem -Recurse -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'approved|icons' } | Select-Object -ExpandProperty FullName
(no output — no approved/icons directories in checkout)
```

### 4. Remote-branch reference inspection (read-only `git ls-tree`, no checkout)

```
$ git ls-tree -r --name-only origin/feature/classic-exact-approved-art-runtime-20261120 | Select-String -Pattern 'manifest.json|\.png$|approved'
prototype/classic/assets/approved/manifest.json
tests/test_approved_art.py
tools/prepare_approved_art.py

$ git ls-tree -r --name-only origin/feature/classic-exact-approved-art-runtime-20261120 | Select-String -Pattern '\.png$'
(no output — that branch tree also contains zero PNG masters)
```

### 5. Located SHA manifest (reference only)

```
$ git show origin/feature/classic-exact-approved-art-runtime-20261120:prototype/classic/assets/approved/manifest.json
{
  "schema_version": 1,
  "source": "The exact eight PNG crops of the user-supplied Canopy Classic approved selection sheet, 2026-11-20; the accompanying wave PNG was used in the subsequently accepted visual concept, not an Apple asset.",
  "artwork_policy": "No redesign, recoloring, JPEG recompression or substitution. SHA-256 of original file bytes must match.",
  "icons": [
    { "name": "Browser",   "path": "icons/Browser_Option_3.png",   "sha256": "28283672dec0621172f3cf793dc6f00174fdce944d986ff144a1d2d1a881469a" },
    { "name": "Mail",      "path": "icons/Mail_Option_5.png",      "sha256": "7baad00f0ddd507b1def24dc067e949e32991e3db06d246bf3a61ec9eaf98b79" },
    { "name": "Files",     "path": "icons/Files_Option_2.png",     "sha256": "aa659307d1a5273fdaa61a9df6f8f70546882d6e89b1380b23ff0f9eb59bf57b" },
    { "name": "Calendar",  "path": "icons/Calendar_Option_3.png",  "sha256": "c99c3356a178f8d0a28c809fada712c8df571c12db8d0f3472521f732fa559b2" },
    { "name": "Photos",    "path": "icons/Photos_Option_2.png",    "sha256": "8ed643b8f67e676ae1ffddfd997cc1156fbc859acfd1e9c935c2b9085e11fc5f" },
    { "name": "Music",     "path": "icons/Music_Option_3.png",     "sha256": "57ca966467597ad0ea8485b51701d8856b2584dd3b28bd194010ffeed149c43f" },
    { "name": "Terminal",  "path": "icons/Terminal_Option_4.png",  "sha256": "40473e715b42037d2619c87e37fa1757419b6a1cdf99cb9ce5236d6bbfd929a5" },
    { "name": "Settings",  "path": "icons/Settings_Option_8.png",  "sha256": "7ee4434d0acf34c676a3d3d908ee363b2553228debd5f7157b3693f7faee6a79" }
  ],
  "wallpaper": {
    "name": "Blue wave visual reference",
    "path": "wallpaper/canopy-wave-preview.png",
    "sha256": "1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a"
  }
}
```

`docs/ICON_OPTICAL_REVIEW.md` and `docs/MINT_CLASSIC_QT_SMOKE.md` state the
original masters come from the owner's verified asset bundle and are not
embedded or republished in this public repository. That matches the lookup
results: digests exist, artwork bytes do not.

## Verification attempt

```
$ python tools/audit_approved_icon_optics.py --approved-art-dir prototype/classic/assets/approved --manifest prototype/classic/assets/approved/manifest.json
CANOPY_ICON_OPTICS_FAIL: approved directory and manifest must be regular paths
EXIT_CODE=1
```

Result: **BLOCKED** — no masters to hash. The tool itself is functional
(unit tests below), but it cannot verify artwork absent from this checkout.

## Tests

```
$ python -m unittest tests.test_approved_icon_optics -v
Ran 17 tests in 1.835s

OK
EXIT_CODE=0
```

PASS — 17/17 tests. These use synthetic PNG fixtures and validate the audit
tool's hashing/decoding/rejection behavior; they are not evidence that the
eight real masters were verified.

## Acceptance status

- Eight master PNGs present in checkout: **BLOCKED** (zero PNG files found).
- SHA manifest located: **yes**, as a reference in a remote branch only.
- Read-only hash verification of real masters: **BLOCKED**.
- Artwork modified/regenerated/replaced: **no**.
- Owner visual approval: **out of scope / not performed**.

## Next step to unblock

Place the eight unmodified masters at
`prototype/classic/assets/approved/icons/<name>.png` with the manifest at
`prototype/classic/assets/approved/manifest.json`, then run:

```
python3 tools/audit_approved_icon_optics.py \
  --approved-art-dir prototype/classic/assets/approved \
  --manifest prototype/classic/assets/approved/manifest.json \
  --output icon-optics-report.json
```
