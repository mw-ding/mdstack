# Spec: land, triage and bootstrap ergonomics

**Status: open (M64, [#2030](https://github.com/mw-ding/mdstack/issues/2030)).**
This spec is the opening slice S0
([#2026](https://github.com/mw-ding/mdstack/issues/2026)). It records the
settled fix and the numbered ACs for each member, the publication ledger
that #1995 applies, and the closing checks that S1
([#2028](https://github.com/mw-ding/mdstack/issues/2028)) runs. Member
statuses live in [portable spec, M64](portable.md#m64-land-triage-and-bootstrap-ergonomics).
Plan-ok: the [owner's M63/M64 decision](https://github.com/mw-ding/mdstack/issues/985#issuecomment-7074684349);
scope decisions follow the coordinator's recommendation under
[c6831237295](https://github.com/mw-ding/mdstack/issues/985#issuecomment-6831237295).

Four members close binding gaps an org pack met on the session runtime with a
non-GitHub backend. One settles a harness dialog report, three encode
repaired M62 failures, and one applies the publication dispositions M62 left
out. Target environment: N/A; none is a platform item. Owner prerequisites:
none.

This spec adds no protocol rule, gate, marker field, label, permission or
role duty. A member that finds it needs one gets its own scope and approval.

## 1. Rules for every member

- **Default off.** Each new key, operation or mode is optional, and its
  default keeps today's behaviour: default renders stay byte-identical and
  today's refusals keep their text. `validate` refuses a bad value in the
  existing `file:key: reason` format.
- **Documented where the schema lives.** A new key goes in its schema page
  ([profile](../profile.md), [runtime options](../configuration/runtime-options.md));
  a new operation in [actions/](../../actions/) and the bundled manifests as
  `unsupported` unless the bundled backend supports it.
- **Repository rules:** one PR per issue, a changelog fragment,
  `scripts/check-repo.py`, `scripts/check-changelog-pr.py`, the tests named
  for each changed script, and the render and parity tests when a template
  changes ([AGENTS.md](../../AGENTS.md)).

## 2. Members

Order: S0 → every member in parallel → S1. Standard flavor, tier default.
Sizes are changed lines without tests, planning ranges, not limits.

| ID | Issue | Scope and named paths | Size | Depends on |
|---|---|---|---|---|
| S0 | #2026 | This spec, its index row and the portable-spec M64 rows | 100–160 | Owner plan-ok |
| L1 | #1956 | `land.stack_separator`; `environments/terminal/crew.d/_land_stack.py`, `docs/profile.md`, `docs/interfaces.md` | 40–100 | #2026 |
| C1 | #1959 | Session `isolation` option; session coordinator template, `docs/configuration/runtime-options.md` | 40–100 | #2026 |
| T1 | #1960 | Optional `tracker.read-comments`; session triage scan, `actions/`, `docs/runtimes/session.md` | 60–120 | #2026 |
| B1 | #1962 | Verified exported packs; `core/crew-pack.py`, bootstrap, `docs/packs.md` | 80–160 | #2026 |
| H1 | #1968 | Name the permission dialog; watcher dialog wake, builder-lead template, `docs/runtimes/harness-adapters.md` | 40–100 | #2026 |
| K1 | #2017 | Bundle-boundary link check; `scripts/check-repo.py`, a lesson | 40–100 | #2026 |
| K2 | #2018 | Diagram edge-source rule; `docs/diagrams/README.md`, a lesson | 30–80 | #2026 |
| K3 | #2019 | Opened-PR number rule; `templates/policy/builder/build-pass.md`, a lesson | 20–60 | #2026 |
| P1 | #1995 | Publication ledger §3 and the re-scan; paths in §3 | 100–200 per commit | #2026 |
| S1 | #2028 | Status sync, closing checks §4 | 100–160 | Every admitted member landed |

### Member fixes and ACs

The ACs are each member's minimum; its issue may add more.

- **L1 (#1956). Fix:** an optional `land.stack_separator`, `" "` (default)
  or `","`, joins `<stack-changes>` and `<stack-revisions>`. The revision
  grammar already excludes commas, so no shell transform is needed.
  1. A stub backend whose stack-land flag takes one comma-separated list
     lands a three-member stack through `mdstack land stack`, receiving one
     argv token.
  2. Without the key, every stack command and default render is
     byte-identical; any other value is refused by `validate`.
- **C1 (#1959). Fix:** a session option `isolation`, `worktree` (default)
  or `assigned-checkout`. Under `assigned-checkout` the coordinator brief
  renders one sentence: each worker runs in its pre-provisioned dedicated
  checkout and creates no worktree. The C6 checks are unchanged.
  1. A profile declaring `assigned-checkout` renders the checkout sentence
     instead of the worktree path.
  2. Default renders are byte-identical; another value is refused.
- **T1 (#1960). Fix:** an optional `tracker.read-comments <id>` binding. When
  it is bound, the session scan calls it for each item `tracker.list-items`
  returned, and the owner-reply rules read those comments. Unbound, the scan
  is unchanged.
  1. A stub tracker with list plus per-item comments yields the same queue as
     the GitHub fixture.
  2. The operation is declared in `actions/` and `unsupported` in the bundled
     GitHub manifest; default renders are byte-identical.
- **B1 (#1962). Fix:** an exported pack carries a `pack.lock` with the source
  `commit` and a `sha256` digest over its sorted relative paths and bytes,
  `pack.lock` excluded. `crew-pack.py` writes it from a checkout; bootstrap
  accepts a non-VCS directory only when the digest verifies, and records
  `pack.commit` from the lock.
  1. Bootstrap installs an exported pack whose digest matches and records
     `pack.commit`.
  2. An export with one changed, added or removed file is refused with a
     nonzero exit naming the first mismatched path.
  3. A VCS checkout installs as today; a plain directory without `pack.lock`
     keeps today's refusal text.
- **H1 (#1968). Fix decided: name the refusal, change no permission.** Claude
  Code can show a built-in safety dialog even under `bypassPermissions`. The
  watcher's `dialog` wake for a window whose run uses `permission_mode =
  bypass` and whose screen matches an adapter permission prompt carries
  `class: permission-dialog` and the matched prompt line. The builder lead
  sends it to the coordinator as an owner ask naming the class, window, item
  and prompt line. No approval, no retry or reframing of the refused command,
  and no change to permission modes, settings or allow rules.
  1. A fake pane with a matching prompt in a bypass run yields a `dialog`
     wake with that class and line; a folder-trust dialog and a non-bypass
     run keep today's wake.
  2. The builder-lead template states the routing above; render and parity
     tests pass with only that rule changed.
  3. The Claude Code adapter section records that bypass does not suppress
     built-in safety dialogs.
- **K1 (#2017), check.** `check-repo.py`'s `links` check fails a relative link
  in a Markdown file the manifest classes `deliverable` when `release-bundle.py`
  would neither keep it (target in the bundle) nor rewrite it (target a
  tracked file), such as a link to an unshipped directory. The hint says to
  link a shipped target or render the path as code.
  1. Negative control: restoring #2000's README link to `changes/unreleased/`
     fails the check; the current tree passes.
  2. A lesson records the card with status `encoded`.
- **K2 (#2018), rule plus lesson.** `docs/diagrams/README.md` requires a
  canonical diagram to keep an edge table beside it, each edge citing the
  code or doc anchor it depicts, and its review to compare every edge with
  that anchor. No check can verify a topology.
  1. The rule is on the page, citing D3's edge table as the example.
  2. A lesson records the card with status `applied`.
- **K3 (#2019), template plus lesson.** Build-pass step 4 says to use only the
  number that opening the change returned for the fragment, labels and
  posts, never a predicted number. The existing post-open fragment lesson
  stays.
  1. The rendered builder briefs carry the sentence; render and parity tests
     pass.
  2. A lesson records the card with status `applied`.
- **P1 (#1995).** Applies the ledger in §3 and runs its re-scan. Several
  logical commits in one PR.
  1. Each ledger row is applied or recorded as a history acceptance.
  2. The re-scan record is posted on #1995 with its boundaries.

## 3. Publication ledger (for P1)

Approved here from [Riley's audit](https://github.com/mw-ding/mdstack/issues/1984#issuecomment-6990086410),
whose disposition column it adopts. Scope: current docs, templates, root
files, `.github/**` and diagram sources.

| # | Category | Disposition |
|---|---|---|
| PL1 | Literal user-home and workspace paths (`docs/specs/framework.md` source table, `docs/roles.md` examples) | Generalize to placeholders such as `<worktree-root>/<n>-<sha7>-<role>-<pass>/`, keeping the unique-run isolation wording |
| PL2 | Real reviewer account text in current examples (`docs/merge-enforcement.md`, `docs/diagrams/render/scene.mjs`) | Generalize to a placeholder account; history pages keep attribution under PL7 |
| PL3 | Links into the private sandbox (`docs/lessons/2026-10-30-tmux-dry-runs.md`, `docs/runbooks/tmux-onboarding-history.md`) | Replace each link with a self-contained one-line summary; no current page cites it as proof |
| PL4 | Owner decision-log references in current rule pages | Generic policy stays; cite the curated [decisions](../decisions.md) row where one exists; the log link stays as provenance |
| PL5 | Grant, speed-mode and away-status wording in guides | Present this deployment's values only as examples of a setting, never as defaults. A sentence whose rule would change is out of scope and is filed separately |
| PL6 | Old repository links on current navigation pages | Point at `mw-ding/mdstack`; history keeps the old links, which redirect |
| PL7 | History: specs, lessons, dated metrics, `*-history.md` runbooks, `docs/decisions.md`, released `CHANGELOG.md` sections | Accepted as published history as they stand, apart from PL3 links |
| PL8 | `memory/*.md` | Unchanged by P1: this project's operating memory, not bundled. `memory/owner.md`'s grants are never adopter defaults; any change is a reviewed memory PR |

Retained as is: the `runtime.name@runtime.instance` identifier, which is not
an email. **Re-scan:** at its head P1 reruns the audit's categories over the
same boundary and records, per category, the count before and after and each
remaining hit's disposition (fixed, history, retained). **Boundary:** no
history rewrite, force-push, tracker deletion or retroactive removal; no
PNG OCR or secret attestation; tool-name clearance is not claimed without
the owner's external denylist.

## 4. Closing checks

S1 runs each check at the final M64 SHA and records the command, its output
and the SHA on #2028. A check that cannot run is recorded as not run, with the
reason; it never counts as a pass.

| # | Check | Pass condition |
|---|---|---|
| G1 | Member ledger | Every member row is `done` with its PR, or `dropped` with a recorded reason |
| G2 | Default renders | `test-render-parity.py` and `test-crew-render.py` pass at the final SHA |
| G3 | Schema coverage | Each key and operation L1, C1, T1 and B1 added is documented with its default |
| G4 | Learning cards | K1–K3 lessons are indexed with the status their row names; K1's negative control is rerun |
| G5 | Publication | P1's re-scan record is linked, and its boundaries are restated |

## 5. Not in M64

Permission-default changes, a fix that approves or retries a harness dialog,
history removal, new runtimes and a release cut. Completing M64 is not a
release; a version decision is separate.
