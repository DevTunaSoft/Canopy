# Native catalog refresh bridge (PE-076)

`canopy_features/catalog/native_catalog_refresh.py` is a pure in-process bridge
from the existing protocol-v2 `app.catalog.changed` topic into the launcher
catalog and the missing-application availability tracker. It is not compiled
wiring: no QML, C++, asset, icon, wallpaper, dock geometry or visual state is
touched.

## Contract

- The bridge grants one exact host **source identity** the single existing
  topic through `canopy_core.event_trust.EventTrustBoundary`. Untrusted
  sources, unknown topics, malformed or oversized payloads are rejected with
  fixed tokens before any refresh.
- One accepted event causes **at most one** call to the existing read-only
  `native_catalog_producer.produce_catalog_bytes()`. There is no timer, poll,
  thread or implicit source discovery. A bounded budget (`MAX_REFRESH_EVENTS`)
  freezes further refreshes with `refresh_limit`.
- The freshly produced wire becomes the bridge's host-visible snapshot and is
  projected into an immutable `LauncherCatalogSnapshot` for `search_catalog`
  and launch previews. Installed ids are recorded as authoritative
  observations; removed ids become unavailable.
- **Positive TryExec and read facts are required.** A trusted `fact_source`
  supplies real `tryexec_ok` / `entry_readable` booleans. If it is absent,
  raises, or returns a non-boolean shape, the fact is unknown and the
  observation denies launch permission. Catalog presence alone is never a
  launch approval.
- Producer refusal (hostile or oversized entry, unreadable source) is atomic:
  the previous wire bytes and availability states stay byte-identical, and the
  report carries `snapshot_refused` with counts only.
- Reports and tracker diagnostics carry counts and fixed reason/claim tokens
  only — no application id, title, TryExec path or URL is echoed.

The same fact requirement is enforced in the tracker's probe path:
`missing_app_availability._probe_facts()` rejects a mapping that omits
`tryexec_ok` or `entry_readable` instead of defaulting them to `True`. The
merged PR-684 behavior for complete facts (full mapping and the historical
bool shorthand) is preserved. `tests/test_pe063_missing_app_availability.py`
pins the NC-05 regression and `tests/test_pe076_native_catalog_refresh.py`
covers NC-01/02/03/04/07/08/09 plus bounds and no-text diagnostics.

`SYNTHETIC`: targeted unittest runs use finite temp directories and no host
probe. `NOT_RUN`: full suite, compiled Qt, Mint guest, real desktop, screen
reader and visual acceptance.
