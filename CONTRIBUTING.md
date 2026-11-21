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

## Branch and merge gates

The historical Canopy PRs are **stacked**, and several ancestors were
visually rejected. Do not merge a green descendant if it imports
unapproved ancestors. First rebase or independently backport bounded,
verified changes onto current `main`, inspect the entire proposed diff,
and test that exact code.

Keep UI/artwork, shared core, VM integration, and QA in separate branches.
Do not substitute the eight SHA-locked original icon masters or silently
enable optional visual candidates. Owner-approved screenshot appearance
remains a distinct gate from Qt compilation or pixel-bound geometry tests.

Run regression and integration checks, verify real Qt and Mint evidence
as applicable, obtain appropriate code review when needed, and never authorize a merge
based on a green badge alone.

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
