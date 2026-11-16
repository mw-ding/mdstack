#!/usr/bin/env python3
"""Role post titles (#1946, docs/protocol.md §4): one bracket-free, emoji-led form, rendered from one place.

Table-driven: every role x pass x report status renders the expected title through both entry points (the
renderer's <title:role/pass> placeholder and crew.d's post_title), and with report.emoji = false drops only the
emoji. The readers moved off the title decide by the crew:v1 marker: an old bracketed post and a new one with
the same marker read the same, and a title without its marker is never accepted (negative controls).
"""
import importlib.util
import os
import sys
import unittest
from importlib.machinery import SourceFileLoader

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(os.path.dirname(TESTS))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pt = load("post_title", "core/post-title.py")
cr = load("crew_render", "core/crew-render.py")
report = load("campaign_report", "scripts/campaign-report.py")
_loader = SourceFileLoader("crew_cli", os.path.join(ROOT, "cli", "mdstack"))
crew = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", _loader))
_loader.exec_module(crew)
shared = sys.modules["crew_shared"]

# Written out by hand, so the oracle never reuses the code under test.
IDENTITY = {"coordinator": ("Ash", "🔥"), "builder": ("Ben", "🛠️"), "reviewer": ("Vera", "🔎"),
            "synthesizer": ("Sam", "🔀"), "researcher": ("Riley", "🔬")}
PASSES = {"coordinator": {"flavor": "Flavor", "decision": "Decision", "steer": "Steer", "handoff": "Handoff",
                          "close-out": "Close out", "kill": "Kill", "placement": "Placement", "ask": "Ask"},
          "builder": {"fix": "Fix", "ci-fix": "CI fix", "merge-up": "Merge up", "selfgate": "Selfgate",
                      "watch": "Watch"},
          "reviewer": {"ack": "Ack", "verdict": "Verdict", "hold": "Hold", "escalation": "Escalation"},
          "synthesizer": {"merge": "Merge", "gate-status": "Gate status"},
          "researcher": {"research": "Research", "triage": "Triage", "docs-pass": "Docs pass",
                         "reflection": "Reflection"}}
STATUS = {"pass": "✅ pass", "changes": "🔁 changes", "landed": "🚢 landed", "escalated": "⛔ escalated",
          "blocked": "🚧 blocked"}
SHA = "a" * 40


def values(emoji=True):
    out = {"report.emoji": emoji}
    for role, (name, mark) in IDENTITY.items():
        out["identities.%s.name" % role], out["identities.%s.emoji" % role] = name, mark
    return out


def marker(role, pass_, **extra):
    fields = dict(role=role, pass_=pass_, pr="12", sha=SHA, round="1", verdict="n/a", **extra)
    return "<!-- crew:v1 %s -->" % " ".join("%s=%s" % (k.rstrip("_"), v) for k, v in fields.items())


class Render(unittest.TestCase):
    def test_every_role_pass_and_status_renders_the_expected_title(self):
        self.assertEqual(set(STATUS), set(cr.crew_config.REPORT_STATUS))
        self.assertEqual(set(IDENTITY), set(cr.ROLES))
        on, off = cr.Renderer(values(), None), cr.Renderer(values(False), None)
        for role, (name, mark) in IDENTITY.items():
            for pass_, word in PASSES[role].items():
                for status in STATUS.values():
                    with self.subTest(role=role, pass_=pass_, status=status):
                        want = "%s %s · %s · round 1 @ aaaaaaa · %s" % (mark, name, word, status)
                        self.assertEqual(shared.post_title(values(), role, pass_, "round 1 @ aaaaaaa", status), want)
                        self.assertEqual(on.line("<title:%s/%s> · round 1 @ aaaaaaa · %s" % (role, pass_, status)),
                                         want)
                        self.assertNotIn("[", want)
                        self.assertEqual(off.line("<title:%s/%s>" % (role, pass_)), "%s · %s" % (name, word))
                        self.assertEqual(shared.post_title(values(False), role, pass_), "%s · %s" % (name, word))
                        self.assertEqual(pt.parse(want), (name, pass_, "round 1 @ aaaaaaa · " + status))
                        self.assertEqual(pt.parse("[%s/%s] round 1 @ aaaaaaa" % (name, pass_)),
                                         (name, pass_, "round 1 @ aaaaaaa"))

    def test_stack_position_reads_naturally(self):
        self.assertEqual(shared.post_title(values(), "reviewer", "review", "stack 4/12", "round 1", "🔁 changes"),
                         "🔎 Vera · Review · stack 4/12 · round 1 · 🔁 changes")

    def test_unknown_role_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "unknown placeholder"):
            cr.Renderer(values(), None).line("<title:owner/merge>")

    def test_prose_is_not_a_title(self):
        for line in ("Fix the · Thing", "plain text", "[not a title", "- [x] done"):
            self.assertIsNone(pt.parse(line), line)


class Readers(unittest.TestCase):
    """Old and new titles over the same marker read the same; a title over a missing or unrelated marker never
    counts (#1951 round 1)."""

    def setUp(self):
        self.poll, self.route = crew.commands()["poll"], crew.commands()["route"]

    def test_decision_relay_reads_the_marker(self):
        coordinator, owners = ("md-mt", "Ash"), {"owner"}
        steer = marker("coordinator", "steer", cmd="decision", **{"cmd-id": "chat"})
        unrelated = marker("coordinator", "flavor")
        rows = []
        for title in ("[Ash/decision] owner: accept #3", "🔥 Ash · Decision · owner: accept #3",
                      "Ash · Decision · owner: accept #3"):  # old, new, new with emoji off
            rows += [(title + "\n\n" + steer, True),  # a valid decision marker decides
                     (title + "\n", False),  # missing marker: the title alone never qualifies
                     (title + "\n\n" + unrelated, False)]  # unrelated marker: neither
        for body, want in rows:
            with self.subTest(body=body):
                comment = {"author": {"login": "md-mt"}, "body": body}
                self.assertEqual(self.poll.triage_feedback(comment, owners, coordinator), want)
                self.assertEqual(report.decision(body), want)

    def test_merge_up_delta_reads_the_marker(self):
        note = "\nThe conflicts are resolved.\n\n%s\n— 🛠️ Ben (Builder) · h · m\n" % marker("builder", "merge-up")
        other = marker("builder", "status")
        for title, body_marker, want in (("[Ben/merge-up] @ aaaaaaa", "valid", True),
                                         ("🛠️ Ben · Merge up · @ aaaaaaa", "valid", True),
                                         ("[Ben/status] @ aaaaaaa", "valid", True),  # the marker decides
                                         ("[Ben/merge-up] @ aaaaaaa", "missing", False),
                                         ("🛠️ Ben · Merge up · @ aaaaaaa", "missing", False),
                                         ("[Ben/merge-up] @ aaaaaaa", "unrelated", False),
                                         ("🛠️ Ben · Merge up · @ aaaaaaa", "unrelated", False)):
            with self.subTest(title=title, marker=body_marker):
                body = title + note.replace(marker("builder", "merge-up"),
                                            {"valid": marker("builder", "merge-up"), "missing": "", "unrelated": other}[body_marker])
                pr = {"number": 12, "reviews": [{"body": body}]}
                self.assertEqual(self.route.merge_up_delta(pr, SHA, "Ben"), want)


if __name__ == "__main__":
    unittest.main()
