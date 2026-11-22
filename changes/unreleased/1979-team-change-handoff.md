---
type: fixed
issue: 1979
pr: TBD
date: 2026-11-22
box-skill: none
---

Cross-team ownership: an owner decision that moves a repo to another team is now carried out with the existing `takeover` handoff on the control item (`docs/handoff.md` Team change, `docs/roles.md` Team change); the decision comment alone moves nothing. Review readiness on tmux also needs a run record in this crew's state naming the PR (a builder's `done: #<item> #<pr> <head>` line or a `builder-pr<n>-` claim), so a PR another crew opened under the same login is skipped as `foreign team`. This crew's own PRs are unaffected; no marker field, label or merge-gate rule changes.
