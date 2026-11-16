"""Check completed sections and post one native head-bound COMMENT verdict; runs neither pass.

Usage: mdstack verdict PR --head H --base B --round K --actor RUN --project FILE
       [--review FILE] [--validation FILE]
Defaults read the retained review and the actor's completed verdict file. Review changes has no validation;
a justified flavor skip is supplied by the review actor. Recheck supplies both sections in its one file.
Refusals have no review/tag effect. A posted verdict whose tag readback fails needs reconciliation, not reposting.
"""
import datetime
import os
import re
import shlex
import subprocess
import sys
from crew_shared import commands, crew_render, git, load, post_title, profile, refuse_paused, require_ownership, ROOT

posts = load("crew_verdict_posts", "environments/terminal/crew.d/_helper-posts.py")
item_flavor = load("crew_verdict_flavor", "scripts/item-flavor.py")
precheck = load("crew_verdict_precheck", "scripts/crew-precheck.py")


def register(sub):
    p = sub.add_parser("verdict")
    p.add_argument("pr", type=int)
    for flag in ("head", "base", "round", "actor", "project"):
        p.add_argument("--" + flag, required=True, type=int if flag == "round" else str)
    for flag in ("org-profile", "review", "validation"):
        p.add_argument("--" + flag)


def sections(args, state, rec):
    retained = os.path.join(state, "verdicts", "pr%s-%s-r%s-review.md" % (args.pr, args.head[:7], args.round))
    paths = [args.review or (rec["verdict"] if rec["pass"] == "recheck" else retained)]
    if args.validation or rec["pass"] == "validate":
        paths.append(args.validation or rec["verdict"])
    parts = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            parts.append(f.read().strip())
    text = "\n\n".join(parts)
    headings = list(re.finditer(r"^## (Review|Validation)[ \t]*$", text, re.M))
    names = [m[1] for m in headings]
    markers = commands()["route"].markers(text)
    expected = ["review", "validate"] if names == ["Review", "Validation"] else ["review"] if names == ["Review"] else []
    if not expected or len(markers) != len(expected):
        raise ValueError("missing or duplicate sections/markers")
    for i, pass_ in enumerate(expected):
        part = text[headings[i].end():headings[i + 1].start() if i + 1 < len(headings) else len(text)]
        found = commands()["route"].markers(part)
        if len(found) != 1:
            raise ValueError("marker outside its section")
        marker = found[0]
        binding = dict(role="reviewer-validator", pr=str(args.pr), sha=args.head, base=args.base, round=str(args.round), **{"pass": pass_})
        if any(marker.get(k) != v for k, v in binding.items()) or marker.get("verdict") not in ("pass", "changes"):
            raise ValueError("wrong section PR/head/base/round/result")
        declared = re.findall(r"^Verdict:[ \t]*(pass|changes)[ \t]*$", part, re.M)
        if not re.sub(r"<!--.*?-->", "", part, flags=re.S).strip() or any(v != marker["verdict"] for v in declared):
            raise ValueError("empty section or inconsistent result")
        if pass_ == "review" and "validation" in marker:
            raise ValueError("skip on wrong section")
    if expected == ["review"] and (markers[0]["verdict"] != "changes" or "skipped: review failed" not in text):
        raise ValueError("incomplete verdict; review changes must say skipped: review failed")
    if len(markers) == 2 and markers[0]["verdict"] != "pass":
        raise ValueError("failed review cannot run validation")
    result = "changes" if any(m["verdict"] == "changes" for m in markers) else "pass"
    skipped = len(markers) == 2 and markers[1].get("validation") == "skipped"
    if len(markers) == 2 and markers[1].get("validation") not in (None, "skipped"):
        raise ValueError("invalid validation mode")
    if rec["pass"] == "review" and not (len(markers) == 1 or skipped) or rec["pass"] == "validate" and (len(markers) != 2 or skipped) or rec["pass"] not in ("review", "validate", "recheck"):
        raise ValueError("wrong actor pass for completed sections")
    return text, result, skipped


def rigor(args, values, pr):
    config = item_flavor.config
    profile_ = config.resolve_profile(args.project, args.org_profile)[0]
    poll, train = commands()["poll"], commands()["train"]
    slug = "%s/%s" % (values["repo.owner"], values["repo.name"])
    paths = train.train_paths(poll, slug, args.pr)
    items = pr["closingIssuesReferences"]
    if len(items) != 1:
        raise ValueError("one linked item required for flavor resolution")
    issue = poll.gh_json("issue", "view", str(items[0]["number"]), "-R", slug, "--json", "comments,labels")
    if {l["name"] for l in issue["labels"]} & {"crew:hold", "crew:escalated"}:
        raise ValueError("linked item held or escalated")
    bodies = [c["body"] for c in issue["comments"] if poll.signed_by(values, "coordinator", c)]
    item = item_flavor.resolve_item(profile_, items[0]["number"], bodies, labels=[l["name"] for l in issue["labels"] + pr["labels"]])
    if item["status"] not in ("recorded", "flavor-missing"):
        raise ValueError("unreadable or refused item flavor")
    if item["status"] == "flavor-missing":
        print("crew: flavor-missing; thorough applies")
    named = dict(config.FLAVOR_PRESETS)
    for name, custom in profile_["flavor"].get("custom", {}).items():
        named[name] = dict(named[custom["base"]], **{k: v for k, v in custom.items() if k != "base"})
    path_rigor = config.class_flavor(profile_, paths)["rigor"]
    choices = [named[item["flavor"]], path_rigor]
    knobs = {k: min((c[k] for c in choices), key=order.index) for k, order in config.FLAVOR_ORDER.items() if k != "builder"}
    knobs["caps"] = [max(c["caps"][i] for c in choices) for i in range(2)]
    return knobs, paths


def validate(args, values, state, rec, result, skipped, text, pr):
    if pr["number"] != args.pr or pr["headRefOid"] != args.head or pr["state"] != "OPEN" or pr["isDraft"] or {l["name"] for l in pr["labels"]} & {"crew:hold", "crew:escalated"}:
        raise ValueError("closed, held or stale PR/head")
    poll, route = commands()["poll"], commands()["route"]
    own = route.own_view(values, pr)
    if rec["args"].get("round") != args.round or rec.get("rereview_id") != route.rereview_id(own, args.head):
        raise ValueError("wrong round or obsolete rereview binding")
    for review in pr["reviews"]:
        if any(poll.round_reset(values, review, m) for m in route.markers(review["body"])):
            if datetime.datetime.fromisoformat(review["submittedAt"].replace("Z", "+00:00")) >= datetime.datetime.fromisoformat(rec["start"].replace("Z", "+00:00")):
                raise ValueError("obsolete reset binding")
    if not route.open_rereview(own, args.head) and any(m.get("pass") == "verdict" and m.get("sha") == args.head and m.get("round") == str(args.round)
                                                      for r in commands()["review"].current_reviews(values, pr) for m in route.markers(r["body"])):
        raise ValueError("pass already completed; reconcile tags without reposting")
    expected = poll.pr_snapshot(own, values=values)["round"]
    if rec["pass"] == "recheck":
        approved = route.approved_merge_up(own, "%s/%s" % (values["repo.owner"], values["repo.name"]), values["repo.default_branch"])
        if not approved or route.open_rereview(own, args.head) or skipped:
            raise ValueError("unconfirmed recheck; escalate to normal review")
        expected = approved["round"]
    if args.round != expected:
        raise ValueError("wrong live round")
    wt = rec["worktree"]
    if git(wt, "rev-parse", "HEAD") != args.head or git(wt, "merge-base", args.head, "origin/" + pr["baseRefName"]) != args.base:
        raise ValueError("unavailable or wrong run head/reviewed base")
    if rec["engine"] in commands()["spawn"].builder_engines(values, state, wt, args.base, args.head, args.pr):
        raise ValueError("reviewer engine matches actual builder")
    if values.get("builder.precheck.enabled", False):
        linked = pr["closingIssuesReferences"]
        answer = precheck.check(pr, {"gh_user": values["identities.builder.gh_user"], "name": values["identities.builder.name"]}, item=str(linked[0]["number"]) if len(linked) == 1 else None)
        if answer != "pass":
            raise ValueError("precheck: " + answer)
    knobs, paths = rigor(args, values, pr)
    if skipped and (result != "pass" or "skipped (flavor " not in text or not re.search(r"^Reason:[ \t]*\S", text, re.M) or
                    knobs["validation"] == "always" or knobs["validation"] == "behaviour" and
                    (not paths or any(not p.endswith(".md") or p.split("/", 1)[0] != "docs" for p in paths))):
        raise ValueError("ineligible or unjustified validation skip")
    if args.round > knobs["caps"][0]:
        raise ValueError("round cap exhausted")
    return knobs


def tags(args, values, state, result, cap):
    if not require_ownership(values, "write") or refuse_paused(state, "verdict tags"):
        raise ValueError("posted verdict; tags require reconciliation")
    pr = posts.view(values, args.pr)
    if pr["headRefOid"] != args.head or pr["state"] != "OPEN" or {l["name"] for l in pr["labels"]} & {"crew:hold", "crew:escalated"}:
        raise ValueError("posted verdict; live binding changed before tags")
    overlay = crew_render.pack_overlay(args.project, args.org_profile, values)
    renderer = crew_render.Renderer(values, os.path.join(ROOT, "templates"), overlay=overlay)
    template, _ = renderer.op("state-tags", "set-approved" if result == "pass" else "set-changes")
    fill = {"<owner>": values["repo.owner"], "<repo>": values["repo.name"], "<n>": str(args.pr)}
    argv = [re.sub("|".join(map(re.escape, fill)), lambda m: fill[m.group(0)], a) for a in shlex.split(template)]
    escalated = result == "changes" and args.round == cap
    if escalated:
        argv += ["--add-label", "crew:escalated"]
    r = subprocess.run(argv, capture_output=True, text=True)
    labels = {l["name"] for l in posts.view(values, args.pr)["labels"]}
    desired, other = ("crew:approved", "crew:changes") if result == "pass" else ("crew:changes", "crew:approved")
    if desired not in labels or labels & {other, "crew:in-review"} or escalated and "crew:escalated" not in labels:
        raise ValueError("posted verdict; tag readback failed: " + r.stderr.strip())
    print("crew: tags read back" + ("; round cap escalated" if escalated else ""))


def run(args):
    try:
        values, _, state = profile(args)
        print("mdstack: config " + os.path.abspath(args.project), file=sys.stderr)
        posts.sha(args.head)
        posts.sha(args.base)
        if args.pr < 1 or args.round < 1 or not require_ownership(values, "write") or refuse_paused(state, "verdict"):
            raise ValueError("verdict refused")
        rec = posts.actor(args, values, state, "reviewer")
        text, result, skipped = sections(args, state, rec)
        check = lambda pr: validate(args, values, state, rec, result, skipped, text, pr)
        knobs = check(posts.view(values, args.pr))
        status = ("✅ pass" if result == "pass" else "🔁 changes") if values.get("report.emoji", True) else result
        escalation = "\nRound cap reached; open blockers need coordinator escalation.\n" if result == "changes" and args.round == knobs["caps"][0] else ""
        body = "%s\n\nTL;DR: %s.\n\n%s\n\nEffective knobs: %s\n%s\nNext: %s.\n\nEngine: %s %s %s\n\n%s\n<!-- crew:v1 role=reviewer-validator pass=verdict pr=%s sha=%s base=%s round=%s verdict=%s -->\n%s\n" % (
            post_title(values, "reviewer", "verdict", "round %s @ %s" % (args.round, args.head[:7]), status), result, text, knobs, escalation,
            "synthesizer checks merge gates" if result == "pass" else "coordinator routes findings", rec["engine"], rec["model"], rec["effort"],
            posts.usage(state, args.actor, rec), args.pr, args.head, args.base, args.round, result, rec["signature"])
        if len(body) >= 60000:
            raise ValueError("verdict exceeds inline size limit")
        return posts.post(args, values, state, args.head, body, check, after=lambda: tags(args, values, state, result, knobs["caps"][0]))
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as e:
        print("crew: refusing verdict: " + str(e))
        return 2
