# The status connector answered `--help` with a usage error, 2026-11-15

## A supported `--help` exits 0 on stdout; only malformed arguments exit 2

- **Date:** 2026-11-15
- **Source / evidence:** Shared-status change #1905 (closes #1313, M57):
  repo-guard failed on head `92e20b92` (Actions run 43672902638) with
  `FAIL --help: connectors/github/status.py prints its Usage: line`. The
  builder's round-1 fix review on #1905, finding 3, names the repair commit
  `b985cd0f`, and CI passed at that head (run 43675467958). Intake card
  #1914. Affected files: `connectors/github/status.py` (`main()`) and
  `dev/tests/scripts/test-check-repo.py` (the `--help` sweep).
- **Finding:** The connector's `main()` accepted only `read-records` or
  `publish-record`. Any other argument list, `--help` included, printed the
  usage text to stderr and returned 2. That treated a supported help call as
  malformed syntax. The connector's own tests,
  `dev/tests/connectors/test-github-status.py`, passed on the failing run:
  they drive the two operations over stdin and never call `--help`. Only the
  repo-wide sweep caught it. That sweep runs every script `check-repo.py`
  classes as `script` with `--help` and expects exit 0 with the docstring's
  `Usage:` line on stdout. This differs from #1295, where malformed syntax
  skipped validation for an unsupported action. Here a supported help call
  was refused as a usage error.
- **Impact:** One red CI run and one extra commit in #1905's round-1 fix,
  before merge. Nothing wrong merged: the sweep caught it, and the merged
  connector keeps the two outcomes apart.
- **Fix:** `b985cd0f` added a help branch ahead of the argument check.
  `--help` or `-h` prints the module docstring to stdout and returns 0.
  Any other argument list still prints the usage lines to stderr and
  returns 2. The regression is the `--help` sweep in
  `dev/tests/scripts/test-check-repo.py`, which repo-guard runs on every PR
  and push to `main`. It holds the help half of the contract for every
  script, this connector included. No test calls the connector with a
  malformed argument list. The connector tests cover a malformed stdin
  request returning 2, not a bad argument list. No new check or test is
  added here.
- **Status:** applied: `connectors/github/status.py` `main()` on `main` has
  the separate help branch (exit 0, stdout) and the malformed-argument
  branch (exit 2, stderr). The `--help` sweep in
  `dev/tests/scripts/test-check-repo.py` enforces the help half in CI. It is
  a test, not a `scripts/check-repo.py` check, and nothing enforces the
  exit-2 half, so it is not `encoded`.
- **Linked issue/PR:** #1914, #1905, #1313
