#!/usr/bin/env python3
"""Review summary card (docs/protocol.md §4 Summary card, #1947): two advisory lines atop a verdict or gate-status post.

    **Status:** 🟢 passed
    **Landing risk:** 🟡 medium · runtime code changed

The card is display only: it supplies no approval, permission or gate input; markers and §7 gates decide.
Status maps the caller's state; landing risk comes from one rule over facts already in the post:

- inputs: verdict at head (`pass`: no open 🔴 finding; `changes`: open 🔴 findings), `crew:sensitive`, the
  changed paths (gate-contract/protocol paths; runtime code = any non-`.md` path, else docs only), CI at head
  (`green`, `red`, `pending`), round and round cap. Any missing input makes the risk ⚪ unknown, never low.
- 🔴 high: open blocking findings, CI red, a sensitive runtime change, or the round cap reached without a pass.
- 🟡 medium: sensitive, gate-contract/protocol paths, runtime code, CI pending, or the round cap reached.
- 🟢 low: none of the above (docs only, CI green, no open blocking finding, round below cap).

Usage: summary-card.py --state S [--verdict V] [--ci C] [--sensitive yes|no] [--round K] [--cap N] [--paths -]
[--no-emoji]; `--paths -` reads changed paths, one per line, from stdin. Python 3 stdlib only.
"""
import argparse
import sys

STATUS = {"passed": ("🟢", "passed"), "ready": ("🟢", "ready to land"), "changes": ("🟡", "changes requested"),
          "blocked": ("🔴", "blocked"), "escalated": ("🔴", "escalated"), "pending": ("⚪", "pending")}
RISK = {"high": "🔴", "medium": "🟡", "low": "🟢", "unknown": "⚪"}
GATE_PATHS = ("docs/protocol.md", "docs/specs/", "templates/")
INPUTS = ("verdict", "ci", "sensitive", "round", "cap", "paths")


def risk(verdict=None, ci=None, sensitive=None, round=None, cap=None, paths=None):
    """(level, reason) by the one rule above; a None or invalid input gives ("unknown", "missing <inputs>")."""
    given = dict(verdict=verdict, ci=ci, sensitive=sensitive, round=round, cap=cap, paths=paths or None)
    bad = [k for k in INPUTS if given[k] is None] + [k for k, ok in (("verdict", ("pass", "changes")),
                                                                     ("ci", ("green", "red", "pending")))
                                                      if given[k] is not None and given[k] not in ok]
    if bad:
        return "unknown", "missing " + ", ".join(bad)
    runtime = any(not p.endswith(".md") for p in paths)
    gate = any(p == g or g.endswith("/") and p.startswith(g) for p in paths for g in GATE_PATHS)
    at_cap = round >= cap
    high = [r for c, r in ((verdict == "changes", "open blocking findings"), (ci == "red", "CI red"),
                           (sensitive and runtime, "sensitive runtime change"),
                           (at_cap and verdict != "pass", "round cap reached")) if c]
    if high:
        return "high", "; ".join(high)
    medium = [r for c, r in ((sensitive, "crew:sensitive"), (gate, "gate-contract/protocol paths"),
                             (runtime, "runtime code changed"), (ci == "pending", "CI pending"),
                             (at_cap, "round %s of %s" % (round, cap))) if c]
    if medium:
        return "medium", "; ".join(medium)
    return "low", "docs only; CI green; no open blocking findings"


def card(state, emoji=True, **inputs):
    """The two card lines for a status state (STATUS key) and the risk inputs."""
    mark, word = STATUS[state]
    level, reason = risk(**inputs)
    lead = lambda m: m + " " if emoji else ""
    return "**Status:** %s%s\n**Landing risk:** %s%s · %s" % (lead(mark), word, lead(RISK[level]), level, reason)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--state", required=True, choices=sorted(STATUS))
    p.add_argument("--verdict", choices=["pass", "changes"])
    p.add_argument("--ci", choices=["green", "red", "pending"])
    p.add_argument("--sensitive", choices=["yes", "no"])
    p.add_argument("--round", type=int)
    p.add_argument("--cap", type=int)
    p.add_argument("--paths", choices=["-"])
    p.add_argument("--no-emoji", action="store_true")
    a = p.parse_args(argv)
    paths = [l.strip() for l in sys.stdin if l.strip()] if a.paths else None
    sensitive = None if a.sensitive is None else a.sensitive == "yes"
    print(card(a.state, emoji=not a.no_emoji, verdict=a.verdict, ci=a.ci, sensitive=sensitive, round=a.round,
               cap=a.cap, paths=paths))
    return 0


if __name__ == "__main__":
    sys.exit(main())
