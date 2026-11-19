---
type: changed
issue: 1992
pr: 2005
date: 2026-11-18
box-skill: none
---

Runtime support table: `docs/runtimes/README.md` gains a **Support** section, one table marking each runtime (tmux, multi-device tmux, session, Grok Bot), session backend (tmux, herdr) and harness (Claude Code, Codex, Pi, Cursor, Muse, OpenCode) as shipped, attended or manual, or design, with its declared gaps summarized and linked. The runtime index and `docs/runtimes/session.md` now describe session as partly built and attended-only (selector, briefs, `mdstack brief`, `mdstack up` and `mdstack upgrade` built; worker lifecycle manual; runner design only). `templates/README.md` is retitled **Template catalog** and opens with an audience table per tree (core, tmux, session, Grok Bot, policy, backends), saying only Grok Bot routines are copied by hand; its session synthesizer row no longer claims merge trains. The README links the support table directly.
