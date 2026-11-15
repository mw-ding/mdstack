---
title: 5 repaired cards where the campaign sandbox checked one channel once; check the boundary at every effect, with a decoy per channel (#1342)
date: 2026-11-08
status: applied
source: 5 repaired intake cards, group H02 of the #1337 clustering, retained by #1342
---

# Sandbox boundary at every effect, 2026-11-08

## Check the boundary at each effect, not once at entry

- **Date:** 2026-11-08
- **Source / evidence:** 5 repaired intake cards, group H02 of the #1337
  clustering, retained by #1342. Cards and repairs: #1191 (#810), #1192
  (#815), #1193 (#816), #1194 (#820), #1204 (#1152; the #1186 report and
  rerun fixture).
- **Finding:** The campaign sandbox checked one boundary once, and every other
  effect channel stayed open. A `manifest --out` destination was written
  unchecked, symlinks included (#1191). Guard pins were checked at start
  only, so a step that edited the sandbox profile was followed by more
  mutating steps (#1192). Teardown checked only the checked-out branch, so
  unpushed work on another branch was deleted (#1193). The tmux shim accepted
  grouped flags whose socket selector reached an outside server (#1194).
  Steps inherited the operator's forge token and SSH agent variables (#1204;
  no real external request was established).
- **Impact:** A sandboxed run could overwrite production state, delete unpushed
  work or reach the operator's tmux server and credentials. The class was
  found one channel at a time, in five separate cards.
- **Fix:** Architecture: resolve and check the boundary at every effect
  (write, mutate, delete, forward, spawn) and test each channel with an
  adversarial decoy or sentinel. The regression tests survive at `main`
  `739fdbe` and pass: `dev/tests/scripts/test-campaign-guard.py`
  `test_out_outside_sandbox_refused`, `dev/tests/scripts/test-campaign-run.py`
  `test_guard_rechecked_before_each_run_step` and
  `test_operator_credentials_do_not_reach_steps`, and
  `dev/tests/scripts/test-campaign-sandbox.py`
  `test_teardown_keeps_unpushed_branch_not_checked_out` and
  `test_shim_pins_the_sandbox_socket_and_refuses_others`. The tmux cases skip
  where tmux is not installed.
- **Status:** applied: every repair is on `main` and each regression test runs
  (#1342 survival table). No card's prevention requirement is left. One
  observation: `CREDENTIAL_ENV` in `scripts/campaign-run.py` is a fixed
  denylist, so a new credential variable name would still be inherited.
- **Linked issue/PR:** #1342
