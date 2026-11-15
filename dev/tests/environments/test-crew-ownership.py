"""Ownership tests: claim race, trusted markers, handoff states and CLI read-only guards.

Uses fake gh and tmux only; verifies blocked actions have no tmux side effects,
poll queues one ownership wake and the Stop guard permits ending a foreign turn.
#937: the read-item output contract (native and GitHub shapes) and a native string control item read through its
recorded binding, never `gh`.
"""
import importlib.util
import json
import os
from pathlib import Path
import unittest
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import Base, SCRIPTS, render_template, write_pack

spec = importlib.util.spec_from_file_location("ownership", os.path.join(os.path.dirname(SCRIPTS), "environments", "terminal", "crew.d", "_ownership.py"))
own = importlib.util.module_from_spec(spec)
spec.loader.exec_module(own)


def marker(state, from_="none", to="tmux@local", id_="20261101-abcdef", login="acme-bot"):
    return {"user": {"login": login}, "body": "<!-- crew:v1 role=coordinator pass=handoff handoff=%s state=%s "
            "from=%s to=%s cmd-id=chat sha=%s round=n/a verdict=n/a -->" % (id_, state, from_, to, "1" * 40)}


class Record(unittest.TestCase):
    def record(self, *comments):
        return own.owner_record(own.posts(json.dumps([list(comments)])), {"acme-bot", "acme-owner"})

    def test_first_claim_wins(self):
        self.assertEqual(self.record(marker("claimed"), marker("claimed", to="grok-bot@box"))[:2],
                         ("tmux@local", None))

    def test_ignored_untrusted_and_malformed_markers(self):
        bad = marker("claimed")
        bad["body"] = bad["body"].replace("1" * 40, "short")
        self.assertEqual(self.record(marker("claimed", login="outsider"), bad), (None, None, None))
        self.assertEqual(self.record(marker("claimed", login="acme-owner"))[0], "tmux@local")

    def test_one_open_handoff_and_matching_ack(self):
        claim = marker("claimed")
        drain = marker("draining", "tmux@local", "grok-bot@box")
        for ignored in [marker("draining", "grok-bot@box"),
                        marker("takeover", "tmux@local", "tmux@second", id_="20261101-aaaaaa"),
                        marker("acked", "tmux@local", "grok-bot@box", id_="20261101-aaaaaa")]:
            self.assertEqual(self.record(claim, drain, ignored)[1], "draining")
        ack = marker("acked", "tmux@local", "grok-bot@box")
        self.assertEqual(self.record(claim, drain, ack, ack, marker("stopped", "tmux@local", "grok-bot@box"))[:2],
                         ("grok-bot@box", None))

    def test_offer_takeover_abort_and_return(self):
        seq = [marker("claimed"), marker("draining", "tmux@local", "grok-bot@box"),
               marker("offered", "tmux@local", "grok-bot@box")]
        self.assertEqual(self.record(*seq)[1], "offered")
        seq.append(marker("takeover", "tmux@local", "grok-bot@box"))
        self.assertEqual(self.record(*seq)[1], "takeover")
        self.assertEqual(self.record(*seq, marker("aborted", "tmux@local", "grok-bot@box"))[:2],
                         ("tmux@local", None))
        seq += [marker("acked", "tmux@local", "grok-bot@box"),
                marker("draining", "grok-bot@box", "tmux@local", id_="20261101-aaaaaa"),
                marker("acked", "grok-bot@box", "tmux@local", id_="20261101-aaaaaa")]
        self.assertEqual(self.record(*seq)[:2], ("tmux@local", None))


def native(state, from_="none", to="tmux@local", author="acme-bot", created="2026-11-04T17:05:00Z"):
    c = marker(state, from_, to)
    return {"author": author, "body": c["body"], "created": created, "id": "10001"}


class ReadItemContract(unittest.TestCase):
    """docs/handoff.md read-item output contract: native posts, normalized GitHub comments, refused outputs."""

    def test_native_and_github_shapes_normalize_alike(self):
        github = dict(marker("claimed"), created_at="2026-11-04T17:05:00Z", id=10001)
        for out in ([native("claimed")], [[github]], [github]):
            self.assertEqual(own.posts(json.dumps(out)), [
                {"author": "acme-bot", "body": github["body"], "created": "2026-11-04T17:05:00Z", "id": "10001"}])
        self.assertEqual(own.posts(json.dumps([marker("claimed")]))[0]["created"], None)  # today's GitHub reads
        self.assertEqual(own.posts("[]"), [])

    def test_untrusted_native_posts_are_dropped(self):
        posts = own.posts(json.dumps([native("claimed", to="grok-bot@box", author="outsider"), native("claimed")]))
        self.assertEqual(own.owner_record(posts, {"acme-bot"})[0], "tmux@local")

    def test_mixed_or_incomplete_output_is_unreadable(self):
        bad = [[native("claimed"), marker("claimed")], [{"body": "x", "created": "2026-11-04T17:05:00Z"}],
               [dict(native("claimed"), created="yesterday")], [{k: v for k, v in native("claimed").items()
                                                                   if k != "created"}],
               [dict(native("claimed"), author=None)], {"posts": []}, ["text"]]
        for out in bad:
            with self.assertRaises((ValueError, KeyError, TypeError), msg=out):
                own.posts(json.dumps(out))
        with self.assertRaises(ValueError):
            own.posts("not json")


class NativeControlItem(Base):
    """#937: a string control item reads through the recorded `markers.read-item` binding; `gh` is never called."""

    def setUp(self):
        super().setUp()
        github = (Path(SCRIPTS).parent / "templates" / "backends" / "github.toml").read_text()
        write_pack(os.path.join(self.project_dir, "pack"), mapping=github.replace("\n[ids]\n", '\n[ids]\nitem = "[A-Z][A-Z0-9]+-[0-9]+"\n'))
        p = Path(self.project)
        p.write_text(p.read_text().replace('[repo]\n', '[repo]\ncontrol_item = "OPS-1042"\n').replace(
            '[runtime]\n', '[runtime]\ninstance = "local"\n') + 'pack = "pack"\n')
        bindir = Path(self.tmp) / "bin"
        (bindir / "gh").write_text('#!/bin/sh\necho "$*" >> "%s/gh.log"\nexit 1\n' % self.tmp)
        (bindir / "ex").write_text('#!/bin/sh\necho "$*" >> "%s/ex.log"\n[ -n "$EX_FAIL" ] && exit 1\n'
                                   'cat "%s/posts.json"\n' % (self.tmp, self.tmp))
        for name in ("gh", "ex"):
            (bindir / name).chmod(0o755)
        self.posts([native("claimed")])

    def posts(self, posts):
        Path(self.tmp, "posts.json").write_text(json.dumps(posts))

    def bind(self, read_item="ex item comments <control-item> --json"):
        os.makedirs(os.path.join(self.state, "render"), exist_ok=True)
        Path(self.state, "render", "bindings.json").write_text(json.dumps({"markers.read-item": read_item}))

    def cli_log(self, name):
        path = Path(self.tmp, name + ".log")
        return path.read_text().splitlines() if path.exists() else []

    def own(self, **env):
        return self.crew("ownership", "--project", self.project, **env)

    def test_string_id_reads_native_posts(self):
        self.bind()
        self.assertEqual(self.own().returncode, 0)
        self.assertEqual(self.cli_log("ex"), ["item comments OPS-1042 --json"])
        self.posts([native("claimed", to="grok-bot@box"), native("claimed")])
        self.assertEqual(self.own().returncode, 1)
        self.posts([native("claimed", to="grok-bot@box", author="outsider"), native("claimed")])
        self.assertEqual(self.own().returncode, 0)
        self.assertEqual(self.cli_log("gh"), [])

    def test_failed_unbound_or_n_only_read_is_read_only(self):
        for read_item, env in (("ex item comments <control-item> --json", {"EX_FAIL": "1"}), (None, {}),
                               ("ex item comments <n> --json", {})):
            with self.subTest(read_item=read_item):
                if read_item:
                    self.bind(read_item)
                else:
                    os.remove(os.path.join(self.state, "render", "bindings.json"))
                r = self.own(**env)
                self.assertEqual(r.returncode, 1, r.stdout)
                self.assertIn("read-only", r.stdout)
        self.assertNotIn("item comments <n> --json", self.cli_log("ex"))
        self.assertEqual(self.cli_log("gh"), [])


class Commands(Base):
    def setUp(self):
        super().setUp()
        p = Path(self.project)
        p.write_text(p.read_text().replace('[repo]\n', '[repo]\ncontrol_item = 99\n').replace(
            '[runtime]\n', '[runtime]\ninstance = "local"\n'))
        self.comments = Path(self.tmp) / "comments.json"
        self.comments.write_text(json.dumps([[marker("claimed", to="grok-bot@box")]]))
        gh = Path(self.tmp) / "bin" / "gh"
        gh.write_text('#!/usr/bin/env python3\nimport os, sys\n'
                      'if os.environ.get("GH_FAIL"): sys.exit(1)\n'
                      'print(open(os.environ["COMMENTS"]).read())\n')
        gh.chmod(0o755)
        self.env["COMMENTS"] = str(self.comments)
        for d in ["wake", "runs"]:
            os.makedirs(os.path.join(self.state, d))

    def test_legacy_no_marker_and_owning_allow(self):
        for comments in [[], [marker("claimed")]]:
            self.comments.write_text(json.dumps([comments]))
            self.assertEqual(self.crew("ownership", "--project", self.project).returncode, 0)

    def test_foreign_and_unreadable_refuse_without_effects(self):
        for env in [{}, {"GH_FAIL": "1"}]:
            for cmd in [("spawn", "builder", "--issue", "7"), ("restart", "ben-7"),
                        ("send", "ben-7", "fix", "#7"), ("land-lock", "acquire"),
                        ("train", "build", "7"), ("train", "land", "1", "7"),
                        ("kill", "ben-7", "--discard", "--reason", "superseded")]:
                r = self.crew(*cmd, "--project", self.project, **env)
                self.assertEqual(r.returncode, 1, r.stderr)
                self.assertIn("read-only; refusing", r.stdout)
            self.assertEqual(self.calls(), [])
            self.assertFalse(os.path.exists(os.path.join(self.state, "locks")))
        self.comments.write_text("not json")
        self.assertEqual(self.crew("ownership", "--project", self.project).returncode, 1)

    def test_draining_only_allows_in_flight_writes(self):
        self.comments.write_text(json.dumps([[marker("claimed"), marker("draining", "tmux@local", "grok-bot@box")]]))
        for action, code in [("start", 1), ("write", 0), ("land", 1)]:
            self.assertEqual(self.crew("ownership", "--project", self.project, "--action", action).returncode, code)
        self.comments.write_text(json.dumps([[marker("claimed"), marker("takeover", "tmux@local", "grok-bot@box")]]))
        self.assertEqual(self.crew("ownership", "--project", self.project, "--action", "write").returncode, 1)

    def test_poll_reports_once_and_guard_allows_stop(self):
        for _ in range(2):
            r = self.crew("poll", "--once", "--project", self.project)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("poll emits no work", r.stdout)
        lines = Path(self.state, "wake", "queue.jsonl").read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["event"], "ownership")
        Path(self.state, "runs", "ben-7.json").write_text('{}')
        r = self.crew("guard", "--state", self.state, CREW_ROLE="coordinator", CREW_PROJECT=self.project)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_control_item_requires_valid_instance_and_positive_issue(self):
        original = Path(self.project).read_text()
        for text in [original.replace('instance = "local"', ''),
                     original.replace('instance = "local"', 'instance = "bad@label"'),
                     original.replace('control_item = 99', 'control_item = 0')]:
            Path(self.project).write_text(text)
            r = self.crew("ownership", "--project", self.project)
            self.assertEqual(r.returncode, 1)
            self.assertTrue("runtime.instance" in r.stdout or "repo.control_item" in r.stdout)

    def test_rendered_grok_guard_has_resolved_issue_and_instance(self):
        p = Path(self.project)
        p.write_text(p.read_text().replace('name = "tmux"', 'name = "grok-bot"'))
        text, problems = render_template(self.project, "runtime/builder-b1.md")
        self.assertEqual(problems, [])
        self.assertIn("<include:policy/shared/flavor.md>",
                      (Path(SCRIPTS).parent / "templates" / "runtimes" / "grok-bot" / "builder-b1.md").read_text())
        self.assertNotIn("<include:", text)
        self.assertIn("control item=99, runtime=grok-bot@local", text)

    def test_grok_routines_and_tmux_briefs_carry_guard(self):
        root = Path(SCRIPTS).parent / "templates" / "runtimes"
        for name in ["builder-b1", "builder-b2", "reviewer-validator", "reviewer-v2-watch", "synthesizer",
                     "coordinator-after-merge", "coordinator-steering-dispatcher", "coordinator-stuck-pr-sweeper"]:
            text = (root / "grok-bot" / (name + ".md")).read_text()
            self.assertIn("Ownership first:", text)
            self.assertIn("no new pass or land", text)
        for name in ["builder", "reviewer", "coordinator", "synthesizer"]:
            text = (root / "tmux" / (name + ".md")).read_text()
            self.assertIn('$CREW_BIN ownership --project "$CREW_PROJECT"', text)
            self.assertIn("--action write", text)
            self.assertIn("--action land", text)

    def test_session_runtime_checks_session_id(self):
        self.comments.write_text(json.dumps([[marker("claimed", to="session@local")]]))
        self.assertEqual(self.crew("ownership", "--project", self.project).returncode, 1)
        for action in ["start", "write", "land"]:
            r = self.crew("ownership", "--project", self.project, "--runtime", "session", "--action", action)
            self.assertEqual(r.returncode, 0, r.stdout)
        self.comments.write_text(json.dumps([[marker("claimed", to="session@local"),
                                              marker("draining", "session@local", "tmux@local"),
                                              marker("offered", "session@local", "tmux@local")]]))
        r = self.crew("ownership", "--project", self.project, "--runtime", "session", "--action", "write")
        self.assertEqual(r.returncode, 1)
        self.assertIn("read-only; refusing write", r.stdout)

    def test_session_brief_carries_guard_and_handoff_steps(self):
        text = (Path(SCRIPTS).parent / "templates" / "runtimes" / "session" / "coordinator.md").read_text()
        self.assertIn('ownership --project "$CREW_PROJECT" --runtime session', text)
        for needle in ["--action write", "--action land", "## Outgoing", "## Incoming"]:
            self.assertIn(needle, text)
        for state in ["claimed", "draining", "offered", "takeover", "acked", "stopped", "aborted"]:
            self.assertIn("`%s`" % state, text)

    def test_grok_binding_uses_same_guard(self):
        p = Path(self.project)
        p.write_text(p.read_text().replace('name = "tmux"', 'name = "grok-bot"'))
        self.assertEqual(self.crew("ownership", "--project", self.project).returncode, 1)
        self.comments.write_text(json.dumps([[marker("claimed", to="grok-bot@local")]]))
        self.assertEqual(self.crew("ownership", "--project", self.project).returncode, 0)


if __name__ == "__main__":
    unittest.main()
