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

## Non-claims

These are source-contract tests. They do not prove that the compiled Qt
settings panel is wired to this module, do not change the approved visual
identity, and do not establish production readiness, security approval or
Linux Mint acceptance.
