# Stale-base / sibling-coverage gate (PE-112)

`tools/qa/stale_base_gate.py` is a pure-Python, read-only gate for detecting a
PR head that is not based on the current integration tip, or that silently
loses declared sibling test coverage. It complements `pr_dependency_gate.py`:
the dependency gate orders merges, this gate checks the *content* of a head.

## Why this gate exists

A PR branched before a sibling's test merged can show a clean three-dot diff
and pass every check while still carrying the pre-merge version of that test —
or omitting it entirely, because it never existed at the branch point. A clean
`git merge-tree` is not proof that the head preserves the tip's regression
coverage. This gate compares the head's sibling blobs directly to the tip's
blobs and requires the tip to be the head's merge base.

## Input boundary

The production module is intentionally inert:

- no network request, no subprocess, no git command;
- no repository read beyond the explicit snapshot file;
- no source mutation, no writes of any kind;
- bounded, absolute, non-symlink JSON input with duplicate-key rejection.

Git blob input is collected only in the test-only adapter
`tests/stale_base_gate_adapter.py`, which uses `subprocess.run` with argv lists
(`shell=False`) to read `git merge-base` and raw blob bytes via `git cat-file`.
Blob identity is SHA-256 of the raw bytes, so the gate is independent of a
repository's object hash algorithm. A missing path is represented as `null`.

Snapshot schema (version 1), all keys required, no extras:

```json
{
  "schema": 1,
  "integration_tip": "<40-hex commit sha>",
  "head": "<40-hex commit sha>",
  "merge_base": "<40-hex commit sha, or null for unrelated histories>",
  "siblings": [
    {
      "path": "tests/test_example.py",
      "tip_blob": "<64-hex sha-256 of blob bytes at the tip>",
      "head_blob": "<64-hex sha-256 of blob bytes at the head, or null>"
    }
  ]
}
```

Sibling paths must be relative POSIX-style paths under `tests/`, end in `.py`,
contain no empty/`.`/`..` segments, no backslashes, no non-ASCII or control
characters, and must be unique. At most 256 siblings and 131072 snapshot bytes
are accepted. Any violation raises `StaleBaseGateError` (fail closed).

## Rules and exit codes

| Condition | Finding | Meaning |
| --- | --- | --- |
| `merge_base != integration_tip` (or `null`) | `STALE_BASE` | Head was not based on the current integration tip |
| `head_blob == null` | `SIBLING_ABSENT` | Declared sibling test is missing from the head |
| `head_blob != tip_blob` | `SIBLING_CHANGED` | Declared sibling test bytes differ from the tip |

Findings are sorted by `(code, path)` and the report is deterministic.
`verdict` is `FAIL` when any finding exists, otherwise `PASS`.

```
python tools/qa/stale_base_gate.py --snapshot /absolute/path/snapshot.json
```

Exit `0` = PASS, `1` = findings (FAIL), `2` = malformed snapshot or usage error.
On exit `2` the report is not emitted and a fixed `MALFORMED_SNAPSHOT` token is
written to stderr. The report hardcodes `merge`, `release`, `visual` and `mint`
approvals to `false`: a PASS is a narrow source-fact check, never merge or
release authorization.

## Tests and evidence

- `tests/test_stale_base_gate.py` — pure unit tests, no subprocess.
- `tests/stale_base_gate_adapter.py` — the only subprocess user; builds small
  local git fixtures and collects real blobs.
- `tests/test_stale_base_gate_adapter.py` — adapter-backed RED/GREEN control
  proving a stale head that omits and changes siblings is flagged, and a
  current head that preserves them passes.

Run with:

```
PYTHONPATH=<repo-root> python -m unittest discover -s tests -p 'test_stale_base_gate*.py' -v
```

Resource impact: the gate allocates at most two bounded dicts per sibling and
one 131072-byte read buffer (`SYNTHETIC` micro-workload; no real-desktop RSS
measurement). Screen-reader behavior: `NOT_RUN` — no UI surface is touched.
Real Mint runtime, compiled Qt and CI-on-guest behavior: `NOT_RUN`.
