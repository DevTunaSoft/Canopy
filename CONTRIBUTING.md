# Canopy engineering and review policy

Canopy is experimental. Passing automated checks alone does not establish
production readiness, visual acceptance, security or Linux Mint compatibility.

## Code review

Code review is welcome from interested contributors and reviewers. **Do not
create unsolicited public reviewer invitations or recruitment campaigns.**
This is not a restriction on who may inspect, comment on, or review the
public repository.

Review perspectives worth covering:

- **Security and supply chain:** permissions, code execution, filesystem
  paths, secrets, dependencies and original/licensed artwork provenance.
- **Reliability and performance:** idle CPU/PSS/wakeups, bounded caches,
  startup/recovery, memory cleanup and real failure-mode regressions.
- **Visual quality and accessibility:** real compiled Qt screenshots at
  1920×1080, 1200×750 and 760×500; optical art centering, clipping,
  keyboard navigation, scaling and accessible focus.
- **Architecture:** shared shell services, extensible versioned Shell Pack
  contracts, no duplicate compositors or background daemons.
- **Linux Mint acceptance:** actual Mint VM or hardware tests with safe
  session selection, rollback, failure recovery and evidence.

A review packet should include the exact commit SHA, linked issue and
draft PR, affected files, reproducible commands, actual logs, comparison
screenshots where appropriate, and PASS/FAIL/BLOCKED/NOT RUN results.
Review packets can be shared with any reviewers the project works with;
a report artifact is **not** a human reviewer signoff.

## PR lifecycle: DEVELOP → TEST → REVIEW → READY → INTEGRATE → VERIFY
Use a draft PR while implementation or required evidence is incomplete; draft status is temporary, not a permanent hold. Pre-merge gates are exact-head verification, dependency/ancestry and conflict review, independent review, applicable checks, and any required owner approval for visual, high-risk security or release decisions. Promote verified drafts to ready and integrate eligible work; post-merge regression testing is required **after** the merge, not before it. There is no circular rule demanding a post-merge result to authorize that merge.

Routine, independently verified engineering changes and authorized bounded GUI refinements may use an autonomous review and integration process into `integration/canopy-classic-20261123`. That automation is engineering review (**AGENT REVIEWED**), **not human approval**. Human approval remains mandatory for final visual acceptance, substantial identity changes, high-risk security decisions, final release acceptance and any merge to `main`. Named owner holds on #279, #151 and #278 are never overridden by general development authorization. The owner-controlled workforce ceiling is **8 concurrent engineering subagents plus Hermes as lead orchestrator (9 total)** under directive SHA-256 `f240bcdf635a498a7476c8104cbf3dc4e6cda492abba318254d80fce7566a197` (2026-11-26); the 15/11/12/10-agent and four-worker configurations are `SUPERSEDED_POINT_IN_TIME`, retained not erased. Compiled/QML/C++ engineering is permitted under the owner's Hermes GUI-engineering grant; a blanket compiled-path ban is superseded. Paths that change approved artwork, wallpaper, dock geometry, colours, typography or frozen visual pins remain owner-gated, and CI or byte-identity evidence never substitutes for final visual acceptance. Current visual status: `AWAITING_OWNER_VISUAL_APPROVAL`; the legacy `AWAITING_CHATGPT_VISUAL_APPROVAL` string in frozen tooling/tests is `SUPERSEDED_POINT_IN_TIME`. See [workforce policy](docs/AGENTS_WORKFORCE.md) and [ND-076 reconciliation](docs/ND076_RESTRICTION_RECONCILIATION.md).

SUPERSEDED_POINT_IN_TIME for active caps, draft rules and integration authority: Rev3 SHA-256 1fba4b1e7128b6bc33aba577c05fdccfa45fcac56ee714f02e9d8b43e32a0f2a and the 2026-11-28 correction SHA-256 32ed075e4fa70fabef110ca1487c653ed0384c88f0f3966e3c219cc5d1ec97ce govern. Historical text, evidence and frozen pins are retained, not erased.

## Branch and merge gates

The historical Canopy PRs are **stacked**, and several ancestors were
visually rejected. Do not merge a green descendant if it imports
unapproved ancestors. For main-targeted changes, rebase or independently backport bounded verified changes onto current `main`. For routine Classic development (engineering work and bounded non-substantive visual refinements), use `integration/canopy-classic-20261123` as the base. In either case inspect the entire proposed diff and test that exact code.

Keep UI/artwork, shared core, VM integration, and QA in separate branches.
Do not substitute the eight SHA-locked original icon masters or silently
enable optional visual candidates. Owner-approved screenshot appearance
remains a distinct gate from Qt compilation or pixel-bound geometry tests.

Run regression and integration checks, verify real Qt and Mint evidence as applicable, and require independent review for routine verified work. Human approval remains mandatory for owner visual decisions, high-risk security decisions and final release acceptance; never authorize a merge based on a green badge alone.

## Shell Pack development

The draft [Shell Pack architecture](https://github.com/DevTunaSoft/Canopy/blob/feature/extensible-shell-pack-contract-20261121/docs/SHELL_PACK_ARCHITECTURE.md)
describes future presentations and versioned host boundaries.
The manifest checker is metadata validation only, not an implemented
loader, sandbox or live switcher. Keep packages and artwork original
or properly licensed, and never execute untrusted community UI in a
privileged desktop session without separate security review.

## Automated review reports

The [Canopy read-only supervisor](.github/workflows/review-supervisor.yml)
periodically records CI/PR status in a GitHub artifact. It does not
request outside reviewers, edit PRs, approve code or merge.
