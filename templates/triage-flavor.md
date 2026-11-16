# Triage flavor record

At install/intake, the owner confirms `flavor.name` in the project profile.
At triage, resolve the item's default from explicitly named paths' classes,
or the project flavor when none are named. An unset project flavor is
`standard`; flag the gap. Until class resolution is available, retain
`thorough` for named paths whose class default cannot be verified.

Post this signed comment on every triaged issue. Replace all placeholders;
omit `Reason:` only when no rigor knob is lowered. Owner-selected flavors
carry the owner's words as the reason. Tier measures difficulty separately.

```text
<title:coordinator/flavor> · #<n>: <flavor> (default <default>)
Reason: <reason>
<!-- crew:v1 role=coordinator pass=flavor issue=<n> flavor=<flavor> default=<default> tier=<tier> -->
<CoordinatorSignature> · <harness> · <model>
```

`tier=` is optional: add it (`trivial`, `default` or `deep`) only to allocate
the item's execution tier, and omit it otherwise. `mdstack spawn` reads the
newest of your records that carries `tier=`, so a later record without it
keeps the allocation; an explicit `--tier` still wins, and no allocation
leaves the role default. A malformed tier refuses the item's spawns until a
newer record corrects it. The tier never changes the flavor or any gate.

Check the proposed record with `scripts/item-flavor.py --project config.toml
--issue N` (add `--default NAME` for a verified class default), passing JSON
comment bodies oldest first, including the proposal last. Exit 1 refuses a
lowered record without a nonempty whole-line `Reason:`. Never post that
proposal; retain the default and request a reason through the coordinator.
On each wake roles read the newest coordinator record; missing records use
`thorough` and report `flavor-missing`, refused records use the default and
report `flavor-refused`. Tightening applies immediately. Flavor records
supply no new merge authority; F1–F7 still apply.

## Express items

Record `express` ([express lane](../docs/express-lane.md#eligibility)) only on
the owner's words or within a recorded owner grant for express items; quote
them in `Reason:`. First run the sensitive classifier
(`core/crew-config.py sensitive --paths-only`) on the paths the issue names and apply
`crew:sensitive` on a match. Then check the record with `--labels` set to the
issue's labels, comma-separated:

```text
scripts/item-flavor.py --project config.toml --issue N --labels "<labels>" < bodies.json
```

A `crew:sensitive` or `crew:spec` item is `express-ineligible` unless the
record carries the owner's per-item words on a whole line
`Owner override: <owner's words>`. A `crew:solo` item is never eligible, and
a missing `--labels` fails closed. On `express-ineligible` (exit 1), post the
default record instead and never apply `crew:express`. On `recorded` with
flavor `express`, post the record, then apply `crew:express` to the issue.
