# Classic settings persistence — isolation and rollback contract

Scope: host-side source contract only. The owned files are
`canopy_features/settings/persisted_preferences.py`,
`tests/test_c100_settings_persistence_isolation.py` and this document.
No QML, artwork, icon, wallpaper, dock geometry, typography, colour or theme
file is changed. Nothing here compiles Qt, starts a desktop session or claims
Linux Mint acceptance.

## What changed

### Per-user isolation

* `state_path_for_user(root, user)` returns one absolute state path per
  profile: `<trusted-root>/users/<user>/preferences.json`.
* `user` must be one lowercase ASCII component of at most 64 bytes
  (`[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?`). Traversal (`..`), separators,
  uppercase aliases, NUL, lone surrogates and wrong types raise
  `PersistedPreferencesError`.
* `PersistedPreferences.for_user(root, user)` binds a store to that path and
  to `root`. Two profiles get two distinct files; writing one cannot be read
  back through the other.
* `root` must be an existing directory. Both the constructor and the factory
  reject a missing or non-directory root before touching the filesystem.

### Boundary rejection and no privileged writes

* `PersistedPreferences(path, root=...)` canonicalizes the root and the
  candidate with the existing
  `canopy_features.security.path_jail_checks.resolve_within` contract, then
  requires component-wise containment. Absolute paths outside the root and
  `..` escapes are refused.
* Existing components (including the final state file) are checked with
  `Path.is_symlink()`; a symlinked profile directory or state file is refused
  instead of being read through or replaced. The boundary is re-checked
  immediately before every read and write, not only at construction.
* The legacy absolute `path` form is retained for existing callers but still
  rejects bytes/wrong types, NUL, `..`, symlinked components and obvious
  system-owned locations (`/etc`, `/usr`, `/Windows/System32`, ...). There is
  still no default path and no write at import or on a rejected input.
* A successful save writes a `0o600` temporary file in a `0o700` parent and
  atomically renames it; POSIX mode bits are asserted by the test suite.

### Windows separator normalization (PR #618 QA regression)

PR #618 QA found that a Windows system location could pass the privileged-path
gate when its path was spelled with `/` instead of `\`. The comparison in
`_is_privileged_path` now normalizes both separators before matching the
`_PRIVILEGED_WINDOWS` prefixes, and recognizes a drive-qualified path on the
POSIX host branch as well. `C:/WINDOWS/...`, `C:\WINDOWS\...` and mixed
separator spellings are refused before any filesystem access, while ordinary
user paths and POSIX system paths keep their earlier decisions. The `..`,
absolute-escape and symlink checks are unchanged; they are re-tested with mixed
separators and with all write entry points spied on.

### Surrogate-safe corrupt-state handling

PR #602 review found that a lone-surrogate JSON key decoded by `json.loads`
reached `key.encode("utf-8", "strict")` in `_validate_document`, raising a raw
`UnicodeEncodeError` instead of the documented discard-to-empty behaviour.
`_utf8_key_size()` now returns `None` for an unencodable key, and the document
validator returns an empty mapping. A surrogate key, an unknown key, an
unavailable key, a wrong-typed value, a duplicate key, a bad version, a JSON
constant and an oversized key or document all discard the whole document and
start the store empty.

### Atomic failure rollback

`set()` snapshots the value mapping before saving. Any failure — including a
fault injected at `Path.mkdir` or `os.replace` — restores the in-memory view,
is reported as `PersistedPreferencesError` and leaves the durable file
byte-for-byte unchanged. A failed first write leaves no state file and no
`.canopy-prefs-*` temporary file.

## Verification

Commands were run from the isolated worktree at integration tip `ec4ccc6`
(branch `fix/settings-persistence-isolation-ec4ccc6`). The environment has no
project pytest dependency, so the test runner is uv's isolated pytest with the
repository on `PYTHONPATH`.

RED, final test file run against the untouched integration tip in a separate
detached worktree:

```
PYTHONPATH=. uv run --no-project pytest tests/test_c100_settings_persistence_isolation.py -q
29 failed, 6 passed, 1 skipped, 2 subtests passed in 17.90s
```

The surrogate control failed with
`UnicodeEncodeError: 'utf-8' codec can't encode character '\ud800' in position 0: surrogates not allowed`
at `persisted_preferences.py:244`, proving the reviewed path was real.

GREEN, same command after the module change:

```
PYTHONPATH=. uv run --no-project pytest \
  tests/test_c100_settings_persistence_isolation.py \
  tests/test_c100_settings_persisted_preferences.py -q
43 passed, 1 skipped, 40 subtests passed in 24.05s
```

The pre-existing settings contract file (`test_c100_settings_persisted_preferences.py`,
25 tests / 21 subtests) stayed green unchanged. One skip is the POSIX mode-bit
assertion on Windows, where mode bits are not authoritative.

Full suite at the final exact head, same worktree:

```
PYTHONPATH=. uv run --no-project pytest -q
3445 passed, 46 skipped, 7873 subtests passed in 2158.68s (0:35:58)
```

Exit code 0; no failures. Log SHA-256
`097c17e27ffde282ffcb00a0e820ac41a7b714dad29d2ae6c195faa9b8406ec2`.
The RED log SHA-256 is
`07b84addcf95759d9a45de0f2accf4a07004568b0db858e97b89998629961caf` and the
targeted GREEN log SHA-256 is
`242f57dbe9153ea5ccacdf5e0efb6b6c8ee4f535c20be6ec0fb2fab6b3e494d6`.
`git diff --check` passes.

### PR #618 QA separator regression (exact evidence)

Worktree base: `integration/canopy-classic-20261123` at
`b9d93138a4990aa8fe4544a788af4a704572dd78` (verified with `git ls-remote`);
private feature branch `fix/windows-privileged-path-separators-b9d9313`. The
runner is uv's isolated pytest with the worktree on `PYTHONPATH`; this host has
no project pytest dependency. `os.name` is patched only inside the new tests to
exercise the POSIX host branch on a Windows runner.

RED, new test file against the untouched base worktree:

```
PYTHONPATH=. uv run --no-project pytest tests/test_c100_settings_persistence_isolation.py -q
9 failed, 22 passed, 1 skipped, 35 subtests passed in 1.90s
```

Log SHA-256 `5971954ed6ad950fc817fecd489f02e3844a9bd6781930a3761b7f19ebdb0422`. The nine subtest failures are
`WindowsPrivilegedSeparatorTests.test_windows_system_prefix_matches_either_separator`
(`C:/WINDOWS`, `C:\WINDOWS`, mixed casing and the Program Files / ProgramData
prefixes on the POSIX branch) and
`WindowsPrivilegedSeparatorTests.test_windows_privileged_path_is_refused_without_any_write`
(three separator spellings were accepted by the constructor). The ordinary
user-path and escape/symlink tests were green on base as negative controls;
they were kept as coverage, not claimed as reproduced defects.

GREEN, same host, after the production change:

```
PYTHONPATH=. uv run --no-project pytest \
  tests/test_c100_settings_persistence_isolation.py \
  tests/test_c100_settings_persisted_preferences.py -q
47 passed, 1 skipped, 65 subtests passed in 1.72s
```

Log SHA-256 `47709d46ec015d7db5c2370af7539c807c2c4e3ba79e46349d7ed4256477a56c`. `python3 tools/check_foundation.py` → PASS on the
fixed tree.

Full suite, `PYTHONPATH=. uv run --no-project python -m unittest discover -s tests`,
run in parallel on two private worktrees pinned to the same base SHA:

| tree | result | normalized FAIL/ERROR set SHA-256 | log SHA-256 |
| --- | --- | --- | --- |
| untouched base `b9d9313` | Ran `3524` tests in `1006.209`s; `OK (skipped=46)` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `5ff97a8f10c279f9e358dee63e307d19ebfd4c958ef5265180d6445a677587b1` |
| fixed tree | Ran `3528` tests in `963.590`s; `OK (skipped=46)` | `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` | `ac33839f7a515c26b833e45ebb56d84d82f391359b3b98b15df5bf13d9cfb294` |

The test-file delta is `+4` tests, and the full-suite delta is `+4`
tests; no new failure or error name was introduced. Base failure names:
`none`. Fixed-tree failure names: `none`.
`git diff --check` passes.

Resource / evidence note: measured here are exact test counts, durations and
log SHA-256s from local CPython 3.14.9 gates on Windows 11 (`SYNTHETIC`,
not a compiled-runtime profile). Deliberately not measured: shell-owned PSS,
CPU, GPU, wakeups, compiled Qt render, real Mint session behavior and
screen-reader behavior — all `NOT_RUN`. This is a pure decision gate with no
new allocation path, no service, no visual or accessibility change, so no
stability, security, accessibility or approved-visual tradeoff is made.

## Non-claims

These are source-contract tests. They do not prove that the compiled Qt
settings panel is wired to this module, do not change the approved visual
identity, and do not establish production readiness, security approval or
Linux Mint acceptance.
