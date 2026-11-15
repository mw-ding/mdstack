# Guard negative controls described, not captured, 2026-11-15

## A fix note pastes the guard's fail-then-pass control inline

- **Date:** 2026-11-15
- **Source / evidence:** Two M56 PRs, both repaired before merge; intake card
  #1884. On PR #1876 (issue #1858), the round-2 verdict found that the
  builder's round-1 fix note said four new tests failed against the pre-fix
  commit but gave no copyable old-code setup, command or captured
  exit/stdout/stderr; the round-2 fix note repaired it with N1/N2 runs at the
  old commits and a P1 run at head. On PR #1877 (issue #1859), the round-2
  verdict found new train guard rows and a mutation audit with no signed
  builder note or proof at that head; the round-2 fix note repaired it with
  inline captures taken before the push.
- **Finding:** Protocol §3 Guard negative control already requires, for each
  new or changed guard, the guard failing on the undone line or nearest wrong
  input and then passing restored, inline in the change body or a signed fix
  or ci-fix note. Both fix rounds added guards and either described the
  failing run in a sentence or posted no note, so the requirement was met
  only after a reviewer asked.
- **Impact:** One extra `changes` finding on each PR (🔴, missing required
  evidence under effective `evidence = typed`), each repaired in the next
  fix round. No guard without its control reached `main`.
- **Fix:** Skill or protocol prose: the builder fix procedure in
  `templates/policy/builder/fix-rounds.md` now says that for a new or changed
  guard, the fix or ci-fix note pastes the copyable fail-then-pass control of
  protocol §3 Guard negative control as captured, not a sentence saying the
  guard failed. It points at the existing rule and changes nothing in it:
  typed/inline treatment, the reasoned N/A and who supplies the proof stay
  as §3 states, and no gate is added. Prose only, because whether a round
  adds or changes a guard, and whether a pasted capture really shows that
  guard failing, is review judgment over the diff and the live note: no repo
  file maps a test to the guard it controls. Review-start timing after a
  push is a separate fix (#1878).
- **Status:** applied: the reminder is on `main` in
  `templates/policy/builder/fix-rounds.md` (#1884); the rule itself is
  `docs/protocol.md` §3, Guard negative control (#1604). Not encoded: no
  check reads a signed note for its control.
- **Linked issue/PR:** #1876, #1877, #1884
