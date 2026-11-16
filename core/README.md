# core

Shared libraries only, used by every axis. Part of the
[module layout](../docs/specs/team.md#4-target-module-layout).

## Contents

| File | Holds |
|---|---|
| `crew-config.py` | Profile schema, layering, validation and resolution ([profile](../docs/profile.md), [resolution](../docs/configuration/resolution.md)) |
| `crew-render.py` | Renders role briefs from templates, the registry and the resolved profile |
| `crew-roles.py` | Role registry validation ([role registry](../docs/roles-registry.md)) |
| `crew-routines.py` | Role routine validation and due-slot logic ([routines](../docs/routines.md)) |
| `crew-memory.py` | Core memory lint and brief injection ([memory](../docs/memory.md)) |
| `crew-pack.py` | Pack plug-in discovery and checks ([packs](../docs/packs.md#pack-plug-ins)) |
| `status-record.py` | Shared-status record S v1: closed schema, slot body and content identity ([shared status](../docs/specs/shared-status.md#3-record-s-version-1-s1)) |
| `post-title.py` | Role post titles: the one bracket-free format and its two-form parser ([protocol §4](../docs/protocol.md#4-marker-conventions)) |
| `summary-card.py` | Advisory review summary card: colored status and the one landing-risk rule ([protocol §4](../docs/protocol.md#4-marker-conventions)) |
| `secret-patterns.py` | Secret-scan patterns shared by profile validation and the repo guard |
| `path-glob.py` | Path glob matching shared by profile rules and the repo guard |
| `markdown-scan.py` | Markdown fence, code-span, comment and link scanning shared by the docs scan and the repo guard |

## How it plugs in

Environments, connectors, harnesses and the CLI import these modules. Core
depends on no module above it (dependency rule D4).
