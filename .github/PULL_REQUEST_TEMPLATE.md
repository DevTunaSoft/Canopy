## Scope

What does this PR change? What does it deliberately **not** change?

## Why and integration

Related issue(s): #
Base branch: `integration/canopy-plasma6-20261127`, legacy `integration/canopy-classic-20261123`, protected `main` after baseline gates, or explicitly documented stacked branch:
Dependencies on other PRs:

## Verification (actual evidence, not estimates)

- [ ] Tests run; show exact commands and PASS/FAIL/BLOCKED/NOT RUN
- [ ] Source/asset provenance, original-icon hash locks, and licensing reviewed
- [ ] Security, privilege boundaries and unintended network/data access reviewed
- [ ] No new unnecessary daemons, background polling or memory leaks
- [ ] App/window/session state preservation and rollback checked where relevant
- [ ] Full-resolution actual compiled Qt screenshots attached for visual changes
- [ ] Applicable native Plasma or legacy VM acceptance completed, or clearly marked NOT RUN/BLOCKED
- [ ] Documentation/AGENTS.md and independent reviewer comments addressed

GitHub Actions link(s):
Commit SHA used for tests:
Hardware, distro, session/compositor and measurement method:

## Visual and architecture signoff

Visual state: **NOT APPLICABLE / VISUAL REVIEW PENDING / REJECTED / APPROVED**
Applicable guest/session acceptance: **NOT RUN / BLOCKED / PASS**
Code review: **NOT YET REVIEWED / REVIEW IN PROGRESS / REVIEWED**

### Merge gate

Green CI **alone never authorizes merging**. Do not merge visually rejected
work, unverified desktop integration or a stacked PR that would transitively
merge an unapproved ancestor. Document source changes before changing status
to ready. Draft status is temporary: promote verified PRs promptly rather
than leaving them in draft indefinitely.

Routine verified changes may integrate into the designated branch during migration; protected main becomes the development trunk after the native baseline gates in the [master owner directive](../docs/MASTER_OWNER_DIRECTIVE.md) pass. Require exact-SHA/current-base/merge-result verification, applicable checks and independent review; mark agent review as **AGENT REVIEWED**, never human approval. Run post-merge regression after integration. Owner approval remains required for final visual acceptance, substantial identity changes, high-risk security decisions and public releases. Named holds #279/#151/#278 remain binding. Maximum eight engineering subagents plus Hermes; throttle lower as needed. Routine upstream security updates must not wait for owner approval.
