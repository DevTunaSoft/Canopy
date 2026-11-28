## Scope

What does this PR change? What does it deliberately **not** change?

## Why and integration

Related issue(s): #
Base branch: `main`, `integration/canopy-classic-20261123`, or explicitly documented stacked branch:
Dependencies on other PRs:

## Verification (actual evidence, not estimates)

- [ ] Tests run; show exact commands and PASS/FAIL/BLOCKED/NOT RUN
- [ ] Source/asset provenance, original-icon hash locks, and licensing reviewed
- [ ] Security, privilege boundaries and unintended network/data access reviewed
- [ ] No new unnecessary daemons, background polling or memory leaks
- [ ] App/window/session state preservation and rollback checked where relevant
- [ ] Full-resolution actual compiled Qt screenshots attached for visual changes
- [ ] Linux Mint VM acceptance completed, or clearly marked NOT RUN/BLOCKED
- [ ] Documentation/AGENTS.md and independent reviewer comments addressed

GitHub Actions link(s):
Commit SHA used for tests:
Hardware, distro, session/compositor and measurement method:

## Visual and architecture signoff

Visual state: **NOT APPLICABLE / VISUAL REVIEW PENDING / REJECTED / APPROVED**
Mint acceptance: **NOT RUN / BLOCKED / PASS**
Code review: **NOT YET REVIEWED / REVIEW IN PROGRESS / REVIEWED**

### Merge gate

Green CI **alone never authorizes merging**. Do not merge visually rejected
work, unverified Mint integration or a stacked PR that would transitively
merge an unapproved ancestor. Document source changes before changing status
to ready. Draft status is temporary: promote verified PRs promptly rather
than leaving them in draft indefinitely.

Routine verified engineering changes and authorized bounded GUI refinements
may be promoted from draft and integrated into
`integration/canopy-classic-20261123` by the autonomous engineering process
after exact-SHA verification, independent review and applicable checks; mark
that as **AGENT REVIEWED**, never as human approval. Run post-merge regression
**after** integration; it is not a pre-merge gate. Obtain explicit owner
approval for final visual acceptance, substantial identity changes, high-risk
security decisions and final acceptance into `main`. Named holds on #279, #151
and #278 are never overridden by general authorization. The authorized workforce
is up to 8 concurrent engineering subagents plus Hermes as lead orchestrator
(9 total) under the 2026-11-26 master directive amendment (SHA-256 `f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197`).
That amendment supersedes earlier workforce ceilings only; visual, security,
protected-PR and release-owner gates remain in force.
