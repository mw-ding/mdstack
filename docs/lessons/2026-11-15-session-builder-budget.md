---
title: A shared build-pass step on #1908 fit the tmux brief but put the session builder brief 14 bytes over budget, caught only by full-suite CI; keep the compact step, the budget and the session-profile upgrade test as the regression (#1915)
date: 2026-11-15
status: applied
source: PR #1908 (closes #1844, M57)
---

# A shared builder step fit the tmux brief but overflowed the session one, 2026-11-15

## Measure shared builder text against every runtime that includes it

- **Date:** 2026-11-15
- **Source / evidence:** PR #1908 (closes #1844, M57). Its first head,
  `521f97f`, added the post-open step to
  `templates/policy/builder/build-pass.md`. Full-suite repo-guard run
  43696359576 then failed `test-crew-upgrade.py`
  `Upgrade.test_session_profile_applies_without_tmux` with
  `runtime/builder.md: 16398 path-normalized UTF-8 bytes exceeds builder
  budget 16384 bytes`. The builder's round-1 `ci-fix` note at `0c1c6bb`
  records the failure and the repair. Intake card #1915. Affected files:
  `templates/policy/builder/build-pass.md`, which both
  `templates/runtimes/tmux/builder.md` and
  `templates/runtimes/session/builder.md` include, the bootstrap self-test
  `size_budget()` in `environments/terminal/crew.d/bootstrap.py`, and
  `[size_budget]` in `docs/profile.md`.
- **Finding:** The tmux and session runtime briefs share
  `build-pass.md`, but their budget headroom differs a lot. The tmux brief
  sat at about 61% of its builder budget, while the session brief was close
  to 16384 bytes. The new step pushed the session brief 14 bytes over. The
  targeted local set for a template change, the render quartet
  (`test-crew-render.py`, `test-render-parity.py`, `test-tmux-briefs.py`,
  `test-crew-bootstrap.py`), passed. Only the full suite in PR CI renders
  the session profile through upgrade and runs its size budget check.
- **Impact:** One red CI run, one `ci-fix` round and one extra push on
  #1908 before review approved the repaired head. Nothing over budget
  reached `main`. The ci-fix note measured about 75 bytes of session
  headroom left at the repaired head, so the next builder addition can hit
  the same limit.
- **Fix:** Commit `0c1c6bb` rewrote the step in fewer bytes, about 90
  fewer, with the same meaning, and updated the rendered tmux fixture. The
  16384-byte budget and its check stay unchanged. Keep the compact step,
  keep the existing budget, and keep the session-profile upgrade test as
  the regression that measures shared builder text under the session
  runtime. When a change grows shared builder text, check the session
  brief's headroom (the `crew-render: budget` stderr line) as well as the
  tmux one. Two related cases have a different mechanism: #1566 is
  coordinator headroom lost after a merge-up, and #1746 is accumulated
  owner-grant text. Whether the targeted local set should include the
  session-profile test is a coverage question for the findings buffer, not
  this lesson.
- **Status:** applied: the compact step is on `main` in
  `templates/policy/builder/build-pass.md` (#1908), and
  `dev/tests/environments/test-crew-upgrade.py`
  `test_session_profile_applies_without_tmux` holds the regression in PR CI
  through the bootstrap `size_budget()` self-test. Not `encoded`: no
  `scripts/check-repo.py` check or lint measures the session brief.
- **Linked issue/PR:** #1915, #1908, #1844
