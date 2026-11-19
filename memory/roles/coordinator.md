# Core memory: coordinator

Reviewed PRs only (`docs/memory.md`).

- Relayed owner decisions: verify, sign if unsigned, apply (#985 c6763466693).
- Sign `pass=flavor` before dispatch; else `thorough` (#1430, #1432).
- Pre-dispatch `cmd=plan-ok` per milestone tracker, even after #985 (#1779).
- Worker/test tmux: no unowned servers (#1474).
- Unbuilt-feature ACs: lab proof on their issue (#1472).
- Owner-shell proofs: milestone close (S1); confirm owner runs them
  early, else follow up on their word (#1989, #985 c7014850164). PRs
  give commands outside tmux; builder-signed fix review at head. Exit
  71: set `runtime.options.sandbox_env`, relaunch leads, window 0;
  check PATH `codex`/`claude` first (#1465, #1478, #1544, #1707,
  #1766, #985 c6816385952).
- List open milestones before adding (#985 c6757404578).
- Merge-ok beats changes only if all open findings are unverifiable
  proofs; log scope at head, file follow-up (#1613, #1614).
- Merge up budgeted coordinator brief PRs before land; lone lands skip
  combined size test (#1625, #1635).
- Approved PR red CI: check test module use before calling flaky (#1803).
- Cut PR waits for milestone's last fragment (#1661), freezes fragment
  PRs; hold by closing unmerged (#985 c6814551260).
- New edge cases per fix: fail closed, split proven work (#1677, #1684).
- Review-changes: always send builder lead `fix` (#1871 c6874052190).
- Until #1878 ships: slow fixes capture evidence, then push and post the
  note at once (#1877).
- Until #1850 installed: Claude builders ack mid-turn inbox at turn
  end; busy one's no-ack: read pane, never restart.
- Post-cut: check release, close milestone, capture, admit next (#1559,
  #1719).
- Until #1830/#1835/#1836 ship: deep tier via builder-lead note ref;
  hand synthesizer land on merge-ok at green CI; lead settles
  owner-blocked held id, re-sends on answer (#1774, #1832, #1833).
- Pre-land simulated cut for new tests reading version, `changes/`,
  CHANGELOG (#1821, #1828).
