# Kinoite validation evidence matrix

Exact head: `ec910d7a7275296ecbc8b5e5c459d356205165d1`. Generated: 2026-11-28T04:22:11Z.

| ID | Check | Evidence class | Verdict |
|---|---|---|---|
| E01 | Official deployment path | STATIC SOURCE ONLY | PASS |
| E02 | Atomic update commands | STATIC SOURCE ONLY | PASS |
| E03 | Rollback and pinning commands | STATIC SOURCE ONLY | PASS |
| E04 | Major upgrade / rebase path | STATIC SOURCE ONLY | PASS |
| E05 | Kernel/driver and security update path | STATIC SOURCE ONLY | PASS |
| E06 | Read-only core behavior | STATIC SOURCE ONLY | PASS |
| E07 | Stock Plasma fallback path | STATIC SOURCE ONLY | PASS |
| E08 | User-level Canopy extension compatibility | STATIC SOURCE ONLY | PASS |
| E10 | Flatpak / Flathub independent app updates | STATIC SOURCE ONLY | PASS |
| E11 | DNF path without writing the base OS | STATIC SOURCE ONLY | PASS |
| E12 | No custom image maintenance required | STATIC SOURCE ONLY | PASS |
| E09 | User-level Canopy extension and operation without LacOS infrastructure (host-side plan and source scan) | NATIVE RUNTIME (Windows host, NOT Kinoite) | PASS |
| E13 | Native Kinoite runtime verification of atomic update/rollback, read-only mount, Plasma fallback, Flatpak/DNF updates | NATIVE RUNTIME | NOT_RUN |

Static/host gate: PASS. Native Kinoite runtime: NOT_RUN (BLOCKED: no disposable Fedora Kinoite environment on this host).

Sources are limited to fedoraproject.org, docs.fedoraproject.org, docs.flatpak.org, freedesktop.org, docs.kde.org, ostreedev.github.io, coreos.github.io and the upstream sddm/sddm repository.
