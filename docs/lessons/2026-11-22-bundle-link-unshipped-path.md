---
title: #2000 linked the README to the unshipped `changes/unreleased/` directory and only the release-bundle test caught it; `check-repo.py`'s `links` check now fails such a link in any deliverable (#2017)
date: 2026-11-22
status: encoded
source: Change #2000 (M62 D2, #1987) signed CI repair and repo-guard run 44417300249, intake card #2017
---

# A deliverable linked a path the release bundle does not ship, 2026-11-22

## Fail a deliverable link the bundle can neither keep nor rewrite

- **Date:** 2026-11-22
- **Source / evidence:** Change #2000 (M62 D2, closes #1987): the failed
  repo-guard job in Actions run 44417300249 (`FAIL:
  test_current_repo_builds_and_install_cli_runs`, `release-bundle: refused:
  offline link check failed`), the signed CI repair and the new-head verdict
  on #2000, and intake card #2017. Affected files: `README.md`,
  `scripts/release-bundle.py` (`rewrite()` and its offline link check) and
  `scripts/check-repo.py` (`check_links()`).
- **Finding:** The README linked `changes/unreleased/`. The link resolved
  in the source tree, so `check-repo.py`'s `links` check passed. The
  manifest classes `changes/**` internal, so the directory is absent from
  the bundle, and `release-bundle.py` rewrites only links to tracked files,
  not to a directory. The bundle's offline link check refused it, which only
  the release-bundle test in the full suite exercises.
- **Impact:** One red CI run and one repair push on #2000 before review.
  Nothing wrong merged: the bundle test caught it.
- **Fix:** `check-repo.py`'s `links` check now fails, as `bundle-link`, a
  relative link in a Markdown file the manifest classes `deliverable` when
  its target is neither a tracked file (rewritten to the release tag) nor a
  directory holding a deliverable (kept in the bundle). The hint says to
  link a shipped target or render the path as code. Outside a git work tree
  or without a manifest the rule is skipped, so the bundle's own offline
  check is unchanged. #2000's README link is the negative control in
  `dev/tests/scripts/test-check-repo.py`.
- **Status:** encoded: the `bundle-link` rule of `scripts/check-repo.py`'s
  `links` check enforces it on every push.
- **Linked issue/PR:** #2017, #2000
