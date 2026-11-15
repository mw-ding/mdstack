# connectors

**Axis:** connectors (the tools of record). Part of the
[module layout](../docs/specs/team.md#4-target-module-layout).

## Purpose

Each connector reaches one tool of record for one or more concerns: change,
review, tracker, state tags, markers, CI, events, owner channel and
knowledge. Only a connector names a tool's CLI or API (dependency rule D6).

## Contents

| Path | Holds |
|---|---|
| `github/manifest.toml` | GitHub's capability declaration for every operation of the [backend interfaces](../docs/interfaces.md) |
| `github/status.py` | The bundled binding of the optional status concern: `read-records` and `publish-record` ([shared status](../docs/specs/shared-status.md#7-optional-seam-s6)) |
| `github/crew-repo.py` | Repo-side setup fixers bootstrap runs (labels, collaborators, CI checks) |
| `notion/manifest.toml`, `notion/knowledge.py` | The knowledge-only Notion connector: `knowledge-read` and `knowledge-propose-edit` ([Notion backend](../docs/backends/notion.md)) |

## How it plugs in

A profile picks one connector per concern; profile validation folds its
manifest's capabilities and rejects a combination that cannot keep an
invariant. Operation mappings live in the backend docs, for example the
[GitHub backend](../docs/backends/github.md). A pack adds a connector as
`connectors/<name>/manifest.toml` ([pack plug-ins](../docs/packs.md#pack-plug-ins)).
