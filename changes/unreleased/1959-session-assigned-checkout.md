---
type: added
issue: 1959
pr: 2040
date: 2026-11-21
box-skill: none
---

Session `isolation` option: `runtime.options.isolation = "assigned-checkout"` makes the session coordinator brief say each worker and probe runs in its pre-provisioned dedicated checkout and creates no worktree, for a venue whose workers run in checkouts on other hosts. The default, `worktree`, renders byte-identically to before; any other value is refused by `validate`. The C6 checks are unchanged.
