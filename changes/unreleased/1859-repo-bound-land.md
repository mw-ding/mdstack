---
type: added
issue: 1859
pr: 1877
date: 2026-11-14
box-skill: none
---

Landing is bound to the repo `--project` selects (team §9.5). `mdstack train` records the selected project's `context` in its train and delegation records and, before any clone, branch, record, push, CI dispatch, merge or cleanup, compares every record and delegation an action names, every member qualifier (`<owner>/<name>#<n>`) and, for `build` and `delegate`, each member's URL read back from the backend; one foreign or unreadable source refuses the whole action with nothing written. `train land` reads the member's verdict, permission, landing control and holds only when their URLs are the selected repo's, so another repo's verdict, merge-ok or train result at the same number and SHA never counts. Async land and stack intents record the `context`, `land request|resume|done`, `land stack|stack-done` and resume refuse an intent naming another repo before any read, request or drop, and `land stack --stack` takes `<owner>/<name>#<n>:<sha>` members, refusing the whole stack when one names another repo. `land-lock` records the repo's `context` and the acquiring window in `locks/merge.pid` and refuses a record naming another repo before any cleanup, signal or removal; each repo keeps its own lock. The tmux synthesizer lead brief gains a team-land paragraph. In a one-repo config a record written before this change, without `context`, stays the selected repo's; gate satisfaction, actors, fail-open paths and markers are unchanged.
