# Correction: 1920x1080 launch evidence (PR #737, foundation remediation)

Scope: evidence correction only. No QML/C++/asset/workflow/source change.
Raw evidence files are preserved byte-for-byte; this file supersedes only the
PR-body wording that described the 1920x1080 launch as a measured success.

## Authoritative raw result

`scratch/native_dock_geometry/logs/results.json` (SHA-256
`36fc3e0f0c8c780e1a6764db82a2c41c77bae2208bebb56ce88ef2b929704a48`), lines 7-11:

```json
  {
    "check": "launch_1920x1080",
    "status": "FAIL",
    "detail": "pid=20969 wid=NONE"
  },
```

The same file records `display_1920x1080` as `PASS` with
`VGA-1 connected primary 1920x1080+0+0 ...`, and `PASS` launch/shot rows only
for 1200x750 (`pid=21101 wid=0x03600012`) and 760x500
(`pid=21273 wid=0x03600012`). There is no `shot_1920x1080` row.

## Conflicting raw PID/WID evidence at 1920x1080

All paths below are under `scratch/native_dock_geometry/per_size/1920x1080/`;
hashes are the committed `SHA256SUMS` values.

| File | Exact raw content | SHA-256 |
|---|---|---|
| `classic.pid` | `20969` | `2ff533157902ff7ab1284dde41bc41ab4f607bc959162ce77e575317bcea8455` |
| `identity.txt` | `PID=23795` / `EXE=/home/canopy/native_dock_geometry_20261127/build/canopy-classic-spike` / `WID=0x03800012` | `2c8acfb7c7966d3e513e4ad7a5037e13421075fe669fc99c5421f1c18ef9999d` |
| `window_id.txt` | `0x03600012` | `769b1650e3a6ffc3ddbf31c4791f462639622c70d9b53c91d57c798967376c03` |
| `window_geometry.txt` | `WINDOW=58720274` (= `0x03800012`), `X=360`, `Y=152`, `WIDTH=1200`, `HEIGHT=750`, `SCREEN=0` | `3669ac575d17c29c8b5cd68ea66f4c06bd5a40901d27c9c470f1043ded1a45f5` |
| `wmctrl.txt` | `0x02a00012  0 5667   360  179  1200 750 ...` and `0x03600012  0 13540  360  152  1200 750 ...` | `e4eae9c24c8e1c5ae0080aa1b40dc974566681db912be039404848c6e5e195ff` |
| `screen_sha256.txt` | `f65e95d17b8f5f555efdb51da23f479c0d286bcea7e8f33e613075bee845215f  /home/canopy/native_dock_geometry_20261127/evidence2/screenshots/screen_1920x1080.png` | `6fb58db4ffabcd6357bf96b76da166061ba3780133c23bff641ca2c1a05025ce` |

Three mutually inconsistent PIDs (`20969`, `23795`, `5667`/`13540`) and three
window ids (`NONE`, `0x03600012`, `0x03800012`/`58720274`) are present. The
capture geometry is a 1200x750 window at (360,152) on the 1920x1080 display,
not a 1920x1080 application window.

## Corrected claim

- `display_1920x1080`: **PASS** (xrandr raw line above).
- `launch_1920x1080`: **FAIL** per authoritative `results.json`, detail
  `pid=20969 wid=NONE`; the conflicting PID/WID artifacts are NOT evidence of a
  successful 1920x1080 launch and are not reconciled here.
- The committed `screen_1920x1080.png` (SHA-256
  `f65e95d17b8f5f555efdb51da23f479c0d286bcea7e8f33e613075bee845215f`) is real
  pixel evidence of a captured 1200x750 window on that display; the scoped
  pixel measurement of that window remains 32/96/14/7. No successful
  1920x1080 launch, full-screen capture, or three-of-three launch PASS is
  claimed anywhere in PR #737.
- No new guest session was launched for this correction; measurement rerun is
  over the committed pixels at the exact remediation head.
