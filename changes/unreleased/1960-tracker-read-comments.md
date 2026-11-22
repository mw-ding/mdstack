---
type: added
issue: 1960
pr: TBD
date: 2026-11-21
box-skill: none
---

Optional `tracker.read-comments` for the non-GitHub triage scan: a tracker CLI that lists items without comments binds it, and `mdstack poll --triage-only` runs it once per open listed item (`<n>` the item id), so the owner-reply rules read its JSON comment array. A failed or unreadable read records that item unreadable; unbound, the scan is unchanged. The bundled GitHub manifest declares it `unsupported`, `docs/interfaces.md`, `docs/profile.md`, `docs/runtimes/session.md` and `actions/README.md` document it.
