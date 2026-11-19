# Spec: public onboarding and documentation

**Status: built (M62, [#1997](https://github.com/mw-ding/mdstack/issues/1997));
every member landed, and the closing slice S1
([#1996](https://github.com/mw-ding/mdstack/issues/1996)) ran C1–C6.**
Outcome, closing-check results and lessons:
[portable spec, M62 outcome](portable.md#m62-outcome-and-lessons).
This spec was the opening slice S0 ([#1985](https://github.com/mw-ding/mdstack/issues/1985)).
It records the owner's decisions, the member rows and the numbered closing
checks that S1 runs. Member statuses live in
[portable spec, M62](portable.md#m62-public-onboarding-and-documentation).

The repository is already public, but a newcomer cannot get from the README
to a first merged PR on one consistent v8.0.0 path. M62 repairs and connects
the existing docs rather than rewriting them: it keeps the reference docs, the
audience index and the two architecture Mermaid diagrams, and adds only the
missing user surfaces. Source analysis:
[Riley's audit](https://github.com/mw-ding/mdstack/issues/1984#issuecomment-6990086410)
(base `3029197b51131126bc2477ceaf82b52230463d40`, v8.0.0); its `path:line`
anchors and per-row risks are not repeated here.

This spec adds no protocol rule, gate, marker field, label, permission or
role duty. A member that finds it needs one gets its own scope and approval;
prose cleanup never carries it.

## 1. Owner decisions

Recorded from the
[owner's M62 decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6991908550)
and the [plan-ok](https://github.com/mw-ding/mdstack/issues/1997#issuecomment-6991910667).

| # | Decision | What it settles |
|---|---|---|
| PD1 | **License: MIT**, copyright "the mdstack authors" | D9 adds a root `LICENSE` with the standard MIT text and that attribution. The owner can change the attribution in D9's review |
| PD2 | **Public name: mdstack**, explained as "a multi-agent engineering crew" | Pages introduce the role names before their default personas. CLI, config, label and marker names stay as they are. The pilot "Eng Crew" diagram leaves the newcomer path (D3) |
| PD3 | **Security reports: GitHub private vulnerability reporting** | D9's `SECURITY.md` routes reports there and nowhere else. Turning the repository setting on is an owner/admin action; D9 records whether it is on |

**Out of scope now (PD4).** Publication boundaries are not decided in M62.
No member decides a per-file disposition of `memory/*.md`, history
retention, or a public/private split of existing pages, and the closing checks
include no public-text re-scan. The publication-dispositions issue
[#1995](https://github.com/mw-ding/mdstack/issues/1995) left M62 and stays
open, unplaced. A member that meets a path, account or private-evidence
reference outside its own rows leaves it as it is and notes it on #1995.

## 2. Writing rules for every member

- **Repair, do not rewrite.** Edit the existing page that owns a topic. Moving
  prose keeps every condition sentence for sentence
  ([CONTRIBUTING](../../CONTRIBUTING.md)). Specs, lessons and dated metrics stay
  as history; they are linked, not flattened.
- **Owner commands are v8.0.0 commands.** An owner shell passes no
  `--project`; it uses the installed team, `MDSTACK_CONFIG` or `--repo`
  ([tmux binding](../runtimes/tmux.md)). Crew-window and low-level config-tool
  examples that take `--project` stay valid and are not changed.
- **Deployment preferences are not defaults.** This crew's own speed modes,
  grants and away status are its deployment settings, not product defaults.
  A guide explains the controls and links the schema
  ([profile](../profile.md)); it never copies this owner's values as advice.
- **Shipped versus not.** A page says what is built, what is attended-only or
  manual, and what is design. It makes no unmeasured claim, such as a setup
  time, until a proof measures it.
- **Released history is immutable.** Released `CHANGELOG.md` sections are
  never edited; a correction is a new fragment.
- **Each member keeps the repository rules:** one PR per issue, a changelog
  fragment, `scripts/check-repo.py`, `scripts/check-changelog-pr.py`, the
  tests named for any changed script, and the render and parity tests when a
  template changes ([AGENTS.md](../../AGENTS.md)).

## 3. Members

Order: S0 → D1 → D2 and D3 → D4 → D5–D8 → D9 → S1. Standard flavor. Sizes are
changed prose lines, planning ranges, not limits. The ACs are each member's
minimum; its issue may add more.

| ID | Issue | Scope and named paths | Size | Depends on | Tier |
|---|---|---|---|---|---|
| S0 | #1985 | This spec, its index row and the portable-spec M62 rows | 100–160 | Owner plan-ok | default |
| D1 | #1986 | Information architecture: user, operator, contributor, reference and history routes; `docs/README.md`, `docs/runbook.md`, `docs/metrics/README.md` | 100–160 | #1985 | trivial |
| D2 | #1987 | README: product and roles, prerequisites, compact launch path, support and version; `README.md` | 150–200 | #1986 | trivial |
| D3 | #1988 | Architecture: one canonical deployment, wake and release Mermaid view; pilot image off the newcomer path; `docs/architecture.md`, `docs/diagrams/README.md` | 120–180 | #1986 | default |
| D4 | #1989 | First-run walkthrough, v8 config to first merged PR, with a copyable owner-shell dry-run block; `docs/guides/getting-started.md`, `docs/runbooks/tmux-onboarding.md`, `docs/runbooks/profile-install.md` | 160–200 | #1987, #1988 | default |
| D5 | #1990 | Configuration guide: identities, engines, team and repo selection, concurrency, flavors; new `docs/guides/configuration.md` | 100–180 | #1989 | default |
| D6 | #1991 | Operating a crew: start, attach modes, pause and resume, status, logs, shutdown, upgrade, recovery; `docs/runbook.md`, `docs/runbooks/tmux-onboarding.md` | 100–180 | #1989 | default |
| D7 | #1992 | Runtime and harness support table; template catalog audience; `docs/runtimes/README.md`, `docs/runtimes/session.md`, `templates/README.md` | 100–160 | #1989 | default |
| D8 | #1993 | Upgrades: 7.x to 8.0.0 owner migration, wrapper regeneration, version-labelled older recipes; `docs/guides/migration.md`, `docs/release.md` | 140–200 | #1989 | default |
| D9 | #1994 | Contributor and community hygiene: `LICENSE`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `.github/ISSUE_TEMPLATE/`, `.github/PULL_REQUEST_TEMPLATE.md` | 150–200 | #1990–#1993 | default |
| S1 | #1996 | Status and tracker sync, the owner's clean-profile dry run, closing checks C1–C6, acceptance ledger | 100–160 | Every admitted member landed | default |

### Member ACs

- **D1.** Every page under `docs/` is reachable by relative links from
  `docs/README.md`, directly or through a subindex; the audit's two orphans
  (`docs/metrics/prs.md`, `docs/metrics/regression-drills.md`) are linked.
  Existing subindexes and the rule/reference/design/history classes stay.
- **D2.** The README leads with what mdstack is (PD2), lists prerequisites
  apart from launch steps, gives a compact launch path and links D4 as the one
  canonical walkthrough. The M51–M61 status narrative becomes a short
  released / current-source / support statement that matches the newest
  release in `CHANGELOG.md`.
- **D3.** The existing stage and module Mermaid diagrams are kept and updated,
  not duplicated. One new Mermaid view shows owner, coordinator and leads,
  role worktrees, the forge, poll/watch/queue/route, runtime and harness
  boundaries, and cut → bundle → install/upgrade, with review and CI as
  independent inputs to the merge gate. Each arrow cites a code or doc anchor.
  README and architecture no longer lead with the pilot image.
- **D4.** One walkthrough owns the copyable config, the identity choice
  (one account with emulated verdicts, or separate review identities), the
  first issue and the expected review, CI, permission and merge results, with
  recovery links. Owner examples use v8.0.0 commands. The PR gives a copyable
  owner-shell block that follows the walkthrough verbatim from a clean profile
  to a merged PR, and the evidence to paste back; the recorded run moves to S1
  ([amendment](https://github.com/mw-ding/mdstack/issues/1989#issuecomment-6996456089)).
- **D5.** A task-ordered guide links the authoritative schema pages and
  explains speed and caps separately from review flavor.
- **D6.** Start, reattach, targeted versus bare attach, pause and resume,
  status, logs, safe shutdown, upgrade and recovery are discoverable from the
  operations router. Pause sits beside stop, and the guide says that a bare
  attach can start the crew.
- **D7.** One support table distinguishes shipped, attended-only or manual,
  and design for each runtime and harness, and keeps declared gaps; the
  template catalog states its audience per runtime.
- **D8.** A 7.x → 8.0.0 section comes first: drop owner `--project`, use
  `MDSTACK_CONFIG` or repo selection, regenerate wrappers, keep crew flags.
  Older recipes stay, labelled by version.
- **D9.** PD1 and PD3 are applied; CONTRIBUTING opens with a human route
  (clone, setup, targeted checks, PR); bug and feature forms and a PR
  checklist sit beside the existing intake card, which stays.

## 4. Closing checks

S1 runs each check at the final M62 SHA and records the command, its output
and the SHA in the acceptance ledger on #1996. A check that cannot run is
recorded as not run, with the reason; it never counts as a pass. Today's
`check-repo.py` link check skips external URLs and strips fragments, so a
green `check-repo.py` alone proves none of C1–C3.

| # | Check | Pass condition |
|---|---|---|
| C1 | Full page reachability | Every tracked Markdown page under `docs/` is reachable by relative links from `README.md` or `docs/README.md`; the unreachable list is empty |
| C2 | Link and anchor validity | Every relative link in tracked Markdown resolves to a tracked file, and every `#fragment` resolves to a heading anchor in its target |
| C3 | Evidence accessibility | Every link on the newcomer path (README, D4–D9 pages) resolves for an unauthenticated reader; none points into a private repository as current proof |
| C4 | Mermaid render at the final SHA | Every Mermaid block in `README.md` and `docs/architecture.md` renders on github.com at the final SHA, and each D3 arrow is compared against the anchor it cites |
| C5 | Clean-profile proof | The owner runs D4's owner-shell block once against the final walkthrough, from a clean profile to a merged PR; its output is recorded as a builder-signed review at S1's head. S1 does not close without it |
| C6 | Member ledger | Every member row is `done` with its PR, or `dropped` with a recorded reason; PD1 and PD3 are visible in `LICENSE` and `SECURITY.md` |

Not in the closing checks (PD4): a public-text or secret re-scan, a
history or tracker audit, PNG OCR and a dependency-license audit.

## 5. Not in M62

Publication dispositions (#1995), release automation, new runtime
capabilities, pack distribution, permission-default changes and a release cut.
Completing M62 is not a release; a version decision is separate.
