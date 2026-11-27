# Wallpaper change path source contract (PE-100)

## Scope

`canopy_features/settings/wallpaper_change_path.py` is a pure, read-only source
contract at the existing wallpaper-selection boundary. It answers one question:
is a caller-supplied **change of wallpaper path** provably limited to the two
approved wallpaper choices, with the exact approved manifest digest?

It is not a runtime wallpaper setter, a Qt binding, a manifest editor or an
asset generator. It opens no file, socket, process or timer, retains no state,
and changes no asset, default, QML, C++, workflow or protected path. It makes
no visual, Mint-guest, acceptance or owner-approval claim.

## Exact pins

| Field | Exact value |
|---|---|
| Approved default path | `prototype/classic/assets/approved/wallpaper/Canopy_Classic_Master_Wallpaper_1920x1080.png` |
| Approved default SHA-256 | `8c6cab50a0977fc129c0d2a20523d9361646f36da66f2f3f2b2436a0d9001381` |
| Manifest wallpaper role path | `prototype/classic/assets/approved/wallpaper/canopy-wave-preview.png` |
| Manifest wallpaper role SHA-256 | `1efa6e83deee160ce9cf225db010025f4f162975f4dfc23e6da3f3ca0973528a` |
| Approved manifest | `prototype/classic/assets/approved/manifest.json` |
| Manifest SHA-256 | `5aa040ddbfeddbd38dcbd1808710676982efbc4146987c42e93eaa57ad0d4737` |
| Wallpaper role | `wallpaper` |
| Sources | `approved-default`, `manifest-wallpaper-role` |

The path/hash/source triple is bound: an approved icon hash presented under a
wallpaper path is refused, the second byte-identical source-tree master alias
is not an approved endpoint, and a source label cannot be swapped between the
two approved records. The caller supplies the manifest digest; this module
compares it to the pin and never reads or edits the manifest.

## Input and output

`validate_wallpaper_change(request)` accepts a mapping with exactly:

- `current`: endpoint mapping (`path`, `sha256`, `role`, `source`);
- `proposed`: endpoint mapping with the same four fields;
- `manifest_sha256`: exact lowercase hex digest.

It returns an immutable `WallpaperChangeDecision` with `current`, `proposed`,
`manifest_sha256` and `direction`. `direction` is one of
`approved-default->manifest-wallpaper-role` or the reverse. There is no
side effect and no application of the change.

Refusals are `WallpaperChangeError` (a `ValueError`) with a stable `code`:

- request shape: `REQUEST_KEYS`;
- endpoint shape or unreadable value: `ENDPOINT_KEYS`;
- manifest pin: `MANIFEST_DIGEST`;
- malformed digest: `BAD_HASH`;
- path/field type, length or unsafe Unicode: `PATH`, `ROLE`, `SOURCE`;
- unknown path: `UNKNOWN_PATH`;
- hash not bound to the path: `HASH_MISMATCH`;
- wrong role/source binding: `ROLE`, `SOURCE`;
- identical endpoints: `NO_OP`.

Bounds: 240 characters per path, 64 per role/source/digest, 64 lowercase hex
digits for both digests, exactly three request fields and four endpoint fields.
Control, format, surrogate, private-use, unassigned and line/paragraph
separator characters are refused before any whitespace folding. Mappings are
gated with `collections.abc.Mapping`; unreadable keys or values fail closed with
the domain error instead of leaking `KeyError` or `TypeError`.

## Distinct scope

- PR #687 / PE-066 owns `canopy_features/settings/wallpaper_selection.py` and
  `tests/test_wallpaper_selection.py`. This change does not import, modify or
  duplicate either path.
- PE-088 is a read-only manifest audit. The manifest's historical wave role,
  the two master aliases and the compiled `main.cpp`/`Main.qml` chain are left
  untouched; no schema-version change or role reassignment is attempted.
- No visual/QML/C++/asset/workflow/protected file is in this change's scope.

## Verification and resources

Targeted tests: `tests/test_pe100_wallpaper_change_path.py` (25 tests).
Combined read-only neighbors at the same head: 64 tests, all OK. An untouched
base worktree at the same tip ran the 39 neighbor tests, all OK: the delta is
exactly the 25 new tests with an empty FAIL/ERROR set on both sides.
`tools/check_visual_lock.py --root .` reports
`AWAITING_CHATGPT_VISUAL_APPROVAL problems=0`, unchanged from base.
`tools/check_wallpaper.py verify --root .` reports `WALLPAPER_CHECK PASS problems=0`.
Raw logs and an evidence ledger with SHA-256 sidecars live in
`C:/Users/X1/Projects/Canopy/scratch/master_directive_20261126/evidence/wallpaper_change_validation/`.

Resource / evidence note:

- Measured: **SYNTHETIC** — bounded pure-Python unittest counts and log bytes on
  the Windows host. Work per call is constant (two endpoint records, one digest
  comparison); there is no retained state, polling, cache or background wakeup.
- Not measured: **NOT_RUN** — full suite, compiled Qt, Mint guest, real desktop
  and any wallpaper change through a running shell.
- Screen reader: **NOT_RUN** — no accessibility, announcement or visual path is
  touched.
- No stability, security, accessibility or approved-visual trade-off is made
  for a resource gain; no visual approval is claimed.
