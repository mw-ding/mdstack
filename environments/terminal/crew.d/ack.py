"""Post checked intake, clean merge-up or owner steering acknowledgements (#237).

Usage: mdstack ack intake|merge-up|steer PR --head SHA --actor RUN --project FILE
       merge-up additionally requires --verified-base B --verified-head H --updated-base U
       steer additionally requires --source COMMENT-ID --command hold|escalate
Inbox delivery remains `mdstack action ack` / `acked`. No approval, tag change or command execution.
"""
import os
import re
import sys
from crew_shared import commands, git, load, post_title, profile, refuse_paused, require_ownership

posts = load("crew_helper_posts", "environments/terminal/crew.d/_helper-posts.py")
precheck = load("crew_ack_precheck", "scripts/crew-precheck.py")
STEERS = {"hold", "escalate"}
EFFECT_STEERS = {"merge-ok", "resume", "cutover", "plan-ok", "rereview", "away", "away-return", "rework",
                 "urgent", "stop-landing", "resume-landing", "hold-release"}
HOLD_EXCEPTIONS = {"escalate"}


def register(sub):
    p = sub.add_parser("ack")
    p.add_argument("mode", choices=["intake", "merge-up", "steer"])
    p.add_argument("pr", type=int)
    for flag in ("head", "actor", "project"):
        p.add_argument("--" + flag, required=True)
    for flag in ("org-profile", "source", "command", "verified-base", "verified-head", "updated-base", "engine", "harness", "start"):
        p.add_argument("--" + flag)


def validate(args, values, state, rec, pr):
    if pr["number"] != args.pr or pr["state"] != "OPEN" or pr["headRefOid"] != args.head:
        raise ValueError("closed or stale PR/head")
    labels = {v["name"] for v in pr["labels"]}
    except_hold = args.mode == "steer" and args.command in HOLD_EXCEPTIONS
    if labels & {"crew:hold", "crew:escalated"} and not except_hold or pr["isDraft"]:
        raise ValueError("held, escalated or draft PR")
    role = "coordinator" if args.mode == "steer" else "reviewer"
    route, poll = commands()["route"], commands()["poll"]
    own = [r for r in pr["reviews"] if poll.signed_by(values, role, r)]
    if args.mode == "steer":
        if args.command in EFFECT_STEERS:
            raise ValueError("steer marker has downstream effects; use the owner-decision dispatcher")
        if args.command not in STEERS or not re.fullmatch(r"[1-9][0-9]*", args.source or ""):
            raise ValueError("recognized non-authorization command and owner source required")
        slug = "%s/%s" % (values["repo.owner"], values["repo.name"])
        source = poll.gh_json("api", "repos/%s/issues/comments/%s" % (slug, args.source))
        text = source["body"]
        match = re.fullmatch(r"/crew ([a-z-]+)(?:[ :].*)?", text.strip(), re.S)
        if (source["user"]["login"] not in values["identities.owners"] or source["id"] != int(args.source) or
                not source["issue_url"].endswith("/repos/%s/issues/%s" % (slug, args.pr)) or
                source["created_at"] != source["updated_at"] or not match or match[1] != args.command):
            raise ValueError("wrong, edited or foreign owner source/command")
        return not any(m.get("pass") == "steer" and m.get("cmd-id") == args.source
                       for r in own for m in route.markers(r["body"]))
    if values.get("builder.precheck.enabled", False):
        issues = pr["closingIssuesReferences"]
        result = precheck.check(pr, {"gh_user": values["identities.builder.gh_user"], "name": values["identities.builder.name"]},
                                item=str(issues[0]["number"]) if len(issues) == 1 else None)
        if result != "pass":
            raise ValueError("precheck: " + result)
    wt = rec["worktree"]
    if git(wt, "rev-parse", "HEAD") != args.head:
        raise ValueError("run copy is not at live head")
    base = git(wt, "merge-base", args.head, "origin/" + pr["baseRefName"])
    engines = commands()["spawn"].builder_engines(values, state, wt, base, args.head, args.pr)
    if rec["engine"] in engines:
        raise ValueError("reviewer engine matches actual builder")
    if args.mode == "intake":
        phase = commands()["poll"].pr_snapshot(pr, values=values)
        if rec["pass"] != "review" or rec["args"].get("round") != 1 or phase["round"] != 1 or phase["verdict"]:
            raise ValueError("intake requires live review round 1")
    else:
        refs = [posts.sha(getattr(args, key)) for key in ("verified_base", "verified_head", "updated_base")]
        previous = [m for r in pr["reviews"] if poll.signed_by(values, "reviewer", r)
                    for m in route.markers(r["body"]) if m.get("pass") == "verdict"]
        if not previous or previous[-1].get("pr") != str(args.pr) or previous[-1].get("verdict") != "changes" or previous[-1].get("sha") != refs[1] or previous[-1].get("base") != refs[0]:
            raise ValueError("merge-up requires latest changes verdict at verified base/head")
        if rec["pass"] != "review" or rec["args"].get("round") != poll.pr_snapshot(pr, values=values)["round"]:
            raise ValueError("merge-up run round does not match changes verdict")
        if git(wt, "show", "-s", "--format=%P", args.head).split() != [refs[1], refs[2]]:
            raise ValueError("unverified merge parents")
        git(wt, "merge-base", "--is-ancestor", refs[2], "origin/" + pr["baseRefName"])
        if route.open_rereview(pr, args.head) or git(wt, "show", "--remerge-diff", "--format=", args.head) or not commands()["content"].identical(wt, *refs, args.head):
            raise ValueError("merge-up content is not a verified clean update")
    return not any(m.get("pass") == "ack" and m.get("sha") == args.head and m.get("pr") == str(args.pr)
                   for r in own for m in route.markers(r["body"]))  # marker only, never the title (#1946)


def run(args):
    try:
        values, _, state = profile(args)
        print("mdstack: config " + os.path.abspath(args.project), file=sys.stderr)
        posts.sha(args.head)
        if args.pr < 1 or not require_ownership(values, "write") or refuse_paused(state, "ack"):
            raise ValueError("ack refused")
        role = "coordinator" if args.mode == "steer" else "reviewer"
        rec = posts.actor(args, values, state, role)
        check = lambda pr: validate(args, values, state, rec, pr)
        pr = posts.view(values, args.pr)
        if not check(pr):
            print("crew: ack already posted")
            return 0
        headline = (post_title(values, role, "steer", "ack " + args.command) if args.mode == "steer"
                    else post_title(values, role, "ack", args.mode))
        message = {"intake": "Review has started at this head.", "merge-up": "Clean update verified; unresolved findings remain.",
                   "steer": "Owner source acknowledged; command not executed."}[args.mode]
        marker = "role=%s pass=%s pr=%s sha=%s round=n/a verdict=n/a" % (
            "coordinator" if role == "coordinator" else "reviewer-validator", "steer" if args.mode == "steer" else "ack", args.pr, args.head)
        if args.mode == "steer":
            marker += " cmd=%s cmd-id=%s" % (args.command, args.source)
        status = "✅ pass" if values.get("report.emoji", True) else "pass"
        body = "%s @ %s · %s\n\nTL;DR: %s\n\n1. Live actor, head and phase/source checked. No approval or tag change.\n\nEvidence: bound to the full SHA in the marker.\nNext: existing dispatcher or reviewer.\n\nEngine: %s %s %s\n\n%s\n<!-- crew:v1 %s -->\n%s\n" % (
            headline, args.head[:7], status, message, rec["engine"], rec["model"], rec["effort"], posts.usage(state, args.actor, rec), marker, rec["signature"])
        return posts.post(args, values, state, args.head, body, check)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as e:
        print("crew: refusing ack: " + str(e))
        return 2
