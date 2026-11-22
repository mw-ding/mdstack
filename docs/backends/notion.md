# Notion knowledge backend

The first backend of the [knowledge concern](../interfaces.md#knowledge)
([#1229](https://github.com/mw-ding/mdstack/issues/1229)). The owner's
personal knowledge lives in Notion, never in git
([team spec REQ-17](../specs/team.md#req-17-knowledge-in-external-services)).
This page adds no rule, gate, cap, marker field or label; knowledge is
context only and never a gate input.

The connector is `connectors/notion/`: a knowledge-only
[manifest](../../connectors/notion/manifest.toml) and the actions binding
`connectors/notion/knowledge.py`, which keeps the
[actions CLI contract](../../actions/cli.md) for
[A21 `knowledge-read`](../../actions/README.md#a21-knowledge-read) and
[A22 `knowledge-propose-edit`](../../actions/README.md#a22-knowledge-propose-edit).
Every other action is refused as `unsupported`. Until `mdstack action`
dispatches to it, a role runs the entry directly:

```sh
python3 connectors/notion/knowledge.py knowledge-read \
  --role researcher --source second-brain --out .crew/brain.md --json
python3 connectors/notion/knowledge.py knowledge-propose-edit \
  --role researcher --source second-brain --body-file .crew/proposal.md --json
```

## Sources a role declares

A role reaches a source only if its definition lists it in `knowledge`
([role registry](../roles-registry.md#schema)), for example
`knowledge = ["second-brain"]`. The name is all the repo holds. A call for
an undeclared source is refused with `no-authority` before any request.
`--roles-dir` names the role definitions to read; the default is
`roles/eng`.

## Private config

Source pointers and the credential come only from the install's private
config, never from the profile or any committed file. The connector reads
the TOML file named by `CREW_KNOWLEDGE_CONFIG`, default
`~/.config/eng-crew/knowledge.toml`:

```toml
[sources.second-brain]
backend = "notion"
page = "<32-hex Notion page ID>"
token_env = "NOTION_TOKEN"
```

- Each source has exactly `backend`, `page` and `token_env`. The token itself
  never goes in the file: `token_env` names the environment variable that
  holds the Notion integration token.
- The config is refused when git tracks it, so a pointer committed by
  mistake stops working instead of leaking quietly. The repo's
  `.gitignore` also ignores `knowledge.toml`.
- Share the page with the integration in Notion. The integration needs the
  read content, read comments and insert comments capabilities.

## Operations

| Action | Notion call | Result |
|---|---|---|
| `knowledge-read` | `GET /v1/pages/<page>`, then `GET /v1/blocks/<page>/children`, following `next_cursor` | The title and the top-level blocks as plain text in `--out`; the page URL and last edited time in the result. Nested blocks are not read. `--out` must be outside any git work tree or ignored by git |
| `knowledge-propose-edit` | `GET /v1/comments?block_id=<page>`, following `next_cursor`, then `POST /v1/comments` on the page | The `--body-file` text as a page comment, prefixed as a proposal that names the idempotency key; the comment and discussion ids, and `replayed`. The page itself is never edited |

## Idempotency

A proposal keeps the [common envelope](../../actions/README.md#common-envelope)
guarantee that the same key and inputs never cause a second effect. The key
is `--key`, or by default the action, item, source, role and a digest of the
body. The comment's first line names the role and key.

- **Key ledger.** The install's private ledger, the JSON file named by
  `CREW_KNOWLEDGE_KEYS` (default `~/.local/state/eng-crew/knowledge-keys.json`),
  records each key with a digest of its inputs, its status and the comment
  it made. It holds no proposal text. Notion lists only unresolved comments,
  so the ledger is what finds a proposal after the owner resolves it. A
  ledger inside a git work tree that git does not ignore is refused with
  `committable-keys`.
- **Lookup.** A key in the ledger with the same digest is returned as
  `completed` with `replayed: true`, and nothing is posted. The same key with a
  different digest is refused with `key-conflict`. A key not in the ledger, such
  as one used by another install, is looked up among the page's open comments
  (`GET /v1/comments`): the same text is a replay, and the same key with
  different text is `key-conflict`.
- **Uncertain posts.** The key is recorded as pending before the post. A post
  that is refused or fails frees the key. A post whose outcome is `unknown`
  keeps it pending, and a later call with that key posts nothing. It replays
  the comment if it now appears among the open comments, and otherwise
  returns `unknown`: read the page's comments, resolved ones included, then
  propose with a new key.

## Reason codes

Beyond the [fixed codes](../../actions/cli.md#json-output), this binding
returns:

| Code | Outcome | Meaning |
|---|---|---|
| `no-source` | `refused` | No private config, or the source is not in it |
| `invalid-config` | `refused` | The source entry is not exactly `backend = "notion"`, a page ID and `token_env` |
| `committed-config` | `refused` | Git tracks the private config file |
| `no-credential` | `refused` | The `token_env` variable is unset, or Notion rejected the token (401) |
| `committable-out` | `refused` | `--out` is in a git work tree and not ignored |
| `committable-keys` | `refused` | The key ledger is in a git work tree and not ignored |
| `key-conflict` | `refused` | A proposal comment on the page already carries this key with different text |

Notion's 400, 403 and 404 answers are `invalid-ref` (the page is not shared
with the integration, or the request was rejected). A read that gets no
answer or a server error is `failed` with `unreadable`. A proposal that gets
no answer or a server error is `unknown` with `uncertain-write`: read the
page comments back before proposing again.

## Tests

`dev/tests/connectors/test-notion-knowledge.py` runs both actions against a
fake Notion API with no network, covers each refusal and error mapping, and
runs the [conformance kit](../packs.md#conformance-kit) on the connector.
