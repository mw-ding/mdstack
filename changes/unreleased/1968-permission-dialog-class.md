---
type: changed
issue: 1968
pr: 2055
date: 2026-11-21
box-skill: none
---

`mdstack watch` names a harness safety dialog that `permission_mode = bypass` did not suppress: a run's `dialog` wake whose screen matches an adapter's new `PERMISSION_PROMPTS` (Claude Code `Do you want to …?`, Codex `Would you like to …?`) carries `class: permission-dialog` and the matched prompt line. The builder lead reports it as an `owner-decision` block naming the window, item and prompt line, never approving or retrying it or changing a permission setting. Folder-trust dialogs and non-bypass runs keep today's wake. The Claude Code adapter section records that bypass does not suppress built-in safety dialogs.
