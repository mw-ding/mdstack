---
title: A wrong-typed item URL in one status record raised `TypeError` through `status --all` on #1905 and hid a valid instance; the parser now diagnoses every wrong type, held by a field-by-type matrix and a CLI matrix with a valid control (#1913)
date: 2026-11-15
status: applied
source: The round-1 verdict on #1905 (closes #1313, M57 ST), intake card #1913
---

# Malformed shared-status record crashed the aggregate view, 2026-11-15

## Diagnose a wrong-typed record field; keep valid neighbours visible

- **Date:** 2026-11-15
- **Source / evidence:** The round-1 verdict on #1905 (closes #1313, M57
  ST) at head `92e20b9`, finding 1; the builder's round-1 fix note at
  `b985cd0`, commit `e53a66af`; the merged change `7c48f9f`; and intake
  card #1913. Affected files: `core/status-record.py` (`_section`,
  `parse_slot`) and `dev/tests/core/test-status-record.py`.
- **Finding:** At `92e20b9`, `_item` reported a list or dict item URL as
  invalid, but `_section` then called `seen.add(item["url"])` on every
  list-section item anyway. One comment with
  `sections.prs.items[0].url = []` raised `TypeError` through shipped
  `mdstack status --all`: exit 1, empty stdout, no table, no diagnostic and
  no row for the valid second instance. Spec S.1 requires a wrong-typed
  field to be refused, and S.5 requires each malformed comment to become a
  `diagnostic:` line while valid instances stay visible, exit 0. The
  reviewer reproduced it through `cli/mdstack` against the fake status API.
  The repair adds only valid string URLs to the duplicate-blocker set and
  makes `parse_slot` refuse a record nested deeper than any valid one
  (`MAX_DEPTH = 8`, measured iteratively), so a hostile body cannot exhaust
  the stack either.
- **Impact:** One of two red findings in #1905's round 1, so one extra
  review round shared with the other. Caught before merge; no released
  build carried the crash.
- **Fix:** Code and regressions: the parser treats a wrong type as a
  problem on every path and never raises. Two regressions in
  `dev/tests/core/test-status-record.py` hold it, and PR CI runs them.
  `RecordRows.test_every_field_with_every_wrong_type` replaces every path
  of the full record, containers included, with each JSON type and expects
  problems and no exception, the valid record as control.
  `RecordRowsThroughCli.test_wrong_typed_item_values_in_every_section`
  puts a wrong-typed value in every item key of every list section, plus a
  5000-deep body, beside a valid control, and expects through shipped
  `status --all` exit 0, one `diagnostic:` per bad comment, each bad
  instance `invalid`, the control `fresh` and no writes. When a change
  touches record S fields or the aggregate view, keep these tests and add
  a row for any new field.
- **Status:** applied: the string-only guard in `_section` and the depth
  limit in `parse_slot` are in `core/status-record.py` on `main` since
  `7c48f9f`, and the tests above enforce them in PR CI. No
  `scripts/check-repo.py` check does, so it is not `encoded`.
- **Linked issue/PR:** #1905, #1313, #1913
