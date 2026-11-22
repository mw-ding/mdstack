"""Tests for mdstack kill, moved from test-crew.py; fixtures in crew_testlib.py (stdlib only).

Covers: removes only its own run, refuses the coordinator, removes a reviewer's verdict files
(review sections retained for re-validation), refuses unlanded work (uncommitted, untracked,
local-only commit; pushed or merged work is removed), `--discard --reason` removes and posts
the reason, step summaries excluded at spawn, scratch files under `runs/` removed, ends a real
pane process that ignores SIGHUP. Run in CI.
"""
import json
import os
import signal
import subprocess
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import KillLandedBase, LivenessBase, SpawnBase


class Kill(SpawnBase):
    def test_kill_removes_reviewer_verdict_files(self):  # #139 follow-up: verdicts/ left behind
        sha = self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("reviewer", "--pr", "9").returncode, 0)
        self.assertEqual(self.spawn("reviewer", "--pr", "9", "--pass", "validate").returncode, 0)
        files = {p: "verdicts/pr9-%s-%s.md" % (sha[:7], p) for p in ["r1-review", "r1-validate", "r1-verdict", "r2-review",
                                                                 "r2-verdict"]}
        for rel in files.values():
            self.put(rel, "section\n")
        self.put("status/vera-9-r1-review.status", "done: #9 %s review pass\n" % sha)
        self.assertEqual(self.crew("kill", "vera-9-r1-review", "--project", self.project).returncode, 0)
        exists = lambda k: os.path.exists(os.path.join(self.state, files[k]))
        self.assertTrue(exists("r1-review"))  # validation and re-validation still read it
        self.assertEqual(self.crew("kill", "vera-9-r1-validate", "--project", self.project).returncode, 0)
        self.assertEqual([exists(k) for k in ["r1-review", "r1-validate", "r1-verdict", "r2-review", "r2-verdict"]],
                         [True, False, False, True, True])  # #139 N6: validate's own -verdict file too
        self.assertEqual(self.spawn("reviewer", "--pr", "9", "--round", "2").returncode, 0)
        self.put("status/vera-9-r2-review.status", "done: #9 %s review changes\n" % sha)
        self.assertEqual(self.crew("kill", "vera-9-r2-review", "--project", self.project).returncode, 0)
        self.assertTrue(exists("r2-review"))

    def test_kill_removes_only_its_own_run(self):
        self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        self.assertEqual(self.spawn("reviewer", "--pr", "9").returncode, 0)
        mine, other = self.record("ben-7"), self.record("vera-9-r1-review")
        os.makedirs(os.path.join(mine["worktree"], "target"))  # build output inside the run's worktree
        for d in ["inbox", "status"]:
            os.makedirs(os.path.join(self.state, d), exist_ok=True)
        self.put("inbox/ben-7.jsonl", "{}\n")
        self.put("status/ben-7.status", "done: x\n")
        self.put("status/vera-9-r1-review.status", "ack: y\n")
        self.put("runs/ben-7.prbody.md", "body\n")  # agent scratch files in runs/ (#139 F7)
        self.put("runs/ben-7.notes.txt", "x\n")
        self.put("runs/ben-7.body.md", "body\n")  # the body file the tmux briefs name (#270)
        for rel in ["runs/body/ben-7-pr.md", "runs/body/ben-70-pr.md", "runs/body/vera-9-r1-review-pr.md"]:
            self.put(rel, "body\n")  # files under a runs/ subdirectory (#139 N6)
        r = self.crew("kill", "ben-7", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn(["kill-window", "-t", "=crew-acme-widgets:10"], self.calls())
        self.assertFalse(os.path.exists(mine["worktree"]))
        self.assertNotIn(mine["worktree"], self.git("worktree", "list"))
        for rel in ["runs/ben-7.json", "runs/ben-7.brief.md", "runs/ben-7.prbody.md", "runs/ben-7.notes.txt",
                    "runs/ben-7.body.md", "runs/body/ben-7-pr.md", "inbox/ben-7.jsonl", "status/ben-7.status",
                    "claims/builder-issue7"]:
            self.assertFalse(os.path.exists(os.path.join(self.state, rel)), rel)
        self.assertTrue(os.path.isdir(other["worktree"]))
        self.assertTrue(os.path.exists(os.path.join(self.state, "runs", "vera-9-r1-review.json")))
        self.assertTrue(os.path.exists(os.path.join(self.state, "runs", "vera-9-r1-review.brief.md")))
        for rel in ["runs/body/ben-70-pr.md", "runs/body/vera-9-r1-review-pr.md"]:
            self.assertTrue(os.path.exists(os.path.join(self.state, rel)), rel)
        self.assertTrue(os.path.exists(os.path.join(self.state, "status", "vera-9-r1-review.status")))
        self.assertTrue(os.path.exists(other["claim"]))

    def test_kill_refuses_coordinator_and_down_kills_runs(self):
        r = self.crew("kill", "ash", "--project", self.project)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.spawn("builder", "--issue", "7").returncode, 0)
        wt = self.record("ben-7")["worktree"]
        self.assertEqual(self.crew("down", "--project", self.project).returncode, 0)
        self.assertFalse(os.path.exists(wt))
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-7.json")))


class KillLanded(KillLandedBase):
    def test_squash_merged_builder_removed_after_branch_deleted(self):
        wt = self.builder()
        self.git("checkout", "-q", "-b", "builder/7-x", cwd=wt)
        head = self.commit(wt)
        self.git("push", "-q", "origin", "HEAD:refs/pull/12/head", cwd=wt)
        self.git("fetch", "-q", "origin", "refs/pull/12/head")  # the builder's own copy: its branch is not here (#1252)
        self.git("merge", "--squash", "FETCH_HEAD")
        self.git("commit", "-q", "-m", "squash PR 12")
        self.git("push", "-q", "origin", "main")
        self.assertNotEqual(self.git("rev-parse", "HEAD"), head)
        self.put("status/ben-7.status", "done: #7 #12 %s\nack: later-message\n" % head)
        r = self.kill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))

    def test_done_line_with_trailing_note_still_names_the_pr(self):  # #695: ben-669's done line carried a note
        wt = self.builder()
        self.git("checkout", "-q", "-b", "builder/7-x", cwd=wt)
        head = self.commit(wt)
        self.git("push", "-q", "origin", "HEAD:refs/pull/12/head", cwd=wt)
        self.put("status/ben-7.status", "done: #7 #12 %s (note: local main was stale)\n" % head)
        r = self.kill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))

    def test_done_line_pr_never_pushed_still_refused(self):
        wt = self.builder()
        self.git("checkout", "-q", "-b", "builder/7-x", cwd=wt)
        head = self.commit(wt)
        self.put("status/ben-7.status", "done: #7 #12 %s (note)\n" % head)
        self.assert_refused(self.kill(), wt, "commit: %s feat: a.txt" % head)

    def test_commit_after_recorded_pr_head_still_refused(self):
        wt = self.builder()
        head = self.commit(wt)
        self.git("push", "-q", "origin", "HEAD:refs/pull/12/head", cwd=wt)
        rec = self.record("ben-7")
        rec["pr"] = 12
        self.put("runs/ben-7.json", json.dumps(rec))
        extra = self.commit(wt, "extra.txt")
        r = self.kill()
        self.assert_refused(r, wt, "commit: %s feat: extra.txt" % extra)
        self.assertNotIn("commit: %s feat: a.txt" % head, r.stdout)

    def test_clean_and_pushed_branch_removed(self):
        wt = self.builder()
        self.git("checkout", "-q", "-b", "infra/7-x", cwd=wt)
        self.commit(wt)
        self.git("push", "-q", "origin", "infra/7-x", cwd=wt)
        r = self.kill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))
        self.assertEqual(self.gh_calls(), [])

    def test_uncommitted_refused(self):
        wt = self.builder()
        with open(os.path.join(wt, "staged.txt"), "w") as f:
            f.write("x\n")
        self.git("add", "staged.txt", cwd=wt)
        self.assert_refused(self.kill(), wt, "uncommitted: A  staged.txt")

    def test_untracked_refused(self):
        wt = self.builder()
        os.makedirs(os.path.join(wt, "new"))
        with open(os.path.join(wt, "new", "file.txt"), "w") as f:
            f.write("x\n")
        self.assert_refused(self.kill(), wt, "uncommitted: ?? new/file.txt")

    def test_step_summaries_excluded_at_spawn(self):  # #234 N7
        wt = self.builder()
        os.makedirs(os.path.join(wt, ".crew", "runs", "issue-7", "r1"))
        with open(os.path.join(wt, ".crew", "runs", "issue-7", "r1", "summary.md"), "w") as f:
            f.write("build: ok\n")
        self.assertEqual(self.git("status", "--porcelain", "--untracked-files=all", cwd=wt), "")
        r = self.kill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))
        wt = self.builder()  # the builder's own copy holds the line, once (#1252)
        with open(os.path.join(wt, ".git", "info", "exclude")) as f:
            self.assertEqual(f.read().split().count(".crew/"), 1)
        self.assertEqual(self.crew("kill", "ben-7", "--project", self.project).returncode, 0)
        self.pr(9, "codex gpt-6.1-sol medium")  # a linked worktree still writes the shared exclude, once
        for _ in range(2):
            self.assertEqual(self.spawn("reviewer", "--pr", "9").returncode, 0)
            self.assertEqual(self.crew("kill", "vera-9-r1-review", "--project", self.project).returncode, 0)
        with open(os.path.join(self.project_dir, ".git", "info", "exclude")) as f:
            self.assertEqual(f.read().split().count(".crew/"), 1)

    def test_researcher_artifact_under_crew_removed_elsewhere_refused(self):  # #1941
        for path, removed in ((".crew/lavish/summary.html", True), (".lavish/summary.html", False)):
            with self.subTest(path=path):
                self.assertEqual(self.spawn("researcher", "--issue", "7").returncode, 0)
                wt = self.record("riley-7")["worktree"]
                os.makedirs(os.path.dirname(os.path.join(wt, path)), exist_ok=True)
                with open(os.path.join(wt, path), "w") as f:
                    f.write("<html></html>\n")
                r = self.crew("kill", "riley-7", "--project", self.project)
                self.assertEqual((r.returncode, os.path.isdir(wt)), (0, False) if removed else (1, True), r.stdout)
                if not removed:
                    self.assertIn("uncommitted: ?? " + path, r.stdout)

    def test_local_only_commit_refused(self):
        wt = self.builder()
        self.git("checkout", "-q", "-b", "infra/7-x", cwd=wt)
        sha = self.commit(wt)
        self.assert_refused(self.kill(), wt, "commit: %s feat: a.txt" % sha)

    def test_merged_into_default_branch_removed(self):
        wt = self.builder()
        self.git("checkout", "-q", "-b", "infra/7-x", cwd=wt)
        self.commit(wt)
        self.git("push", "-q", "origin", "HEAD:main", cwd=wt)  # landed on main; the branch itself never pushed
        r = self.kill()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))

    def test_discard_with_reason_removes_and_posts(self):
        wt = self.builder()
        sha = self.commit(wt)
        r = self.kill("--discard", "--reason", "owner: superseded by #8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))
        self.assertFalse(os.path.exists(os.path.join(self.state, "runs", "ben-7.json")))
        (call,) = self.gh_calls()
        self.assertEqual(call[:4], ["issue", "comment", "7", "-R"])
        body = call[call.index("--body") + 1]
        self.assertIn("owner: superseded by #8", body)
        self.assertIn(sha, body)

    def test_discard_without_reason_refused(self):
        wt = self.builder()
        r = self.kill("--discard")
        self.assertEqual(r.returncode, 2)
        self.assertIn("--reason", r.stdout)
        self.assertTrue(os.path.isdir(wt))
        self.assertNotIn(["kill-window", "-t", "=crew-acme-widgets:10"], self.calls())

    def test_discard_keeps_worktree_when_post_fails(self):
        wt = self.builder()
        self.commit(wt)
        self.gh_exit = 1
        self.write_gh()
        r = self.kill("--discard", "--reason", "x")
        self.assertEqual(r.returncode, 1)
        self.assertIn("not recorded", r.stdout)
        self.assertTrue(os.path.isdir(wt))

    def test_reviewer_worktree_removed_and_pr_discard_posts_on_pr(self):
        self.pr(9, "claude-code opus-5.5 default")
        self.assertEqual(self.spawn("reviewer", "--pr", "9").returncode, 0)
        wt = self.record("vera-9-r1-review")["worktree"]
        r = self.crew("kill", "vera-9-r1-review", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # PR head is on the remote: nothing unlanded
        self.assertFalse(os.path.exists(wt))
        self.pr(10, "codex gpt-6.1-sol medium")
        self.assertEqual(self.spawn("reviewer", "--pr", "10").returncode, 0)
        wt = self.record("vera-10-r1-review")["worktree"]
        with open(os.path.join(wt, "notes.txt"), "w") as f:
            f.write("x\n")
        r = self.crew("kill", "vera-10-r1-review", "--project", self.project, "--discard", "--reason", "scratch")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(wt))
        (call,) = self.gh_calls()
        self.assertEqual(call[:4], ["pr", "review", "10", "--comment"])


class KillLiveness(LivenessBase):
    def test_reclaim_kills_detached_child_group_before_removing_worktree(self):
        code = ("import os, signal, subprocess, sys, time\n"
                "if os.fork(): sys.exit(0)\n"
                "os.setsid()\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
                "print(os.getpid(), child.pid, flush=True)\n"
                "null = os.open(os.devnull, os.O_RDWR)\n"
                "os.dup2(null, 1); os.dup2(null, 2)\n"
                "time.sleep(60)\n")
        output = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=10).stdout
        parent, child = map(int, output.split())
        for pid in (parent, child):
            self.addCleanup(lambda pid=pid: subprocess.run(["kill", "-9", str(pid)], capture_output=True))
        with open(os.path.join(self.tmp, "bin", "ps"), "w") as f:
            f.write('#!/bin/sh\nexec /bin/ps "$@"\n')
        self.set_pane(10, pid=str(parent))
        worktree = self.record("ben-7")["worktree"]
        result = self.crew("kill", "ben-7", "--project", self.project)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.alive(parent))
        self.assertFalse(self.alive(child))
        self.assertFalse(os.path.exists(worktree))

    def test_kill_terminates_pane_group_that_ignores_sighup(self):
        pid, log = self.stubborn(signal.SIGHUP)
        self.set_pane(10, pid=str(pid))
        r = self.crew("kill", "ben-7", "--project", self.project)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(self.alive(pid))
        self.assertFalse(os.path.exists(log))  # SIGTERM ended it; no SIGHUP was needed


if __name__ == "__main__":
    unittest.main()
