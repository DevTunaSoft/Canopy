# Independent track — safe GitHub PR dependency inventory

The Canopy project has many open draft PRs on stacked branches. `scripts/pr_stack_audit.py` computes the dependency graph from GitHub **head/base refs** and flags unknown bases, cycles, duplicate heads, parallel main roots and non-draft items. It is **read-only**: it neither merges nor retargets anything and never requires a GitHub token. It does not attempt to prove code ancestry, conflict freedom, CI state, review approval or whether diffs overlap.

Online, when public GitHub API access is available:
```bash
python3 -m scripts.pr_stack_audit --live --output test-results/pr-stack-audit.json
```

For offline/CI testing, pass a saved response from `GET /repos/DevTunaSoft/Canopy/pulls?state=open&per_page=100`:
```bash
python3 -m scripts.pr_stack_audit --input /path/to/pulls.json
```

A 100-entry response is refused rather than silently missing pagination. Test fixtures cover stacked ancestors, two independent main roots, unknown parent refs, cycle, invalid input and non-draft flags. Actual main integration requires intentional review: order PR #1 foundation, subsequent stacked branches, separate Ponytail and Classic design branches, and the independent test-lab tracks. Update dependency graph from live GitHub after other coding agents change branches. No merges to main without user approval.

This checkpoint is separate from Classic GUI code, VM runner and their tests, and is safe to develop without modifying shared files.
