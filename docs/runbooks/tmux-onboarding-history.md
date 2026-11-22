# tmux onboarding history

History module, not current instructions: the dated live run that closed
[#139](https://github.com/mw-ding/eng-crew/issues/139), split out of the
[onboarding runbook](../runbook-new-repo.md) under the M26 modular
organization principle ([#676](https://github.com/mw-ding/eng-crew/issues/676)).
It records what was tested on 2026-10-30 against eng-crew `main` at
`7eb454d`, with the tmux runtime, one identity for every role and
`merge_grant = "none"`. It applies to that revision only; it makes no claim
about the current release. For the current steps, use the
[tmux onboarding module](tmux-onboarding.md).

## End-to-end run (2026-10-30)

The final live run for #139 on a private sandbox repo, real GitHub and real
CI: eng-crew `main` at `7eb454d`, one identity for every role, sandbox
issue #5 to PR #6 to squash `3a8be25` in about 13 minutes. Two earlier live
runs failed the pass bar; their findings and fixes are in the
[dry-run and live-run lesson](../lessons/2026-10-30-tmux-dry-runs.md). Times
are PDT. The sandbox repo is private, so the GitHub objects below are named,
not linked; this table is their self-contained record.

| # | Time | Event | Window (engine) | Marker / GitHub object |
|---|---|---|---|---|
| 1 | 21:50:54 | `mdstack up`; Claude trust dialog answered once (21:51:07) | `ash` (claude-code) | none |
| 2 | 21:51:39 | Start sweep spawns the builder for `crew:ready` issue #5 | `ben-5` (claude-code sonnet) | claim `builder-issue5`; issue #5 |
| 3 | 21:52:12 | PR #6 opened, `crew:in-review` | `ben-5` | PR #6; `role=builder issue=5 tier=trivial engine=claude-code model=sonnet`; trailer `Engine: claude-code sonnet medium` |
| 4 | 21:52:24 | CI `check` green at `cedd053` | GitHub Actions | run 41170296758 |
| 5 | 21:52:54 → 21:53:57 | `ci-passed` → review pass, `done: … review pass` | `vera-6-r1-review` (codex) | claim `reviewer-pr6-cedd053-r1-review` |
| 6 | 21:56:02 | Validate → verdict at head; `crew:in-review` → `crew:approved` | `vera-6-r1-validate` (codex) | review 5721362072, `pass=verdict pr=6 sha=cedd0538… round=1 verdict=pass` |
| 7 | 21:56:40 | Merge-ok ask, default keep hold; `sam` refuses: `blocked: #6 no owner merge-ok … merge_grant=none` | `ash`, `sam` | review 5721364245, `cmd=ask` |
| 8 | 21:59:38 | Owner merge-ok ("merge-ok, go go go", 21:59:28) recorded; ask closed | `ash` | reviews 5721375572 `cmd=merge-ok`, 5721375653 `cmd=ask-closed` |
| 9 | 21:59:55 → 22:00:00 | `land-lock acquire` → `pr merge --squash --match-head-commit cedd0538…` (21:59:56) → `[Sam/merge]` → `release` | `sam` | review 5721376964 `pass=merge`; merge `3a8be25`; issue #5 closed |
| 10 | 22:00:34 | Close-out: windows killed without `--discard`, labels cleared, branch deleted | `ash` | PR #6 and issue #5 with no labels; head branch 404 |
| 11 | 22:03:46 | `mdstack down` rc 0; no harness process left | none | `pgrep` empty |

Pass bar adopted by the owner for #139:

| # | Criterion | Result | Evidence |
|---|---|---|---|
| a | No human input but the trust answer and the owner's merge-ok | PASS | Rows 1 and 8 are the only inputs; no Codex dialog or approval prompt |
| b | No role types into another role's window | PASS | No `send-keys`, `attach --rw` or paste in any transcript; only the C3 `mdstack send sam land` nudge, acked |
| c | No merge-ok without the owner's words under `merge_grant = "none"` | PASS | Row 7: ask defaulted to hold and `sam` refused; row 8 from the owner's words |
| d | Land lock on the real state dir; placeholder paths refused | PASS | Lock on `<state-dir>/md-mt__eng-crew-sandbox/locks/merge.lock` 21:59:54.99–22:00:00.58, merge inside it; inherited and explicit placeholders refused (rc 1) |
| e | Clean close-out | PASS | Row 10 |
| f | No leftover harness processes | PASS | Row 11 |
| g | No new high-severity finding | PASS | New: M1 (medium, #269) and L1 (low, #270), backlog |
