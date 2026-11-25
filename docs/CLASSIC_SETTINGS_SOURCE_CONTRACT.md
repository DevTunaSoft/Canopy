# Classic settings panel — source contract

The Classic settings panel (`prototype/classic/SettingsPanel.qml`) is a
read-only presentation of host-owned decisions. It declares no new event
topic, performs no privileged write, and does not change the approved visual
identity. `canopy_features/settings/persisted_preferences.py` is the matching
pure host-side contract; `tests/test_c100_settings_persisted_preferences.py`
holds its source-contract checks.

## Host event topic identity

`canopy_core.host_events` protocol v2 is pinned to exactly four topics by
`docs/HOST_EVENT_CONTRACT.md`:

- `app.catalog.changed`
- `window.state.changed`
- `session.state.changed`
- `capabilities.report`

The settings module loads that source through
`checked_host_event_topics(topics)`, which returns the approved immutable set
only when the input is unique **and** equal to that exact set. Import fails
closed with `RuntimeError` on any drift; direct callers get the module's
`PersistedPreferencesError`. The validated set is published as
`HOST_EVENT_TOPICS`.

A length check plus one membership check is not an exact-set claim. A source
of four entries that duplicates `window.state.changed`, omits
`session.state.changed` and still contains `capabilities.report` passes both
old checks; so does a four-entry source that swaps an approved topic for an
unapproved one. `tests/test_c100_settings_persisted_preferences.py` feeds both
shapes to a fresh module import and to the gate as negative controls, and
asserts the approved set is unchanged on the real source. Those controls were
red against the pre-guard source and green after the guard landed.

## Writes and identity

Only `reduced_motion` is available, with the value domain already owned by
`canopy_features.accessibility.reduced_motion_contract`. Every other row is a
disclosed placeholder backed by existing `quick_controls_state` text. Writes
go only to a caller-supplied path through an atomic replace; there is no
default path, no privileged location and no write at import or on a rejected
input. Available disclosures explicitly state that approved preview visuals
do not change; no icon, wallpaper, dock geometry, typography or colour is
touched by this contract.

The negative controls are source-level only: they import a fresh module
against crafted topic data and check that no `Path.write_bytes`, `mkdir`,
`os.replace` or `os.chmod` call occurs. They do not compile Qt, launch a
desktop session or claim Mint acceptance.
