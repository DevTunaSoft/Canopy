# Contributing to Canopy

Thank you for helping make Linux welcoming to people migrating from macOS
and Windows. Canopy is open source but **experimental**. Neither a green
build nor a beautiful preview proves a production-ready desktop shell.

## Independent review is welcome

Please review focused draft or review-ready pull requests and add specific,
reproducible comments. Start with the [review queue](https://github.com/DevTunaSoft/Canopy/pulls)
or [QA issue](https://github.com/DevTunaSoft/Canopy/issues/88).

Priority review perspectives:

- **Security and trust:** inspect asset provenance, path handling, arbitrary
  QML execution, privilege boundaries, token handling and dependency updates.
- **Performance and reliability:** check shell-owned CPU/PSS/wakeups,
  orphan processes, memory/cache cleanup, crash recovery, startup/shutdown,
  and whether tests verify failure modes.
- **Visual and accessibility QA:** compare screenshot evidence from the
  *compiled Qt app* at 1920×1080, 1200×750 and 760×500; inspect optical
  centering of artwork, clipping, focus, keyboard access and high DPI.
- **Architecture and extensibility:** confirm Classic, Modern and future
  Shell Packs share one service core rather than duplicating daemons or
  compositor responsibilities; guard API compatibility.
- **Linux Mint:** test on a real Mint session/VM with an independent
  rollback and non-disruptive installer path; do not treat Ubuntu CI
  smoke tests as Mint acceptance.

Each report should include the affected PR/commit SHA, file/line,
expected vs. observed behavior, reproduction steps and severity. Actual
test logs and screenshots are far more useful than "looks good".

## Branches and review gates

The main branch is intentionally conservative. Historic PRs are **stacked**
and several contain deliberately rejected visual work. Before a PR is
considered merge-ready:

1. Rebase or independently backport onto current `main` without silently
   importing rejected upstream commits. Review exact file list and diff.
2. Keep functional, documentation, icon/visual and test-lab work separate.
3. Run GitHub Actions, unit tests, Qt runtime tests and Mint VM tests as
   applicable; explicitly note gates that remain BLOCKED/NOT RUN.
4. Never replace SHA-locked original artwork or hide an optional image
   candidate inside the default asset set without user visual acceptance.
5. Obtain independent review for security-sensitive or session-changing
   code. The author should not treat their own review as independent.
6. Do **not** automatically merge based on green CI alone.

Final aesthetic acceptance comes from the project owner, not an AI-generated
concept, geometric bounding-box test or a successful nonblank screenshot.

## For new Shell Pack contributors

Read [Shell Pack architecture on its draft branch](https://github.com/DevTunaSoft/Canopy/blob/feature/extensible-shell-pack-contract-20261121/docs/SHELL_PACK_ARCHITECTURE.md).
Pack metadata validation alone is not a secure loader or a working live
switch. Use original or properly licensed icons and wallpaper. Never run a
community pack in a privileged desktop session without explicit sandbox,
trust and capability review.

## How to participate from GitHub or mobile

Use GitHub's Files changed tab to leave inline review comments and
a **Review changes** summary. Any GitHub user can inspect public code and
open an issue with reproduction steps. Formal reviewer requests require
permission/eligibility; we won't invent an external reviewer or claim
their signoff when no one has reviewed the code.

The scheduled `Canopy read-only engineering supervisor` will produce a
GitHub Actions report with the open PR/CI queue after it is merged to
`main`. This report doesn't write to GitHub or automatically review
source code.
