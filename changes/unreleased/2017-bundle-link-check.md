---
type: added
issue: 2017
pr: TBD
date: 2026-11-22
box-skill: none
---

Bundle-boundary link check: `scripts/check-repo.py`'s `links` check now fails, as `bundle-link`, a relative link in a deliverable Markdown file whose target `release-bundle.py` can neither keep (a directory holding a deliverable) nor rewrite (a tracked file), such as #2000's README link to the unshipped `changes/unreleased/` directory. A lesson records the card as `encoded` (#2017).
