# Derived context leaking into the resolved profile, 2026-11-14

## Keep derived values out of the resolved profile

- **Date:** 2026-11-14
- **Source / evidence:** #1866 (closes #1856, M56 T1), the builder's
  round-1 fix note on head `5b561aa`, its passing re-review, and intake
  card #1883. Cause commit `2e0b6df`, fix commit `7f749f3`. Affected
  files: `environments/terminal/crew.d/_shared.py`,
  `environments/terminal/crew.d/grant.py` and
  `dev/tests/environments/test-crew-grant.py`.
- **Finding:** To give work envelopes a routing context, `2e0b6df` made
  `_shared.profile()` add three derived keys (`context.team`,
  `context.project`, `context.repo`) to the resolved values it returns.
  `grant prune` relies on those values being exactly the profile: before
  it replaces the project file, it resolves the staged copy with
  `crew_render.resolve` and refuses unless the result equals the current
  values with only `runtime.options.merge_grant` changed
  (`grant.py`, the `proposed != dict(values, ...)` check). A fresh resolve
  has no `context.*` keys, so the two never matched, every prune refused
  with `pruned profile invalid or other effective values changed`, and
  `test-crew-grant.py` failed in `repo-guard` CI on `bb296ab`. The fix
  (`7f749f3`) removed the keys from `profile()` and made
  `work_context(project, values)` compute the context on demand from the
  project path and the resolved repo and team. Its callers (`route.py`,
  `send.py`, `poll.py`, `spawn.py`, `lead.py`, `up.py`, `_repo_bind.py`)
  call it where they build or compare an envelope. `test-crew-grant.py`
  then passed 27 of 27.
- **Impact:** One ci-red fix on #1866, folded into its round-1 fix. No
  release shipped the leak; it never reached `main`.
- **Fix:** Architecture: derived values stay out of the resolved profile,
  so the "values are exactly the profile" contract holds by design rather
  than by a filter. `_shared.profile()` returns only what
  `crew_render.resolve` produced (plus the runtime binding it already
  did), and anything computed from it, such as the routing context, is a
  separate function its callers call. The existing whole-dict equality in
  `grant prune` and the apply-path tests in `test-crew-grant.py` are what
  fail if a derived key comes back, and CI runs them on every PR. Future
  runtime observations (review readiness, delivery or shared status) get
  their own functions or records, not new keys in the resolved output.
- **Status:** applied: `work_context` in
  `environments/terminal/crew.d/_shared.py` on `main` at `a62eb19`, with
  `profile()` returning the resolved values unchanged. Not `encoded`: no
  `check-repo.py` check names the rule; the `test-crew-grant.py` prune
  tests in PR CI are the regression.
- **Linked issue/PR:** #1866, #1856, #1883
