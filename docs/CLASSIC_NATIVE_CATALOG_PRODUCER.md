# Classic native launcher catalog producer

Status: **implemented, offline-only**. Base: `97a151b` (exact integration tip
`integration/canopy-classic-20261123` at task start). This change owns only
`canopy_features/launcher/native_catalog_producer.py`,
`tests/test_c100_native_catalog_producer.py` and this document. It touches no
compiled runtime, `main.cpp`, `CMakeLists.txt`, approved asset, PR #279 path,
workflow or another agent's file. The approved Classic visual identity is
unchanged: this module emits bytes; it renders nothing.

## Purpose

`produce_catalog_bytes(applications_dir)` is the read-only host-side producer
for the existing guarded compiled bridge described in
[CLASSIC_LAUNCHER_RUNTIME_CATALOG.md](CLASSIC_LAUNCHER_RUNTIME_CATALOG.md).
The caller supplies one explicit, absolute `XDG_DATA_HOME/applications`
directory; the module never guesses a home, expands `~`, scans a real host
path, globs, walks recursively, launches a process or opens a socket.

## Exact wire contract

`LauncherCatalogModel::loadFromFile` accepts one headerless UTF-8 file of
`app_id<TAB>title<LF>` rows. The producer emits exactly that:

- one ASCII `app_id` matching the existing `DESKTOP_ID` grammar
  (`[A-Za-z0-9][A-Za-z0-9._-]*\.desktop`), taken from the regular filename;
- one literal tab, then the validated `Name` from the desktop entry;
- one LF terminator per row, no header, no blank lines, no CR, no NUL and no
  trailing bytes;
- rows sorted by `app_id`, so byte output is deterministic and independent of
  directory iteration order or hash seed;
- the whole snapshot is built in memory and returned only after every source
  passes; a refusal returns no partial bytes and writes no file.

## Bounds

| Guard | Limit | Refusal |
| --- | --- | --- |
| Directory entries scanned | 512 (refuse at 513) | counted one at a time from `scandir`; at most 512 names retained, before any file body is read |
| Filename characters | 256 | fail closed |
| Per-entry bytes | 64 KiB (parser default) | bounded read of limit + 1, then refuse |
| Catalog rows | 1024 (`MAX_ENTRIES`) | existing ingest contract refuses |
| Title characters | 256 (`MAX_TITLE_CHARS`) | existing ingest contract refuses |
| Total snapshot bytes | 64 KiB | refuse before returning |

Only immediate children are considered. A subdirectory is never descended
into; the name/symlink checks run in this order — length, character and
desktop-id grammar first, then `lstat` on names that match the grammar. An
entry whose name is not a valid desktop id is therefore skipped before any
`lstat` or symlink check, so a non-`.desktop` file is never stat'ed. All caller
bounds are strict `int` values inside those ceilings, so a host cannot raise
them past the compiled model's limits.

## Refusals and negative controls

- Every path component and the root itself is checked with `lstat`; a symlink
  is refused, never followed. Each candidate desktop entry is checked again
  before an `O_NOFOLLOW` bounded read, so a symlink inside the directory cannot
  redirect the read outside the synthetic tree.
- The root must be absolute and named `applications`; a relative path, a wrong
  basename, a control character in the path, a missing path or a non-directory
  is refused.
- A filename that is not a valid desktop id is never emitted. Hostile names
  (spaces, URL-like text, control characters) cannot enter the bridge.
- Invalid UTF-8, NUL, CR, tabs, bidi/control scalars, duplicate keys, wrong
  `Type`, missing `Exec`, malformed key syntax, oversized files and invalid
  categories are refused by the existing parser/ingest contracts. Error text
  is generic: no source token, URL or credential marker is echoed.
- `Hidden`/`NoDisplay` entries are counted and skipped by the existing ingest
  contract; their titles never reach the emitted bytes.
- An empty snapshot is refused because the compiled model also rejects an
  empty file; the approved hard-coded launcher catalogue stays authoritative
  until a valid opt-in snapshot is supplied.

## Ownership and reuse

The producer reuses `desktop_entry_parser.parse()` for entry parsing and
`launcher_catalog_ingest.compose_launcher_catalog()` for validation,
hidden-entry filtering, first-wins duplicate handling and fixed negative
claims. It does not reimplement either contract and does not modify
`prototype/classic/LauncherModel.*`. Wiring an emitted file into the compiled
host remains the separate, owner-locked integration step already documented
in `CLASSIC_LAUNCHER_RUNTIME_CATALOG.md`.

## Verification and labels

Targeted commands (from the worktree root) at the final head, all exit 0:

```text
python -m unittest tests.test_c100_native_catalog_producer -v
Ran 16 tests in 8.317s
OK
python tools/check_foundation.py
PASS: foundation files, tagline, and local Markdown links
python -m py_compile canopy_features/launcher/native_catalog_producer.py tests/test_c100_native_catalog_producer.py
(exit 0, no output)
```

`SYNTHETIC` RED/GREEN negative control: the new test creates 1000 synthetic
names in a fresh temp directory and wraps `os.scandir` with a finite counting
proxy. On the untouched base it failed with `AssertionError: 1000 != 513` —
every name was materialized before the cap was checked. After the incremental
count fix it passed with exactly 513 consumed entries (`MAX_DIRECTORY_ENTRIES`
+ 1), no partial bytes or output file, and a byte-identical tree. The other 15
tests are unchanged and still pass.
Full `unittest discover -s tests` is `NOT_RUN` as authoring evidence here: the
local run exceeded a 600-second foreground limit on this host. All fixtures
are fresh `tempfile.TemporaryDirectory()` trees; no test reads a real host
`XDG_DATA_HOME`, no network endpoint, no privileged operation and no compiled
Qt binary.

Producer SHA-256 of the committed LF blob (`git show HEAD:<path> | sha256sum`):
`b48fffff5aefb62abe3981013a03f128e01cd45b29b380a36cdccb480a3088bb`.
Test SHA-256 of the committed LF blob:
`afc713436398ec9daaa77cac97265b77bacbbd9c489363b8863c694376ee5f42`.
The worktree files are CRLF under `core.autocrlf=true`; their byte SHA-256
values are `9c3f0fdf7d4e517eda36fbf81cdb092dce4fb44a59028c2b1c1232ac1fca82e7`
and `9d11aad5913c34f2d0bb0f446c09638186d1702640acec4be991d2353971ec01`.

- `SYNTHETIC` — unittest evidence from synthetic temp directories only,
  including byte-for-byte TSV assertions, bounds at their edges, symlink
  refusal, hostile-name/content negative controls and no-write snapshots.
- `NOT_RUN` — real Mint desktop session, real host desktop-entry discovery,
  compiled Qt bridge wiring at this head, real PSS/CPU profile, screen-reader
  session and owner visual acceptance. No acceptance verdict is claimed for
  any of them.

Resource impact: `SYNTHETIC` bounded work only — one directory scan capped at
512 names, at most 64 KiB read and one 64 KiB returned bytes object, performed
only on an explicit call. There is no timer, cache, polling, background wakeup
or retained state, and no continuous work is added. The module has no UI,
icon, geometry or announcement surface; screen-reader behaviour is unchanged
because nothing is rendered or announced. No stability, security,
accessibility or approved-visual tradeoff is made for a minor gain.
