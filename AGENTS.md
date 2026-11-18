# Canopy autonomous engineering rules

These supplement, never replace, existing requirements.

1. Read all engineering documentation fully before changing code; inspect repository, issues and PRs to avoid duplicate work.
2. Sync with origin/main, work on isolated feature branches and draft PRs; do not merge main without authorization.
3. Implement one shared, modular, low-memory core with interchangeable Classic and future Modern layouts.
4. Reuse mature Linux Mint and freedesktop services rather than duplicating OS functionality.
5. Keep Cinnamon fallback; ensure reversible installation, configuration migrations and crash recovery.
6. Shell never runs as root; use narrowly authorized polkit/system-service operations without storing passwords.
7. Preserve privacy, accessibility, security, licensing and original branding.
8. Autonomously test, independently review, diagnose root causes, add regression coverage and measure resource use.
9. Never claim PASS without executed evidence; distinguish PASS, FAIL, BLOCKED and NOT RUN.
10. Update architecture, requirements, traceability, roadmap, handoff and user documentation with changes.
11. Commit and push verified green changes; open/update draft PR; no unauthorized main merge.
12. Continue autonomously until genuinely blocked or session ends; avoid redundant work and verbose token use.
13. Ponytail guidance may augment these instructions after compatibility review, never override them.
