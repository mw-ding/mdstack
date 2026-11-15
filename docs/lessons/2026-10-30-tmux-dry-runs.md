---
title: Two local dry runs and three live runs of the tmux crew for #139: 6 manual unblocks in dry run 1, then a land lock on a placeholder path and an auto-apply merge-ok offer live, until the final run passed pass bar a–g; each finding mapped to its fix PR or backlog issue (#269, #270)
date: 2026-10-30
status: mixed
source: Two local dry runs and three live runs of the tmux crew for #139 (mw-ding/eng-crew#139, mw-ding/eng-crew#234)
---

# Lessons: tmux crew dry runs and live runs

Two local dry runs and three live runs of the tmux crew for #139, all on
2026-10-30. The dry runs used an isolated tmux server, a fake `gh` and a
local bare origin; the live runs used the private sandbox repo
md-mt/eng-crew-sandbox on real GitHub with real CI. All used real Claude Code
and Codex windows. Each run's evidence comment numbers its own findings, so
IDs repeat across runs; below they are qualified by run (for example "live
F5", "re-run N1"). Unqualified B and F IDs are the first dry run's.

| Run | Evidence | Result | Fixes |
|---|---|---|---|
| Dry run 1 (main fe0a70b) | mw-ding/eng-crew#139 | Reached a merge with 6 manual unblocks: B1, B2, F1–F21 | #241, #240, #247, #244 |
| Dry run 2 (main 863a2c2) | mw-ding/eng-crew#234 | 0 unblocks, but two scenarios failed: N1–N8, F15 confirmed | #260, #253 |
| Live run 1 (main d811df6, sandbox PR #2) | mw-ding/eng-crew#139 | Merged; pass bar a and f only: F1–F7 | #253, #256, #260 |
| Live re-run (main 18ef546, sandbox PR #4) | mw-ding/eng-crew#139 | Merged; pass bar b, c, f; d partial: N1–N6 | #268, #267, host hook trust |
| Final live run (main 7eb454d, sandbox PR #6) | mw-ding/eng-crew#139 | Pass bar a–g all PASS; M1, L1 non-blocking | #269, #270 (open) |

## Entries

### The watcher wedged and the wake queue lost or doubled records (B1, F10, F11, F12)

- **Date:** 2026-10-30
- **Source / evidence:** first dry run, mw-ding/eng-crew#139. The watcher ran
  `crew poll` (no `--once`) as a blocking `--source` and never read
  `queue.jsonl`: the queue held `ci-passed` while the coordinator slept. Poll
  events were queued twice (F10); the coordinator truncated the queue by hand
  (F11); a killed watcher left `watcher.pid` and replayed an old `done:` (F12).
- **Finding:** The one wake path into the coordinator could block forever,
  and the queue had no safe reader.
- **Impact:** Blocker; one manual unblock (re-arm with `--once`).
- **Fix:** Architecture: each source runs under a timeout and a timed-out
  source becomes a `source-timeout` wake; the watcher wakes on queue growth;
  a source that grew the queue has its stdout ignored; state saved after
  every scan and on SIGTERM/SIGINT; new `crew drain` under `wake/queue.lock`.
  Regression tests in `scripts/test-crew.py`. The brief's one-shot source is
  in #244.
- **Status:** applied. `docs/runtimes/tmux.md` crew watch and crew drain, in
  #241.
- **Linked issue/PR:** mw-ding/eng-crew#230, mw-ding/eng-crew#241

### An evidence-only fix round deadlocked round 2 (B2, F3, F18, F21)

- **Date:** 2026-10-30
- **Source / evidence:** first dry run, mw-ding/eng-crew#139. `crew poll`
  emitted `ci-passed` only on a head or CI change, so a fix with no commit
  woke no reviewer, and the round-2 reviewer stopped as `stale`. Review and
  validate claims collided (F3); the reviewer worktree and the `ci-passed`
  record had no round (F18, F21).
- **Finding:** Multi-round review at an unchanged head could not proceed
  without the owner.
- **Impact:** Blocker; one manual unblock (the owner chose to push a commit).
- **Fix:** Architecture: poll derives the round and emits `fix-at-head` for a
  builder `pass=fix` at the verdict head; claims and worktrees carry round and
  pass; `ci-passed` carries `round` (#247). Brief side: the coordinator
  spawns the next round on that `done:`, and the reviewer's idempotency check
  is keyed per round (#244). Tests in `scripts/test-crew.py`.
- **Status:** applied. `docs/runtimes/tmux.md` crew poll table and spawn
  claims, in #247; tmux briefs in #244.
- **Linked issue/PR:** mw-ding/eng-crew#232, mw-ding/eng-crew#247,
  mw-ding/eng-crew#244

### Processes, hooks and env leaked across windows (F2, F5, F6, F8, F19)

- **Date:** 2026-10-30
- **Source / evidence:** first dry run, mw-ding/eng-crew#139. 7 Codex
  processes survived `crew down` and `kill-server` (Codex ignores SIGHUP,
  F2). The coordinator's Stop hook fired in a builder window (F5). The
  coordinator's trust dialog defaulted to `No, exit` (F6). The sandbox
  variable reached Codex role windows only, so both harnesses first exited 71
  (F8). `crew up` printed render chatter (F19).
- **Finding:** Window isolation held for worktrees but not for processes,
  hooks or environment.
- **Impact:** Two manual unblocks (sandbox env, trust dialog) and orphaned
  processes after teardown.
- **Fix:** Architecture: `crew kill` / `crew down` stop the pane's process
  group and verify it is gone; `crew guard` is a no-op unless
  `CREW_ROLE=coordinator`; `CREW_SANDBOX_ENV` goes to every window; Codex
  coordinator pre-trusted; render output only on failure. Claude Code has no
  per-project trust option, so its dialog now probes `ambiguous` and the
  operator accepts it once ([runbook: tmux runtime](../runbook-new-repo.md#tmux-runtime)).
  Tests in `scripts/test-crew.py`.
- **Status:** applied. `docs/runtimes/tmux.md` crew up, crew kill, crew guard
  and crew status, in #240.
- **Linked issue/PR:** mw-ding/eng-crew#231, mw-ding/eng-crew#240

### Probes and restart misread runs (F4, F7, F17, F20)

- **Date:** 2026-10-30
- **Source / evidence:** first dry run, mw-ding/eng-crew#139. A builder that
  died after a normal `done:` could not be restarted or flagged (F4). Codex's
  `Hooks need review` dialog stalled every Codex window while status said
  `alive`, losing about 5 minutes on one review (F7). The synthesizer used
  the reviewer's avoid-the-builder-engine rule (F17). A dead pane's command
  read `export` (F20).
- **Finding:** Liveness and restart rules treated a waiting builder as
  finished and a stalled window as alive.
- **Impact:** One manual unblock per Codex window (F7) and one refused
  restart (F4).
- **Fix:** Architecture: `done:` is terminal only for reviewer and
  synthesizer runs; the hooks dialog probes `ambiguous`; only the reviewer
  avoids builder engines; a dead pane reads `dead`. Tests in
  `scripts/test-crew.py`. Dismissing the Codex dialog is still an operator
  step (runbook troubleshooting).
- **Status:** applied. `docs/runtimes/tmux.md` Q7, crew status and crew
  restart, in #247.
- **Linked issue/PR:** mw-ding/eng-crew#232, mw-ding/eng-crew#247

### The briefs did not work outside eng-crew (F1, F9, F13, F14, F16)

- **Date:** 2026-10-30
- **Source / evidence:** first dry run, mw-ding/eng-crew#139. The briefs never
  said where `crew` is (F1); the synthesizer took a raw `flock` on a missing
  `locks/` dir and hand-rolled a lock (F9); they cited eng-crew `docs/` paths
  absent in the target repo, copied in by hand (F13); no role wrote a step
  summary, so `crew logs` was empty (F14); `gh` commands lacked `-R` (F16).
- **Finding:** The rendered briefs assumed they ran inside the eng-crew repo.
- **Impact:** One manual unblock (docs copied in); one improvised land lock.
- **Fix:** `CREW_BIN` in every window env (#240), and in the briefs with
  `<eng-crew>/docs/` paths from `paths.eng_crew`, `crew land-lock`, a
  concrete `step-summary.py` call and a `-R <owner>/<repo>` rule (#244).
  Prose only for the brief text, because whether a role follows its brief
  depends on agent behaviour at run time; the renderer's golden files only
  pin the text.
- **Status:** applied. `templates/runtimes/tmux/*.md`, in #244.
- **Linked issue/PR:** mw-ding/eng-crew#233, mw-ding/eng-crew#244,
  mw-ding/eng-crew#240

### Codex read-only sandbox and status writes (F15)

- **Date:** 2026-10-30
- **Source / evidence:** suspected in dry run 1 (masked by the inherited
  outer sandbox) and confirmed in dry run 2, mw-ding/eng-crew#234: the first
  sandboxed write exited 71 and every later one needed an escalation. Not
  reproduced in the live runs on this host (live F3).
- **Finding:** Codex `-s read-only` cannot write `$CREW_STATUS` or
  `verdicts/`, which sit outside the worktree.
- **Impact:** A reviewer that cannot write `done:` looks silent; where the
  escalation prompts, the window stalls.
- **Fix:** Architecture: every Codex pass runs `-s workspace-write
  --add-dir <state-dir>/<owner>__<repo>` (#260). Network for the same passes
  is a separate gap (final M1).
- **Status:** applied. `scripts/crew` Codex launch and
  `docs/runtimes/tmux.md` spawn pre-trust, in #260; network is
  mw-ding/eng-crew#269.
- **Linked issue/PR:** mw-ding/eng-crew#250, mw-ding/eng-crew#260,
  mw-ding/eng-crew#269

### Dry run 2: a restart duplicated a PR and the coordinator typed into windows (dry-2 N1–N8)

- **Date:** 2026-10-30
- **Source / evidence:** dry run 2, mw-ding/eng-crew#234. Restarting a
  builder that died after `done:` opened a duplicate PR 59 s after the first
  (N2, high). A Codex `Hooks need review` dialog stalled a reviewer for 15
  minutes, then the coordinator cleared it and every later one with
  `tmux send-keys`, which no doc allows (N3, high). Also: `.crew/` step
  summaries counted as unlanded work (N7), no `CREW_PROJECT` (N5), the
  watcher died on SIGHUP (N8), a liveness-class change re-fired a stale wake
  (N4), `<role>` unrendered in a branch name (N1), scratch files left after
  kill (N6).
- **Finding:** The happy path needed no unblocks, but restart and dialog
  handling had no safe rule, so the coordinator improvised.
- **Impact:** A duplicate PR, 15 minutes stalled, and a coordinator acting
  inside role windows.
- **Fix:** Architecture: a builder after `done: #n #pr sha` restarts as
  `--pass fix --pr <pr>`; a `dialog` wake on the next scan; `.crew/` in
  `info/exclude`; `CREW_PROJECT` in every window; SIGHUP trapped; stale key
  without the liveness class (#260). Briefs: never type into a role window,
  escalate instead; the build pass adopts an open PR; the branch prefix is
  rendered (#253); the brief lint guards the no-typing rule in CI (#261). Scratch files:
  #268 and, for files outside the state dir, #270.
- **Status:** applied. `docs/runtimes/tmux.md` restart and `dialog:` wake,
  in #260; `templates/runtimes/tmux/coordinator.md`, in #253;
  `scripts/test-tmux-briefs.py`, in #261.
- **Linked issue/PR:** mw-ding/eng-crew#250, mw-ding/eng-crew#260,
  mw-ding/eng-crew#251, mw-ding/eng-crew#253

### Live run 1: wrong land-lock path and an auto-apply merge-ok offer (live F1–F7)

- **Date:** 2026-10-30
- **Source / evidence:** first live run, mw-ding/eng-crew#139, sandbox PR #2
  squashed. The synthesizer ran `crew land-lock --project crew.toml` in its
  worktree, whose committed `crew.toml` has placeholder paths, so the lock
  serialised nothing (F5, high). The coordinator offered to auto-apply the
  merge-ok at a deadline under `merge_grant = "none"`, citing an eng-crew
  grant from `docs/protocol.md` (F4, high). It answered a Codex dialog
  itself (F2). Close-out left `crew:ready`, `crew:approved` and the head
  branch (F6). Untracked `.crew/` forced `crew kill --discard` (F7). An
  assignment before the first poll gave no wake; the §6 sweep covered it
  (F1). One trust answer covered every worktree (F3, positive).
- **Finding:** The crew merged, but the land lock, the merge-ok rule and the
  close-out each relied on the brief reader getting it right.
- **Impact:** Pass bar failed on b, c, d, e and g; two high findings.
- **Fix:** Architecture: `CREW_PROJECT` with the absolute path, refusal
  of placeholder paths, `.crew/` excluded and every `runs/<window>.*`
  removed by kill (#260). Briefs: no auto-apply merge-ok, a hold default
  at the deadline, protocol-prose grants never apply to a target profile,
  post-merge close-out with label clearing and a guarded branch delete
  (#256); no typing into role windows (#253). F1 needs no fix.
- **Status:** applied. `scripts/crew` placeholder refusal, in #260;
  `templates/runtimes/tmux/coordinator.md` merge-ok asks and close-out, in
  #256.
- **Linked issue/PR:** mw-ding/eng-crew#255, mw-ding/eng-crew#256,
  mw-ding/eng-crew#260

### Live re-run: an inherited placeholder path and an incomplete close-out (re-run N1–N6)

- **Date:** 2026-10-30
- **Source / evidence:** second live run, mw-ding/eng-crew#139, sandbox PR #4
  squashed. The placeholder check read only keys written in the profile
  file, so a `crew.toml` without `paths.state_dir` inherited `<state-dir>`
  from the default profile and the lock went under the working dir (N1,
  high). An untrusted hook in the host's own Codex config showed the hooks
  dialog in every Codex window; detection and escalation worked (N2). The
  close-out left `crew:in-review`, and no role set `crew:approved` (N5). One
  ask was closed by a plain comment (N4). Kill left a verdict file, a
  `runs/body/` file and a `/tmp` scratch file (N6).
- **Finding:** The F5 class came back through layering, and the label rules
  had no single owner.
- **Impact:** Pass bar failed on a, e and g; d partial.
- **Fix:** Architecture: placeholder checks run on resolved values,
  whichever layer set them; kill removes `runs/**/<window>[.-]*` and the
  round's verdict files (#268). Briefs: the verdict sets the state labels,
  close-out clears `crew:in-review` and `crew:changes`, asks close as COMMENT
  reviews (#267). N2: the owner trusted the host hook; it is a host
  prerequisite in the [runbook](../runbook-new-repo.md#tmux-prerequisites),
  and safe pre-resolution is #262. The `/tmp` file is #270.
- **Status:** applied. `scripts/crew` placeholder check and kill, in #268;
  `templates/runtimes/tmux/*.md`, in #267; the final run passed d and e.
- **Linked issue/PR:** mw-ding/eng-crew#265, mw-ding/eng-crew#268,
  mw-ding/eng-crew#266, mw-ding/eng-crew#267, mw-ding/eng-crew#262

### Final live run: review network and scratch files (final M1, L1)

- **Date:** 2026-10-30
- **Source / evidence:** final live run, mw-ding/eng-crew#139, sandbox PR #6
  squashed with pass bar a–g all PASS.
- **Finding:** Codex review and validate run with network off, so their
  `gh` calls work only because this host auto-approves escalations (M1,
  medium). `--body-file` scratch files are written outside the state dir
  (L1, low).
- **Impact:** None in this run. On a host that prompts, review and validate
  stall (M1); scratch files outlive the run (L1).
- **Fix:** Proposed: give review and validate network for `gh` without
  host approval (#269); write scratch files under the state dir (#270).
- **Status:** L1 applied: the tmux briefs write `--body-file` scratch files
  under `$CREW_STATE/runs/`, which `crew kill` cleans (#270). M1 open.
  Backlog, non-blocking per pass bar g; documented as a known gap in the
  [runbook troubleshooting](../runbook-new-repo.md#tmux-troubleshooting).
- **Linked issue/PR:** mw-ding/eng-crew#269, mw-ding/eng-crew#270,
  mw-ding/eng-crew#356
