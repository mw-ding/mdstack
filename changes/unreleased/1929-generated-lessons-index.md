---
type: added
issue: 1929
pr: TBD
date: 2026-11-15
box-skill: none
---

Lessons index generated from lesson metadata: every `docs/lessons/*.md` file opens with a `title`, `date`, `status` and `source` front-matter block, and the new `lessons` check in `scripts/check-repo.py` validates it (path-named failures; `mixed` exactly for multi-entry files) and the committed index rows between the `lessons:begin`/`lessons:end` markers. A valid lesson with no row yet passes as pending, so a lesson PR adds only its own file and parallel lesson PRs no longer conflict; the milestone bookend PRs run `--fix` to regenerate the index, which writes nothing while any file or marker is invalid. The lessons README, `CONTRIBUTING.md` and `docs/self-improve.md` now say to add the lesson file and not edit the index.
