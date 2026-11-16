#!/usr/bin/env python3
"""Review summary card (#1947, docs/protocol.md §4): one rule from verdict facts to status and landing risk.

Table-driven: each rule input is varied over its values from one low-risk baseline, with the expected status
and risk written out by hand; every missing input gives unknown, never low (negative controls); the CLI entry
point prints the same card and refuses an unknown state with a nonzero exit.
"""
import importlib.util
import os
import subprocess
import sys
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(TESTS))
SCRIPT = os.path.join(ROOT, "core", "summary-card.py")
spec = importlib.util.spec_from_file_location("summary_card", SCRIPT)
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

BASE = dict(verdict="pass", ci="green", sensitive=False, round=1, cap=3, paths=["docs/guide.md"])
LOW = ("low", "docs only; CI green; no open blocking findings")

# (input, value, expected (level, reason)) from BASE with that one input changed.
RISK = [
    ("verdict", "pass", LOW),
    ("verdict", "changes", ("high", "open blocking findings")),
    ("ci", "green", LOW),
    ("ci", "pending", ("medium", "CI pending")),
    ("ci", "red", ("high", "CI red")),
    ("sensitive", False, LOW),
    ("sensitive", True, ("medium", "crew:sensitive")),
    ("round", 1, LOW),
    ("round", 2, LOW),
    ("round", 3, ("medium", "round 3 of 3")),
    ("cap", 1, ("medium", "round 1 of 1")),
    ("paths", ["docs/guide.md", "changes/unreleased/1-x.md"], LOW),
    ("paths", ["environments/terminal/crew.d/verdict.py"], ("medium", "runtime code changed")),
    ("paths", ["docs/protocol.md"], ("medium", "gate-contract/protocol paths")),
    ("paths", ["docs/specs/team.md"], ("medium", "gate-contract/protocol paths")),
    ("paths", ["templates/policy/reviewer/passes.md"], ("medium", "gate-contract/protocol paths")),
    ("paths", ["docs/protocol-notes.md"], LOW),
]

# Combinations the single-input table cannot show: reasons join at the winning level only.
COMBOS = [
    (dict(sensitive=True, paths=["core/x.py"]), ("high", "sensitive runtime change")),
    (dict(verdict="changes", round=3), ("high", "open blocking findings; round cap reached")),
    (dict(verdict="changes", ci="red", sensitive=True, paths=["core/x.py"]),
     ("high", "open blocking findings; CI red; sensitive runtime change")),
    (dict(ci="pending", paths=["templates/a.md", "core/x.py"]),
     ("medium", "gate-contract/protocol paths; runtime code changed; CI pending")),
]

STATUS = {"passed": "🟢 passed", "ready": "🟢 ready to land", "changes": "🟡 changes requested",
          "blocked": "🔴 blocked", "escalated": "🔴 escalated", "pending": "⚪ pending"}


class Rule(unittest.TestCase):
    def test_each_input_by_value(self):
        self.assertEqual({k for k, _, _ in RISK}, set(sc.INPUTS))
        for key, value, want in RISK:
            with self.subTest(key=key, value=value):
                self.assertEqual(sc.risk(**dict(BASE, **{key: value})), want)

    def test_combinations(self):
        for change, want in COMBOS:
            with self.subTest(change=change):
                self.assertEqual(sc.risk(**dict(BASE, **change)), want)

    def test_missing_or_invalid_input_is_unknown_never_low(self):
        for key in sc.INPUTS:
            with self.subTest(key=key):
                self.assertEqual(sc.risk(**dict(BASE, **{key: None})), ("unknown", "missing " + key))
        self.assertEqual(sc.risk(**dict(BASE, paths=[])), ("unknown", "missing paths"))
        self.assertEqual(sc.risk(**dict(BASE, ci="failed")), ("unknown", "missing ci"))
        self.assertEqual(sc.risk(), ("unknown", "missing verdict, ci, sensitive, round, cap, paths"))

    def test_status_and_card_lines(self):
        self.assertEqual(set(STATUS), set(sc.STATUS))
        for state, word in STATUS.items():
            with self.subTest(state=state):
                self.assertEqual(sc.card(state, **BASE), "**Status:** %s\n**Landing risk:** 🟢 low · %s" % (word, LOW[1]))
        self.assertEqual(sc.card("pending", emoji=False), "**Status:** pending\n**Landing risk:** unknown · "
                         "missing verdict, ci, sensitive, round, cap, paths")


class Cli(unittest.TestCase):
    def run_cli(self, *argv, stdin=""):
        return subprocess.run([sys.executable, SCRIPT, *argv], input=stdin, capture_output=True, text=True)

    def test_prints_card_from_flags_and_stdin_paths(self):
        r = self.run_cli("--state", "ready", "--verdict", "pass", "--ci", "pending", "--sensitive", "no",
                         "--round", "2", "--cap", "3", "--paths", "-", stdin="docs/protocol.md\n\ncore/x.py\n")
        self.assertEqual((r.returncode, r.stdout, r.stderr), (0, "**Status:** 🟢 ready to land\n**Landing risk:** 🟡 medium · "
                         "gate-contract/protocol paths; runtime code changed; CI pending\n", ""))

    def test_missing_flags_print_unknown(self):
        r = self.run_cli("--state", "pending", "--verdict", "pass", "--no-emoji")
        self.assertEqual((r.returncode, r.stdout), (0, "**Status:** pending\n**Landing risk:** unknown · "
                                                       "missing ci, sensitive, round, cap, paths\n"))

    def test_refuses_unknown_state_or_value(self):
        for argv in (["--state", "approved"], ["--state", "ready", "--ci", "failed"], []):
            with self.subTest(argv=argv):
                r = self.run_cli(*argv)
                self.assertEqual((r.returncode, r.stdout), (2, ""))
                self.assertIn("error", r.stderr)


if __name__ == "__main__":
    unittest.main()
