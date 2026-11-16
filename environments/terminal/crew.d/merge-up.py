"""Merge the default branch into an actual builder run's clean, owned PR copy (#239).

Usage: mdstack merge-up PR --head H --actor RUN --repo DIR --check 'COMMAND' [--check 'COMMAND'] --project FILE
Only configured Git drivers are used. Checks run before normal push; conflicts/check failures restore H.
Exit 0: current (no note), or published with signed COMMENT. Exit 2: refusal/failure; a pushed head is reported
for reconciliation if its note fails. No rebase, force push, approval or automatic feature resolution.
"""
import os
import re
import shlex
import subprocess
import sys
from crew_shared import (checkout, commands, copy_claim, fetch, git, HERE, load, post_title, profile, refuse_paused,
                         require_ownership, runs)

posts = load("crew_merge_posts", "environments/terminal/crew.d/_helper-posts.py")


def register(sub):
    p = sub.add_parser("merge-up")
    p.add_argument("pr", type=int)
    for name in ("head", "actor", "repo", "project"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--check", action="append", required=True, help="targeted check argv, shell-quoted; no shell evaluation")
    p.add_argument("--org-profile")


def live(args, values, head, branch, pr):
    if (pr["number"] != args.pr or pr["state"] != "OPEN" or pr["headRefOid"] != head or
            pr["baseRefName"] != values["repo.default_branch"] or pr["headRefName"] != branch or pr["isCrossRepository"]):
        raise ValueError("wrong, closed or moved PR/repo/branch/head")
    if {v["name"] for v in pr["labels"]} & {"crew:hold", "crew:escalated"}:
        raise ValueError("held or escalated PR")
    return pr


def clean(repo):
    if git(repo, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("dirty tracked/untracked worktree")
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_START"):
        if os.path.exists(git(repo, "rev-parse", "--path-format=absolute", "--git-path", name)):
            raise ValueError("in-progress Git operation: " + name)


def copy(args, values, state, rec):
    repo = os.path.realpath(args.repo)
    source = checkout(values, args.project)
    if (repo != os.path.realpath(rec["worktree"]) or repo != os.path.realpath(git(repo, "rev-parse", "--show-toplevel")) or
            git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir") !=
            git(source, "rev-parse", "--path-format=absolute", "--git-common-dir")):
        raise ValueError("wrong run copy/repository")
    if git(repo, "remote", "get-url", "--push", "origin") != git(source, "remote", "get-url", "origin"):
        raise ValueError("foreign push destination")
    for name, other in runs(state):
        if name != args.actor and other["role"] in ("builder", "coordinator") and any(
                os.path.realpath(other.get(k, "")) == repo for k in ("worktree", "copy_claim")):
            raise ValueError("busy worktree: run " + name)
    clean(repo)
    if git(repo, "rev-parse", "HEAD") != args.head:
        raise ValueError("wrong local head")
    return repo, git(repo, "symbolic-ref", "--short", "HEAD")


def note(args, values, state, rec, base, updated, head, paths, unions, identical, checks):
    content = "content=identical" if identical else "content=different; differing patch requires delta review"
    status = "✅ pass" if values.get("report.emoji", True) else "pass"
    return ("%s\n\nTL;DR: Default branch merged and published; approval carry stays with the synthesizer.\n\n"
            "1. B=%s\n   H=%s\n   U=%s\n   new-head=%s\n"
            "2. Merge paths: %s\n   Configured union paths: %s\n3. Strict B/H versus U/new-head comparison: %s.\n\n"
            "Evidence: targeted checks before push:\n\n%s\n\nNext: synthesizer or delta reviewer.\n\n"
            "Engine: %s %s %s\n\n%s\n"
            "<!-- crew:v1 role=builder pass=merge-up pr=%d sha=%s round=n/a verdict=n/a -->\n%s\n") % (
                post_title(values, "builder", "merge-up", "@ " + head[:7], status), base, args.head, updated, head,
                ", ".join(paths) or "none", ", ".join(unions) or "none", content, "\n".join(checks),
                rec["engine"], rec["model"], rec["effort"], posts.usage(state, args.actor, rec), args.pr, head, rec["signature"])


def run(args):
    repo = None
    merged = False
    pushed = False
    acquired = False
    try:
        values, _, state = profile(args)
        print("mdstack: config " + os.path.abspath(args.project), file=sys.stderr)
        posts.sha(args.head)
        if args.pr < 1 or not require_ownership(values, "write") or refuse_paused(state, "merge-up"):
            raise ValueError("merge-up refused")
        if values.get("strategy.update_from_base", "merge") != "merge":
            raise ValueError("rebase update strategy refused")
        rec = posts.actor(args, values, state, "builder")
        repo, branch = copy(args, values, state, rec)
        pr = live(args, values, args.head, branch, posts.view(values, args.pr))
        associated = rec.get("pr") == args.pr or rec["args"].get("pr") == args.pr
        if not associated and not any(i["number"] == rec["args"].get("issue") for i in pr["closingIssuesReferences"]):
            raise ValueError("foreign run PR/issue")
        held = copy_claim.holder(repo)
        copy_claim.acquire(repo, state, args.actor, "pr #%d" % args.pr)
        acquired = held is None
        updated = fetch(repo, values["repo.default_branch"])
        base = git(repo, "merge-base", args.head, updated)
        if base == updated:
            print("crew: current @ " + args.head + "; no push or note")
            return 0
        paths = git(repo, "diff", "--name-only", base, updated).splitlines()
        attrs = git(repo, "check-attr", "-z", "merge", "--", *paths).split("\0") if paths else []
        unions = [attrs[i] for i in range(0, len(attrs) - 1, 3) if attrs[i + 2] == "union"]
        merged = True
        git(repo, "merge", "--no-ff", "--no-edit", updated, "-m",
            "Merge default branch into " + branch + "\n\nEngine: none (pure merge-up, plain git)")
        head = posts.sha(git(repo, "rev-parse", "HEAD"))
        if git(repo, "show", "-s", "--format=%P", head).split() != [args.head, updated]:
            raise ValueError("unverified merge parents")
        identical = commands()["content"].identical(repo, base, args.head, updated, head)
        checks = []
        for command in args.check:
            argv = shlex.split(command)
            if not argv:
                raise ValueError("empty targeted check")
            result = subprocess.run([sys.executable, os.path.join(HERE, "evidence-cli.py"),
                                     "--label", "merge-check-%d" % (len(checks) + 1), "--sha", head, "--root", repo,
                                     "--", *argv], cwd=repo, capture_output=True, text=True)
            checks.append(result.stdout)
            print(checks[-1])
            code = re.search(r"^exit: (-?\d+)$", result.stdout, re.M)
            if result.returncode or code is None or int(code[1]) != 0:
                raise ValueError("targeted check failed")
        clean(repo)
        if git(repo, "rev-parse", "HEAD") != head:
            raise ValueError("check changed head")
        body = note(args, values, state, rec, base, updated, head, paths, unions, identical, checks)
        live(args, values, args.head, branch, posts.view(values, args.pr))
        if not require_ownership(values, "write") or refuse_paused(state, "merge-up push"):
            raise ValueError("ownership/pause changed before push")
        # Once push starts, retain the merge on ambiguous failure until native readback confirms its head.
        pushed = True
        result = subprocess.run(["git", "-C", repo, "push", "origin", head + ":refs/heads/" + branch],
                                capture_output=True, text=True)
        published = posts.view(values, args.pr)
        if published["headRefOid"] != head:
            raise ValueError("push unconfirmed (exit %d); reconcile local %s and published %s" %
                             (result.returncode, head, published["headRefOid"]))
        print("crew: published head=" + published["headRefOid"])
        def validate(pr):
            live(args, values, head, branch, pr)
            if refuse_paused(state, "merge-up post"):
                raise ValueError("paused before note")
            return not any(commands()["poll"].signed_by(values, "builder", r) and
                           any(m.get("pass") == "merge-up" and m.get("role") == "builder" and
                               m.get("pr") == str(args.pr) and m.get("sha") == head
                               for m in commands()["route"].markers(r["body"])) for r in pr["reviews"])
        return posts.post(args, values, state, published["headRefOid"], body, validate)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as e:
        if merged and not pushed:
            git(repo, "reset", "--hard", args.head)
        print("crew: refusing merge-up: " + str(e))
        if pushed:
            print("crew: pushed/attempted head retained; reconcile head/note by readback, do not push again")
        return 2
    finally:
        if acquired:
            copy_claim.release(repo, state, args.actor)
