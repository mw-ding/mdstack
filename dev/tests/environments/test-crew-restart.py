"""Tests for mdstack restart, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: only when dead, missing or quota and only once (quota: on the next eligible engine past every exhausted
one, in place or fresh; none left refuses, #631) (fresh worktree when clean, relaunch in place
keeping unlanded work), a finished run refused, a builder after `done:` restarts as its PR's fix
pass (fresh or in place), an in-place relaunch accepts a Claude Code pane whose command reads as
its version (#286), a dead train worker respawns with --train and keeps the pending train record (#1391), a dead
reflection run rechecks its posted report and refuses, else respawns with the same request (#1520), and the coordinator's window relaunches in place with the current
sandbox_env and --resume, refused while the land lock is held or from window 0 itself (#1544); a dead worker's
unacked inbox messages keep their ids through the one restart, fresh or in place, re-recorded for the successor, which
gets one nudge of the same id, and a second restart is refused with the id still pending (#1850, D2.3). Run in CI.
"""
import fcntl
import json
import os
import unittest
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import DeliveryBase, HEAD, LivenessBase


class Restart(LivenessBase):
    def coordinator(self, *args, project=None):
        with open(self.state_file) as f:
            state = json.load(f)
        state.setdefault("_panes", {})["crew-acme-widgets:0"] = "claude"
        with open(self.state_file, "w") as f:
            json.dump(state, f)
        r = self.crew("restart", "ash", "--project", project or self.project, "--timeout", "1", *args)
        return r, [c for c in self.calls() if c[0] == "respawn-window"]

    def test_restart_relaunches_the_coordinator_in_place(self):  # #1544
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('name = "tmux"', 'name = "tmux"\noptions = { sandbox_env = "CREW_TEST_SANDBOX=profile" }'))
        self.env.pop("CREW_SANDBOX_ENV", None)
        r, calls = self.coordinator("--resume", "d3af8514-565a")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: relaunched ash in place (window 0, resume d3af8514-565a)", r.stdout)
        [call] = calls
        self.assertEqual(call[:5], ["respawn-window", "-k", "-t", "=crew-acme-widgets:0", "-c"])
        self.assertEqual(call[5], self.project_dir)
        env = dict(call[i + 1].split("=", 1) for i, a in enumerate(call) if a == "-e")
        self.assertEqual({k: env[k] for k in ("CREW_TEST_SANDBOX", "CREW_SANDBOX_ENV", "CREW_ROLE", "CREW_PROJECT")},
                         {"CREW_TEST_SANDBOX": "profile", "CREW_SANDBOX_ENV": "CREW_TEST_SANDBOX=profile",
                          "CREW_ROLE": "coordinator", "CREW_PROJECT": self.project})
        self.assertNotIn("TMUX", env)  # window 0 keeps the crew's $TMUX
        self.assertIn(" --resume d3af8514-565a \"Read your brief at $CREW_BRIEF and follow it.\"", call[-1])
        self.assertTrue(call[-1].startswith('export GH_TOKEN="$(gh auth token --user "$CREW_IDENTITY")"; exec claude '))

    def test_coordinator_relaunch_refusals(self):  # #1544
        self.set_pane(0, pid=str(os.getpid()))  # the caller's parent: it runs beneath window 0's pane
        r, calls = self.coordinator("--resume", "x")
        self.assertEqual((r.returncode, calls), (1, []))
        self.assertIn("refusing coordinator relaunch: run it from the owner's terminal, not window 0", r.stdout)
        self.set_pane(0)
        team = os.path.join(self.project_dir, "ext.toml")
        with open(team, "w") as f:
            f.write('[team]\npersonas = { builder = "Ben" }\naccounts = { all = "acme-bot", reviewer = "acme-reviewer" }\n'
                    '[team.runtime]\nname = "tmux"\n[team.identities]\nowners = ["acme-owner"]\n'
                    '[team.paths]\nstate_dir = "%s"\nworktree_root = "%s/wt"\ntoolchain_bin = "/opt/node/bin"\n'
                    '[repos.widgets]\nrepo = "acme/widgets"\n' % ((os.path.join(self.tmp, "state"),) * 2))
        r, calls = self.coordinator("--resume", "x", project=team + "#widgets")
        self.assertEqual((r.returncode, calls), (1, []))
        self.assertIn("refusing coordinator relaunch: a team coordinator is not relaunched here", r.stdout)
        r, calls = self.coordinator("--resume", "bad id")
        self.assertEqual((r.returncode, calls), (1, []))
        self.assertIn("--resume expects fresh, ask or a session id", r.stdout)
        with open(os.path.join(self.state, "locks", "merge.lock"), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            r, calls = self.coordinator("--resume", "x")
        self.assertEqual((r.returncode, calls), (1, []))
        self.assertIn("refusing coordinator relaunch: the land lock is held", r.stdout)

    def test_restart_passes_profile_sandbox_env_fresh_and_in_place(self):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace('name = "tmux"', 'name = "tmux"\noptions = { sandbox_env = "CREW_TEST_SANDBOX=profile" }'))
        self.env.pop("CREW_SANDBOX_ENV", None)
        self.assertEqual(self.spawn("builder", "--issue", "8").returncode, 0)
        with open(os.path.join(self.record("ben-8")["worktree"], "notes.txt"), "w") as f:
            f.write("keep\n")
        for name, index in (("ben-7", 10), ("ben-8", 11)):
            self.set_pane(index, dead="1")
            result = self.crew("restart", name, "--project", self.project, "--timeout", "1")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            call = self.windows()[-1]
            env = dict(call[i + 1].split("=", 1) for i, a in enumerate(call) if a == "-e")
            self.assertEqual(env["CREW_TEST_SANDBOX"], "profile")
            self.assertEqual(env["CREW_SANDBOX_ENV"], "CREW_TEST_SANDBOX=profile")

    def test_restart_only_dead_or_missing_and_once(self):
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("ben-7 is alive", r.stdout)
        self.set_pane(10, dead="1")
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(len(self.windows()), 2)
        self.assertEqual(self.record("ben-7")["restarts"], 1)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already restarted once; escalate", r.stdout)
        self.assertEqual(len(self.windows()), 2)

    def test_restart_refuses_finished_run(self):
        self.set_pane(10, dead="1")
        wt = self.record("ben-7")["worktree"]
        with open(os.path.join(wt, "notes.txt"), "w") as f:  # unlanded work does not change the refusal
            f.write("draft\n")
        self.put("status/ben-7.status", "failed: tests red\n")
        r = self.crew("restart", "ben-7", "--project", self.project)
        self.assertEqual(r.returncode, 1)
        self.assertIn("finished", r.stdout)
        self.assertEqual(len(self.windows()), 1)
        self.assertTrue(os.path.exists(os.path.join(wt, "notes.txt")))
        self.pr(9, "codex gpt-6.1-sol medium")  # done: is terminal for a reviewer run
        self.assertEqual(self.spawn("reviewer", "--pr", "9").returncode, 0)
        self.set_pane(20, dead="1")
        self.put("status/vera-9-r1-review.status", "done: #9 %s review pass\n" % HEAD)
        r = self.crew("restart", "vera-9-r1-review", "--project", self.project)
        self.assertEqual((r.returncode, "finished" in r.stdout), (1, True), r.stdout)

    def test_restart_builder_dead_after_done(self):  # #139 F4: a builder stays for fix rounds after done:
        sha = self.pr(12, "claude-code opus-5.5 default")
        self.set_pane(10, dead="1")
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % sha)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rec = self.record("ben-7")  # #234 N2: the PR's fix pass, never a second build pass
        self.assertEqual((rec["restarts"], rec["pass"], rec["item"]), (1, "fix", "issue #7, PR #12"))
        self.assertEqual(rec["args"], {"issue": 7, "pr": 12, "pass": "fix", "round": 1, "tier": "default"})
        self.assertEqual(os.path.basename(rec["worktree"]), "12-%s-builder-fix" % sha[:7])
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=rec["worktree"]), sha)
        with open(os.path.join(self.state, "runs", "ben-7.brief.md")) as f:
            self.assertIn("- Pass: fix\n", f.read())

    def test_restart_builder_after_done_with_unlanded_work_relaunches_as_fix(self):  # #234 N2
        wt = self.record("ben-7")["worktree"]
        with open(os.path.join(wt, "notes.txt"), "w") as f:
            f.write("draft\n")
        self.set_pane(10, dead="1")
        self.put("status/ben-7.status", "done: #7 #12 %s\n" % HEAD)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("keeping unlanded work", r.stdout)
        rec = self.record("ben-7")
        self.assertEqual((rec["pass"], rec["item"], rec["args"]["pr"], rec["worktree"]), ("fix", "issue #7, PR #12", 12, wt))
        with open(os.path.join(self.state, "runs", "ben-7.brief.md")) as f:
            self.assertIn("- Restarted after done: as Pass fix, Item issue #7, PR #12\n", f.read())

    def test_restart_dead_run_with_unlanded_work_relaunches_in_its_worktree(self):
        before = self.record("ben-7")
        wt = before["worktree"]
        self.git("commit", "-q", "--allow-empty", "-m", "local only", cwd=wt)
        with open(os.path.join(wt, "notes.txt"), "w") as f:
            f.write("draft\n")
        self.set_pane(10, dead="1")
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("keeping unlanded work", r.stdout)
        self.assertIn("uncommitted: ?? notes.txt", r.stdout)
        self.assertIn("commit: ", r.stdout)
        self.assertIn(["kill-window", "-t", "=crew-acme-widgets:10"], self.calls())
        call = self.windows()[-1]
        self.assertEqual((len(self.windows()), call[3], call[call.index("-c") + 1]), (2, "=crew-acme-widgets:10", wt))
        self.assertIn("--dangerously-bypass-approvals-and-sandbox --add-dir %s " % self.state, call[-1])  # #293
        env = dict(call[i + 1].split("=", 1) for i, a in enumerate(call) if a == "-e")
        self.assertEqual(env["CREW_BRIEF"], os.path.join(self.state, "runs", "ben-7.brief.md"))
        self.assertNotIn("GH_TOKEN", env)
        after = self.record("ben-7")
        self.assertEqual((after["worktree"], after["claim"], after["restarts"]), (wt, before["claim"], 1))
        self.assertTrue(os.path.exists(os.path.join(wt, "notes.txt")))
        self.assertTrue(os.path.exists(before["claim"]))
        self.assertEqual(self.git("log", "-1", "--format=%s", cwd=wt), "local only")
        self.assertTrue(os.path.isdir(os.path.join(wt, ".git")))  # the builder's own copy, kept (#1252)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("already restarted once; escalate", r.stdout)
        self.assertTrue(os.path.exists(os.path.join(wt, "notes.txt")))

    def relaunch_with(self, options):
        wt = self.record("ben-7")["worktree"]
        self.git("commit", "-q", "--allow-empty", "-m", "local only", cwd=wt)
        with open(self.project, "a") as f:
            f.write("[runtime.options]\n" + options)
        self.set_pane(10, dead="1")
        return wt, self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")

    def test_restart_in_place_decides_confinement_again(self):  # #1252
        self.sandboxing_codex()
        wt, r = self.relaunch_with('permission_mode = "safe"\nconfinement = "enforce"\n')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        call = self.windows()[-1]
        self.assertIn("-c sandbox_workspace_write.exclude_slash_tmp=true", call[-1])
        env = dict(call[i + 1].split("=", 1) for i, a in enumerate(call) if a == "-e")
        self.assertEqual(env["TMPDIR"], os.path.join(wt, ".crew", "tmp"))
        rec = self.record("ben-7")
        self.assertIs(rec["confined"], True)
        self.assertNotIn("unconfined", rec)

    def test_restart_in_place_under_enforce_refuses_unconfined_and_keeps_all(self):  # #1252
        wt, r = self.relaunch_with('confinement = "enforce"\n')  # bypass
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("crew: refusing launch: confinement=enforce: Codex with permission_mode=bypass", r.stdout)
        self.assertIn("worktree, claim and run record kept", r.stdout)
        self.assertEqual(len(self.windows()), 1)
        self.assertEqual(self.git("log", "-1", "--format=%s", cwd=wt), "local only")
        self.assertTrue(os.path.exists(self.record("ben-7")["claim"]))

    def test_restart_dead_run_with_clean_worktree_respawns_fresh(self):
        wt = self.record("ben-7")["worktree"]
        with open(os.path.join(self.project_dir, ".git", "info", "exclude"), "a") as f:
            f.write("build-out/\n")  # ignored build output: the worktree still counts as clean
        os.makedirs(os.path.join(wt, "build-out"))
        self.set_pane(10, dead="1")
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: started ben-7", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(wt, "build-out")))  # removed by mdstack kill, then re-created
        self.assertNotIn("keeping unlanded work", r.stdout)
        rec = self.record("ben-7")
        self.assertEqual((rec["restarts"], rec["worktree"]), (1, wt))  # same base SHA, so the same fresh path
        self.assertEqual(self.git("status", "--porcelain", cwd=wt), "")
        self.assertEqual(len(self.windows()), 2)

    def test_restart_keeps_the_recorded_item_tier(self):  # #1830: clean respawn and preserved-work relaunch
        record = "<!-- crew:v1 role=coordinator pass=flavor issue=%d flavor=standard default=standard tier=%s -->\n— 🔥 Ash (CTO) · x"
        for issue, index, unlanded in ((8, 11, False), (9, 12, True)):
            with self.subTest(unlanded=unlanded):
                key, name = "FAKE_COMMENTS_%d" % issue, "ben-%d" % issue
                self.env[key] = json.dumps([{"author": {"login": "acme-bot"}, "body": record % (issue, "deep")}])
                self.assertEqual(self.spawn("builder", "--issue", str(issue)).returncode, 0)
                if unlanded:
                    self.git("commit", "-q", "--allow-empty", "-m", "local only", cwd=self.record(name)["worktree"])
                self.env[key] = json.dumps([{"author": {"login": "acme-bot"}, "body": record % (issue, "trivial")}])
                self.set_pane(index, dead="1")
                r = self.crew("restart", name, "--project", self.project, "--timeout", "1")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("keeping unlanded work" if unlanded else "crew: started " + name, r.stdout)
                rec = self.record(name)
                self.assertEqual((rec["args"]["tier"], rec["effort"], rec["restarts"]), ("deep", "high", 1))
                self.assertIn("model_reasoning_effort=high", self.windows()[-1][-1])  # relaunched at deep effort

    QUOTA = "■ You've hit your usage limit. Upgrade to Pro or try again in 2 days."  # Codex's own banner (#631)

    def test_quota_run_restarts_once_on_the_next_engine(self):  # #631: a clean run too stays in place
        before = self.record("ben-7")
        msg = {"id": "20261111T073000Z-abcdef", "from": "ben-lead", "kind": "fix", "ts": "2026-11-11T07:30:00Z",
               "refs": ["#12", before["head"], "https://github.com/acme/widgets/pull/12#pullrequestreview-123"]}
        self.put("inbox/ben-7.jsonl", json.dumps(msg) + "\n")  # never acked: the quota stopped the session first
        self.git("commit", "-q", "--allow-empty", "-m", "main advanced")
        self.git("push", "-q", "origin", "HEAD:main")
        self.set_pane(10, screen=self.QUOTA)
        self.assertEqual(self.probe(), "quota")
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: restarted ben-7 (window 10) in its worktree", r.stdout)
        self.assertIn("exec claude --model sonnet --effort medium", self.windows()[-1][-1])
        rec = self.record("ben-7")
        self.assertEqual((rec["engine"], rec["model"], rec["harness"], rec["restarts"], rec["exhausted"]),
                         ("claude-code", "sonnet", "claude", 1, ["codex"]))
        self.assertEqual((rec["head"], rec["worktree"], rec["claim"], rec["args"]),  # same head despite main moving
                         (before["head"], before["worktree"], before["claim"], before["args"]))
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=rec["worktree"]), before["head"])
        with open(os.path.join(self.state, "inbox", "ben-7.jsonl")) as f:
            self.assertEqual(json.loads(f.read()), msg)  # the pending fix request survives
        with open(os.path.join(self.state, "runs", "ben-7.brief.md")) as f:
            self.assertIn("- Pending: inbox: 20261111T073000Z-abcdef\n", f.read())
        self.set_pane(10, screen="  ⎿  You've hit your limit · resets 3pm")
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)  # once: a second quota escalates
        self.assertIn("already restarted once; escalate", r.stdout)

    def test_quota_run_with_unlanded_work_relaunches_in_its_worktree_on_the_next_engine(self):  # #631
        before = self.record("ben-7")
        wt = before["worktree"]
        with open(os.path.join(wt, "notes.txt"), "w") as f:
            f.write("draft\n")
        self.set_pane(10, screen=self.QUOTA)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("keeping unlanded work", r.stdout)
        call = self.windows()[-1]
        self.assertEqual(call[call.index("-c") + 1], os.path.dirname(wt))
        self.assertIn("explicit cd", call[-1])
        self.assertIn("warning before restart: claude copy trust", r.stdout)
        self.assertIn("exec claude --model sonnet --effort medium", self.windows()[-1][-1])
        after = self.record("ben-7")
        self.assertEqual((after["worktree"], after["claim"], after["engine"], after["harness"], after["exhausted"]),
                         (wt, before["claim"], "claude-code", "claude", ["codex"]))
        self.assertTrue(os.path.exists(os.path.join(wt, "notes.txt")))
        with open(os.path.join(self.state, "runs", "ben-7.brief.md")) as f:
            self.assertIn("- Quota fallback: codex is out of quota; this session runs claude-code sonnet medium.", f.read())

    def test_quota_reviewer_with_a_moved_head_refuses_keeping_its_state(self):  # #631: never a stale review
        sha = self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("reviewer", "--pr", "9", "--head", sha).returncode, 0)
        self.put("inbox/vera-9-r1-review.jsonl", '{"id": "x1", "kind": "review", "refs": ["#9"]}\n')
        self.git("commit", "-q", "--allow-empty", "-m", "feat: y\n\nEngine: claude-code opus-5.5 default")
        self.git("push", "-q", "-f", "origin", "HEAD:refs/pull/9/head")  # the PR head moves
        self.git("reset", "-q", "--hard", "origin/main")
        self.set_pane(self.record("vera-9-r1-review")["index"], screen=self.QUOTA)
        r = self.crew("restart", "vera-9-r1-review", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("PR #9 head moved from %s" % sha[:7], r.stdout)
        rec = self.record("vera-9-r1-review")
        self.assertEqual((rec["engine"], rec["head"], "restarts" in rec), ("codex", sha, False))
        self.assertTrue(os.path.exists(os.path.join(self.state, "inbox", "vera-9-r1-review.jsonl")))
        self.assertTrue(os.path.isdir(rec["worktree"]))

    def test_quota_run_with_no_eligible_engine_left_refuses(self):  # #631: a durable block, the run kept
        with open(self.project, "a") as f:
            f.write('\n[engines.roles]\nbuilder = { order = ["codex/gpt-6.1-sol"] }\n')
        self.set_pane(10, screen=self.QUOTA)
        r = self.crew("restart", "ben-7", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("codex is out of quota: crew: no eligible", r.stdout)
        self.assertEqual((self.record("ben-7")["engine"], len(self.windows())), ("codex", 1))
        self.assertNotIn("restarts", self.record("ben-7"))

    def test_restart_clean_reviewer_keeps_its_rereview_id(self):  # #1477
        sha = self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("reviewer", "--pr", "9", "--head", sha, "--rereview-id", "42").returncode, 0)
        self.set_pane(self.record("vera-9-r1-review")["index"], dead="1")
        r = self.crew("restart", "vera-9-r1-review", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.record("vera-9-r1-review")
        self.assertEqual((after["restarts"], after["rereview_id"], after["head"]), (1, "42", sha))

    def test_restart_clean_reviewer_refuses_a_moved_head(self):  # #1477: a moved head never inherits the steer
        sha = self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("reviewer", "--pr", "9", "--head", sha, "--rereview-id", "42").returncode, 0)
        self.git("checkout", "-q", "--detach", sha)  # the PR head moves on while the reviewer is dead; the old
        self.git("commit", "-q", "--allow-empty", "-m", "newer")  # head stays reachable, so the worktree is clean
        self.git("push", "-q", "origin", "HEAD:refs/pull/9/head")
        self.git("checkout", "-q", "main")
        self.set_pane(self.record("vera-9-r1-review")["index"], dead="1")
        r = self.crew("restart", "vera-9-r1-review", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("stale spawn", r.stdout)
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "vera-9-r1-review.json")))

    def test_restart_dead_train_worker_respawns_with_its_train(self):  # #1391 AC 4: the one restart through the lead
        self.assertEqual(self.spawn("builder", "--train", "3").returncode, 0)
        before = self.record("ben-train3")
        self.put("trains/train-3.json", json.dumps({"n": 3, "ci": "pending", "members": [{"pr": 12}]}))
        self.set_pane(before["index"], dead="1")
        r = self.crew("restart", "ben-train3", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.record("ben-train3")
        self.assertEqual((after["restarts"], after["pass"], after["args"]["train"], after["item"]),
                         (1, "train", 3, before["item"]))
        self.assertTrue(os.path.exists(after["claim"]))
        self.assertTrue(os.path.exists(os.path.join(self.state, "trains", "train-3.json")))  # the worker resumes with train wait
        self.set_pane(after["index"], dead="1")
        again = self.crew("restart", "ben-train3", "--project", self.project, "--timeout", "1")
        self.assertIn("already restarted once; escalate", again.stdout)  # the lead then sends train-failed

    def reflection_gh(self, comments, exit=0):
        """A fake gh: one open reflection:log issue, #5, holding these comments."""
        with open(os.path.join(self.tmp, "bin", "gh"), "w") as f:
            f.write("#!/usr/bin/env python3\nimport json, sys\na = sys.argv[1:]\n"
                    "open(%r, 'a').write(json.dumps(a) + '\\n')\nif %d: sys.exit(%d)\n"
                    "if a[:2] == ['issue', 'list']: print(json.dumps([{'number': 5}]))\n"
                    "elif a[:2] == ['issue', 'view']: print(json.dumps({'comments': json.loads(%r)}))\n" % (
                        os.path.join(self.tmp, "gh-calls.log"), exit, exit, json.dumps(comments)))

    def test_restart_dead_reflection_respawns_with_its_request(self):  # #1520
        self.assertEqual(self.spawn("researcher", "--reflection", "close-3").returncode, 0)
        before = self.record("riley-reflection")
        self.git("commit", "-q", "--allow-empty", "-m", "newer")
        self.git("push", "-q", "origin", "main")
        self.reflection_gh([{"url": "https://example.invalid/5#c1", "body": "[Riley/reflection] close-2\n\n"
                             "<!-- crew:v1 role=researcher pass=reflection window=close-2 sha=%s proposals=0 new=0 "
                             "incidents=0 -->" % HEAD}])
        self.set_pane(before["index"], dead="1")
        r = self.crew("restart", "riley-reflection", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        after = self.record("riley-reflection")
        self.assertEqual((after["restarts"], after["args"], after["item"], after["head"]),
                         (1, before["args"], before["item"], before["head"]))
        with open(os.path.join(self.tmp, "gh-calls.log")) as f:
            self.assertEqual([json.loads(line)[:3] for line in f], [["issue", "list", "-R"], ["issue", "view", "5"]])

    def test_restart_refuses_a_reflection_whose_report_is_posted(self):  # #1520
        self.assertEqual(self.spawn("researcher", "--reflection", "close-3", "--log", "5").returncode, 0)
        rec = self.record("riley-reflection")
        self.set_pane(rec["index"], dead="1")
        self.reflection_gh([], exit=1)
        r = self.crew("restart", "riley-reflection", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing restart: cannot recheck reflection close-3's report", r.stdout)
        self.reflection_gh([{"url": "https://example.invalid/5#c2", "body": "[Riley/reflection] week-2026-W45+close-3\n\n"
                             "<!-- crew:v1 role=researcher pass=reflection window=week-2026-W45+close-3 sha=%s "
                             "proposals=1 new=1 incidents=2 -->" % HEAD}])
        r = self.crew("restart", "riley-reflection", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("refusing restart: reflection close-3 already posted at https://example.invalid/5#c2", r.stdout)
        self.assertEqual(self.record("riley-reflection"), rec)  # nothing respawned to write again

    def test_restart_in_place_accepts_claude_version_pane(self):  # #286: the relaunch takes spawn's start evidence
        self.assertEqual(self.spawn("builder", "--issue", "8", "--tier", "trivial").returncode, 0)
        wt = self.record("ben-8")["worktree"]
        self.assertEqual(self.record("ben-8")["harness"], "claude")
        with open(os.path.join(wt, "notes.txt"), "w") as f:
            f.write("draft\n")
        self.set_pane(11, dead="1")
        claude = os.path.join(self.tmp, "bin", "claude")  # a plain `claude` on PATH: only the foreground names match
        with open(claude, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(claude, 0o755)
        self.env["FAKE_TMUX_PANE"] = "2.1.314"
        with open(self.ps, "w") as f:
            json.dump({"fg": {"/dev/ttyp11": [["S+", "claude"]]}}, f)
        r = self.crew("restart", "ben-8", "--project", self.project, "--timeout", "1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("crew: restarted ben-8 (window 11) in its worktree", r.stdout)
        self.assertEqual(self.record("ben-8")["restarts"], 1)


class RestartKeepsPendingDelivery(DeliveryBase):  # #1850 D2.3: the prescribed restart discards no pending id
    def test_pending_id_survives_the_one_restart_fresh_or_in_place(self):
        for unlanded in (False, True):
            with self.subTest(unlanded=unlanded):
                if unlanded:  # a second builder whose worktree holds work: relaunched in place
                    self.assertEqual(self.spawn("builder", "--issue", "8").returncode, 0)
                window, index = ("ben-8", 11) if unlanded else ("ben-7", 10)
                wt = self.record(window)["worktree"]
                if unlanded:
                    with open(os.path.join(wt, "notes.txt"), "w") as f:
                        f.write("draft\n")
                self.set_pane(index, command=self.record(window)["harness"], screen=self.BUSY)
                send = lambda *refs: self.crew("send", window, "fix", *refs, "--project", self.project)
                self.assertEqual(send("#12", "a" * 40).returncode, 0)
                self.assertEqual(send("#13", "b" * 40).returncode, 0)
                done, pending = [m["id"] for m in self.inbox_of(window)]
                with open(os.path.join(self.state, "status", window + ".status"), "a") as f:
                    f.write("ack: %s\n" % done)
                self.set_pane(index, command=self.record(window)["harness"], screen=self.BUSY, dead="1")
                self.assertEqual(self.read(window, pending)["action"], "restart")
                r = self.crew("restart", window, "--project", self.project, "--timeout", "1")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                ids = [m["id"] for m in self.inbox_of(window)]
                self.assertEqual(ids, [done, pending] if unlanded else [pending])  # the unacked id is kept
                if not unlanded:
                    self.assertIn("kept 1 pending inbox message(s) for %s: %s" % (window, pending), r.stdout)
                self.set_pane(index, command=self.record(window)["harness"], screen=self.IDLE)
                d = self.read(window, pending)
                self.assertEqual([d["delivery"], d["worker"], d["action"], d["nudges"], d["restarts"]],
                                 ["recorded", "idle", "nudge", 0, 1])
                r = send("#13", "b" * 40)  # the successor gets the same id once; no second message
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                self.assertIn("sent %s to %s (pending id kept)" % (pending, window), r.stdout)
                self.assertEqual([m["id"] for m in self.inbox_of(window)].count(pending), 1)
                self.set_pane(index, command=self.record(window)["harness"], screen=self.IDLE, dead="1")
                self.assertEqual(self.read(window, pending)["action"], "escalate")
                r = self.crew("restart", window, "--project", self.project, "--timeout", "1")
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("already restarted once", r.stdout)
                self.assertIn(pending, [m["id"] for m in self.inbox_of(window)])

    def inbox_of(self, window):
        with open(os.path.join(self.state, "inbox", window + ".jsonl")) as f:
            return [json.loads(line) for line in f]

    def read(self, window, msg_id):
        r = self.crew("acked", window, msg_id, "--delivery", "--project", self.project)
        self.assertIn(r.returncode, (0, 3), r.stdout + r.stderr)
        return json.loads(r.stdout)


if __name__ == "__main__":
    unittest.main()
