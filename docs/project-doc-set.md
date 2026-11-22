# Project doc set

Reference module for the docs of the projects a crew works on, split out of
the [project docs consolidation design](project-docs.md) under the M26
modular organization principle
([#1024](https://github.com/mw-ding/mdstack/issues/1024)): the essential
doc set every crew-run project should have and the status banner a design
doc carries. Owner 2026-11-07 ([#1219](https://github.com/mw-ding/mdstack/issues/1219)):
specs are every project's source of truth, so they are essential too. The profile's [`[docs]`](profile.md#docs) table maps a
project's homes; the docs pass that checks them stays in the design.

## Essential doc set

Every crew-run project should have these six docs. The canonical home is
a default; a project with an existing home for one maps it in the profile
(`[docs] homes`, [profile](profile.md#docs)) instead of moving it.

| Doc | Purpose | Default home | Kind |
|---|---|---|---|
| Overview | What the project is, who it serves, how to get started, links to the rest | `README.md` | reference |
| Agent guide | What a crew role needs to build and review here: build and test commands, the local check set, review posture, crew profile notes | `AGENTS.md` | rule |
| Architecture | Components, boundaries, data flow and where each lives in the tree | `docs/architecture.md` | reference |
| Runbook | How to run, deploy, operate and recover the project | `docs/runbook.md` | reference |
| Decisions | Dated decisions with their reasons and rejected options, newest first; each design doc's decision links here | `docs/decisions.md` | history |
| Specs | The project's source of truth: what it must do, as stable requirement IDs with acceptance criteria and verification, one spec per topic; each carries a [status banner](#status-banners) | `docs/specs/` | design |

- **Agent guide.** The file the builder brief already reads ("Read the
  repo's `AGENTS.md`", [roles](roles.md)). Its **crew profile notes** say
  what the crew must know about this project and the profile can't express:
  which paths are sensitive and why, the flavor and its reason, owner rules
  specific to the repo, and which docs a role reads at start. It links to
  `config.toml` for values and never restates them.
- **Specs.** A directory of one or more specs, each seeded from the
  [spec template](../templates/spec.md). A spec is a design doc, so it carries
  the status banner below; work that changes what the project must do updates
  its spec first. `[docs] homes` maps `specs` to a directory (no anchor);
  the docs pass reports it missing when no Markdown spec sits under it, and
  `mdstack bootstrap` seeds `project.md` there from the template's skeleton
  when it has none, never overwriting a spec
  ([#1225](https://github.com/mw-ding/mdstack/issues/1225)).
  A project whose specs live outside the repository names that tracker item
  or document with `[docs] specs_external` instead
  ([profile](profile.md#docs), #1725): the coordinator's spec bookends name
  it, bootstrap seeds nothing, and the docs pass records it as not checked.
  The spec-first and status-sync bookends still apply.
- **Docs index.** A project with more than five docs under `docs/` also keeps
  `docs/README.md`: one row per doc with its purpose and kind, in the shape of
  [mdstack's index](README.md#available-now).
- **Small projects.** A section of `README.md` may be the home of the
  architecture, runbook or decisions doc while it stays under about 100 lines
  (specs keep their own directory);
  the profile maps it to `README.md#<anchor>`.
- **Not essential.** API references, changelogs, contributor guides and
  design docs are kept when a project has them; the pass checks their banners
  and links but never reports them missing.

## Status banners

A design doc in a target project states its lifecycle right under its H1,
in the shape of [principle 3](README.md#documentation-principles) and
[triage.md](triage.md):

```markdown
# <Title>

> - **Status:** design | partly built | built | superseded
> - **Applies to:** <scope>
> - **Current rules:** <links to the docs that own the live rules>
> - **Built:** <issues or PRs, or "nothing">
> - **Last checked:** <YYYY-MM-DD> at `<sha7>`
```

- `superseded` names its successor in **Current rules**.
- Kind (rule, reference, design, history) stays in the index, not the banner.
- Only design docs carry a banner. A rule or reference doc is live by
  definition; a history doc is dated by its title or first line.
