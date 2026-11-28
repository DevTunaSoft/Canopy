# Native bundle integration candidate (2026-11-28)

Non-release integration candidate. Built from `ec910d7a7275` on unprotected branch
`integration/native-bundle-candidate-20261128`. **No merge to a protected base and no approval was requested or granted.**

## Exact combination (applied in PR-number order)

| PR | Verified head (exact SHA) | Application method | Resulting commit |
| --- | --- | --- | --- |
| #732 | `a14e335a75f35f775bcd669de4e2ba5ab173168c` | net diff `base..head` applied with `git apply --3way` (shallow/grafted head: parent object absent locally) | `4acfce37f826ea63a10a6c4f5bae8abe1061a498` |
| #733 | `a0b1c77b94bd0cb3b341a472f68de596ff5f6dce` | cherry-pick (1 commit) | `8b64773ce394914e9c9484ec1f276fc983eda284` |
| #734 | `bd67e7359908b56d53cb68acbb1fb9941b84cc11` | net diff `base..head` applied with `git apply --3way` (shallow/grafted head: parent object absent locally) | `7fe0d75f7239e07b83f5f655552b79c71d131614` |
| #735 | `349742749a4ab9dbf2903df876e3d9b70e299986` | cherry-pick (2 commits) | `100ff8bde93e3605f4e9e853060701dc6ccbbbfa` |
| #736 | `df73dfb6d1272b72e1f57b3b57539373c05dd636` | cherry-pick (1 commit) | `6ce14937b00bc53a1b6a787a14df75ca937e79fa` |
| #737 | `35c1fe7a0c76cc3dbebe9e3f633b587cbfc377e6` | cherry-pick (2 commits) | `ede970ab03ab4841c6197f219ecb237922143ba6` |
| #738 | `07a5d8c3b750eb7c76d9a69be460384797c4937f` | cherry-pick (2 commits) | `a2b85b89b1d8f62254718a6f9cf8c879fd264996` |
| #739 | `cde4b120f427cd1cc682c84037e71169e2f547a3` | cherry-pick (1 commit) | `0524c5de6fa41591ad30719e7086a6fa0b8d092b` |
| #740 | `f8ba8187bc67b8bf1de49c4e40977f33e17d6e74` | cherry-pick (1 commit) | `bc7ed3c5becea24f88ce02cf81f7abed8416399f` |
| #741 | `ba1994b835308132ac964520ffcbe032923c177c` | cherry-pick (1 commit) | `d3abec7db39a707569409844d31718db72171a1e` |
| #742 | `83854452db545e30777017906974f69f385bae39` | cherry-pick (1 commit) | `e7bada4f44eea5d1215e73ff9ce0928b970d2383` |
| #743 | `2b8bca910d84b19966b29db37dfb3ce7512e810f` | cherry-pick (2 commits) | `5aec78ebc41e5d3cc58abfb1f09e6063935e6258` |
| #744 | `2733f7e09e0e3447fe39eebce6a71171e2ebf476` | cherry-pick (1 commit) | `1bc407e349d87d0c9742bd869706bf986b2a6dcc` |
| #745 | `80097f8b97b7d5df35b4e53bb9cd835b546aca9f` | cherry-pick (1 commit) | `3bb219c244bd91c2e2eb787a415fc622b82b05d5` |
| #746 | `050853173419c7224ab8875233f5ef1d7aea622c` | cherry-pick (2 commits) | `0c1ab1debb52c7e4f7cd00ad04b7ae6bb9100dc5` |
| #747 | `ca378da2c2b116db8ce79dc711001add9af59897` | cherry-pick (2 commits) | `0f5761c3ae0430e091d2c20acbd46dc998a0e55f` |
| #748 | `9f766d06225f4a7e7cfe9be010a3432a4109ea05` | cherry-pick (1 commit) | `4b493d7a651f3ffe1b3ee17157e2b35daf0cd482` |

All 17 heads were applied cleanly; zero cherry-pick or patch conflicts.

## Conflicts

`conflicts = {}`: no file-level conflicts, no substantive resolution, no guessed edits.
For every PR, every path changed by `git diff --name-only ec910d7a7275 <head>` is byte-identical
in the candidate tree to that PR head (`git diff HEAD <head> -- <owned paths>` is empty).
`git grep -n -E '^(<<<<<<<|>>>>>>>)' HEAD -- tests canopy_core canopy_features tools docs`
returns no conflict markers. The two shallow heads (PR732 `a14e335`, PR734 `bd67e735`)
were applied as their exact net diff from the base because their parent objects are absent
locally; their resulting commit SHAs are therefore candidate-local, not the upstream head SHAs.

## Commands executed

```sh
# worktree from the pinned base, on an unprotected branch
git -C C:/Users/X1/Projects/Canopy worktree add -b integration/native-bundle-candidate-20261128 \
  C:/Users/X1/AppData/Local/hermes/cache/scratch/wt-native-bundle-20261128 ec910d7a7275296ecbc8b5e5c459d356205165d1

# each PR head: cherry-pick the commits in base..head, in PR-number order
git -C <worktree> cherry-pick <commit>

# PR732 / PR734 (shallow heads): exact net diff, 3-way applied
git -C <worktree> diff --binary ec910d7a7275 <head> > patch
git -C <worktree> apply --3way patch && git add -A && git commit -m 'integrate(candidate): ...'

# identity / conflict evidence
git -C <worktree> diff --name-only HEAD <head> -- <owned paths>   # empty for all 17
git -C <worktree> grep -n -E "^(<<<<<<<|>>>>>>>)" HEAD -- tests canopy_core canopy_features tools docs

# foundation + targeted smoke (PYTHONPATH=<worktree>, PYTHONUTF8=1)
python tools/check_foundation.py
python -m unittest -v tests.test_c100_dock_display_geometry_contract \
  tests.test_classic_preview_scrollbar_theme tests.test_classic_qt_source \
  tests.test_classic_status_a11y tests.test_host_event_bounded_lifetime \
  tests.test_host_event_ceiling_contracts
for d in scratch/native_a11y scratch/native_notifications/tests \
  scratch/native_quick_controls/tests scratch/native_suspend \
  scratch/native_tasks_model/tests scratch/native_windows tools/native/tests; do
  python -m unittest discover -s "$d" -v
done
```

## Verification results

| Gate | Result |
| --- | --- |
| `tools/check_foundation.py` | PASS (`PASS: foundation files, tagline, and local Markdown links`) |
| changed_tests | rc=0, Ran 57 tests, OK |
| native_a11y | rc=0, Ran 6 tests, OK |
| native_notifications | rc=0, Ran 35 tests, OK |
| native_quick_controls | rc=0, Ran 21 tests, OK |
| native_suspend | rc=0, Ran 8 tests, OK |
| native_tasks_model | rc=0, Ran 6 tests, OK |
| native_windows | rc=0, Ran 16 tests, OK |
| native_baseline | rc=0, Ran 8 tests, OK |
| Full `unittest discover -s tests -v` at code head `4b493d7a651f3ffe1b3ee17157e2b35daf0cd482` | PASS rc=0, Ran 4687 tests, OK (skipped=49) |

## Known gaps / boundaries

- **No release and no protected-branch merge.** This branch is an integration candidate only;
  the missing distinct human approval is not manufactured or bypassed here.
- Native Plasma/Mint guest runtime acceptance is **NOT_RUN** in this candidate. Runtime
  evidence carried in the PR heads is static/CI-scoped evidence from those PRs, not a
  fresh runtime verdict for the combined tree.
- CI checks for the pushed candidate branch are not claimed green; no CI result was used
  as a merge authorization.
- Six native smoke suites live outside `tests/` (under `scratch/` and `tools/native/tests`)
  and are invisible to Foundation CI's `unittest discover -s tests`; they were run
  explicitly in the targeted smoke above.
- PR732/PR734 commit identity differs from their upstream heads because they were applied
  as net diffs from the pinned base (shallow parent objects absent). Their tree content is
  byte-identical to the verified heads.
- No substantive conflict existed, so no conflict resolution decision was required.
