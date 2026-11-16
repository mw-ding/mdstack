Standing grant: <merge-grant>
Profile: scope `<merge-grant-scope>`, spec `<spec-paths>`,
`hold_label_blocks = <hold-label-blocks>`, `train_min = <train-min>`,
`train_window = <train-window>` seconds, `lone_pr_land = "<lone-pr-land>"`,
`mirror_deferral = "<mirror-deferral>"`.

For each PR:

1. Re-read it live (protocol §6 step 1); stop on a moved
   head or closed/merged PR. For `crew:escalated`, an open coordinator hold-until,
   or `crew:hold`, report gate-status below before stopping.
2. Check the whole §7 merge gate at the current head. One identity: the
   approval is the reviewer's COMMENT review with
   `pass=verdict verdict=pass sha=<head-sha>`, or a passing verdict at verified H
   carried only under the portability check below. If express resolves
   (`core/crew-config.py class-flavor --express`), approval is the builder
   `pass=selfgate verdict=pass` at head or verified H. Merge permission: owner
   merge-ok (`pass=steer cmd=merge-ok`) at head, or recorded `merge_grant`.
   §7 spec changes need merge-ok unless scope has `spec` and the grant's
   decision authorizes it.
   Until follow-up B, existing recorded owner grants retain their scope regardless of merge mode.
   With `none`, require per-PR owner merge-ok; no standing grant applies.
   An applied ask default is never a merge-ok. Grants supply permission only,
   never approval or overrides for sensitive PRs, `unverified` evidence
   or open rereview (§7). `crew:sensitive` requires owner merge-ok at head;
   only a recorded owner classification override clears it. CI is never waived.
   <mirror-gate>
   Apply protocol's builder pre-review gate with `<mdstack>/scripts/crew-precheck.py --item <issue#>`
   on the live body and builder-signed reviews when enabled, including
   immediately before each train member lands. Check inline N/A reasons.
   Missing, stale, malformed or failed results block unless the
   owner's recorded per-change merge-ok is at head; standing grants never waive it.
