# Shell Pack starter — metadata and QML template only

This **does not run inside Canopy today**. A secure Shell Host API,
pack loader, installation and session switcher have not been built yet.

To begin a new shell, copy this folder, set a **unique nonreserved** `id`
in `manifest.json`, choose valid capabilities and replace `ui/Main.qml`
with original artwork and accessible UI. Avoid implementing duplicate
notification daemons, system services or compositors.

Check the manifest before review:

```sh
python3 tools/check_shell_pack.py examples/shell-pack-starter
python3 -m unittest tests.test_shell_pack -v
```

A passing manifest check does not verify code safety, visuals, Mint
compatibility or runtime switchability. Do not load untrusted QML based on
metadata alone; eventual community packs require signed packages,
capability isolation, review and rollback.

See [the draft Shell Pack specification](../../docs/SHELL_PACK_ARCHITECTURE.md).
