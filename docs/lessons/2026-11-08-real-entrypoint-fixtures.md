---
title: 7 repaired cards where a test or check bypassed the production path; test through it and fail closed, with three leftovers filed (#1342)
date: 2026-11-08
status: applied
source: 7 repaired intake cards, group H03 of the #1337 clustering, retained by #1342
---

# Fixtures exercise the real entrypoint, 2026-11-08

## Test through the path production uses

- **Date:** 2026-11-08
- **Source / evidence:** 7 repaired intake cards, group H03 of the #1337
  clustering, retained by #1342. Cards and repairs: #1126 (#888), #1138
  (#992), #1198 (#1066, #1073, #1080), #1210 (#1169; the flake showed on
  #1063), #1248 (#1243), #1260 (#1253), #1272 (#1264).
- **Finding:** A test or check did not go through the code path that
  production uses, so it passed while the real path failed, or failed when
  nothing was wrong:
  - a fixture read a doc's table from its old home after the move (#1126);
  - a busy-demand skip, applied to every pool, broke reviewer runs (#1138);
  - campaign steps under `sh -c` counted only the last command, which masked
    failing assertions, and positive oracles were dropped (#1198);
  - a "writes only scan.json" snapshot compared all of `.git/`, so git
    maintenance churn flaked it (#1210);
  - `check-repo.py` reads tracked files only, so a local run before
    `git add` skipped new files (#1248);
  - a template test skipped include expansion (#1260);
  - the dependency lint matched only whole-path literals and missed imports
    and joined paths (#1272).
- **Impact:** Red CI on unrelated PRs, a false local pass claimed as
  evidence, and campaign scenarios that accepted duplicate worktrees and
  failed adoption. No card measured time lost.
- **Fix:** CI check per site. Drive tests through the production entrypoint
  or pipeline. Make every assertion affect the result, so it fails closed.
  Scope a fixture comparison to what the code under test can change. Run repo
  checks on the tree as it will be pushed, with new files tracked. The
  regression tests survive at `main` `739fdbe` and pass:
  `dev/tests/environments/test-crew-doctor.py` (the `gh` fixture reads
  `docs/runbooks/github-tracking.md`), `dev/tests/environments/test-crew-schedule.py`
  `test_demand_a_busy_worker_runs_takes_no_budget`,
  `dev/tests/scripts/test-campaign-run.py` A03 and A05 cases,
  `dev/tests/scripts/test-docs-scan.py`
  `test_snapshot_ignores_git_churn_but_not_work_tree_writes`,
  `dev/tests/environments/test-crew-ownership.py`
  `test_rendered_grok_guard_has_resolved_issue_and_instance` and the
  imports-and-joins rows of `dev/tests/scripts/test-check-repo.py`. #1248 added
  no test; the existing `deliverables` check caught it in CI.
- **Status:** applied for each repaired instance (#1342 survival table). The
  general rule is open in three places. #1412: campaign steps still run
  `sh -c` without `-e`, and nothing records a required failing case. #1413:
  no shared expand-then-line path for template tests. #1414: nothing warns
  about untracked files at check time. #1126's process step is not written
  down, but its fixture now fails closed if the doc moves again.
- **Linked issue/PR:** #1342, #1412, #1413, #1414. Related and separate:
  #373 (a fail-closed tool untested at its entry point), #1174, #1177 and
  #1333 (committed scenarios that drift).
