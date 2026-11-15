# Findings buffer

The live buffer. How to append, when to batch and who owns it are in
[README.md](README.md). Entries use the template there.

## Entries

### Builder per-PR watch (B2) missing or not verified

- **Date:** 2026-10-23
- **PR / repo:** this repo (eng-crew), PRs #35, #38 and #41. See
  [builder-watch-attach](../lessons/2026-10-23-builder-watch-attach.md),
  [watch-handoff-first-run](../lessons/2026-10-23-watch-handoff-first-run.md)
  and [merge-gate-watch-race](../lessons/2026-10-23-merge-gate-watch-race.md)
- **Smell:** The builder's B2 watch was missing, unverified or unreadable. On
  #35 B2 never attached and the PR stalled about 62 min. On #38 the
  `pass=watch` marker carried a 7-char SHA, so the reviewer cross-check could
  not match it. On #41 the PR merged before the B2 hand-off reached the
  builder's parent turn, so no watch or marker existed.
- **Count:** 3
- **Proposed fix layer:** architecture: create and verify B2 in the same turn
  that opens the PR, so no hand-off can lag behind a fast merge. The fixes
  documented so far are prose plus a merge gate: the verified hand-off (#36, fix
  PR #37), one watch identifier and full-SHA markers (#39, fix PR #41), and the
  merge gate requiring the `pass=watch` marker (#43, fix PR #45).
- **Status:** fixed by #37, #41 and #45 (all `documented` in the lessons).
  Seeded as a worked example: three sightings of one smell became three lesson
  files and three fix PRs; under this buffer they would have been one batch
  issue.

### Synthesizer race past open coordinator hold / rereview

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), PRs #74 and #78. See
  [synthesizer-hold-race](../lessons/2026-10-29-synthesizer-hold-race.md)
- **Smell:** The synthesizer squash-merged while a coordinator hold was open:
  on #78 on a standing doc-only merge-ok before a hold-until took effect, on
  #74 on a prior APPROVE before the requested engine-diversity re-verdict.
- **Count:** 2
- **Proposed fix layer:** prose, because both checks depend on live GitHub
  state and timing; a static check-repo guard keeps the rules in the protocol
  and template. Architecture (the ruleset in
  [merge-enforcement](../merge-enforcement.md)) is the real fix.
- **Status:** fixing -> #81

### No typed runtime evidence for "prove it" (gap-table row 8)

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), issue #83. See
  [typed-verify-evidence](../lessons/2026-10-29-typed-verify-evidence.md)
- **Smell:** Reviews relied on diff and CI. No shape-specific artifact was
  required, so the validation pass had no fixed proof to check and the
  synthesizer had no evidence to gate on.
- **Count:** 1
- **Proposed fix layer:** CI check for the shape table, prose for judging
  whether an artifact matches a claim (it depends on live PR content).
- **Status:** fixing -> #83

### Long agent runs invisible mid-flight (row 9, runtime / observe)

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), issue #85. See
  [step-summary-observe](../lessons/2026-10-29-step-summary-observe.md)
- **Smell:** Long builds and tests leave no readable trace until the PR opens,
  so retries are blind and pass claims are unverifiable. Pasting full pane
  scrollback into chat would swamp the other roles instead.
- **Count:** 1
- **Proposed fix layer:** prose plus a thin helper and a fixture test; the
  structural fix (a runtime that emits step events itself) is deferred
- **Status:** fixing -> #85

### Metrics gave no decisions (gap row 11)

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), issue #86. See
  [metrics-to-decisions](../lessons/2026-10-29-metrics-to-decisions.md)
- **Smell:** Baselines for open-to-merge time and review rounds existed in
  `docs/metrics/` but nothing read them, so a slow streak or a wave of
  reviewer rework did not force a harness change.
- **Count:** 1
- **Proposed fix layer:** CI check is out of reach (needs live PR data);
  prose plus a script: `scripts/metrics-decide.py` computes the verdict
  and the coordinator files the gate issue. A scheduled routine would
  move this toward architecture.
- **Status:** fixing -> #86

### Failures and near-misses are not turned into harness work

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), issue #89. See
  [self-improve-intake](../lessons/2026-10-29-self-improve-intake.md)
- **Smell:** Failed or stuck crew work is discussed in chat and PR threads and
  then forgotten; lessons land only when someone remembers, and nothing
  separates product-local lessons from crew-wide ones (gap-table row 10).
- **Count:** 1
- **Proposed fix layer:** architecture: an intake queue with a scoped lesson
  store and a fixed trigger set, so intake does not depend on memory. v1 is
  prose plus an offline helper for one trigger.
- **Status:** fixing -> #89

### Review rounds burned on wording and script edge cases

- **Date:** 2026-10-29
- **PR / repo:** this repo (eng-crew), PRs #74, #77 and #88
- **Smell:** Reviewer rounds went to CHANGELOG and prose wording and to script
  edge cases beyond the acceptance criteria, not to criteria that failed.
  Nothing told the reviewer to keep review thin.
- **Count:** 3
- **Proposed fix layer:** prose: a root `AGENTS.md` review posture that the
  builder and reviewer templates require reading (gap row 7).
- **Status:** fixing -> #92

### Consumer reads part of a gate or action contract and treats the gap as permission

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1296)
- **PR / repo:** cards #1134, #1135, #1136, #1137, #1144, #1147, #1205,
  #1206, #1292, #1293, #1294, #1295 and #1296; repairs #979, #981, #984,
  #991, #996, #1008, #1119, #1154, #1163, #1275, #1277 and #1280. See
  [complete-contract](../lessons/2026-11-08-complete-contract.md).
  Added 2026-11-14 by the
  [M55-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6871909199)
  (#1873): #1868, its empty-present-tier finding: the parser dropped
  `tier=` and read a malformed allocation as absent, allowing a
  default-tier launch
  ([finding](https://github.com/mw-ding/mdstack/pull/1868#pullrequestreview-5900917439),
  [repair](https://github.com/mw-ding/mdstack/pull/1868#pullrequestreview-5901190217),
  [round-2 pass](https://github.com/mw-ding/mdstack/pull/1868#pullrequestreview-5901450160)).
  Added 2026-11-14 by the
  [M56-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6884116200)
  (#1887): #1866, its completion/envelope and lead-read predicates
  ([findings](https://github.com/mw-ding/mdstack/pull/1866#pullrequestreview-5899897159),
  [class-wide repair](https://github.com/mw-ding/mdstack/pull/1866#pullrequestreview-5901365620));
  #1875, its grant/eligibility/head predicates
  ([findings](https://github.com/mw-ding/mdstack/pull/1875#pullrequestreview-5902166313),
  [complete head repair](https://github.com/mw-ding/mdstack/pull/1875#pullrequestreview-5904001857));
  #1876, the successor-process check omitted from retained-work restart
  ([finding](https://github.com/mw-ding/mdstack/pull/1876#pullrequestreview-5903121022),
  [repair](https://github.com/mw-ding/mdstack/pull/1876#pullrequestreview-5903247333));
  and #1877, its incomplete train read-before-write coverage
  ([findings](https://github.com/mw-ding/mdstack/pull/1877#pullrequestreview-5904913556),
  [repair](https://github.com/mw-ding/mdstack/pull/1877#pullrequestreview-5906333201)),
  each PR counted once.
  Added 2026-11-15 by the
  [M57-close sweep](https://github.com/mw-ding/mdstack/issues/1903#issuecomment-6895229944)
  (#1916): #1896, its pending payload
  ([finding](https://github.com/mw-ding/mdstack/pull/1896#pullrequestreview-5908314357));
  #1904, counted once for its round/reset, item and author findings
  ([round/reset](https://github.com/mw-ding/mdstack/pull/1904#pullrequestreview-5908818891),
  [item](https://github.com/mw-ding/mdstack/pull/1904#pullrequestreview-5909239411),
  [author](https://github.com/mw-ding/mdstack/pull/1904#pullrequestreview-5909393321));
  #1905, its confirmed slot
  ([finding](https://github.com/mw-ding/mdstack/pull/1905#pullrequestreview-5908877174));
  and #1906, its invalid earlier ack
  ([finding](https://github.com/mw-ding/mdstack/pull/1906#pullrequestreview-5909433991)),
  each PR counted once
- **Smell:** A gate or action consumed only the fields, lines or flags it
  expected. A missing field, truncated status, unparsed flag, missing run
  record, later changes request or replayed authority read then passed as
  clean.
- **Count:** 22
- **Proposed fix layer:** types/schemas: validate the whole contract and
  treat anything incomplete as unknown; per-site regression tests hold it.
- **Status:** fixed by #979, #981, #984, #991, #996, #1008, #1154, #1163,
  #1275, #1277 and #1280; every regression test survives at `main` (#1342).

### Sandbox boundary checked once, not at every effect

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1204)
- **PR / repo:** cards #1191, #1192, #1193, #1194 and #1204; repairs #810,
  #815, #816, #820 and #1152 (#1186 reran them). See
  [sandbox-every-effect](../lessons/2026-11-08-sandbox-every-effect.md)
- **Smell:** The campaign sandbox guarded one channel once. An output path,
  a profile changed between steps, a branch that was not checked out, a
  grouped socket flag and inherited credentials each crossed the boundary.
- **Count:** 5
- **Proposed fix layer:** architecture: check the boundary at every effect,
  with a decoy test per channel.
- **Status:** fixed by #810, #815, #816, #820 and #1152; every regression test
  survives at `main` (#1342).

### Test or check bypasses the path production uses

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1272)
- **PR / repo:** cards #1126, #1138, #1198, #1210, #1248, #1260 and #1272;
  repairs #888, #992, #1066, #1073, #1080, #1169, #1243, #1253 and #1264. See
  [real-entrypoint-fixtures](../lessons/2026-11-08-real-entrypoint-fixtures.md).
  Added 2026-11-13 by the
  [M53-close sweep](https://github.com/mw-ding/mdstack/issues/1781#issuecomment-6866552379)
  (#1862): #1825, its omitted role-doc/template consumer
  ([#1126 record](https://github.com/mw-ding/mdstack/issues/1126#issuecomment-6866460059)),
  and #1833, counted once for its two format findings: fake bare milestone
  titles and unprefixed tags hid real-tracker failures
  ([round-1 finding](https://github.com/mw-ding/mdstack/pull/1833#pullrequestreview-5889997782),
  [repair](https://github.com/mw-ding/mdstack/pull/1833#pullrequestreview-5890269178)).
  Added 2026-11-14 by the
  [M55-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6871909199)
  (#1873): #1865, its omitted validate/recheck handoffs
  ([finding](https://github.com/mw-ding/mdstack/pull/1865#pullrequestreview-5899267029),
  [repair](https://github.com/mw-ding/mdstack/pull/1865#pullrequestreview-5899330693)),
  and #1868, counted once for its CI campaign-stub response shape: the fake
  issue-view JSON lacked the newly required comments field
  ([finding and repair](https://github.com/mw-ding/mdstack/pull/1868#pullrequestreview-5901190217)).
  Added 2026-11-14 by the
  [M56-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6884116200)
  (#1887): #1877, its fake returned a URL real gh had not been asked for,
  hiding a broken ordinary `train check`
  ([finding](https://github.com/mw-ding/mdstack/pull/1877#pullrequestreview-5903990882),
  [repair inventory](https://github.com/mw-ding/mdstack/pull/1877#pullrequestreview-5906333201)).
  Added 2026-11-15 by the
  [M57-close sweep](https://github.com/mw-ding/mdstack/issues/1903#issuecomment-6895229944)
  (#1916): #1897, a driver-only deletion masked by a JSON-backed failure
  ([finding](https://github.com/mw-ding/mdstack/pull/1897#pullrequestreview-5908358037));
  #1908, its omitted session-render consumer
  ([finding](https://github.com/mw-ding/mdstack/pull/1908#pullrequestreview-5910048200));
  and #1909, a direct disposition test that missed the parked-wait wake
  ([finding](https://github.com/mw-ding/mdstack/pull/1909#pullrequestreview-5910488046)),
  each PR counted once
- **Smell:** A fixture or check took a shortcut around the production path.
  Examples are a moved doc source, a skipped render stage, a shell that
  masks exit codes, a snapshot over git internals, a lint that knew one
  syntax form and a checker that reads only tracked files.
- **Count:** 15
- **Proposed fix layer:** CI check: route tests through the production
  pipeline and make every assertion fail closed.
- **Status:** fixed by #888, #992, #1066, #1073, #1080, #1169, #1243, #1253
  and #1264; every regression test survives at `main` (#1342). Leftovers ->
  #1412, #1413, #1414.

### Release or install rewrite changes the meaning of what it touches

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1308)
- **PR / repo:** cards #1129, #1130, #1139, #1140, #1146, #1207, #1208, #1209,
  #1297, #1306, #1269, #1270 and #1308; repairs #913, #920, #1000, #1016,
  #1148, #1153, #1159, #1181, #1186, #1278, #1301 and #1304
- **Smell:** A release cut, upgrade or migration rewrote owner-visible state
  and changed its meaning. A minor bump made capabilities newly required
  (#1129). A `Closes` reference auto-closed an issue before publication
  (#1130). A failed toolkit replacement had already moved the working copy
  (#1139). A pinned toolkit was written into (#1140). The last launch note
  hit a no-change shortcut (#1146). Reload killed a window before respawn
  (#1207). A guard hook had two identities (#1208). A retry lost verified
  provenance (#1209). Core memory was counted against the brief budget
  (#1297). A released CHANGELOG section was edited (#1306). Unrelated hook
  text was requoted (#1269). Rollback paths were left unquoted (#1270). A
  single-quoted TOML name was skipped (#1308).
- **Count:** 13
- **Proposed fix layer:** CI check: verify before displacing, never write
  pinned content, keep one identity per invocation path, leave unrelated text
  byte-for-byte, quote anything printed for re-running, parse the result
  before moving state. The modern relocation and rename paths (#1269, #1270,
  #1308) stay supported and tested.
- **Status:** fixed by #1000, #1016, #1148, #1153, #1159, #1181, #1278 and
  #1304; their regression tests survive at `main` (#1342). The release-process
  cards (#913, #920 and #1301 were manual repairs) have no guard yet:
  leftovers -> #1415, #1416, #1417.

### Moved or quoted prose loses its consumer contract

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1212)
- **PR / repo:** cards #1125, #1127, #1128, #1131, #1133, #1142, #1143, #1211
  and #1212; repairs #830, #950, #972, #973, #1008, #1043, #1046, #1048,
  #1094 and #1186. Added 2026-11-13 by the
  [M53-close sweep](https://github.com/mw-ding/mdstack/issues/1781#issuecomment-6866552379)
  (#1862): #1851, an MD038 code-span occurrence
  ([#1128 record](https://github.com/mw-ding/mdstack/issues/1128#issuecomment-6866461542)).
  Added 2026-11-15 by the
  [M57-close sweep](https://github.com/mw-ding/mdstack/issues/1903#issuecomment-6895229944)
  (#1916): #1910, its banner omitted the installation status AC2 required
  ([finding](https://github.com/mw-ding/mdstack/pull/1910#pullrequestreview-5910831280))
- **Smell:** Text that moved or was quoted kept its words but not what its
  readers relied on. Runtime qualifiers were dropped (#1125). Numbered lists
  were split under new headings (#1127). A code span gained a separator
  space (#1128). A slice PR body kept stale linkage (#1131). A renamed
  heading broke an anchor (#1133). Generated commands lost `--project` or
  their order (#1142, #1143). A descriptive phrase parsed as a closing
  reference (#1211). A wrapped `#N` line became a heading (#1212).
- **Count:** 11
- **Proposed fix layer:** lint and CI check for the mechanical half
  (markdownlint, the CI `links` job, `check-markdown.py` MD018 and the render
  test's `assert_crew_commands_parse`); prose only for qualifiers, slice
  linkage and closing keywords, because those depend on meaning and live PR
  bodies.
- **Status:** fixed by #830, #950, #972, #973, #1008, #1043, #1046, #1048,
  #1094 and #1186; the mechanical guards survive at `main` (#1342). MD029 is
  now off repo-wide (#1190). Leftovers for #1125, #1131 and #1211 -> #1418.

### Terminal record lost or mismatched by a downstream consumer

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1199)
- **PR / repo:** cards #1141, #1145, #1195, #1196, #1197, #1199 and #1070;
  repairs #1007, #1009, #1063, #1065, #1071, #1073, #1081, #1150 and #1186.
  See [terminal-record-consumers](../lessons/2026-11-08-terminal-record-consumers.md).
  Added 2026-11-14 by the
  [M56-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6884116200)
  (#1887): #1876, its clean restart dropped the correctly produced durable
  handoff
  ([finding](https://github.com/mw-ding/mdstack/pull/1876#pullrequestreview-5902179715),
  [repair](https://github.com/mw-ding/mdstack/pull/1876#pullrequestreview-5903113186),
  [passing source verdict](https://github.com/mw-ding/mdstack/pull/1876#pullrequestreview-5903457187)).
  Added 2026-11-15 by the
  [M57-close sweep](https://github.com/mw-ding/mdstack/issues/1903#issuecomment-6895229944)
  (#1916): #1906, counted once for its restart and inbox/ledger interruption,
  including its later ack finding
  ([finding](https://github.com/mw-ding/mdstack/pull/1906#pullrequestreview-5908983465)),
  and #1909, its spawned fix that never woke the relay
  ([finding](https://github.com/mw-ding/mdstack/pull/1909#pullrequestreview-5910488046))
- **Smell:** A record was produced correctly, then lost downstream. The
  consumers were accuracy history, ID parsing, the wake matcher, the reaper,
  scheduler inputs and the reservation ledger.
- **Count:** 10
- **Proposed fix layer:** CI check: key records by stable identity and test
  each consumer with the record as the runtime produces it.
- **Status:** fixed by #1007, #1009, #1063, #1065, #1071, #1081 and #1150;
  every regression test survives at `main` (#1342). #1266 is a later,
  separate capacity report.

### Evidence gate keyed on incidental prose, not typed proof

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1203)
- **PR / repo:** cards #1200, #1201, #1202 and #1203; repairs #1080, #1084,
  #1085, #1104, #1110 and #1113. See
  [inline-evidence](../lessons/2026-11-01-inline-evidence.md) and
  [typed-verify-evidence](../lessons/2026-10-29-typed-verify-evidence.md)
- **Smell:** The train evidence check judged surface text. It refused valid
  `user-attachments` media (#1200). It kept blocking on uncited files after a
  signed inline fix proof at head (#1201). It read paths quoted in code as
  required artifacts (#1202). Separately, every campaign PR appended to one
  shared scenario list and conflicted (#1203).
- **Count:** 4
- **Proposed fix layer:** CI check: the precheck keys on typed or signed proof;
  `merge=union` with a `check-repo.py` guard for the shared list.
- **Status:** fixed by #1084, #1085, #1110 and #1113; every regression test
  survives at `main` (#1342). #1203's optional one-file-per-scenario
  alternative -> #1419.

### Optional pack input assumed present, or a floor checked per layer

- **Date:** 2026-11-08 (recorded by #1342 from repaired cards; the last
  sighting is #1273)
- **PR / repo:** cards #1132 and #1273; repairs #919, #972 and #1265.
  Added 2026-11-14 by the
  [M56-close sweep](https://github.com/mw-ding/mdstack/issues/1870#issuecomment-6884116200)
  (#1887): #1866, a regression of the #1273 family, now closed: it used the
  nearest flavor layer and hid a stricter lower floor
  ([finding](https://github.com/mw-ding/mdstack/pull/1866#pullrequestreview-5899897159),
  [repair](https://github.com/mw-ding/mdstack/pull/1866#pullrequestreview-5900677877))
- **Smell:** Pack handling validated each input alone. A pack without
  `profile.toml` lost `pack.version` and a backend without a render map
  raised TypeError (#1132). A weaker custom flavor split across environment
  and pack layers passed the floor check (#1273).
- **Count:** 3
- **Proposed fix layer:** types/schemas: validate the merged view across every
  layer and every supported absence, through the real discovery path.
- **Status:** fixed by #919, #972 and #1265; every regression test survives at
  `main` (#1342). #1132's absence cases through `pack.toml` discovery ->
  #1411. The floor-selector false positive #1325 and VCS pinning #1326 are
  separate.
