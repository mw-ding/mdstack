---
title: The #2001 deployment diagram drew a nonexistent spawn edge and routed merge-ok to Issues; canonical diagrams now keep a per-edge source table that review compares edge by edge (#2018)
date: 2026-11-22
status: applied
source: Docs change #2001 (closes #1988, M62 D3), its two changes-requested reviews, intake card #2018
---

# A canonical diagram's edges disagreed with their sources, 2026-11-22

## Compare every diagram edge with the anchor it depicts

- **Date:** 2026-11-22
- **Source / evidence:** Docs change #2001 (closes #1988, M62 D3), the new
  deployment, wake and release Mermaid diagram in `docs/architecture.md`.
  Round-one review found a synthesizer-to-worker spawn edge that the
  runtime does not have, and no per-edge source mapping; the first repair
  drew the lead-as-lander topology and added the E1–E23 source table.
  Round-two review found owner merge-ok drawn to Issues, while protocol §9
  and §7 take steering on the PR conversation or a review; the second
  repair split issue feedback from PR steering (E2, E23). Intake card
  #2018 and its triage record.
- **Finding:** The diagram's acceptance criteria were declared met while
  two edges contradicted the runtime and protocol sources they stood for.
  Nothing tied each edge to a source, so the author never compared them,
  and each review round found a different wrong edge. One diagram change,
  two distinct wrong edges.
- **Impact:** Two changes-requested review rounds and two repair pushes on
  #2001 before merge. Nothing wrong merged; no runtime or gate behaviour
  changed.
- **Fix:** Level 5, prose only, because whether a drawn edge matches the
  runtime is judgement over prose and code that no repo check can verify.
  `docs/diagrams/README.md`, "Rule: every canonical edge cites its source",
  requires an edge table beside every canonical diagram, each row citing
  the code or doc anchor it depicts, with the deployment diagram's E1–E23
  table as the example. The review of a diagram change compares every
  changed edge's ends, direction and channel with its anchor; an
  uncited or contradicted edge is an unmet acceptance criterion.
- **Status:** applied: the rule is on `main` in `docs/diagrams/README.md`
  (#2018), and the E1–E23 table is in `docs/architecture.md`. No
  `scripts/check-repo.py` check enforces it, so it is not `encoded`.
- **Linked issue/PR:** #2018, #2001, #1988
