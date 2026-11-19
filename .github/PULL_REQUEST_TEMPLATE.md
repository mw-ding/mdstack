<!-- Same headings as the crew PR body (docs/roles.md, PR conventions);
crew builders write the full body and may leave this checklist out. -->

## Context

<!-- Why this change is needed. -->

Closes #

## Changes Made

- `<path>`: <what changed and why>

## Testing Done

- <each check or test, and what it confirms>

## Test Output

~~~text
$ python3 scripts/check-repo.py
<key output lines>
~~~

## Checklist

- [ ] One issue, one PR; the PR closes it.
- [ ] A changelog fragment `changes/unreleased/<issue>-<slug>.md` with this PR's number (CONTRIBUTING.md, CHANGELOG).
- [ ] `python3 scripts/check-repo.py` and `python3 scripts/check-changelog-pr.py --base origin/main` pass.
- [ ] The targeted tests for the change pass (`python3 scripts/run-tests.py <files>`, AGENTS.md); PR CI runs the full suite.
- [ ] No tokens, keys, emails, private chat quotes or real box paths.
- [ ] Protocol, template or gate changes follow the protocol freeze; no permission or gate change rides along unapproved.
