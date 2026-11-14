"""`mdstack train build` merges approved PR heads onto the fetched default branch as `crew/train-<n>` in a temporary clone
that ignores local merge attributes (a conflicting PR is dropped), skips local checks by default (`--local` opts in), and waits for CI on a draft train PR after a grace period; `mdstack train land <n> <pr>` lands the next member head-bound after re-checking the
tested default branch, head, blocking state tags, verdict (for a crew:express change, the selfgate record), open rereview, open hold-until, recorded project stop-landing, merge permission and
GitHub mergeability, pauses on transient reads, and closes on a real stop or the last member. Overlapping
members stay in the train unless their merge conflicts. Dropped members are routed for merge-up when the train ends; `mdstack train route` retries their queue; `bisect` isolates red members and rebuilds survivors on main.
Solo dropped members send refs to the coordinator for PR pickup by the owner's session.
`delegate` (#1391) reserves the next train number, records the members' heads and the base under `trains/` and hands the
build to a builder worker through the builder lead; that worker runs `build --train N` (and `wait`/`bisect`), and the
synthesizer keeps landing. `close` also ends a delegated train that never got a record.
`build` and `bisect` refuse before any clone, branch or PR when the change backend declares
strategy.update_from_base = "rebase".
Membership is decided before the push (#1425): drops leaving one member under lone_pr_land = "direct" close the
train unpushed (`path=direct`, collapsed-to-direct) for the synthesizer's direct land, and `check`'s `train-merge`
gate runs the build's drop checks per PR on the default branch with merge-tree.
Repo binding (#1859, team §9.5): before any write, every train record, delegation and qualified member (`<owner>/<name>#<n>`)
an action names must be the selected repo's, and build and delegate read each member's URL from the backend; one foreign
or unreadable source refuses the whole action with nothing written. Train and delegation records carry the selected
project's context, and land reads the member's verdict, permission, control and hold records only from that repo.

Usage: mdstack train build PR... [--after N] [--no-wait] [--local] | build --train N | delegate PR... [--after N] | check PR...
       | wait N | land N PR [--mirror-deferred] | close N | route N | bisect N
       --project FILE [--org-profile FILE]
"""
import argparse
import contextlib
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from crew_shared import (checkout, commands, coordinator_window, fetch, GATEWAY, gateway_error, git, load, NAMES, ownership, profile,
                         require_ownership, runs)

precheck = load("crew_precheck", "scripts/crew-precheck.py")
item_flavor = load("crew_item_flavor", "scripts/item-flavor.py")
repo_bind = load("crew_repo_bind", "environments/terminal/crew.d/_repo_bind.py")


# Merge train (tmux.md mdstack train, #321): build crew/train-<n> = fetched main + each PR head as --no-ff merges, run the
# local checks, push it with a draft PR so CI runs once on the combined result, then land the members one call each, in
# order, at their tested heads with no catch-up between them. Machine-readable lines: member, dropped, landed, stopped,
# train.
def train_path(state, n):
    return os.path.join(state, "trains", "train-%d.json" % n)


def train_load(state, n):
    try:
        with open(train_path(state, n)) as f:
            return json.load(f)
    except FileNotFoundError:
        print("crew: no train %d (run mdstack train build)" % n)
        return None


def train_save(state, rec):
    for d in rec["dropped"]:
        if d["reason"] != "no-head":
            d.setdefault("merge_up", "queued")
    rec["report"] = train_report(rec)
    os.makedirs(os.path.join(state, "trains"), exist_ok=True)
    path = train_path(state, rec["n"])
    pending = path + ".tmp-%d" % os.getpid()
    with open(pending, "w") as f:
        json.dump(rec, f, indent=2)
    os.replace(pending, path)


def delegation_path(state, n):
    return os.path.join(state, "trains", "delegated-%d.json" % n)


def delegation_load(state, n):
    try:
        with open(delegation_path(state, n)) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def delegation_save(state, rec):
    os.makedirs(os.path.join(state, "trains"), exist_ok=True)
    with open(delegation_path(state, rec["n"]) + ".tmp", "w") as f:
        json.dump(rec, f, indent=2)
    os.replace(delegation_path(state, rec["n"]) + ".tmp", delegation_path(state, rec["n"]))


def train_delegate(args, values, state, repo, slug):
    """Reserve the next train number with a delegation record (base and member heads) and hand its build to a builder
    worker through the builder lead (#1391). Refs only: train-<n>, the base, then #<pr> <head> per member."""
    if not require_ownership(values, "write"):
        return 1
    n = train_number(repo, state)
    if args.after:
        parent = train_load(state, args.after)
        if parent is None:
            return 1
        base = fetch(repo, parent["branch"]) if not parent.get("closed") else parent["sha"]
    else:
        base = fetch(repo, values["repo.default_branch"])
    rec = {"n": n, "base": base, "after": args.after, "members": [], "closed": False,
           "context": repo_bind.context(args.project, values),
           "synthesizer": values.get("identities.synthesizer.name", NAMES["synthesizer"]).lower() +
           ("-lead" if commands()["lead"].enabled(state, "synthesizer") else "")}  # its lead lands (#1569)
    for pr in dict.fromkeys(args.items):
        try:
            rec["members"].append({"pr": pr, "head": fetch(repo, "pull/%d/head" % pr)})
        except RuntimeError:
            print("dropped pr=%d reason=no-head" % pr)
    if not rec["members"]:
        print("crew: no member heads; nothing delegated")
        return 1
    delegation_save(state, rec)
    refs = ["train-%d" % n, base] + [r for m in rec["members"] for r in ("#%d" % m["pr"], m["head"])]
    sent = commands()["lead"].handoff(argparse.Namespace(project=args.project, org_profile=args.org_profile,
                                                         timeout=15.0, wait_ack=None), "builder", "train", refs)
    if sent not in (0, 4):  # 4: the nudge was ambiguous but the message is in the lead's inbox
        rec["closed"] = True
        delegation_save(state, rec)
        print("crew: builder lead handoff failed; delegation %d closed; build the train yourself" % n)
        return 1
    print("delegated train n=%d base=%s members=%s path=%s" % (
        n, base, ",".join("%d@%s" % (m["pr"], m["head"]) for m in rec["members"]), delegation_path(state, n)))
    return 0


def train_number(repo, state):
    """1 + the highest train number on the remote or in the state dir, so no train branch is ever reused."""
    remote = git(repo, "ls-remote", "--heads", "origin", "refs/heads/crew/train-*")
    seen = [int(m) for m in re.findall(r"refs/heads/crew/train-(\d+)$", remote, re.M)]
    seen += [int(re.search(r"(\d+)\.json$", p).group(1)) for p in glob.glob(os.path.join(state, "trains", "*.json"))]
    return max(seen, default=0) + 1


def train_local_checks(wt):
    """check-repo, then every dev/tests/*/test-*.py the train's tree has; (failing script, last output lines) or None."""
    scripts = [s for s in ["scripts/check-repo.py"] if os.path.exists(os.path.join(wt, s))]
    scripts += sorted(os.path.relpath(p, wt) for p in glob.glob(os.path.join(wt, "dev", "tests", "*", "test-*.py")))
    for s in scripts:
        r = subprocess.run([sys.executable, s], cwd=wt, capture_output=True, text=True)
        if r.returncode:
            return s, (r.stdout + r.stderr).strip().splitlines()[-5:]
    return ("none" if not scripts else None), []


def train_wait_ci(slug, pr, args, required=()):
    """pass | fail | timeout for the train PR's checks, and their CI run links. Sleeps --grace first: checks register
    a few seconds after the PR opens and `gh pr checks` exits non-zero until they do, so no checks yet is pending, and
    so is an expected check not registered yet (`[ci] required_checks`, #1536): absent at the deadline, it times out."""
    time.sleep(args.grace)
    deadline = time.monotonic() + args.timeout
    while True:
        r = subprocess.run(["gh", "pr", "checks", str(pr), "-R", slug, "--json", "name,bucket,link"],
                           capture_output=True, text=True)
        try:
            checks = json.loads(r.stdout or "[]")
        except ValueError:
            checks = []
        buckets = {c.get("bucket") for c in checks}
        if checks and "pending" not in buckets and (not buckets <= {"pass", "skipping"} or
                                                    not commands()["poll"].missing_checks(checks, required)):
            links = list(dict.fromkeys(re.sub(r"/job/\d+$", "", c["link"]) for c in checks if c.get("link")))
            return ("pass" if buckets <= {"pass", "skipping"} else "fail"), links
        if time.monotonic() >= deadline:
            return "timeout", []
        time.sleep(args.interval)


def train_close(repo, slug, rec, values):
    """Close the train PR without a comment and delete the train branch; the line saying whether both happened."""
    if not require_ownership(values, "write"):
        return "ownership-lost; train kept"
    rec["closed"] = True
    closed = subprocess.run(["gh", "pr", "close", str(rec["pr"]), "-R", slug], capture_output=True).returncode == 0
    deleted = subprocess.run(["git", "-C", repo, "push", "-q", "origin", "--delete", rec["branch"]],
                             capture_output=True).returncode == 0
    return "pr-closed=%s branch-deleted=%s" % ("yes" if closed else "no", "yes" if deleted else "no")


def train_compose(wt, base, prs, rec):
    candidates = []
    for pr in dict.fromkeys(prs):
        try:
            head = fetch(wt, "pull/%d/head" % pr)
        except RuntimeError:
            rec["dropped"].append({"pr": pr, "reason": "no-head"})
            continue
        ancestor = git(wt, "merge-base", base, head)
        paths = set(git(wt, "diff", "--name-only", "--no-renames", ancestor, head).splitlines())
        candidates.append({"pr": pr, "head": head, "paths": paths})
    # Overlapping members stay, in the dependency/approval order the synthesizer supplied; train_build drops a
    # member only when its merge actually conflicts, and train CI tests the combined result (scheduling.md#overlap).
    return candidates


def train_route(args, values, state, repo, slug, rec):
    if not rec.get("closed"):
        return
    poll = commands()["poll"]
    for d in rec["dropped"]:
        if d.get("merge_up", "queued") != "queued" or d["reason"] == "no-head":
            continue
        if d["reason"] == "no-verified-base":
            d["merge_up"] = "reviewer"
            train_save(state, rec)
            print("merge-up pr=%d status=reviewer reason=no-verified-base" % d["pr"])
            continue
        try:
            view = train_view(poll, slug, d["pr"], args, state, rec["n"])
            tags = {lb["name"] for lb in view["labels"]}
            if tags & {"crew:escalated", "crew:hold"}:
                continue
            holds = set(re.findall(r"hold-until-#(\d+)", "\n".join(p["body"] for p in view["reviews"] + view["comments"])))
            if any(poll.gh_json("issue", "view", x, "-R", slug, "--json", "state")["state"] == "OPEN" for x in holds):
                continue
            if view["state"] != "OPEN":
                d["merge_up"] = "closed"
            elif not require_ownership(values, "write"):
                return
            elif commands()["lead"].solo(values, pr=d["pr"]):
                d["merge_up"] = "solo"
                train_save(state, rec)
                sent = commands()["send"].run(argparse.Namespace(
                    window=coordinator_window(values), kind="solo",
                    refs=["#%d" % d["pr"], view["headRefOid"], train_path(state, rec["n"])],
                    wait_ack=None, project=args.project, org_profile=args.org_profile))
                if sent not in (0, 4):
                    d["merge_up"] = "queued"
            elif view["mergeable"] == "CONFLICTING" or d["reason"] in ("conflict", "content-different"):
                d["merge_up"] = "builder"
                train_save(state, rec)  # the worker can read the record as soon as the dispatch starts
                builder = next((name for name, run in runs(state) if run["role"] == "builder" and
                                run.get("pr") == d["pr"]), None)
                if builder:
                    sent = commands()["send"].run(argparse.Namespace(
                        window=builder, kind="fix", refs=["#%d" % d["pr"], view["headRefOid"], train_path(state, rec["n"])],
                        wait_ack=None, project=args.project, org_profile=args.org_profile))
                    if sent not in (0, 4):  # ambiguous nudge is already in the inbox: do not send twice
                        d["merge_up"] = "queued"
                else:
                    linked = poll.gh_json("pr", "view", str(d["pr"]), "-R", slug, "--json", "closingIssuesReferences")
                    issues = linked.get("closingIssuesReferences", [])
                    if issues:
                        if not require_ownership(values, "write"):
                            d["merge_up"] = "queued"
                            train_save(state, rec)
                            return
                        spawned = commands()["spawn"].run(argparse.Namespace(
                            role="builder", issue=issues[0]["number"], pr=d["pr"], pass_="fix", round=1,
                            tier=None, timeout=15.0, project=args.project, org_profile=args.org_profile))
                        if spawned:
                            d["merge_up"] = "queued"
                    else:
                        d["merge_up"] = "queued"
                        d["merge_up_reason"] = "no linked issue for builder dispatch"
            else:
                r = subprocess.run(["gh", "api", "--method", "PUT", "repos/%s/pulls/%d/update-branch" % (slug, d["pr"]),
                                    "-f", "expected_head_sha=" + view["headRefOid"]], capture_output=True, text=True)
                if not r.returncode:
                    d["merge_up"] = "updated"
                elif "already up to date" in r.stderr.lower():
                    d["merge_up"] = "current"
                d["merge_up_reason"] = r.stderr.strip()
        except RuntimeError as e:
            d["merge_up"] = "queued"
            d["merge_up_reason"] = str(e)
        train_save(state, rec)
        print("merge-up pr=%d status=%s" % (d["pr"], d.get("merge_up", "queued")))


def train_build(args, values, state, repo, slug):
    n, main = train_number(repo, state), values["repo.default_branch"]
    delegated = None
    if getattr(args, "train", None):  # a builder worker builds the synthesizer's delegated train (#1391)
        delegated, n = delegation_load(state, args.train), args.train
        if delegated is None or delegated.get("closed") or os.path.exists(train_path(state, n)):
            print("crew: delegated train %d is %s" % (n, "missing" if delegated is None else "closed" if delegated.get(
                "closed") else "already built; run mdstack train wait %d" % n))
            return 1
        args.items, args.after = [m["pr"] for m in delegated["members"]], delegated.get("after")
    base = fetch(repo, main)
    parent = train_load(state, args.after) if args.after else None
    if args.after:
        if parent is None or parent.get("ci") == "fail" or (parent.get("stopped") and not parent["stopped"].get("paused")) or (parent.get("closed") and
                len(parent.get("landed", [])) != len(parent["members"])):
            print("crew: predecessor unavailable; build on the default branch instead")
            return 1
        base = fetch(repo, parent["branch"]) if not parent.get("closed") else parent["sha"]
        if base != parent["sha"]:
            print("crew: predecessor train branch moved")
            return 1
    wt = os.path.join(os.path.abspath(values["paths.worktree_root"]), "train-%d-%s" % (n, base[:7]))
    if os.path.lexists(wt):
        print("crew: refusing train: %s exists" % wt)
        return 1
    rec = {"n": n, "branch": "crew/train-%d" % n, "base": base, "sha": base, "members": [], "dropped": [],
           "pr": None, "local": "none", "ci": "none", "ci_links": [], "after": args.after, "deferred": [],
           "context": repo_bind.context(args.project, values)}
    if delegated and base != delegated["base"]:  # the synthesizer landed meanwhile: a stale base never trains
        rec.update(closed=True, stopped={"reason": "delegated base %s moved to %s" % (delegated["base"], base)})
        train_save(state, rec)
        print("stopped train=%d reason=base-moved" % n)
        print(train_report(rec))
        return 1
    os.makedirs(os.path.dirname(wt), exist_ok=True)
    # A temporary clone, not a worktree: the shared repo's info/attributes (or a global attributes file) can resolve a
    # conflict locally, e.g. merge=union, that GitHub's merge then hits (train 4, #321).
    git(repo, "clone", "-q", "--shared", "--no-checkout", repo, wt)
    try:
        with contextlib.suppress(FileNotFoundError):  # an init template could still supply one
            os.remove(os.path.join(wt, ".git", "info", "attributes"))
        git(wt, "remote", "set-url", "origin", git(repo, "remote", "get-url", "origin"))
        git(wt, "checkout", "-q", "--detach", base)
        prs = []
        for pr in dict.fromkeys(args.items):
            if parent and pr in {m["pr"] for m in parent["members"]}:
                rec["deferred"].append({"pr": pr, "reason": "predecessor-member"})
            else:
                prs.append(pr)
        heads = {m["pr"]: m["head"] for m in delegated["members"]} if delegated else {}
        for candidate in train_compose(wt, base, prs, rec):
            pr, head, paths = candidate["pr"], candidate["head"], candidate["paths"]
            if delegated and head != heads[pr]:  # a new head needs its own verdict; not a merge-up
                rec["dropped"].append({"pr": pr, "head": head, "reason": "head-moved", "merge_up": "none"})
                continue
            before = git(wt, "rev-parse", "HEAD")
            view = commands()["poll"].gh_json("pr", "view", str(pr), "-R", slug, "--json", "number,reviews,labels")
            try:
                lane, _ = train_express(args, values, slug, view)
            except RuntimeError:
                rec["dropped"].append({"pr": pr, "head": head, "reason": "express-unreadable"})
                continue
            verified_base, verified_head = train_verified(commands()["poll"], view, lane)
            if not verified_base and verified_head != head:
                rec["dropped"].append({"pr": pr, "head": head, "reason": "no-verified-base"})
                continue
            if verified_base:
                fetch(wt, verified_base)
                fetch(wt, verified_head)
            r = subprocess.run(["git", "-C", wt, "-c", "core.attributesFile=" + os.devnull, "merge", "-q", "--no-ff",
                                "--no-edit", "-m",
                                "mdstack train %d: merge #%d @ %s" % (n, pr, head[:7]), head], capture_output=True)
            if r.returncode:  # a conflict drops the PR; its builder resolves it (synthesizer brief)
                subprocess.run(["git", "-C", wt, "merge", "--abort"], capture_output=True)
                rec["dropped"].append({"pr": pr, "head": head, "reason": "conflict"})
                continue
            step = git(wt, "rev-parse", "HEAD")
            if verified_base and not commands()["content"].identical(wt, verified_base, verified_head, before, step):
                git(wt, "reset", "--hard", before)
                rec["dropped"].append({"pr": pr, "head": head, "reason": "content-different"})
                continue
            rec["members"].append({"pr": pr, "head": head, "step": step, "paths": sorted(paths),
                                   "verified_base": verified_base, "verified_head": verified_head, "updated_base": before,
                                   "approval": "selfgate" if lane else "verdict"})
        rec["sha"] = git(wt, "rev-parse", "HEAD")
        rec["path"] = "train" if rec["members"] else "none"
        # Membership is decided before the push (#1425): drops that leave one member on the default branch under
        # lone_pr_land = "direct" close the train unpushed; the synthesizer lands that PR directly (land rules).
        if (len(rec["members"]) == 1 and rec["dropped"] and not args.after and not getattr(args, "no_collapse", False)
                and values.get("runtime.options.lone_pr_land", "train") == "direct"):
            rec.update(path="direct", closed=True, path_reason="collapsed-to-direct: train %d dropped %s" % (
                n, ", ".join("#%d (%s)" % (d["pr"], d["reason"]) for d in rec["dropped"])))
        skip_local = not (args.local or values.get("runtime.options.train_local_checks", False))
        train = rec["path"] == "train"
        failed, tail = train_local_checks(wt) if train and not skip_local else ("none", [])
        rec["local"] = "pass" if failed is None else "none" if failed == "none" else "fail " + failed
        if train and skip_local:
            rec["local"] = "skipped"
        if train and failed in (None, "none"):
            if not require_ownership(values, "write"):
                return 1
            git(wt, "push", "-q", "origin", "HEAD:refs/heads/" + rec["branch"])
            body = ("Merge train %d: CI on the combined result only. Never merge this PR; `mdstack train land %d` lands "
                    "the members and closes it.\n\n- Base: `%s` %s\n- Train SHA: %s\n- Members, in landing order: %s\n"
                    "- Dropped / deferred: %s\n" % (
                        n, n, main, base, rec["sha"], ", ".join("#%d @ %s" % (m["pr"], m["head"][:7])
                                                                for m in rec["members"]),
                        ", ".join("#%d (%s)" % (d["pr"], d["reason"]) for d in rec["dropped"]) or "none"))
            if not require_ownership(values, "write"):
                return 1
            r = subprocess.run(["gh", "pr", "create", "-R", slug, "--draft", "--base", main, "--head", rec["branch"],
                                "--title", "mdstack train %d (CI only, do not merge)" % n, "--body", body],
                               capture_output=True, text=True)
            found = re.search(r"/pull/(\d+)", r.stdout)
            if not found:
                print("crew: gh pr create failed: %s" % r.stderr.strip())
                subprocess.run(["git", "-C", repo, "push", "-q", "origin", "--delete", rec["branch"]],
                               capture_output=True)
            else:
                rec["pr"] = int(found.group(1))
                train_save(state, rec)
                rec["ci"] = "pending"
                train_save(state, rec)
                if not args.no_wait:
                    rec["ci"], rec["ci_links"] = train_wait_ci(slug, rec["pr"], args,
                                                               commands()["poll"].required_checks(values))
                if rec["ci"] not in ("pass", "pending"):  # a red train never lands; its check links stay readable after the close
                    train_close(repo, slug, rec, values)
        for line in tail:
            print("crew: %s: %s" % (failed, line))
    finally:
        shutil.rmtree(wt, ignore_errors=True)
    train_save(state, rec)
    for m in rec["members"]:
        print("member pr=%d head=%s step=%s" % (m["pr"], m["head"], m["step"]))
    for d in rec["dropped"]:
        print("dropped pr=%d reason=%s" % (d["pr"], d["reason"]))
    for d in rec["deferred"]:
        print("deferred pr=%d reason=%s" % (d["pr"], d["reason"]))
    for link in rec["ci_links"]:
        print("ci-link %s" % link)
    if rec["path"] == "direct":  # its drops route (`train route <n>`) after the direct land: main has nothing new yet
        print("direct pr=%d head=%s reason=%s" % (rec["members"][0]["pr"], rec["members"][0]["head"], rec["path_reason"]))
    print("train n=%d branch=%s base=%s sha=%s pr=%s local=%s ci=%s" % (
        n, rec["branch"], base, rec["sha"], rec["pr"] or "none", rec["local"].replace(" ", ":"), rec["ci"]))
    print(train_report(rec))
    return 0 if rec["ci"] in ("pass", "pending") or rec["path"] == "direct" else 1


def train_bisect(args, values, state, repo, slug):
    rec = train_load(state, args.items[0])
    if rec is None or rec["ci"] != "fail" or rec.get("landed") or not rec["members"]:
        print("crew: bisect requires a red, unlanded train with members")
        return 1
    if not require_ownership(values, "write"):
        return 1
    if not rec.get("closed"):
        train_close(repo, slug, rec, values)
    result = rec["bisect"] = {"trains": [], "culprits": [], "remaining": None}
    heads = {m["pr"]: m["head"] for m in rec["members"]}
    options = argparse.Namespace(**vars(args))
    options.after, options.no_wait, options.train, options.no_collapse = None, False, None, True  # diagnostic trains

    def build(prs, diagnostic=True):
        if any(fetch(repo, "pull/%d/head" % pr) != heads[pr] for pr in prs):
            raise RuntimeError("crew: bisect member head changed; rebuild the batch")
        n = train_number(repo, state)
        options.items = prs
        train_build(options, values, state, repo, slug)
        child = train_load(state, n)
        result["trains"].append(n)
        train_save(state, rec)
        exact = child and [(m["pr"], m["head"]) for m in child["members"]] == [(pr, heads[pr]) for pr in prs]
        if diagnostic or not exact:
            if child and child.get("pr") and not child.get("closed"):
                train_close(repo, slug, child, values)
                train_save(state, child)
        if not exact or child["ci"] not in ("pass", "fail"):
            raise RuntimeError("crew: bisect test incomplete; no culprit inferred")
        if diagnostic and child["base"] != rec["base"]:
            raise RuntimeError("crew: bisect default branch moved; rebuild the batch")
        return child

    def split(prs):
        if len(prs) == 1:
            result["culprits"].append(prs[0])
            rec["dropped"].append({"pr": prs[0], "head": heads[prs[0]], "reason": "ci-culprit", "merge_up": "culprit"})
            train_save(state, rec)
            print("culprit pr=%d" % prs[0])
            return
        middle = len(prs) // 2
        halves = [prs[:middle], prs[middle:]]
        children = [build(half) for half in halves]
        for half, child in zip(halves, children):
            if child["ci"] == "fail":
                split(half)

    try:
        prs = [m["pr"] for m in rec["members"]]
        if len(prs) > 1 or build(prs)["ci"] == "fail":
            split(prs)
        survivors = [m["pr"] for m in rec["members"] if m["pr"] not in result["culprits"]]
        if survivors:
            remaining = build(survivors, diagnostic=False)
            result["remaining"] = remaining["n"]
            if remaining["ci"] != "pass":
                raise RuntimeError("crew: remaining batch is red; interaction or flake unresolved")
            print("bisect train=%d remaining=%d ci=pass" % (rec["n"], remaining["n"]))
        else:
            print("bisect train=%d remaining=none" % rec["n"])
        if not result["culprits"]:
            print("bisect train=%d culprit=none green-on-retry" % rec["n"])
    finally:
        train_save(state, rec)
        print(train_report(rec))
    return 0


def train_predecessor(args, values, state, repo, slug, rec):
    """A stopped predecessor invalidates the speculative tree; rebuild its successor on current main."""
    if not rec.get("after"):
        return None, rec["base"]
    parent = train_load(state, rec["after"])
    if parent is None or parent.get("ci") == "fail" or (parent.get("stopped") and not parent["stopped"].get("paused")) or (parent.get("closed") and
            len(parent.get("landed", [])) != len(parent["members"])):
        train_close(repo, slug, rec, values)
        rec["stopped"] = {"reason": "predecessor stopped; rebuilt on main"}
        train_save(state, rec)
        args.items = [m["pr"] for m in rec["members"]]
        args.after = None
        print("rebuild train=%d reason=predecessor-stopped" % rec["n"])
        return train_build(args, values, state, repo, slug), None
    if parent.get("stopped", {}).get("paused") or len(parent.get("landed", [])) != len(parent["members"]):
        return None, None
    expected = parent["landed"][-1]["merge"]
    if parent["sha"] != rec["base"] or git(repo, "rev-parse", expected + "^{tree}") != git(
            repo, "rev-parse", rec["base"] + "^{tree}"):
        raise RuntimeError("crew: predecessor did not land the successor's tested base")
    return None, expected


def train_premerge(clone, base, head, verified_base, verified_head):
    """Survey-time pre-filter (#1425): train build's per-member drop checks for one PR on base, without a worktree
    merge (merge-tree in a clone without info/attributes); the drop reason, or None when it would stay a member."""
    if not verified_base and verified_head != head:
        return "no-verified-base"
    tree = subprocess.run(["git", "-C", clone, "-c", "core.attributesFile=" + os.devnull, "merge-tree", "--write-tree",
                           "--no-messages", base, head], capture_output=True, text=True)
    if tree.returncode:
        return "conflict"
    if verified_base and not commands()["content"].identical(clone, verified_base, verified_head, base,
                                                             tree.stdout.split()[0]):
        return "content-different"
    return None


def train_check(args, values, state, repo, slug):
    """Read-only, conservative pre-check. Manual gates remain explicit; land always re-checks §7."""
    poll = commands()["poll"]
    clone = tempfile.mkdtemp(prefix="train-check-")
    try:
        git(repo, "clone", "-q", "--shared", "--bare", repo, clone)
        with contextlib.suppress(FileNotFoundError):
            os.remove(os.path.join(clone, "info", "attributes"))
        return train_check_prs(args, values, state, repo, slug, poll, clone)
    finally:
        shutil.rmtree(clone, ignore_errors=True)


def train_collapsed_drop(poll, slug, state, pr, head):
    """A collapsed train's drop at this head while its survivor is open (#1425): not ready, so the lone-ready
    re-survey sees only the survivor; the survivor's land then makes the conflict real for its merge-up."""
    for path in sorted(glob.glob(os.path.join(state, "trains", "train-*.json"))):
        with open(path) as f:
            rec = json.load(f)
        if rec.get("path") != "direct" or not any(d["pr"] == pr and d.get("head") == head for d in rec["dropped"]):
            continue
        survivor = rec["members"][0]["pr"]
        if poll.gh_json("pr", "view", str(survivor), "-R", slug, "--json", "state")["state"] == "OPEN":
            return "dropped at this head by collapsed train %d while #%d is open" % (rec["n"], survivor)
    return None


def train_check_prs(args, values, state, repo, slug, poll, clone):
    blocked, base = False, fetch(repo, values["repo.default_branch"])
    for pr in args.items:
        view = poll.gh_json("pr", "view", str(pr), "-R", slug, "--json", poll.PR_FIELDS +
                            ",commits,comments,mergeable,body,files,isDraft,baseRefName,closingIssuesReferences")
        head = view["headRefOid"]
        mode = ownership(values)
        results = {"ownership": ("pass", "runtime owns project") if mode == "active" else ("blocked", mode)}
        try:
            lane, lane_why = train_express(args, values, slug, view)
        except RuntimeError as e:
            lane, lane_why = False, str(e)
        verified_base, verified_head = train_verified(poll, view, lane)
        carried = None
        if verified_base and verified_head != head:
            try:
                for ref in (verified_base, verified_head, head):
                    fetch(repo, ref)
                base = fetch(repo, values["repo.default_branch"])
                if commands()["content"].identical(repo, verified_base, verified_head,
                                                    git(repo, "merge-base", base, head), head):
                    carried = verified_head
            except RuntimeError:
                pass
        why, merge_ok, spec = train_gate(poll, values, slug, view, head, state, carried, lane)
        results["state-permission"] = ("blocked", why) if why else ("pass", "current gate snapshot")
        verdict = None
        verdict_head = carried or head
        for review in view["reviews"]:
            markers = [dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
                       for line in poll.CREW_LINE.findall(review["body"])]
            if any(m.get("pass") == "verdict" and m.get("sha") == verdict_head for m in markers):
                verdict = review, markers
        approved = False
        if verdict:
            review, markers = verdict
            expected = values.get("identities.reviewer.gh_user")
            identity = not expected or review.get("author", {}).get("login") == expected
            formal = review.get("state") == "APPROVED" or values.get(
                "backends.review.capabilities.post-verdict", "").startswith("emulated")
            approved = identity and formal and all(any(m.get("role") == "reviewer-validator" and
                m.get("pass") == kind and m.get("sha") == verdict_head and m.get("verdict") == "pass"
                for m in markers) for kind in ("review", "validate", "verdict"))
        results["verdict"] = ("pass", "formal review + validate + verdict at " + verdict_head) if approved else (
            "blocked", "missing formal passing review/validate/verdict at head")
        if lane:  # the express gate replaces the formal approval (express-lane.md, express gate)
            gate = train_selfgate(values, view, verdict_head)
            results["verdict"] = ("pass", "express selfgate pass at " + verdict_head) if gate == "pass" else (
                "blocked", "express selfgate at head: " + gate)
        if express(view):
            results["express"] = ("blocked", "spec change needs owner merge-ok at head") if lane and spec else (
                "pass", "resolved express") if lane else ("blocked", lane_why) if "unreadable" in lane_why else (
                "blocked", "crew lane (%s): drop crew:express" % lane_why)
        required = poll.required_checks(values)
        ci, missing = poll.pr_snapshot(view, required)["ci"], poll.missing_checks(view["statusCheckRollup"], required)
        results["ci"] = ("pass", "checks green at head") if ci == "passed" else (
            "blocked", "checks %s%s" % (ci, "; missing " + ", ".join(missing) if missing else ""))
        tags = {lb["name"] for lb in view["labels"]}
        results["sensitive"] = ("blocked", "owner merge-ok needed at head") if (
            "crew:sensitive" in tags and not merge_ok) else ("pass", "merge-ok present or not sensitive")
        evidence = re.search(r"## Acceptance Evidence\s+(.+?)(?=\n## |\Z)", view["body"], re.S)
        fixes = [p["body"] for p in view["reviews"] if any(
            m.get("role") == "builder" and m.get("pass") in ("fix", "ci-fix") and m.get("sha") in (head, verdict_head)
            for m in (dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
                      for line in poll.CREW_LINE.findall(p["body"])))]
        posts = "\n".join([evidence.group(1) if evidence else "", *fixes])
        # a fence or a code span quotes; only a span holding just one artifact-shaped evidence path cites (#1102)
        cited = re.sub(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", lambda m: m.group(0) if len(m.group(1)) == 1 and re.fullmatch(
            r"evidence/[\w-]*[/.][\w./-]+", m.group(2)) else " ", re.sub(r"^ {0,3}(`{3,}|~{3,}).*?^ {0,3}\1[ \t]*$", " ", posts,
                                                                flags=re.M | re.S))
        paths = {ref for m in re.findall(r"\]\((evidence/[\w./-]+)|`(evidence/[\w./-]+)`|"  # link, image, backtick
                                       r"(?<![\w./-])(evidence/[\w./-]*\.\w+)(?![\w/-])", cited) for ref in m if ref}
        proof = "\n".join([view["body"], *fixes])
        inline = lambda text: re.search(r"(?:```|~~~)sh", text) and re.search(r"(?:```|~~~)text", text)
        if paths:
            tree = poll.gh_json("api", "repos/%s/git/trees/%s?recursive=1" % (slug, head))
            missing = paths - {entry["path"] for entry in tree["tree"]}
            # the body is never edited, so head-bound inline fix proof supersedes its stale paths (verification Q5)
            results["evidence"] = ("manual", "missing artifacts superseded by inline fix proof at head: " + ", ".join(
                sorted(missing)) + "; verify the proof and validation") if missing and inline("\n".join(fixes)) else (
                "blocked", "missing artifacts: " + ", ".join(sorted(missing))) if missing else (
                "manual", "artifacts present; verify validation agrees with each claim")
        elif evidence and re.search(r"\bN/A\b[^\n]*[a-zA-Z]{3}", evidence.group(1)):
            results["evidence"] = ("manual", "verify the stated N/A reason against behaviour")
        elif inline(proof):
            results["evidence"] = ("manual", "inline reproduction; verify applicable evidence policy and validation")
        elif re.search(r"(?<![\w./-])https://github\.com/user-attachments/[\w-]+/[\w.-]+", posts):  # web/mobile media
            results["evidence"] = ("manual", "user-attachments media; verify route or device, viewport or build, and SHA")
        else:
            results["evidence"] = ("blocked", "no evidence artifacts or reasoned N/A")
        mirrored = os.path.isfile(os.path.join(repo, "cli", "mdstack")) and any(  # mdstack's own checkout, by layout
            f["path"] == "docs/protocol.md" or f["path"].startswith("templates/") for f in view["files"])
        mirror_posts = [p for p in view["comments"] if p.get("author", {}).get("login") ==
                        values.get("identities.coordinator.gh_user") and "check-skill-drift.py" in p["body"]]
        results["mirror"] = ("pass", "n/a: profile mirror = none") if values.get(
            "runtime.options.mirror", "live-copy") == "none" else ("blocked", "crew:needs-mirror") if "crew:needs-mirror" in tags else (
            ("manual", "verify coordinator deployed and clean drift check after last touching commit") if mirrored
            and (mirror_posts or values.get("runtime.options.mirror_deferral", "none") not in ("none", ""))
            else ("blocked", "no coordinator mirror/drift record") if mirrored
            else ("pass", "no mirrored paths"))
        results["change"] = ("blocked", "closed, draft or wrong base") if (view["state"] != "OPEN" or
            view["isDraft"] or view["baseRefName"] != values["repo.default_branch"]) else ("pass", "open on default base")
        results["grant-scope"] = ("manual", "verify the recorded owner decision merge_grant names authorizes spec coverage"
                                  if spec else "verify owner authorization and grant scope")
        results["engine"] = ("manual", "verify actual builder engine and diversity re-check")
        results["linkage"] = ("manual", "verify Closes linkage, a release cut's Refs plus Release issue line, or protocol exemption")
        results["runtime"] = ("manual", "verify runtime gates and synthesizer inbox holds")
        results["tested-base"] = ("manual", "train supplies tested-base evidence at serial land")
        try:
            fetch(repo, "pull/%d/head" % pr)
            for ref in (verified_base, verified_head):
                if ref:
                    fetch(repo, ref)
            drop = train_premerge(clone, base, head, verified_base, verified_head)
            collapsed = train_collapsed_drop(poll, slug, state, pr, head)
            cut = release_cut(poll, values, slug, pr)[0]
            behind = cut and subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", base, head]).returncode
        except (RuntimeError, ValueError, KeyError, TypeError) as e:
            drop, collapsed, cut, behind = "unreadable: %s" % e, None, None, None
        # a release cut never lands on a stale merge ref (#1433): it is ready only at a head containing main, where
        # update-branch re-ran release.yml validate
        results["release-cut"] = ("blocked", drop) if drop and drop.startswith("unreadable") else (
            "blocked", "release cut %s behind %s: update-branch so release.yml validate re-runs on current %s; "
            "never land it direct" % (cut, base[:7], values["repo.default_branch"])) if behind else (
            "pass", "release cut %s contains %s" % (cut, base[:7])) if cut else ("pass", "not a release cut")
        results["train-merge"] = ("blocked", collapsed + ": not ready until it lands or closes") if collapsed else (
            "pass", "merges onto %s with the verified patch" % base[:7]) if not drop else (
            "blocked", "%s on %s: route to merge-up before training" % (drop, base[:7]))
        for gate, (status, reason) in results.items():
            print("gate pr=%d sha=%s name=%s status=%s reason=%s" % (pr, head, gate, status, json.dumps(reason)))
            blocked |= status == "blocked"
    return 1 if blocked else 0


def train_wait(args, values, state, repo, slug):
    rec = train_load(state, args.items[0])
    if rec is None or rec.get("closed") or not rec.get("pr"):
        return 1
    rebuilt, _ = train_predecessor(args, values, state, repo, slug, rec)
    if rebuilt is not None:
        return rebuilt
    rec["ci"], rec["ci_links"] = train_wait_ci(slug, rec["pr"], args, commands()["poll"].required_checks(values))
    if rec["ci"] != "pass":
        train_close(repo, slug, rec, values)
    train_save(state, rec)
    rebuilt, _ = train_predecessor(args, values, state, repo, slug, rec)
    if rebuilt is not None:
        return rebuilt
    print("train n=%d ci=%s" % (rec["n"], rec["ci"]))
    for link in rec["ci_links"]:
        print("ci-link %s" % link)
    return 0 if rec["ci"] == "pass" else 1


def train_merge_record(values, rec, i, m, merge, permission, mirror_deferral="none", branch="retained"):
    content = " content=identical carried-from=" + m.get("verified_head", m["head"]) if m.get("verified_base") else ""
    return ("[%s/merge] squashed @ %s → %s (mdstack train %d)\n\n"
            "Land rule: train of %d (ready together).\n\n"
            "- Train: `%s` @ %s (base `%s` %s), member %d of %d, train PR #%d (draft, CI only); CI green: %s. "
            "Tested with main: `%s` held exactly the train's state before this member, so no catch-up.\n"
            "- Passing approval carried from: `pass=%s verdict=pass` at %s.\n- Permission: %s.\n"
            "- %s.\n- Head branch: %s.\n- %s\n\n"
            "<!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a%s -->\n" % (
                values.get("identities.synthesizer.name", "Sam"), m["head"][:7], merge[:7], rec["n"], len(rec["members"]), rec["branch"],
                rec["sha"], values["repo.default_branch"], rec["base"], i, len(rec["members"]), rec["pr"],
                ", ".join(rec["ci_links"]) or "all checks", values["repo.default_branch"], m.get("approval", "verdict"),
                m.get("verified_head", m["head"]), permission, "Mirror: n/a (profile)" if values.get(
                    "runtime.options.mirror", "live-copy") == "none" else "Mirror deferral used: " + mirror_deferral,
                branch, train_report(rec), m["pr"], m["head"], content))


def train_report(rec):
    path = rec.get("path", "train")
    return "train-report n=%d members=%s landed=%s dropped=%s stop=%s path=%s" % (
        rec["n"], ",".join(str(m["pr"]) for m in rec["members"]) or "none",
        ",".join(str(m["pr"]) for m in rec.get("landed", [])) or "none",
        ",".join("%s:%s" % (d["pr"], d["reason"]) for d in rec["dropped"]) or "none",
        re.sub(r"\s+", ":", rec.get("stopped", {}).get("reason", "ci=" + rec["ci"] if rec["ci"] not in ("pass", "none") else
                                             rec["local"] if rec["local"].startswith("fail") else "none")),
        {"direct": "direct:collapsed-to-direct", "none": "none:no-member"}.get(path, path))


def train_transient(reason):
    return bool(re.search(r"\bHTTP\s+(?:429|500|502|503|504)\b", reason, re.I)) or any(s in reason.lower() for s in (
        "github mergeability unknown", "train ci unknown", "github api unknown", "rate limit", "timed out", "timeout", "connection", "could not resolve",
        "temporarily unavailable", "something went wrong", "error fetching", "unexpected end of json"))


class ViewError(RuntimeError):
    """train_view's last failed read; each gateway failure among its reads is already in schedule/errors.jsonl."""


def train_view(poll, slug, pr, args, state, n):
    """The PR with comments and mergeability; GitHub reports UNKNOWN until it has computed it: read up to 10 times.
    Each failed read naming a gateway error is recorded, including reads a later retry recovers from."""
    for attempt in range(10):
        try:
            view = poll.gh_json("pr", "view", str(pr), "-R", slug, "--json", poll.PR_FIELDS + ",headRefName,isCrossRepository,headRepositoryOwner,headRepository,baseRefName,commits,comments,mergeable,closingIssuesReferences,url")
            if view.get("mergeable") != "UNKNOWN":
                return view
            reason = "GitHub mergeability UNKNOWN"
        except RuntimeError as e:
            if not train_transient(str(e)):
                raise
            reason = str(e)
            if GATEWAY.search(reason):
                gateway_error(state, "train-%d" % n, reason)
        except ValueError:
            reason = "GitHub API UNKNOWN: invalid JSON"
        if attempt == 9:
            raise ViewError(reason)
        time.sleep(min(args.interval, 3.0))


def express(view):
    return "crew:express" in {lb["name"] for lb in view.get("labels", [])}


def train_selfgate(values, view, head):
    """The express gate's selfgate result at head (pass or the miss), read by crew-precheck --pass selfgate's check.
    The independent keys are the live view's change number and its one linked issue (#876)."""
    builder = {"gh_user": values.get("identities.builder.gh_user", ""), "name": values.get("identities.builder.name", "")}
    ids = precheck.id_patterns({key[4:]: v for key, v in values.items() if key.startswith("ids.")})
    linked = [str(i["number"]) for i in view.get("closingIssuesReferences", [])]
    return precheck.check_selfgate(dict(view, headRefOid=head), builder, values.get("flavor.selfgate_engine", "different"),
                                   ids, linked[0] if len(linked) == 1 else None, str(view["number"]))


def train_paths(poll, slug, n):
    """The change's paths at head, both rename paths; 100 or more changed files is unreadable (ValueError)."""
    files = poll.gh_json("api", "repos/%s/pulls/%d/files?per_page=100" % (slug, n))
    if len(files) >= 100:
        raise ValueError("100 or more changed files")
    return [p for f in files for p in (f["filename"], f.get("previous_filename")) if p]


def release_cut(poll, values, slug, n):
    """(cut version or None, fragment paths the change adds) from its changed files at head (#1433): a cut adds a new
    version heading to the CHANGELOG. 100 or more changed files, or a CHANGELOG change without its patch, is unreadable
    (ValueError): no reader treats an unclassified change as a non-cut."""
    files = poll.gh_json("api", "repos/%s/pulls/%d/files?per_page=100" % (slug, n))
    if len(files) >= 100:
        raise ValueError("100 or more changed files")
    changelog, fragments = values.get("release.changelog", "CHANGELOG.md"), values.get("release.fragments", "changes/unreleased")
    if any(f["filename"] == changelog and not f.get("patch") for f in files):
        raise ValueError("%s patch unavailable" % changelog)
    cut = next((m.group(1) for f in files if f["filename"] == changelog
                for m in [re.search(r"^\+## \[(\d+\.\d+\.\d+[^\]]*)\]", f["patch"], re.M)] if m), None)
    return cut, [f["filename"] for f in files if f["filename"].startswith(fragments.rstrip("/") + "/")
                 and f.get("status") != "removed"]


def release_hold(poll, values, slug, n):
    """While another change cuts a release, a change adding a CHANGELOG fragment waits for the cut to land (#1433):
    the hold reason, or None. Unreadable holds too."""
    try:
        cut, added = release_cut(poll, values, slug, n)
        if cut or not added:
            return None
        changelog = values.get("release.changelog", "CHANGELOG.md")
        for pr in poll.gh_json("pr", "list", "-R", slug, "--state", "open", "--limit", "100", "--json", "number,files"):
            if pr["number"] != n and any(f["path"] == changelog for f in pr.get("files") or []):
                version = release_cut(poll, values, slug, pr["number"])[0]
                if version:
                    return "release cut #%d (%s) open: fragment changes hold until it lands" % (pr["number"], version)
    except poll.RateLimited:
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        return "release-cut hold unreadable: %s" % e
    return None


def train_spec(poll, values, slug, view):
    """Spec change (protocol §7): crew:spec, or any changed path, both rename paths, matching spec.paths (default
    docs/specs/**). Unreadable raises RuntimeError: no reader treats an unclassified change as non-spec."""
    if "crew:spec" in {lb["name"] for lb in view["labels"]}:
        return True
    try:
        rules = values.get("spec.paths", precheck.config.SPEC_PATHS)
        return bool(precheck.config.spec_matches({"spec": {"paths": rules}}, train_paths(poll, slug, view["number"])))
    except poll.RateLimited:  # poll's caller holds until the reset (#1300)
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        raise RuntimeError("spec classification unreadable: %s" % e)


def spec_scope(values):
    """merge_grant_scope lists spec beside a standing grant; the synthesizer still reads the recorded owner decision
    the grant names before each land (synthesizer brief)."""
    return "spec" in (values.get("runtime.options.merge_grant_scope") or []) and values.get(
        "runtime.options.merge_grant", "none") != "none"


def train_express(args, values, slug, view):
    """Express resolution (express-lane.md, flavor knobs) for a crew:express change: (express?, why not). The newest
    signed coordinator item record on the one linked issue must resolve express (item-flavor.py, issue and PR labels,
    a train_spec match counted as crew:spec) and no changed path, both rename paths, may match a tightening class.
    Unreadable raises RuntimeError."""
    if not express(view):
        return False, "no crew:express"
    poll, n = commands()["poll"], view["number"]
    try:
        profile_ = precheck.config.resolve_profile(args.project, args.org_profile)[0]
        linked = poll.gh_json("pr", "view", str(n), "-R", slug, "--json", "closingIssuesReferences")
        issues = [i["number"] for i in linked["closingIssuesReferences"]]
        if len(issues) != 1:
            raise ValueError("%d linked issues" % len(issues))
        issue = poll.gh_json("issue", "view", str(issues[0]), "-R", slug, "--json", "comments,labels")
        coordinator = values.get("identities.coordinator.gh_user")
        bodies = [c["body"] for c in issue["comments"] if c.get("author", {}).get("login") == coordinator]
        labels = [lb["name"] for lb in issue["labels"] + view["labels"]]
        if train_spec(poll, values, slug, view):  # a spec.paths match is a spec change too: same override rule
            labels.append("crew:spec")
        item = item_flavor.resolve_item(profile_, issues[0], bodies, labels=labels)
        result = precheck.config.class_flavor(profile_, train_paths(poll, slug, n), express=True)
    except poll.RateLimited:  # poll's caller holds until the reset (#1300)
        raise
    except (KeyError, TypeError, ValueError, RuntimeError) as e:
        raise RuntimeError("express resolution unreadable: %s" % e)
    if item["flavor"] != "express":
        return False, "item flavor %s (%s)" % (item["flavor"], item["status"])
    return (True, None) if result["lane"] == "express" else (False, "tightening class rule")


def train_verified(poll, view, lane=False):
    """(base, head) of the latest passing approval: the verdict, or on the express lane the selfgate record."""
    role, name = ("builder", "selfgate") if lane else ("reviewer-validator", "verdict")
    verdicts = [m for r in view["reviews"] for line in poll.CREW_LINE.findall(r["body"])
                for m in [dict(kv.split("=", 1) for kv in line.split() if "=" in kv)]
                if m.get("role") == role and m.get("pass") == name]
    latest = verdicts[-1] if verdicts else {}
    base, head = latest.get("base", ""), latest.get("sha", "")
    if latest.get("verdict") == "pass" and re.fullmatch(r"[0-9a-f]{40}", head):
        return base if re.fullmatch(r"[0-9a-f]{40}", base) else None, head
    return None, None


def landing_stop(poll, slug, view, state):
    posts = list(view["reviews"])
    path = os.path.join(state, "landing-control.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                control = json.load(f)["issue"]
            if not isinstance(control, int) or isinstance(control, bool) or control < 1:
                raise ValueError("invalid control issue")
            read = poll.gh_json("issue", "view", str(control), "-R", slug, "--json", "comments,url")
            foreign = repo_bind.off_repo(slug, [("landing control #%d" % control, read.get("url"))])
            if foreign:
                return "%s; nothing may land" % foreign
            posts += read["comments"]
        except (OSError, ValueError, KeyError, TypeError, RuntimeError, AttributeError):
            return "landing control unreadable; nothing may land"
    stops = poll.landing_steers(posts)["stops"]
    return "open stop-landing: %s" % ", ".join(sorted(set(stops))) if stops else None


def train_gate(poll, values, slug, view, head, state, verified_head=None, lane=False):
    """The §7 gates land re-checks at head right before the squash: (first miss or None, merge-ok at head). The other
    gates are the synthesizer's check right before this call (synthesizer brief)."""
    stop = landing_stop(poll, slug, view, state)
    rereview = merge_ok = False
    rework, reviewer = None, values.get("identities.reviewer.gh_user")
    for r in view["reviews"]:  # in order: a rereview or later changes request at head stays open until a verdict at head
        verdict = False
        for line in poll.CREW_LINE.findall(r["body"]):
            k = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if k.get("sha") in (head, verified_head) and k.get("pass") == "steer":
                rereview = rereview or k.get("cmd") == "rereview"
                rework = rework or ("rework steer" if k.get("cmd") == "rework" else None)
                merge_ok = merge_ok or (k.get("sha") == head and k.get("cmd") == "merge-ok")
            elif k.get("sha") in (head, verified_head) and k.get("pass") == "verdict" and k.get("role") == "reviewer-validator":
                rereview, rework, verdict = False, None, True
        if r.get("state") == "CHANGES_REQUESTED" and not verdict and (
                not reviewer or r.get("author", {}).get("login") == reviewer):  # §7: a formal changes request
            rework = rework or "reviewer CHANGES_REQUESTED review"
    tags = {lb["name"] for lb in view["labels"]} & {"crew:escalated", "crew:changes", "crew:hold"}
    coordinator = values.get("identities.coordinator.name")
    posts = []
    for post in sorted(view["comments"] + view["reviews"],
                       key=lambda p: p.get("submittedAt") or p.get("createdAt") or ""):
        body = post["body"]
        markers = [dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
                   for line in poll.CREW_LINE.findall(body)]
        if any(m.get("role") in ("reviewer-validator", "builder", "synthesizer") for m in markers):
            continue
        if any(m.get("role") == "coordinator" and m.get("pass") == "steer" for m in markers) or (
                coordinator and body.startswith("[%s/" % coordinator)):
            posts.append(body)
    holds = set()
    for body in posts:
        dependencies = set(re.findall(r"hold-until-#(\d+)", body))
        released = any(dict(kv.split("=", 1) for kv in line.split() if "=" in kv).get("cmd") == "hold-release"
                       for line in poll.CREW_LINE.findall(body))
        if released:
            holds.difference_update(dependencies)
        else:
            holds.update(dependencies)
    hold_miss = None
    for x in sorted(holds):
        try:
            dependency = poll.gh_json("issue", "view", x, "-R", slug, "--json", "state,url")
            state = dependency["state"]
        except RuntimeError:
            hold_miss = "unresolved coordinator hold-until-#%s: dependency missing or lookup failed" % x
            break
        hold_miss = repo_bind.off_repo(slug, [("hold-until-#%s dependency" % x, dependency.get("url"))])
        if hold_miss:
            break
        if state == "OPEN":
            hold_miss = "open coordinator hold-until-#%s" % x
            break
    verdict_view = dict(view, headRefOid=verified_head) if verified_head else view
    _, latest_head = train_verified(poll, view, lane)
    selfgate = train_selfgate(values, view, verified_head or head) if lane else None
    approved = (selfgate == "pass" if selfgate else poll.pr_snapshot(verdict_view)["verdict"] == "pass") and (
        not verified_head or verified_head == head or latest_head == verified_head)
    grant, spec, unclassified = values.get("runtime.options.merge_grant", "none"), False, None
    if not merge_ok:
        try:
            spec = train_spec(poll, values, slug, view)
        except RuntimeError as e:
            unclassified = str(e)
    sensitive = any(lb["name"] == "crew:sensitive" for lb in view["labels"])
    release = release_hold(poll, values, slug, view["number"])
    foreign = repo_bind.off_repo(slug, [("change #%d's verdict and permission read" % view["number"], view.get("url"))])
    why = (foreign if foreign else stop if stop else
           "PR is %s" % view["state"] if view["state"] != "OPEN" else
           "head changed: %s, tested %s" % (view["headRefOid"], head) if view["headRefOid"] != head else
           "state tag %s" % ", ".join(sorted(tags)) if tags else
           "no express selfgate pass at head: %s" % selfgate if selfgate not in (None, "pass") else
           "no approval verdict at head" if not approved else
           "later changes request at head: %s" % rework if rework else
           "open rereview at head" if rereview else
           hold_miss if hold_miss else
           "crew:sensitive needs owner merge-ok at head" if sensitive and not merge_ok else
           unclassified if unclassified else
           "express spec change needs owner merge-ok at head" if selfgate and spec else
           "spec change needs owner merge-ok at head: merge_grant_scope does not cover spec" if spec and not spec_scope(values) else
           "no merge permission: no merge-ok at head and merge_grant is none" if not merge_ok and grant == "none" else
           release if release else
           "not mergeable: GitHub reports %s" % view.get("mergeable") if view.get("mergeable") != "MERGEABLE" else None)
    return why, merge_ok, spec


def train_land(args, values, state, repo, slug):
    """Land one member, the next in order; the synthesizer re-runs the whole §7 check at its head right before."""
    (n, pr), main, poll = args.items, values["repo.default_branch"], commands()["poll"]
    mirror_deferral = values.get("runtime.options.mirror_deferral", "none") if args.mirror_deferred else "none"
    if args.mirror_deferred and mirror_deferral == "none":
        print("crew: no profile mirror deferral; nothing landed")
        return 2
    rec = train_load(state, n)
    if rec is None:
        return 1
    if rec["ci"] != "pass" or rec.get("closed"):
        print("crew: train %d is %s; nothing landed" % (n, "CI " + rec["ci"] if rec["ci"] != "pass" else "closed"))
        return 1
    rebuilt, predecessor_base = train_predecessor(args, values, state, repo, slug, rec)
    if rebuilt is not None:
        return rebuilt
    if predecessor_base is None:
        print("crew: predecessor has not finished; nothing landed")
        return 1
    landed = rec.setdefault("landed", [])
    pending = rec.get("pending_record")
    if pending:
        if not require_ownership(values, "write"):
            return 1
        posted = subprocess.run(["gh", "pr", "review", str(pending["pr"]), "--comment", "-R", slug,
                                 "--body", pending["body"]], capture_output=True)
        if posted.returncode:
            print("paused pr=%d reason=merge record still pending" % pending["pr"])
            print(train_report(rec))
            return 1
        rec.pop("pending_record")
        rec.pop("stopped", None)
        train_save(state, rec)
        if len(landed) == len(rec["members"]):
            tail = train_close(repo, slug, rec, values)
            train_save(state, rec)
            train_route(args, values, state, repo, slug, rec)
            print("train n=%d landed=%d/%d %s" % (n, len(landed), len(rec["members"]), tail))
            print(train_report(rec))
            return 0
    i, m = len(landed) + 1, rec["members"][len(landed)]
    if pr != m["pr"]:
        print("crew: train %d lands #%d next, not #%d; nothing landed" % (n, m["pr"], pr))
        return 2
    expected, why, merge_ok, spec, recorded = landed[-1]["merge"] if landed else predecessor_base, None, False, False, False
    rec.pop("stopped", None)
    try:
        checks = subprocess.run(["gh", "pr", "checks", str(rec["pr"]), "-R", slug, "--json", "name,bucket"],
                                capture_output=True, text=True)
        if checks.returncode not in (0, 1, 8):
            raise RuntimeError(checks.stderr.strip())
        try:
            observed = json.loads(checks.stdout or "[]")
            buckets = {c["bucket"] for c in observed}
        except ValueError:
            raise RuntimeError("train CI UNKNOWN: invalid API JSON")
        missing = poll.missing_checks(observed, poll.required_checks(values))
        if buckets & {"fail", "cancel"}:
            rec["ci"] = "fail"
            why = "train CI red"
        elif not buckets or "pending" in buckets:
            raise RuntimeError("train CI UNKNOWN or pending")
        elif missing:  # the live baseline at land, even one set after the build (#1536)
            raise RuntimeError("train CI UNKNOWN or pending; missing " + ", ".join(missing))
        cur = fetch(repo, main)
        if fetch(repo, rec["branch"]) != rec["sha"]:
            why = "train branch moved"
        elif cur != expected:
            why = "main moved: %s, train state %s" % (cur, expected)
        elif (m.get("verified_head", m["head"]) != m["head"] and not m.get("verified_base")) or (
                m.get("verified_base") and not m.get("updated_base")):
            why = "no-verified-base: request fresh verdict and rebuild train"
        elif m.get("verified_base") and not commands()["content"].identical(
                repo, m["verified_base"], m.get("verified_head", m["head"]), m["updated_base"], m["step"]):
            why = "content-different: route to builder for delta re-review"
            rec["dropped"].append({"pr": pr, "head": m["head"], "reason": "content-different"})
        elif not why:
            view = train_view(poll, slug, pr, args, state, n)
            why, merge_ok, spec = train_gate(poll, values, slug, view, m["head"], state, m.get("verified_head"),
                                       train_express(args, values, slug, view)[0])
        if not why:
            if not require_ownership(values, "land"):
                return 1
            # eligible same-repo heads are deleted by the merge itself, never by a later route DELETE (#395)
            keep = commands()["route"].branch_retained(values, view, main)
            r = subprocess.run(["gh", "pr", "merge", str(pr), "-R", slug, "--squash", "--match-head-commit", m["head"]]
                               + ([] if keep else ["--delete-branch"]), capture_output=True, text=True)
            branch = "retained (%s)" % keep if keep else "deleted at merge"
            if r.returncode and not keep and poll.gh_json("pr", "view", str(pr), "-R", slug, "--json", "state")["state"] == "MERGED":
                branch = "delete failed (%s)" % (r.stderr.strip() or "exit %d" % r.returncode)
            elif r.returncode:
                why = "merge refused: " + r.stderr.strip()
            print("branch pr=%d %s" % (pr, branch))
        if not why:  # landed: the squash must sit on the tested state and reproduce the train step's tree
            new = fetch(repo, main)
            landed.append({"pr": pr, "head": m["head"], "merge": new})
            tree = [git(repo, "rev-parse", c + "^{tree}") for c in (new, m["step"])]
            grant = 'merge_grant = "%s"' % values.get("runtime.options.merge_grant", "none")
            if spec:  # the grant source and its spec coverage (protocol §7 spec change, Records)
                grant += " with merge_grant_scope = %s: covered a spec change" % json.dumps(
                    values["runtime.options.merge_grant_scope"])
            if git(repo, "rev-parse", new + "^") != expected or tree[0] != tree[1]:
                why = "landed as %s, not the train's tested state; merge record not posted" % new
            else:
                body = train_merge_record(values, rec, i, m, new, "owner merge-ok at head" if merge_ok else grant, mirror_deferral,
                                          branch)
                if not require_ownership(values, "write"):
                    rec["pending_record"] = {"pr": pr, "body": body}
                    train_save(state, rec)
                    return 1
                posted = subprocess.run(["gh", "pr", "review", str(pr), "--comment", "-R", slug, "--body", body],
                                        capture_output=True, text=True)
                if posted.returncode:
                    rec["pending_record"] = {"pr": pr, "body": body}
                    why = "merge record pending: " + posted.stderr.strip()
    except RuntimeError as e:
        why, recorded = str(e), isinstance(e, ViewError)
    if landed and landed[-1]["pr"] == pr:
        print("landed pr=%d head=%s merge=%s" % (pr, m["head"], landed[-1]["merge"]))
    if why:
        if GATEWAY.search(why) and not recorded:
            gateway_error(state, "train-%d" % n, why)
        paused = train_transient(why) and bool(rec.get("pending_record") or not (landed and landed[-1]["pr"] == pr))
        rec["stopped"] = {"pr": pr, "reason": why, "paused": paused}
        print("%s pr=%d reason=%s" % ("paused" if paused else "stopped", pr, why))
    done = (why and not rec["stopped"]["paused"]) or (not why and len(landed) == len(rec["members"]))
    tail = train_close(repo, slug, rec, values) if done else "record-pending" if rec.get("pending_record") else "next=%d" % rec["members"][len(landed)]["pr"]
    train_save(state, rec)
    if done:
        train_route(args, values, state, repo, slug, rec)
    print("train n=%d landed=%d/%d %s" % (n, len(landed), len(rec["members"]), tail))
    print(train_report(rec))
    return 1 if why else 0


def train_close_cmd(args, values, state, repo, slug):
    """End a train early (the synthesizer's own §7 check failed for the next member): close its PR, delete its branch."""
    delegated = delegation_load(state, args.items[0])
    if delegated and not delegated.get("closed"):  # a delegated build that never ran or died stays unbuilt (#1391)
        delegated["closed"] = True
        delegation_save(state, delegated)
        if not os.path.exists(train_path(state, args.items[0])):
            print("train n=%d delegation closed before build" % args.items[0])
            return 0
    rec = train_load(state, args.items[0])
    if rec is None:
        return 1
    rec.setdefault("stopped", {"reason": "closed by synthesizer"})
    tail = train_close(repo, slug, rec, values)
    train_save(state, rec)
    train_route(args, values, state, repo, slug, rec)
    print("train n=%d landed=%d/%d %s" % (rec["n"], len(rec.get("landed", [])), len(rec["members"]), tail))
    print(train_report(rec))
    return 0


def register(sub):
    p = sub.add_parser("train", help="merge train: CI once on main + approved PRs, then land them in order")
    p.add_argument("action", choices=["build", "delegate", "wait", "check", "land", "close", "route", "bisect"])
    p.add_argument("items", nargs="*", type=repo_bind.member,
                   help="build: PR numbers in landing order; land: the train number and its next PR; close/route/bisect: the number")
    p.add_argument("--after", type=int, help="build on this predecessor train's tested tip")
    p.add_argument("--train", type=int, help="build: the delegated train N, its members, heads and base (#1391)")
    p.add_argument("--no-wait", action="store_true", help="push the train and return while CI is pending")
    p.add_argument("--local", action="store_true", help="build: opt in to the local full suite before opening the CI train")
    p.add_argument("--mirror-deferred", action="store_true",
                   help="land: record the profile mirror deferral after the synthesizer checks its scope")
    p.add_argument("--grace", type=float, default=20.0, help="seconds after the train PR opens before reading CI")
    p.add_argument("--interval", type=float, default=20.0, help="seconds between CI reads")
    p.add_argument("--timeout", type=float, default=1800.0, help="seconds to wait for CI after the grace period")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def recorded(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        return "unreadable"


def train_foreign(args, values, state, slug, qualified):
    """Why this action would act outside the selected repo, or None: one comparison over every train record and
    delegation it names, every member qualifier and, for build and delegate, each member's URL read from the backend."""
    numbers = [n for n in (args.train, args.after) if n]
    numbers += args.items[:1] if args.action in ("wait", "land", "close", "route", "bisect") else []
    records = [("train %d %s" % (n, kind), recorded(path(state, n))) for n in numbers
               for kind, path in (("record", train_path), ("delegation", delegation_path))]
    members = list(args.items) if args.action in ("build", "delegate") else []
    if args.train and isinstance(records[1][1], dict):
        members = [m.get("pr") for m in records[1][1].get("members", []) if isinstance(m, dict)]
    urls = []
    for pr in dict.fromkeys(members):
        try:
            urls.append(("member #%s" % pr, commands()["poll"].gh_json("pr", "view", str(pr), "-R", slug, "--json",
                                                                       "url").get("url")))
        except (RuntimeError, ValueError, AttributeError) as e:
            return "member #%s's repo is unreadable (%s)" % (pr, e)
    return repo_bind.foreign(repo_bind.context(args.project, values), "team.name" in values, records=records,
                             urls=urls, repos=[("%s#%d" % (q, n), q) for q, n in qualified])


def run(args):
    qualified, args.items = args.items, [n for _, n in args.items]
    many = len(args.items) or -1
    if args.train and (args.action != "build" or args.items or args.after):
        print("crew: train build --train N takes no PRs or --after")
        return 2
    if not args.train and len(args.items) != {"build": many, "delegate": many, "check": many, "wait": 1, "land": 2, "close": 1, "route": 1, "bisect": 1}[args.action]:
        print("crew: train %s takes %s" % (args.action, "<n> <pr>" if args.action == "land" else "PR..." if many < 0 else "<n>"))
        return 2
    values, _, state = profile(args, *(("worktree_root",) if args.action in ("build", "bisect") else ()))
    if args.action in ("build", "bisect") and values.get("strategy.update_from_base") == "rebase":
        # Trains stack merge commits; a rebase backend lands one change at a time (docs/interfaces.md#trains).
        print('crew: refusing train %s: the change backend declares strategy.update_from_base = "rebase", and a '
              "merge train stacks merge commits; land ready PRs one at a time after the declared update" % args.action)
        return 1
    if args.action in ("build", "bisect") and values.get("land.tests_against_tip"):
        print("crew: refusing train %s: the change backend declares land.tests_against_tip, so its land check tests "
              "each patch on the tip; land each PR alone with mdstack land request" % args.action)
        return 1
    slug = "%s/%s" % (values["repo.owner"], values["repo.name"])
    problem = train_foreign(args, values, state, slug, qualified)
    if problem:  # before any clone, branch, record, push, CI, merge or cleanup (team §9.5)
        print("crew: refusing train %s: %s; nothing written" % (args.action, problem))
        return 1
    try:
        repo = git(checkout(values, args.project), "rev-parse", "--show-toplevel")
        if args.action == "route":
            rec = train_load(state, args.items[0])
            if rec is None:
                return 1
            train_route(args, values, state, repo, slug, rec)
            print(train_report(rec))
            return 0
        return {"build": train_build, "delegate": train_delegate, "wait": train_wait, "check": train_check, "land": train_land, "close": train_close_cmd, "bisect": train_bisect}[args.action](
            args, values, state, repo, slug)
    except RuntimeError as e:
        print(e)
        return 1
