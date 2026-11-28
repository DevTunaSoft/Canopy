# Independent tester helpers

These files support `docs/NATIVE_TESTER_WALKTHROUGH.md`. They are tester-side
only: no product source, QML, asset, workflow or protected path is modified.

- `native_tester_guest.sh` — guest-side walkthrough: artifact identity, unpack,
  user-scope `kpackagetool6` install/verify, compiled-binary self-tests
  (offscreen), Terminal GIO launch fixture, D-Bus owner guard, settings
  persistence, uninstall and stock-config fallback. Writes timestamped
  `commands.log` and `checks.tsv`.
- `native_tester_owner_guard.sh` — read-only single-owner probe for
  `org.freedesktop.Notifications` (owner, PID/comm, foreign daemons, foreign
  activatable service files, bus-name occurrence count). It never requests a
  bus name or starts a daemon.
- `wallpaper_shim/plasma-apply-wallpaperimage` — bounded-timeout PATH shim for
  the known D-Bus wallpaper no-reply in this guest. It logs the real command's
  rc and returns 0 so the unchanged product `install.sh` can complete its
  in-place KConfig write. Do not install this into a normal user environment.
- `../scratch/native_tester/` — lease, raw probe logs, guest evidence copies,
  VBox framebuffer captures and `SHA256SUMS.txt`.

Reproduction command sequence is in the walkthrough document. No credential is
stored here; the pre-existing scratch SSH key stays outside the repository.
