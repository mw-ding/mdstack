# Core memory

A crew remembers in three layers (owner, 2026-11-07,
[#1230](https://github.com/mw-ding/mdstack/issues/1230)):

| Layer | Holds | Lives in | Changes by |
|---|---|---|---|
| 1. Core memory | A small curated core: the owner profile and one file per role | Git, under `memory/` in the checkout | A reviewed memory PR |
| 2. Personal knowledge | The owner's personal notes and data | An external service, through the `knowledge` connector ([team spec REQ-17](specs/team.md#req-17-knowledge-in-external-services)) | The connector's proposed edit |
| 3. Platform memory | Whatever a harness remembers natively between sessions | The harness, outside the repo | The harness; scratch only |

Only core memory is injected at start, and only core memory is reviewed.
Platform memory is scratch: an entry worth keeping is promoted into core
memory by a memory PR ([capture](#capture)), never read as a rule.

## Files and limits

| File | Holds | Limit |
|---|---|---|
| `memory/owner.md` | The owner profile: standing preferences on communication, decisions and how work flows | 3000 bytes |
| `memory/roles/<role>.md` | One registered role's lessons that should outlive any one session | 2000 bytes each |

No other file belongs under `memory/`. A memory file is read at every
start, so keep it short: correct or replace an entry before adding one,
cite where each entry was decided, and write no relative links (the text
is copied into briefs). mdstack's own crew keeps its core memory in
[memory/](../memory/owner.md); another project keeps it in its own repo.

## Injection at start

The renderer, `core/crew-render.py`, appends a `## Core memory` section
to each role's rendered brief: the owner profile, then that role's file.
A pool lead's brief carries its pool role's file. The memory comes from
`memory/` in the checkout the profile names (`paths.checkout`, else the
profile's directory), read at the tip of that checkout's remote default
branch (`repo.default_branch` on `origin`), never from its local tree
(#1537). Each render resolves that tip once, fetching its objects if needed,
and every role output of the render shares the one revision; the
checkout's branch, index and files stay as they are. The render names the
revision on stderr (`crew-render: core memory from origin/main@<sha>`).
With neither file at that revision, nothing is added. If the remote cannot
be resolved, fetched or read, the render fails closed rather than use stale
or local memory. A root with no `origin` remote (or outside git) adds
nothing when it has no `memory/` directory and fails closed when it has one.

| Environment | Where the section lands |
|---|---|
| Terminal (tmux) | Every rendered role brief and pool lead brief, so every role window and the coordinator start with it |
| Session | The coordinator and each worker brief |
| Grok Bot | Each role's main routine prompt (the role's `discovery` file), inside its closing fence; the other routines of a role do not carry it |

A memory lint problem in either file fails the render closed, so a bad
memory file never reaches a brief. The brief size budget (`[size_budget]`)
does not count this section; the memory limits above bound it instead. A
merged memory PR reaches running roles at the next render (`mdstack up` or
`mdstack upgrade`), even when the local checkout has not been pulled.

## Lint

`core/crew-memory.py` checks `memory/`: the layout above, each file's size
limit, and personal data. `scripts/check-repo.py` runs it as its `memory`
check, and the renderer runs the same checks on the files it injects.
Run it on any project with `python3 <mdstack>/core/crew-memory.py --root
<repo>`.

### Personal data

The lint refuses email addresses, phone numbers, street addresses and
personal details (birthday, home address, salary, medical, family and
similar). Each refusal says to keep the item in the knowledge connector
instead: personal data never goes into git
([REQ-17](specs/team.md#req-17-knowledge-in-external-services)). The
patterns catch common shapes only; review still checks every memory PR.

## Capture

The coordinator's
[memory-capture skill](../templates/policy/coordinator/skills/memory-capture/SKILL.md)
runs when the owner asks and at each milestone close. Its brief carries
only a one-line pointer to this section: the coordinator brief is at its
size budget.

1. Read the harness's platform memory for entries worth keeping.
2. Promote an entry only when it is a standing owner preference or a team
   lesson that should outlive any one session, is not already in
   `memory/` or a reviewed doc, and holds no personal data.
3. File one memory issue listing each promotion: the entry, its target
   file (`memory/owner.md` or `memory/roles/<role>.md`) and where it was
   decided. Dispatch it like any build.
4. Its PR changes only `memory/`, corrects or replaces an entry before
   adding one, stays within the size limits and passes the memory lint.
   It needs no changelog fragment: the changelog check exempts `memory/`.
   It lands only through review, like every change.
5. Personal data found on the way goes to the knowledge connector as a
   proposed edit, or is dropped when no connector is configured; never
   to git.
