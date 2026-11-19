# Release workflow and update path (design)

> - **Status:** partly built
> - **Applies to:** `release.yml`, `scripts/changelog-cut.py`, `scripts/release-*.py`
> - **Current rules:** release gate in the [gate registry](protocol.md#gate-registry)
> - **Built:** [Steps](#steps), [Release gate](#release-gate), release on cut merge (#387) and R1.2–R1.4 (#217–#219); M54 [session-tooling helpers](#upstreaming-the-session-tooling) (PRs #1834, #1838, #1837)
> - **Design only:** The bootstrap-driven rows of the [Update path](#update-path) were not re-checked; treat them as unverified
> - **Last checked:** M54 helper status 2026-11-13 at `73a23b5`; other release/update claims retain their prior scope

How a version of the [deliverables](deliverables.md) is cut, approved and
published, how installed environments take it, and how to roll back
(roadmap R1.1, [#145](https://github.com/mw-ding/mdstack/issues/145);
umbrella [#110](https://github.com/mw-ding/mdstack/issues/110);
[portable spec P9](specs/portable.md#2-requirements)).

This page adds no rule, gate, cap, marker field or label. Its release gate
row is in the [gate registry](protocol.md#gate-registry), added by
[R1.3](#follow-up-issues) under the
[gate contract](protocol.md#gate-contract). Implemented: the release
workflow ([#218](https://github.com/mw-ding/mdstack/issues/218), PR #243),
the bundle build ([#236](https://github.com/mw-ding/mdstack/issues/236),
PR #245) and the bundle attach
([#246](https://github.com/mw-ding/mdstack/issues/246), PR #248). `v1.0.0`
was tagged and released by hand on `b2144a2`, and `v2.0.0` was cut through
`release.yml` after the CHANGELOG cut in PR #273 (both
[#219](https://github.com/mw-ding/mdstack/issues/219)).

## Decisions

Release on cut merge is the approved design
([#274](https://github.com/mw-ding/mdstack/issues/274)), implemented by
[#387](https://github.com/mw-ding/mdstack/issues/387). Dispatch remains the
manual fallback.

| Question | Choice | Alternatives considered |
|---|---|---|
| Trigger | Landing the CHANGELOG cut PR: `release.yml` runs on a `push` to `main` touching `CHANGELOG.md`; `workflow_dispatch` remains for dry runs and manual fallback | Milestone close: an outward action as a side effect of tracker hygiene, and not every milestone is a release. A release label: overloads `crew:*` state tags, which the protocol keeps for change state |
| Who starts the release | The synthesizer lands the approved cut PR; the workflow completes the release without a coordinator dispatch or run watch | A separate dispatch after landing the cut: an extra owner action |
| Who approves | The owner's per-PR merge-ok on the cut PR at its head (`pass=steer cmd=merge-ok sha=<head>`), or the coordinator's merge-ok there citing a recorded [release delegation](#release-delegation) ([#1435](https://github.com/mw-ding/mdstack/issues/1435)); the publish job verifies it and the `RELEASE_OWNER` actor check | A standing merge grant: never covers a cut PR. A per-cut chat reply every time: the owner gave the same go repeatedly |
| CHANGELOG cut | A normal crew PR runs `scripts/changelog-cut.py <version>` ([#217](https://github.com/mw-ding/mdstack/issues/217)) and lands through §7 with the owner's per-PR merge-ok to trigger the release | The workflow committing the cut to `main`: a direct push bypasses review and breaks invariant 4 (only the synthesizer lands). A workflow-opened PR: PRs opened with the workflow token start no CI, so §7 could never pass |
| What the workflow writes | A tag, a GitHub Release and the release-issue notice and closure; never a commit | none |
| Release workflow PR | `crew:sensitive` ([#184](https://github.com/mw-ding/mdstack/issues/184)); until that class lands, the owner's per-change merge-ok is stated on the PR | Standing doc-only merge-ok: never covers `.github/` |

## Steps

1. **Release issue.** The coordinator files "Release vX.Y.Z" with the bump
   reason: the largest change class among the `[Unreleased]` entries
   ([versioning](deliverables.md#versioning)).
2. **Cut PR.** A builder runs `changelog-cut.py X.Y.Z` on a branch; the diff
   cuts `CHANGELOG.md` and consumes the fragments under `changes/unreleased/`.
   Its body names the release issue in the release-only non-closing form
   ([#1416](https://github.com/mw-ding/mdstack/issues/1416)): `Refs #<release
   issue>` in `## Context` and one whole line `Release issue: #<release
   issue>`, the same repository, with no closing keyword for it, so landing
   never closes the issue before publication. Other issues the cut PR
   closes keep `Closes #n`. On the cut PR, `release.yml` runs
   `release-trigger.py linkage` and fails on a missing, ambiguous or foreign
   target, or a closing keyword for it, naming the correction. The body is
   written once: the builder reports a refusal as `blocked:`, and the
   coordinator settles the correction through the owner-decision path.
   It goes through review and the
   [§7 merge gate](protocol.md#7-merge-gate-synthesizer); the owner gives
   per-PR merge-ok at the cut PR's head (`pass=steer cmd=merge-ok sha=<head>`),
   or a recorded [release delegation](#release-delegation) stands in for it.
   The standing merge grant never covers a cut PR. CI validates and builds the
   bundle on the real cut before it can land.
   A cut PR may carry a small release-pipeline fix (only
   `.github/workflows/release.yml`, `.github/workflows/ci.yml`,
   `scripts/release-*.py` or `scripts/changelog-cut.py`) with its entry
   written directly into the new version section instead of a fragment
   ([CONTRIBUTING: CHANGELOG](../CONTRIBUTING.md#changelog),
   [#616](https://github.com/mw-ding/mdstack/issues/616)). Any other change
   goes in its own PR.
   See [Cut freeze](#cut-freeze) for what holds while it is open.
3. **Trigger.** The synthesizer lands the cut PR. `release.yml` runs on
   `push` to `main` touching `CHANGELOG.md`. It proceeds only for a new top
   versioned section `[X.Y.Z]`, empty `[Unreleased]` and no existing
   `vX.Y.Z`; otherwise it exits green with a one-line summary. For a real
   cut it then refuses at once unless the run's actor and triggering actor
   are `RELEASE_OWNER`, naming the fix: dispatch as the owner account, or
   have the synthesizer merge the cut PR
   ([#615](https://github.com/mw-ding/mdstack/issues/615)).
4. **Validate job** (read-only token). At the pushed merge commit it runs
   release-specific checks only and fails closed unless:
   - the top versioned `CHANGELOG.md` section is `[X.Y.Z]` and
     `[Unreleased]` above it is empty, with no unconsumed fragments;
   - `vX.Y.Z` does not exist and is greater than the latest tag;
   - markdownlint and the offline link check pass;
   - `scripts/release-compat.py` finds no
     [manifest break](#manifest-compatibility) below a major.

   `check-repo.py` and every `dev/tests/*/test-*.py` run once, in `ci.yml`, not
   here. On the cut PR, `ci.yml` `repo-guard` covers them like any PR.
5. **CI gate** (`ci-gate` job, `actions: read`). In parallel with
   validation, it waits up to 40 minutes for the latest `ci.yml` push run on
   `main` at the same commit. It proceeds only when that run succeeded. A
   red, cancelled, timed-out or skipped run, or no run at that SHA (missing,
   or still pending past the bound), refuses publishing with the reason.
   `ci.yml` cancels superseded runs only for pull requests and groups `main`
   runs per commit, so a quick second merge never cancels the cut's CI.
   After a refusal, re-run CI to green, then re-run the failed release jobs.
6. **Build** (validate job). Build `mdstack-X.Y.Z.tar.gz` and `SHA256SUMS`
   ([packaging](deliverables.md#packaging)); upload them as a workflow
   artifact with the release notes, which are the `[X.Y.Z]` section.
7. **Approval check.** The publish job needs validate and the CI gate. It
   locates the one merged PR whose merge commit is the validated SHA on
   `main` and whose diff changes `CHANGELOG.md`, then verifies the owner's merge-ok marker
   at the merged cut PR's head and that the push actor matches the
   `RELEASE_OWNER` repository variable. Missing approval or an actor mismatch
   refuses publishing. There is no second owner approval after landing.
   It reads all review bodies and conversation comments, checking the author,
   PR number and full head SHA; a marker on the merge commit or an earlier
   PR head does not authorize publishing. Reruns also require the triggering
   actor to match `RELEASE_OWNER`.
   It reads the release issue from the cut PR body with the same linkage
   check; a refusal stops publishing.
8. **Publish job** (`contents: write`). In the same workflow run, after
   validation, the CI gate and the approval check, create the annotated tag
   `vX.Y.Z` on the validated merge commit; create the GitHub Release with the
   notes and attach the bundle and `SHA256SUMS`. A tag created with the workflow token
   starts no other workflow, so validation, tagging and publishing stay in
   one run.
9. **Notice.** Only after the Release exists, the publish job posts its link
   on the release issue the cut PR names, then closes the issue. A failed
   validation, CI gate, approval check, publish or notice leaves the issue
   open. No coordinator run watch is required.

### Manifest compatibility

The [versioning](deliverables.md#versioning) table makes a newly required
manifest field or operation a major bump; `validate` enforces it at cut time
([#1415](https://github.com/mw-ding/mdstack/issues/1415)).
`scripts/release-compat.py X.Y.Z` pins the baseline: the greatest stable
`vA.B.C` tag below `X.Y.Z`, the published predecessor, at its commit. Its
corpus is named in the script: the shipped `connectors/github/manifest.toml`
and an external pack derived from it, both read from the baseline tree. Each
must pass the baseline's own `core/crew-config.py validate`, then the
candidate's.

- **Refusal.** A manifest that newly fails refuses a same-major minor or
  patch. The message names the baseline, the manifest, the failing
  requirement and the major to cut. The cut's builder fixes it: re-run
  `changelog-cut.py` at that major with a `**Breaking:**` entry, or restore
  compatibility in a normal PR first.
- **Major.** A major cut allows the break and lists it.
- **Baseline unreadable.** A missing tag, or a corpus manifest the baseline
  itself rejects, fails with a repair step: fetch tags or repair the corpus.

It runs in the validate job on a real cut PR, on a simulated cut, on a
dispatch and before publishing. Release validation green stays the release
gate's condition; this check only makes that validation refuse a version the
versioning rules already forbid. Red validation is fixed, never waived: no
merge-ok covers it.

### Cut freeze

A cut validated on a stale merge ref is not validated: a fragment that lands
after the cut's base leaves `changes/unreleased/` non-empty at the merge
commit, and `validate` refuses publishing (v5.0.0,
[#918](https://github.com/mw-ding/mdstack/issues/918); 7.2.0, #1424 and
main-red #1432). The [§7 merge gate](protocol.md#7-merge-gate-synthesizer)
closes it with two rules
([#1433](https://github.com/mw-ding/mdstack/issues/1433)); on tmux
`mdstack train check` reports both and `train land` re-checks the hold:

- **Fresh validate.** A cut PR, one whose diff adds a new version heading
  to `CHANGELOG.md`, is ready only when its head contains the current
  default branch (gate `release-cut`). Update-branch it, so `release.yml`
  `validate` re-runs on current `main`; it never takes the
  `lone_pr_land = "direct"` waiver. A fragment landed meanwhile then fails
  the cut's own `validate`, and the builder re-runs the cut.
- **Fragment hold.** While a cut PR is open, every other PR that adds a
  file under `changes/unreleased/` holds until the cut lands (gate
  `state-permission`). An unreadable open-PR list or CHANGELOG patch holds too, and blocks the cut. This replaces
  the coordinator's hand-posted `hold-until-#<cut>`.

Paths follow the profile `[release]` table (`changelog`, `fragments`).

`workflow_dispatch` on `main` with `version=X.Y.Z` and `dry_run` remains
for dry runs and manual fallback. Every dispatch runs the CI gate at the
dispatched `main` commit: it refuses unless `ci.yml` is green there.
`dry_run=true` validates and builds only; it never tags or publishes, and
skips the actor check. Other PRs touching the workflow or release
scripts run validate and build on a simulated cut without publishing.
A real fallback is owner-only and retains the
cut PR's per-PR merge-ok and actor check; it supplies no new approval path.

## Release operations

Release is a backend concern ([interfaces: release](interfaces.md#release),
[#585](https://github.com/mw-ding/mdstack/issues/585)), so a project or
pack on any backend gets the release gate from its profile instead of
rebuilding it. The optional [`[release]` table](profile.md#release) names
the CHANGELOG, the fragment directory, the versioning scheme and the release
id kind; its defaults are today's behaviour. The synthesizer lands an
approved cut; the backend then runs approve-check, record-release and notify
on the landed revision.

| Operation | GitHub binding (this repo, unchanged) | Commit-id binding ([below](#commit-release-id)) |
|---|---|---|
| `cut` | Steps 1–2: `changelog-cut.py X.Y.Z` on a branch, opened as the cut PR | `changelog-cut.py X.Y.Z --project config.toml` on a branch, opened as the cut change |
| `approve-check` | Steps 3–5 and 7: `release.yml` `prepare`, `ci-gate`, `validate` and the publish job's approval step: owner merge-ok marker at the cut PR's head, green `ci.yml` push run at the merge commit, push actor `RELEASE_OWNER` | A release job on the landed revision reads the cut change's markers (`markers.read`) for the owner's merge-ok at its head, checks required CI green at that revision (`ci.check-status`) and runs the same validation as step 4 |
| `record-release` | Step 8: annotated tag `vX.Y.Z` on the merge commit and a GitHub Release with the bundle and `SHA256SUMS` | The full 40-character hash of the landed cut commit, posted on the release item with the version and bundle checksum |
| `notify` | Step 9: release link on the release issue, which is closed | The id and link posted on the release item, which is closed |

`changelog-cut.py` works on any layout: paths come from flags or the
profile, it needs no `check-repo.py`, and a fragment needs only `type`
(`issue`, `pr`, `date` and `box-skill` are optional). It ships in the
release bundle as a [Deliverable](deliverables.md#inventory)
([#1033](https://github.com/mw-ding/mdstack/issues/1033)), so a pack on a
host with only the installed bundle runs `cut` as
`python3 <bundle>/scripts/changelog-cut.py X.Y.Z --project config.toml`
from its own checkout; the other release scripts stay Internal. mdstack's repo guard
still requires all five fields here
([CONTRIBUTING: CHANGELOG](../CONTRIBUTING.md#changelog)).

The mechanical [`mdstack merge-up`](runtimes/tmux.md#mdstack-merge-up)
helper (#239) is an additive minor command surface. It reuses Git merges,
strict content comparison and the native signed COMMENT transport;
helper success adds no approval, CI waiver or release permission.

## Release gate

Summary of the registry row that [R1.3](#follow-up-issues) added; the
[gate registry](protocol.md#gate-registry) holds the current wording. It
gates publishing, not merging; the §7 gates are unchanged. The row is
backend-neutral ([#585](https://github.com/mw-ding/mdstack/issues/585));
the GitHub binding of each term is in the table above.

| Gate | Satisfied by | Who / how fast | Fail-open | Binding |
|---|---|---|---|---|
| Release approval | The owner's per-change `pass=steer cmd=merge-ok sha=<head>` marker at the landed cut change's head (or the coordinator's, citing a recorded [release delegation](#release-delegation)), verified by `release.approve-check` before `release.record-release` writes the release id, with release validation green, required CI green at the landed cut revision and the publishing actor matching the configured release owner | Owner on the cut change before landing, on the coordinator's ask under the §6 owner SLA; approve-check verifies before the release id is written | None for publishing: no standing merge grant or auto-applied default publishes a release; a recorded release delegation is the owner's go, not a fail-open. The §6 owner-decision path may only defer or cancel it | backend (`release` concern) |

### Release delegation

The owner may record a standing go for cuts once instead of a chat reply per
cut ([#1435](https://github.com/mw-ding/mdstack/issues/1435)). The profile
key `runtime.options.release_delegation`
([runtime options](configuration/runtime-options.md#tmux-options), on `tmux`
and `session`) holds the
owner's recorded words and a `https://` link to the record; the default
`none` keeps a per-cut owner merge-ok. It takes effect only when an owner
account sets it in the owner's profile or team file; a pack is refused, and
no role sets or edits it.

- **With the key set,** the coordinator records the owner's merge-ok on a cut
  PR at its full head SHA, citing the delegation's link:
  `role=coordinator pass=steer cmd=merge-ok sha=<head> cmd-id=release-delegation`.
  That marker satisfies the synthesizer's §7 merge permission for the cut
  ([Steps](#steps) 2) and `release.approve-check` (step 7), which still
  checks the marker's author, PR number and full head SHA against
  `RELEASE_OWNER` as before.
- **Unchanged either way:** the `RELEASE_OWNER` actor check, required CI,
  release validation, holds and `crew:sensitive`. A `crew:sensitive` cut
  still needs the owner's own per-change merge-ok at head.
- **Without the key,** a `cmd-id=release-delegation` merge-ok counts for
  nothing; the synthesizer blocks the cut until the owner's words for that
  cut are recorded, as today. The publish job cannot read the profile, so
  the key is enforced at the synthesizer's §7 check, before the cut lands.

The key covers release cut PRs only; it is not a merge grant for any other
change.

**Enforcement gap.** This repo is private on the GitHub Free plan, which
cannot add required reviewers to an environment, and the bots share the
owner-level account on some runtimes
([merge enforcement](merge-enforcement.md), [#80](https://github.com/mw-ding/mdstack/issues/80)).
The publish job checks the cut PR's head-bound owner merge-ok marker and
`RELEASE_OWNER` actor before tagging or publishing; environment approval is
not the release go. With `RELEASE_OWNER` unset, publishing refuses. Shared
owner-level accounts mean the actor check alone cannot distinguish a bot
from the owner, so owner authorization remains a convention enforced through
the marker: no role invents an owner merge-ok. The standing merge grant and
an auto-applied default never authorize publishing; only the owner's
per-cut merge-ok or a recorded [release delegation](#release-delegation) does. Roles may dispatch dry runs;
only the owner dispatches a real manual fallback with the same approval.

## Rollback

| Case | Action |
|---|---|
| Validate or build fails | Nothing was published. Fix forward by PR; retry through the owner-only manual fallback |
| Published release is bad | Never delete or move a tag; pins depend on it. Edit the Release title to "Withdrawn" with a pointer, then cut a patch that reverts or fixes |
| An environment must go back | Reinstall the previous tag ([update path](#update-path)), re-render, drift check, deploy, record the version |
| A pack must go back | Move `mdstack_version` back to the previous tag ([version pin](packs.md#version-pin)) |

## Commit release id

The non-GitHub reference binding: a project whose repo and review system
have no tags sets `release_id = "commit"` in its
[`[release]` table](profile.md#release). Everything above holds; only the
recorded id differs.

- **Release id.** The full 40-character hash of the landed cut commit, the
  revision approve-check verified. The version is the top `[X.Y.Z]` section
  of the CHANGELOG at that commit; the release item's record-release post
  maps version to id. Landed history is never rewritten, so the id never
  moves.
- **Version pin.** A pack or install pinned to such a release names the
  hash; the [version pin](packs.md#version-pin) rule applies unchanged. A
  hash that is not a recorded release id is not a release.
- **Update path.** Record writes the hash as `VERSION`. Learn compares it
  with the latest record-release post on the tracker instead of the latest
  GitHub Release. Take checks out that commit, checks that its top
  CHANGELOG section is the recorded version and the bundle matches the
  posted checksum, then re-renders, drift-checks, deploys and records the
  hash.
- **Rollback.** Never revert or rewrite the cut commit. A bad release gets
  a "Withdrawn" post on its release item, then a patch cut. An environment
  or pack goes back by moving `VERSION` or the pin to the previous recorded
  hash and re-rendering, as for a tag.

## Update path

How installed environments learn about and take a new version. Pull only:
nothing pushes a version into an environment.

| Step | Mechanism | Owner |
|---|---|---|
| Record | The install writes the bundle's `VERSION` (a tag, or a hash under a [commit release id](#commit-release-id)) next to the live copy | Bootstrap ([#144](https://github.com/mw-ding/mdstack/issues/144)) |
| Learn | Each coordinator compares its recorded version with the latest GitHub Release in its triage window; bootstrap's `mdstack doctor` reports it too ([#160](https://github.com/mw-ding/mdstack/issues/160) row 17). The live Grok Bot coordinator learns the same way; the publish job's release-issue notice is a courtesy, not the mechanism | Coordinator |
| Decide | Minor or patch: the coordinator upgrades. Major: the owner OKs it after reading the `**Breaking:**` entries and the major's section of the [migration guide](guides/migration.md) | Coordinator / owner |
| Take | Fetch the bundle at the tag (from GitHub, or the `url` or `mirror` [release source](bootstrap.md#release-sources-design) in `[install]`), check `SHA256SUMS` (a `git` source instead checks the tag against its pinned commit and builds the bundle from it), re-render with the project profile, run `check-skill-drift.py --project` against the live dir, deploy, record `VERSION`. Under a user-level install ([mdstack install](runtimes/tmux.md#mdstack-install)), `mdstack upgrade --version` (or `--latest`) also re-renders every other project the install serves, then moves `~/.mdstack/releases/current`, so the `~/.mdstack/bin/mdstack` launcher follows; the previous tag rolls back. Grok Bot keeps the [mirror hold gate](runtimes/grok-bot.md#mirror-hold-gate) record for the deploy | Coordinator via bootstrap upgrade |
| Before bootstrap | Check out the tag in an mdstack clone, or extract the release bundle ([README: Install](../README.md#install)), and run the same render, drift check and deploy by hand | Coordinator |

After a major, the owner applies its migration before the next owner command:
for 8.0.0, drop `--project` from owner commands and scripts and rerun
`mdstack layout --write`
([7.x to 8.0.0](guides/migration.md#7x-to-800-owner-commands-without---project)).
The `--project` forms in this page are the low-level scripts', which keep it.

## Upstreaming the session tooling

The first non-Grok session built its helpers outside the repo, unversioned
([#144](https://github.com/mw-ding/mdstack/issues/144) problem list). Each
becomes a deliverable `crew` subcommand, a module after
[#224](https://github.com/mw-ding/mdstack/issues/224), so they land after
that split and touch no shared lines.

| Helper role | What it does | Becomes |
|---|---|---|
| Brief generator | Fills the [worker brief template](roles.md#worker-brief-template) from an issue, role, tier and engine | `mdstack brief` |
| Review runner | Hands pinned review to the existing lead; passing review routes fresh validation with actual builder-engine exclusion | [`mdstack review`](runtimes/tmux.md#mdstack-review-verdict-and-recheck) |
| Verdict poster | Checks completed sections and posts one COMMENT verdict bound to full head/base/round, under the actual author | [`mdstack verdict`](runtimes/tmux.md#mdstack-review-verdict-and-recheck) |
| Ack poster | Checked intake, clean merge-up and owner steering acknowledgements, with no approval power | [`mdstack ack`](runtimes/tmux.md#mdstack-ack) |
| Merge-up runner | Merges the default branch into a behind change and posts the merge-up note | `crew merge-up` |
| Light re-check | Explicit fresh merge-up recheck at the prior approval round; unconfirmed/broader content routes normal review | [`mdstack recheck`](runtimes/tmux.md#mdstack-review-verdict-and-recheck) |

Proposed as follow-ups (below); the coordinator files them.

The #237 remainder adds [`mdstack brief --issue`](runtimes/tmux.md#mdstack-brief)
over the rendered role instructions while preserving existing run-block
output. Marker ack is separate from the shipped inbox `action ack`/`acked`;
its generic steering mode refuses commands with downstream marker effects,
including `merge-ok` and round resets. These additive helpers are a
minor version change; they change no protocol marker or merge gate.

The #238 remainder ships the three command surfaces over the existing
passes and checked posting transport. Verdict runs neither pass, rejects
incomplete/stale/foreign bindings before any review/tag write, and reconciles
lost post responses by readback. Single-identity COMMENT verdicts and all
merge gates retain their meaning; this additive surface is a minor change.

## Follow-up issues

| ID | Issue | Scope | Depends on |
|---|---|---|---|
| R1.2 | [#217](https://github.com/mw-ding/mdstack/issues/217) | `scripts/changelog-cut.py`: `[Unreleased]` to `[x.y.z] - <date>` | this design |
| R1.3 | [#218](https://github.com/mw-ding/mdstack/issues/218) | `release.yml`, validate and publish jobs, dry-run in CI, release gate row; `crew:sensitive` | R1.2 |
| R1.4 | [#219](https://github.com/mw-ding/mdstack/issues/219) | Retro-tag `v1.0.0`; cut `v2.0.0` after M14 and the #139 smoke | R1.3, #139 |
| proposed | not filed yet | Deliverables manifest with an unclassified-path check; bundle build; helper upstreaming | listed in the #145 PR |
