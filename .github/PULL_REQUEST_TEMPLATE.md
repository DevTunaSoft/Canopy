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
to ready.

Routine nonvisual work may be reviewed and integrated by the autonomous
engineering process after exact-SHA verification and regression tests; mark
that as **AGENT REVIEWED**, never as human approval. Obtain explicit owner
approval for visual changes, high-risk security decisions and release
acceptance. A named PR hold is never overridden by general authorization.
