# Launcher enumeration source contract

Status: **implemented, pure-Python only**. Base: `b3af78fec35caffa7ede16c5dc0e67c0bae4eeac`
(exact tip of `integration/canopy-classic-20261123` at task start). This change
owns exactly three files:

- `canopy_features/launcher/launcher_enumeration_sources.py`
- `tests/test_pe095_launcher_enumeration_sources.py`
- this document

It touches no compiled runtime, `main.cpp`, `CMakeLists.txt`, QML, approved
asset, wallpaper, dock geometry, workflow or protected file. The approved
Classic visual identity is unchanged: this module describes inputs; it renders
nothing.

## Purpose and scope boundary

`describe_enumeration_sources(sources)` converts a caller-supplied, finite,
ordered set of source descriptors into one immutable, deterministic snapshot of
the enumeration sources a launcher may use. It answers only *which sources are
admissible and under what caps*. It does not enumerate a directory, read a
desktop entry, emit catalog bytes or change a running process.

It is deliberately distinct from two adjacent efforts:

| Effort | Concern | Why this change does not overlap |
| --- | --- | --- |
| PR #694 — native catalog refresh bridge | Converts trusted `app.catalog.changed` host events into bounded producer calls and wire bytes | This module takes no event, calls no producer and emits no bytes; it defines the source-shape a future consumer may pass in |
| PR #696 — compiled refresh boundary test | Characterizes that the single-load compiled bridge cannot reload a running snapshot | This is a production module with its own contract tests, not a characterization of compiled behavior |

No path from either PR is imported or modified. The new module contains no
directory scan, file open, event subscription, process launch, timer, network
call or visual operation.

## Input shape

`sources` must be a finite ordered `Sequence` (for example a `list` or
`tuple`). Unordered containers (`set`, `frozenset`, set-like views), mappings,
strings, bytes, scalars and one-shot iterators are refused. Each element is a
`Mapping` with:

- `role`: one of `explicit`, `xdg_data_dirs`, `xdg_data_home`;
- `path`: an explicit absolute path as text (either POSIX-rooted or
  drive-qualified Windows form);
- `max_entries`: optional strict `int` cap for that source, defaulting to
  `MAX_ENTRIES_PER_SOURCE`.

Duplicate `(role, path)` pairs are refused. Two different paths may share a
role, so a multi-directory `xdg_data_dirs` configuration is representable.
Sources are returned in fixed role-then-path order, independent of input order
and `PYTHONHASHSEED`.

## Bounds

| Guard | Ceiling | Refusal |
| --- | --- | --- |
| Sources | 8 (`MAX_SOURCES`) | counted one at a time; refuse at the first excess, before later descriptors are validated |
| Path length | 512 characters (`MAX_PATH_CHARS`) | fail closed on the exact stored string, never on a re-derived value |
| Per-source entries | 512 (`MAX_ENTRIES_PER_SOURCE`) | strict `int`, `1..ceiling` |
| Total entries across sources | 1024 (`MAX_TOTAL_ENTRIES`) | cross-field sum of per-source caps must fit, refusing an oversized catalog before any snapshot is returned |
| Roles | 3 allowlisted values | any other role is refused |

All caller bounds are strict `int` values inside those ceilings: `bool`,
`float`, `str`, `None` and values above the ceiling are refused, so a caller
cannot widen the contract past the producer's limits. Bounds may only be
*tightened*.

## Fixed negative claims

Every snapshot carries these tokens, all of which are true by construction:

`no_implicit_discovery`, `no_symlink_follow`, `no_recursive_walk`,
`no_duplicate_sources`, `no_unbounded_growth`, `no_filesystem_io`,
`no_process_launch`, `no_visual_change`.

No implicit home, environment lookup, glob, `~` expansion, symlink resolution
or recursive traversal occurs. Paths are validated textually and are never
resolved or stat'ed; symlink and recursion safety is therefore a property of
this contract, not a claim about a real host path.

## Fail-closed diagnostics

- Wrong container types, wrong descriptor types, unknown or duplicated keys,
  non-string keys, incomplete descriptors and unreadable mappings all raise
  `EnumerationSourceError`. A custom `Mapping` whose `__getitem__` disagrees
  with `keys()` produces the domain error, never a raw `KeyError`; any
  exception raised by a hostile `__getitem__` or `keys()` (including
  `OSError`, `ValueError` and `RuntimeError`) is likewise translated to the
  domain error with no caller text echoed.
- Control, format, surrogate, private-use, noncharacter and line-separator
  scalars in a path are rejected before the path is stored. Traversal
  components (`..`, with either separator) and relative paths are refused.
- `to_dict()` returns counts, per-source caps and claim tokens only. No role,
  path or caller-supplied text is echoed into a log or host bridge.
- Refusals are atomic: a bad source late in the sequence returns no partial
  snapshot and retains no state.

## Verification and resource impact

Targeted tests: `python -m unittest tests.test_pe095_launcher_enumeration_sources -v`.
RED at the unfixed base is an import error; GREEN at the exact head is 26 tests
(23 original contract tests plus 3 hostile-`Mapping` regression controls),
`OK`, with no skip. An untouched worktree at the same base is used for the
related-module baseline; no pre-existing failure is attributed to this change.
The re-pinned head also runs the 126 restored sibling tests from the five
integration test modules that were absent at the stale branch point.

- Measured: **SYNTHETIC** — bounded pure-Python unittest counts and log bytes
  on the Windows host. The source list is finite and bounded; per-call work is
  O(sources) with no retained state.
- Not measured: **NOT_RUN** — full suite (left to CI), compiled Qt, Mint guest,
  real desktop and screen reader.
- Screen reader: **NOT_RUN** — this module touches no accessibility,
  announcement or visual path.
- Rationale: the module adds no persistent worker, poll, timer, cache or
  background wakeup and no stability, security, accessibility or approved
  visual trade-off is made for a gain.

Boundary: pure source-contract code and tests only. No compiled-host consumer,
Mint acceptance or visual approval is claimed.
