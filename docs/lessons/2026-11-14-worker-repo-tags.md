# Worker repo tags that aliased two valid repos, 2026-11-14

## Keep the repo tag one-to-one, with the punctuation-pair regressions

- **Date:** 2026-11-14
- **Source / evidence:** The round-1 verdict on #1876 (closes #1858, M56
  T3) at head `201122d`, the builder's round-1 fix note at `025f990`, the
  merged change `43ecdb8`, and intake card #1882. Affected files:
  `environments/terminal/crew.d/_team.py` (`tag()`) and
  `dev/tests/environments/test-crew-team.py` (`RepoTags`).
- **Finding:** Team workers carry a repo tag in their window name and
  path (`ben-42-<owner>__<repo>`). At `201122d`, `tag()` folded
  punctuation, so two valid repos, `example/alpha.foo` and
  `example/alpha-foo`, both became `example__alpha-foo`. After the first
  repo spawned issue 42, the second repo's shipped `spawn` for the same
  issue exited 1 with `ben-42-example__alpha-foo already running`. The
  window-name check runs before team-global slot and run allocation, so the
  allocator could not separate the two. The reviewer reproduced it through
  shipped `up` and `spawn`. The repair made `tag()` one-to-one: `/` becomes
  `__`, and every character outside `[a-z0-9-]`, `_` and `.` included,
  becomes `_<hex>`. `example/alpha.foo` is now `example__alpha_2efoo`. A
  repo literally named `example/alpha_2efoo` becomes
  `example__alpha_5f2efoo`, so an escaped form cannot alias a literal name.
  A plain name keeps its old tag (`example/alpha` stays `example__alpha`),
  so existing names and paths did not move.
- **Impact:** One of three red findings in #1876's round 1, so one extra
  review round shared with the other two. No released build carried the
  aliasing tag: it was caught before merge.
- **Fix:** Architecture: the encoding is injective by construction, so two
  valid repos cannot share a tag. Two regressions in
  `dev/tests/environments/test-crew-team.py` hold it, and PR CI runs them.
  `RepoTags.test_valid_repos_whose_names_differ_only_in_punctuation_get_distinct_windows`
  drives the `alpha.foo` / `alpha-foo` pair through shipped `up` and
  `spawn` and expects both same-ID workers to start, with distinct windows.
  `RepoTags.test_tag_is_one_to_one_and_keeps_plain_names` checks that seven
  punctuation, `__` and escaped-literal names map to seven distinct
  `[a-z0-9_-]` tags, and that `Example/Alpha` keeps `example__alpha`. The
  one-repo control `OneRepo.test_a_one_repo_profile_keeps_its_names_and_lead_home`
  keeps untagged names such as `ben-42`. When a change touches worker
  names, keep these tests and keep the tag one-to-one. Do not add a second
  identity rewrite on top of it.
- **Status:** applied: `tag()` in `environments/terminal/crew.d/_team.py`
  is one-to-one on `main` since `43ecdb8`, and `docs/runtimes/tmux.md`
  Team pools states the encoding. The tests above enforce it in PR CI; no
  `scripts/check-repo.py` check does, so it is not `encoded`.
- **Linked issue/PR:** #1876, #1858, #1882
