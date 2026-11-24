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
Use a draft PR while implementation or required evidence is incomplete. When all applicable checks pass, verify the exact head SHA and full diff, confirm dependencies/conflicts/ancestry, perform an independent code review, confirm any required human approval is present, then promote to ready-for-review and integrate through the appropriate branch. Run post-integration regression tests.

Routine, independently verified nonvisual changes may use an autonomous review and integration process. That automation is engineering review, **not human approval**. Human approval remains mandatory for owner visual decisions, high-risk security decisions and final release acceptance. A specific PR hold (for example #278) is never overridden by general development authorization.

## Branch and merge gates

The historical Canopy PRs are **stacked**, and several ancestors were
visually rejected. Do not merge a green descendant if it imports
unapproved ancestors. For main-targeted changes, rebase or independently backport bounded verified changes onto current `main`. For routine nonvisual Classic development, use the designated integration branch as the base. In either case inspect the entire proposed diff and test that exact code.

Keep UI/artwork, shared core, VM integration, and QA in separate branches.
Do not substitute the eight SHA-locked original icon masters or silently
enable optional visual candidates. Owner-approved screenshot appearance
remains a distinct gate from Qt compilation or pixel-bound geometry tests.

Run regression and integration checks, verify real Qt and Mint evidence as applicable, and require independent review for routine nonvisual work. Human approval remains mandatory for owner visual decisions, high-risk security decisions and final release acceptance; never authorize a merge based on a green badge alone.

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
