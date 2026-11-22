---
type: added
issue: 1956
pr: 2037
date: 2026-11-21
box-skill: none
---

Stack land: an optional `land.stack_separator` (`" "` default, or `","`) joins the member ids in `<stack-changes>` and the revision ids in `<stack-revisions>`, so a review tool whose stack-land flag takes one comma-separated list receives a single argument without a shell transform in the pack. `<stack>` stays space-separated; `validate` refuses any other value and the key without `stack = true`. Without the key every stack command and default render is unchanged.
