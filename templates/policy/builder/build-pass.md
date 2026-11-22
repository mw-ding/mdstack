   that closes #<n>:
   `<op:change.list-open>`.
   If one exists, adopt it and never open a second PR: check out its branch
   in your worktree, handle it as a fix round (below) for its latest verdict
   findings or red CI, then go to step 5.
2. Read the repo's `AGENTS.md` and the worker brief rules in
   `<mdstack>/docs/roles.md`; if cited docs are unreadable, write
   `blocked: #<n> spec-unreadable`. A ban on tested sends never blocks your
   required reporting writes. Rigor comes only from flavor records and path
   classes; report an unrecorded brief floor as `flavor-unrecorded`.
   Pin the toolchain: `export PATH=<toolchain-bin>:$PATH`. Work only in your
   worktree, on a branch `builder/<n>-` plus a short slug.
   <local-checks>
3. Run `$CREW_BIN action heartbeat` (it refreshes the claim
   file's `heartbeat:` line; where it answers `unsupported`, as in a session
   run, edit that line yourself) at least every 5 min and after each commit,
   push and post (§6).
   Never start a background loop that refreshes the claim, heartbeat or
   status file; for a long wait (CI, a test rerun) use the harness's own
   background-task notification (#1283).
4. Classify full diff paths with `<op:classify.sensitive> --project "$CREW_PROJECT"`
   per protocol `Sensitive class`; with `[[sensitive.content]]` rules, pipe
   `git diff --no-color --no-renames origin/<default-branch>...HEAD` to
   `sensitive --diff` instead. Apply `crew:sensitive` and record matches
   (carry, re-check and override: PR conventions).<linkage-check> Open a non-draft PR: `<op:change.open>`, body per §3, written once, never
   edited; label it `crew:in-review`. Labels, fragment and posts use only
   the opened number, never a guess (#2019).<land-publish><fragment-step>
   After each push, read the head back (`<op:change.read-head>`); use that
   full SHA, never a local hash, in markers, evidence and `done:`.
   A CLI change that only runs against test fakes may use a named test
   command that invokes it and asserts exit, stdout and stderr as its repro
   pair (verification Q2).
