## Scope

What does this PR change? What does it deliberately **not** change?

This reconciliation PR is **DRAFT**: no merge and no self-approval. Sole controlling Canopy/LacOS goal is Rev3 (`C:/Users/X1/Downloads/Canopy_LacOS_Master_Execution_Directive_2026-11-28_Rev3.md`, SHA-256 `1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a`, short `1fba4b1e`). Older cap/draft-only/integration-authority wording is `SUPERSEDED_POINT_IN_TIME`; retained, not retracted or erased. Security gates, approved visual assets/hash locks, named PR holds #151/#278/#279 and branch protection remain binding. Rev3 requires an exclusive guest lease for interactive VM/session work and no-global-change.

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
- [ ] A0.1: current assignments finish on their authorized branches; no interrupt/reassign merely to apply a directive
- [ ] Project-scoped cap 8+Hermes observed; no change to global Hermes settings or other projects (no-global-change)
- [ ] Exclusive guest lease (owner/heartbeat/recovery checkpoint) used for VM/session work; heavy work serialized; timeouts are NOT passes
- [ ] Distinct human approving review obtained when branch protection requires it (never self-approval); if unavailable, PR stays DRAFT/PENDING and the required owner action is recorded

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

Rev3 integration authority: integration/main protection requires **1 distinct human approving review with `enforce_admins=true`**; the only authenticated account (`DevTunaSoft`) authors the eligible PRs, so this is a genuine external blocker. Never self-approve, impersonate a reviewer or bypass protection. Promote eligible PRs to ready, record the exact owner action needed and continue unrelated eligible work; a worker's no-self-approval rule does not block the authorized integration lead, who still needs a real distinct human approver.

Routine verified engineering changes and authorized bounded GUI refinements
may be promoted from draft and integrated into
`integration/canopy-classic-20261123` by the autonomous engineering process
after exact-SHA verification, independent review and applicable checks; mark
that as **AGENT REVIEWED**, never as human approval. Run post-merge regression
**after** integration; it is not a pre-merge gate. Obtain explicit owner
approval for final visual acceptance, substantial identity changes, high-risk
security decisions and final acceptance into `main`. Named holds on #279, #151
and #278 are never overridden by general authorization. The 12-subagent ceiling
under the 2026-11-26 directive is `SUPERSEDED_POINT_IN_TIME`; Rev3 (`1fba4b1e`)
sets a project-scoped cap 8+Hermes with A0.1 finish-current-work protection.
See [workforce policy](../docs/AGENTS_WORKFORCE.md). No global Hermes settings
or other projects are changed; this PR is DRAFT with no merge or self-approval.
