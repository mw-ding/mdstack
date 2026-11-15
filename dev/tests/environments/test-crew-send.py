"""Tests for mdstack send, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: inbox line format, fixed nudge, refs-only and oversized refusals, unknown window
refused; the composer check on captured Codex and Claude Code screens (stacked nudges found,
the transcript's copy and other text never cleared); against a fake composer, stacked nudges
cleared with `C-u`, other text kept, a swallowed `Enter` retried without retyping, exit 4 when
the nudge never submits or the clear fails; no key typed into any captured stuck screen in
`fixtures/dialog/` (exit 4, inbox line kept, `dialog` reported) and no `Enter` retried into a
prompt that comes up after typing, while a working screen still gets the nudge (#315). Busy delivery (#1850): a
duplicate send of a pending message keeps its id and adds no message; a busy worker gets no key past two waits and a
late ack still settles it (D2.2); dead or replaced workers take one restart unless held, idle ones one re-nudge then a
named block, dialog and unknown screens no key, quota the restart path, and an interrupted send resumes its id (D2.3);
the ledger record precedes the inbox line, and an interruption at each durable boundary leaves one id the watcher
tracks (D2.4).
Run in CI.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import os
import unittest
from unittest import mock
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import CREW, DeliveryBase, FAKE_COMPOSER, FAKE_TMUX_PANES, screen, SendBase, STUCK, WORKING


class Send(SendBase):
    def test_solo_findings_never_reach_existing_or_missing_builder(self):
        self.env["FAKE_SOLO_PR"] = "12"
        for window in ("ben-7", "ben-8"):
            for kind in ("fix", "ci-red", "merge-up"):
                result = self.send(window, kind, "#12", "a" * 40)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("skip builder delivery", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", window + ".jsonl")))
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])
        self.assertFalse(os.path.exists(os.path.join(self.state, "wake", "queue.jsonl")))

    def test_append_format_and_nudge(self):
        sha = "a" * 40
        r = self.send("ben-7", "fix", "#171", sha, "https://github.com/acme/widgets/pull/171", "docs/x.md")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r2 = self.send("ben-7", "ci-red", "#171")
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        first, second = self.inbox()
        self.assertEqual(sorted(first), ["context", "from", "id", "kind", "refs", "ts"])
        self.assertEqual(first["kind"], "fix")
        self.assertEqual(first["refs"], ["#171", sha, "https://github.com/acme/widgets/pull/171", "docs/x.md"])
        self.assertEqual(first["from"], "coordinator")
        self.assertRegex(first["ts"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertNotEqual(first["id"], second["id"])
        self.assertIn("sent %s to ben-7" % first["id"], r.stdout)
        keys = [c for c in self.calls() if c[0] == "send-keys"]
        self.assertEqual(keys[:2], [["send-keys", "-t", "=crew-acme-widgets:10", "-l", "inbox: " + first["id"]],
                                    ["send-keys", "-t", "=crew-acme-widgets:10", "Enter"]])
        self.assertEqual(len(keys), 4)

    def test_message_carries_the_envelope_and_refuses_a_foreign_one(self):  # #1856, team §9.3
        sha, mine = "a" * 40, os.path.realpath(self.project)
        own = dict(team="repo:acme/widgets", project=mine, repo="acme/widgets", item=None, change=171, head=sha, round=2)
        own["pass"] = "review"
        r = self.send("ben-7", "ci-red", "#171")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.inbox()[0]["context"], dict(own, change=None, head=None, round=None, **{"pass": None}))
        self.assertEqual(self.send("ben-7", "fix", "#171", sha).returncode, 0)  # refs `#n <sha>` name the change and head
        self.assertEqual(self.inbox()[1]["context"], dict(own, round=None, **{"pass": None}))
        before = (self.inbox(), [c for c in self.calls() if c[0] == "send-keys"])
        for env, reason in ((dict(own, repo="acme/gadgets", team="repo:acme/gadgets"),
                             "work envelope names acme/gadgets in team repo:acme/gadgets, not acme/widgets"),
                            (dict(own, head="b" * 40, change=None), "work envelope has an invalid head"),
                            ({"repo": "acme/widgets"}, "work envelope missing or not the closed key set")):
            r = self.send("ben-7", "fix", "#171", sha, "--context", json.dumps(env))
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("crew: refusing send: " + reason, r.stdout)
            self.assertEqual((self.inbox(), [c for c in self.calls() if c[0] == "send-keys"]), before)
        r = self.send("ben-7", "fix", "#171", sha, "--context", json.dumps(own))  # the control: this project's own
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.inbox()[-1]["context"], own)

    def test_self_resolved_unblocked_to_coordinator_not_nudged(self):  # #578
        ref = os.path.join(self.state, "leads", "builder-delivery-7.json")
        self.assertEqual(self.send("ash", "blocked", ref).returncode, 0)
        nudged = len([c for c in self.calls() if c[0] == "send-keys"])
        r = self.send("ash", "unblocked", ref)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("no nudge", r.stdout)
        self.assertEqual([m["kind"] for m in self.inbox("ash")], ["blocked", "unblocked"])
        self.assertEqual(len([c for c in self.calls() if c[0] == "send-keys"]), nudged)
        r = self.send("ash", "unblocked", ref + ".other")
        self.assertIn("sent ", r.stdout)
        self.assertGreater(len([c for c in self.calls() if c[0] == "send-keys"]), nudged)

    def test_team_window_0_by_full_name_or_bare_alias(self):  # #1329
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('owners = ["acme-owner"]\n', 'owners = ["acme-owner"]\nteam = "mdp-m4"\n'))
        with open(self.state_file, "w") as f:
            json.dump({"crew-acme-widgets": {"0": "ash-mdp-m4", "10": "ben-7"}}, f)
        ref = os.path.join(self.state, "leads", "builder-delivery-7.json")
        for window in ("ash", "ash-mdp-m4"):
            r = self.send(window, "blocked", ref)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("to ash-mdp-m4", r.stdout)
        self.assertEqual([c[2] for c in self.calls() if c[0] == "send-keys"][0], "=crew-acme-widgets:0")
        r = self.send("ash", "unblocked", ref)
        self.assertIn("no nudge", r.stdout)
        self.assertEqual([m["kind"] for m in self.inbox("ash-mdp-m4")], ["blocked", "blocked", "unblocked"])
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ash.jsonl")))

    def test_oversized_or_payload_rejected(self):
        diff = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n"
        for refs in [["p" * 201], ["d/" + "y" * 198] * 5, [diff], ["---a/x"], ["@@"],
                     ["Traceback"], ["two words"], ["#171", "line\nbreak"]]:
            r = self.crew("send", "--project", self.project, "ben-7", "fix", "--", *refs)  # --: refs may start with -
            self.assertEqual(r.returncode, 2, (refs, r.stdout, r.stderr))
            self.assertIn("refusing send", r.stdout)
        self.assertIn("over 1024", self.send("ben-7", "fix", *["d/" + "y" * 198] * 5).stdout)  # each ref legal
        self.assertEqual(self.send("ben-7", "Fix it", "#1").returncode, 2)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-7.jsonl")))
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])

    def test_unknown_window_refused(self):
        r = self.send("ben-8", "fix", "#1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("no window ben-8", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-8.jsonl")))
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])


# Real screens (#308), bottom rows of `tmux capture-pane -p` with the cursor from `#{cursor_x} #{cursor_y}`; the
# workdir and status line are redacted. Codex 0.164.0 after three `mdstack send` nudges whose Enter each added a newline:
CODEX_STACKED = ("", "• Explored", "  └ List probe", "    + Show details", "",
                 "■ Conversation interrupted - use /feedback if something went wrong", "", "",
                 "› inbox: 20261031T081746Z-30673c", "  inbox: 20261031T085326Z-c9db18",
                 "  inbox: 20261031T092356Z-55f592", "", "", "  GPT-5.5 xhigh · <workdir>",
                 " " * 64 + "⚠ 1 warning · f2 to view", "")
# The same stack once submitted: it is now a user message in the transcript and the composer is empty.
CODEX_SUBMITTED = ("■ Conversation interrupted - use /feedback if something went wrong", "", "",
                   "› inbox: 20261031T081746Z-30673c", "  inbox: 20261031T085326Z-c9db18",
                   "  inbox: 20261031T092356Z-55f592", "", "", "", "• Working (1s • esc to interrupt)", "", "",
                   "› Ask Codex to do anything", "", "  GPT-5.5 xhigh · <workdir>", "  ? for shortcuts", "")
# Claude Code 2.1.310 with a two-line draft: the glyph row has a no-break space after `❯`.
CLAUDE_STACKED = ("", "─" * 80, "❯\xa0inbox: 20261031T100200Z-111111", "  inbox: 20261031T100300Z-222222", "",
                  "─" * 80, "  ⏸ plan mode on (shift+tab to cycle)", "")


class Composer(unittest.TestCase):
    """The composer check on the real screens: only a composer of nothing but earlier nudges is cleared."""

    @classmethod
    def setUpClass(cls):
        loader = importlib.machinery.SourceFileLoader("crew_cli", CREW)
        cls.mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(cls.mod)

    def test_real_screens(self):
        stack = ["inbox: 20261031T081746Z-30673c", "inbox: 20261031T085326Z-c9db18", "inbox: 20261031T092356Z-55f592"]
        screen = "\n".join(CODEX_STACKED)
        self.assertEqual(self.mod.composer_draft(screen, (2, 11)), stack + [""])
        self.assertEqual(self.mod.stale_nudges(screen, (2, 11)), stack + [""])
        screen = "\n".join(CODEX_SUBMITTED)  # the transcript's copy is above the cursor's composer, never read
        self.assertEqual(self.mod.composer_draft(screen, (2, 12)), ["Ask Codex to do anything"])
        self.assertEqual(self.mod.stale_nudges(screen, (2, 12)), [])
        screen = "\n".join(CLAUDE_STACKED)
        self.assertEqual(self.mod.stale_nudges(screen, (2, 4)),
                         ["inbox: 20261031T100200Z-111111", "inbox: 20261031T100300Z-222222", ""])

    def test_other_text_never_cleared(self):
        screen = "\n".join(CODEX_STACKED).replace("› inbox: 20261031T081746Z-30673c", "› fix the flaky test")
        self.assertEqual(self.mod.composer_draft(screen, (2, 11))[0], "fix the flaky test")
        self.assertEqual(self.mod.stale_nudges(screen, (2, 11)), [])
        screen = "\n".join(CODEX_STACKED)
        self.assertEqual(self.mod.stale_nudges(screen, (9, 10)), [])  # cursor inside the last line
        self.assertEqual(self.mod.stale_nudges(screen, (32, 9)), [])  # a draft line below the cursor
        self.assertEqual(self.mod.stale_nudges(screen, None), [])  # tmux could not answer
        self.assertIsNone(self.mod.composer_draft(screen, (0, 3)))  # no composer at the cursor
        self.assertEqual(self.mod.stale_nudges("\n".join(CODEX_STACKED[:8]), (0, 7)), [])


class VerifiedNudge(SendBase):
    """mdstack send on a fake composer: clear earlier nudges, type once, retry Enter only, exit 4 if never submitted."""

    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.tmp, "bin")
        os.rename(os.path.join(bindir, "tmux"), os.path.join(bindir, "tmux-base"))
        with open(os.path.join(bindir, "tmux"), "w") as f:
            f.write(FAKE_COMPOSER)
        os.chmod(os.path.join(bindir, "tmux"), 0o755)
        self.composer = os.path.join(self.tmp, "composer.json")
        self.env["FAKE_COMPOSER"] = self.composer

    def model(self, draft=(), enters=("submit",), **kv):
        with open(self.composer, "w") as f:
            json.dump(dict({"history": ["› inbox: 20261031T070000Z-000000"], "draft": list(draft),
                            "enters": list(enters)}, **kv), f)

    def current(self):
        with open(self.composer) as f:
            return json.load(f)

    def keys(self):
        return [c[3:] for c in self.calls() if c[0] == "send-keys"]

    def test_stacked_composer_cleared_then_submitted(self):
        self.model(draft=["inbox: 20261031T081746Z-30673c", "inbox: 20261031T085326Z-c9db18", ""])
        r = self.send("ben-7", "land", "#12")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        nudge = "inbox: " + self.inbox()[0]["id"]
        self.assertEqual(self.keys(), [["C-u"] * 6, ["-l", nudge], ["Enter"]])
        self.assertIn("cleared 2 earlier inbox line(s)", r.stdout)
        self.assertEqual(self.current()["draft"], [])
        self.assertEqual(self.current()["history"][-1], "› " + nudge)  # submitted alone, not after the old lines

    def test_swallowed_enter_retried_never_retyped(self):
        self.model(enters=["newline", "submit"])
        r = self.send("ben-7", "fix", "#12")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        nudge = "inbox: " + self.inbox()[0]["id"]
        self.assertEqual(self.keys(), [["-l", nudge], ["Enter"], ["Enter"]])
        self.assertEqual(self.current()["history"][-2:], ["› " + nudge, "  "])
        self.assertIn("sent ", r.stdout)

    def test_never_submitted_exits_4(self):
        self.model(enters=["newline"])
        r = self.send("ben-7", "land", "#12", "--wait-ack", "5")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        msg_id = self.inbox()[0]["id"]  # the inbox line stays: the message is not lost
        self.assertEqual(self.keys(), [["-l", "inbox: " + msg_id]] + [["Enter"]] * 4)
        self.assertIn("nudge not submitted: %s to ben-7" % msg_id, r.stdout)
        self.assertIn("after 3 Enter retries", r.stdout)
        self.assertIn("treat ben-7 as ambiguous", r.stdout)
        self.assertNotIn("no ack", r.stdout)
        r = self.send("ben-7", "land", "#12")  # the next send clears the leftover nudge and its newlines first
        self.assertEqual(self.keys()[5], ["C-u"] * 10)

    def test_other_text_kept(self):
        self.model(draft=["fix the flaky test"])
        r = self.send("ben-7", "fix", "#12")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertNotIn(["C-u"], [k[:1] for k in self.keys()])
        self.assertEqual(self.current()["history"][-1], "› fix the flaky testinbox: " + self.inbox()[0]["id"])

    def test_clear_that_fails_types_nothing(self):
        self.model(draft=["inbox: 20261031T081746Z-30673c"], clears=False)
        r = self.send("ben-7", "land", "#12")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.keys(), [["C-u"] * 2])
        self.assertIn("still holds earlier inbox lines after the clear; nothing typed", r.stdout)
        self.assertEqual(self.current()["draft"], ["inbox: 20261031T081746Z-30673c"])

    def test_prompt_after_typing_gets_no_retried_enter(self):  # #315
        self.model(enters=["newline"], below_on_enter=screen("claude-proceed").splitlines())
        r = self.send("ben-7", "fix", "#12")
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertEqual(self.keys(), [["-l", "inbox: " + self.inbox()[0]["id"]], ["Enter"]])  # no Enter into it
        self.assertIn("dialog: a prompt came up after the nudge was typed; Enter not retried", r.stdout)


class NoNudgeIntoDialog(SendBase):
    """#315: a window showing a prompt (#289's captured screens) gets no key at all, since a permission or approval
    prompt preselects yes; the message stays in the inbox and the window is reported ambiguous."""

    def setUp(self):
        super().setUp()
        bindir = os.path.join(self.tmp, "bin")
        os.rename(os.path.join(bindir, "tmux"), os.path.join(bindir, "tmux-base"))
        with open(os.path.join(bindir, "tmux"), "w") as f:
            f.write(FAKE_TMUX_PANES)
        os.chmod(os.path.join(bindir, "tmux"), 0o755)
        self.panes = os.path.join(self.tmp, "panes.json")
        self.env["FAKE_PANES"] = self.panes

    def show(self, name):
        with open(self.panes, "w") as f:
            json.dump({"crew-acme-widgets:10": {"screen": screen(name)}}, f)

    def test_prompt_on_screen_types_nothing_and_reports_dialog(self):
        for name in STUCK:
            with self.subTest(name):
                self.show(name)
                r = self.send("ben-7", "fix", "#12")
                self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
                msg_id = self.inbox()[-1]["id"]
                self.assertIn("nudge not submitted: %s to ben-7: dialog: a prompt is on its screen; nothing typed; "
                              "the message is in the inbox; treat ben-7 as ambiguous" % msg_id, r.stdout)
        self.assertEqual(len(self.inbox()), len(STUCK))  # every message queued
        self.assertEqual([c for c in self.calls() if c[0] == "send-keys"], [])  # no text, no C-u, no Enter

    def test_working_screen_still_nudged(self):
        for name in WORKING:
            with self.subTest(name):
                self.show(name)
                r = self.send("ben-7", "fix", "#12")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn(["send-keys", "-t", "=crew-acme-widgets:10", "-l", "inbox: " + self.inbox()[-1]["id"]],
                              self.calls())


class BusyDelivery(DeliveryBase):  # #1850 D2.2, D2.3
    REFS = ("fix", "#12", "a" * 40)

    def test_busy_worker_keeps_one_pending_id_past_two_waits_until_its_late_ack(self):
        self.show(self.BUSY)
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        msg_id = self.inbox()[0]["id"]
        typed = self.typed()
        self.assertEqual(sum(1 for c in typed if c[-1] == "inbox: " + msg_id), 1)
        for wait in ("0.2", "0.2"):  # two waits and a retry by the old recipe, each a fresh process
            r = self.send(*self.REFS, "--wait-ack", wait)
            self.assertEqual(r.returncode, 3, r.stdout + r.stderr)
            self.assertIn("pending %s to ben-7: worker busy; same id kept; not sent again, nothing typed" % msg_id, r.stdout)
        r = self.send(*self.REFS)  # a duplicate caller
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["id"] for m in self.inbox()], [msg_id])
        self.assertEqual(self.typed(), typed)  # no retyped nudge, no Enter
        r, d = self.delivery(msg_id)
        self.assertEqual([d["delivery"], d["worker"], d["disposition"], d["action"], d["nudges"], d["restarts"]],
                         ["submitted", "busy", "pending", "wait", 1, 0])
        self.show(self.IDLE)  # busy -> idle, then the late ack
        self.put("status/ben-7.status", "ack: %s\n" % msg_id)
        r, d = self.delivery(msg_id)
        self.assertEqual([r.returncode, d["disposition"], d["nudges"]], [0, "dispatched", 1])
        self.assertFalse(os.path.exists(os.path.join(self.state, "inbox", "ben-7.undelivered")))

    def test_idle_unacked_gets_one_renudge_of_the_same_id_then_a_named_block(self):
        self.assertEqual(self.send(*self.REFS).returncode, 0)
        msg_id = self.inbox()[0]["id"]
        self.assertEqual(self.delivery(msg_id)[1]["action"], "nudge")
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sent %s to ben-7 (pending id kept)" % msg_id, r.stdout)
        self.assertEqual(sum(1 for c in self.typed() if c[-1] == "inbox: " + msg_id), 2)
        typed = self.typed()
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 4, r.stdout + r.stderr)
        self.assertIn("nudge not submitted: %s to ben-7: idle-unacked after one re-nudge (escalate)" % msg_id, r.stdout)
        self.assertEqual(self.typed(), typed)
        self.assertEqual([m["id"] for m in self.inbox()], [msg_id])
        d = self.delivery(msg_id)[1]
        self.assertEqual([d["disposition"], d["action"], d["nudges"]], ["blocked", "escalate", 2])
        r = self.send("fix", "#12", "b" * 40)  # a new head supersedes the old message: a new id, nudged
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.delivery(msg_id)[1]["disposition"], "superseded")

    def test_worker_states_choose_restart_escalation_or_wait_with_no_unsafe_key(self):
        self.show(self.BUSY)
        self.assertEqual(self.send(*self.REFS).returncode, 0)
        msg_id = self.inbox()[0]["id"]
        rec = os.path.join(self.state, "runs", "ben-7.json")
        with open(rec) as f:
            original = json.load(f)
        quota = "• Working\n■ You've hit your usage limit. Upgrade to Pro or try again in 2 days.\n"
        for name, pane, restarts, held, expect in [
                ("busy -> dead", dict(dead="1"), 0, False, ("dead", "pending", "restart")),
                ("replacement process, same window", dict(id="%99", pid="9000099"), 0, False, ("missing", "pending", "restart")),
                ("dead after its one restart", dict(dead="1"), 1, False, ("dead", "blocked", "escalate")),
                ("dead but held", dict(dead="1"), 0, True, ("dead", "pending", "wait")),
                ("dialog", dict(screen=screen("claude-proceed")), 0, False, ("ambiguous", "blocked", "escalate")),
                ("unknown screen", dict(screen="loading...\n"), 0, False, ("ambiguous", "blocked", "escalate")),
                ("quota", dict(screen=quota), 0, False, ("quota", "pending", "restart"))]:
            with self.subTest(name):
                self.show(self.BUSY, **pane)
                with open(rec, "w") as f:
                    json.dump(dict(original, restarts=restarts), f)
                self.put("poll-state.json", json.dumps({"held": ["#12"] if held else []}))
                typed = self.typed()
                d = self.delivery(msg_id)[1]
                self.assertEqual((d["worker"], d["disposition"], d["action"]), expect)
                self.assertEqual([d["id"], d["restarts"]], [msg_id, restarts])
                r = self.send(*self.REFS)
                self.assertEqual(r.returncode, 0 if expect[2] == "wait" else 4, r.stdout + r.stderr)
                self.assertEqual(self.typed(), typed)  # no key into a dead, replaced, dialog or unknown screen
                self.assertEqual([m["id"] for m in self.inbox()], [msg_id])  # no discarded or duplicated work

    def test_interruption_at_each_durable_boundary_keeps_one_watchable_id(self):  # D2.4
        ledger = os.path.join(self.state, "runs", "ben-7.delivery.jsonl")
        self.show(self.BUSY)
        self.assertEqual(self.send(*self.REFS).returncode, 0)
        msg_id = self.inbox()[0]["id"]
        with open(ledger) as f:
            events = [json.loads(line) for line in f]
        self.assertEqual([e["event"] for e in events], ["recorded", "submitted"])  # the ledger precedes the inbox line
        # 1. after the ledger record, before the inbox line: no message to read; the retry sends one new id
        self.put("runs/ben-7.delivery.jsonl", json.dumps(dict(events[0], id="20331118T031000Z-0rphan")) + "\n" +
                 "".join(json.dumps(e) + "\n" for e in events))
        self.assertEqual(self.delivery("20331118T031000Z-0rphan")[0].returncode, 2)
        # 2. an inbox line with no ledger record (written before the record existed): a retry records it, same id
        self.put("runs/ben-7.delivery.jsonl", "")
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("pending %s to ben-7: worker busy" % msg_id, r.stdout)
        self.assertEqual([m["id"] for m in self.inbox()], [msg_id])
        d = self.delivery(msg_id)[1]
        self.assertEqual([d["ledger"], d["delivery"], d["worker"], d["action"]], [True, "recorded", "busy", "wait"])
        with mock.patch.dict(os.environ, self.env):
            send, watch = self.mod.commands()["send"], self.mod.commands()["watch"]
            values, session, state = self.mod.profile(argparse.Namespace(project=self.project, org_profile=None))
            mine, seen = send.ours(self.project, None, values), {}
            windows = dict((n, i) for i, n in self.mod.tmux.list_windows(session))
            self.assertEqual(watch.deliveries(state, session, windows, seen, mine), [])  # tracked from here
            self.show(self.IDLE)
            wakes = watch.deliveries(state, session, windows, seen, mine)
        self.assertEqual([(w["id"], w["action"]) for w in wakes], [(msg_id, "nudge")])
        # 3. recorded, nudge not yet logged: the retry nudges the same id
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("sent %s to ben-7 (pending id kept)" % msg_id, r.stdout)
        self.assertEqual([m["id"] for m in self.inbox()], [msg_id])
        self.assertEqual(self.delivery(msg_id)[1]["delivery"], "submitted")

    def test_interrupted_send_resumes_its_recorded_id(self):
        self.assertEqual(self.send(*self.REFS).returncode, 0)
        msg_id = self.inbox()[0]["id"]
        ledger = os.path.join(self.state, "runs", "ben-7.delivery.jsonl")
        with open(ledger) as f:
            recorded = f.readline()
        self.put("runs/ben-7.delivery.jsonl", recorded + '{"id": "%s", "event": "subm' % msg_id)  # killed before nudge
        d = self.delivery(msg_id)[1]
        self.assertEqual([d["delivery"], d["nudges"], d["action"]], ["recorded", 0, "nudge"])
        r = self.send(*self.REFS)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([m["id"] for m in self.inbox()], [msg_id])
        self.assertEqual(self.delivery(msg_id)[1]["delivery"], "submitted")


if __name__ == "__main__":
    unittest.main()
