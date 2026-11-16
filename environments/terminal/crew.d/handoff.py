"""`mdstack handoff` posts owner handoff commands, builds the manifest and the incoming side's plan (docs/handoff.md).

Usage: mdstack handoff to RUNTIME_ID [--mode drain|stop] [--deadline MINUTES] [--dry-run] --signature TEXT --project FILE
       mdstack handoff abort [--dry-run] --signature TEXT --project FILE
       mdstack handoff takeover RUNTIME_ID [--dry-run] --signature TEXT --project FILE
       mdstack handoff manifest --project FILE [--org-profile FILE] [--mode drain|stop] [--post --signature TEXT]
       mdstack handoff reconcile --project FILE [--org-profile FILE]
       mdstack handoff ack [--rules-confirmed] [--dry-run] --signature TEXT --project FILE
       mdstack handoff stopped [--foreground] [--dry-run] --signature TEXT --project FILE
       mdstack handoff lift [--owner-confirmed] [--keep ITEM]... --project FILE

`to`, `abort` and `takeover` are the owner's chat commands (protocol §9): each re-reads the record, refuses an illegal
transition and posts the signed `draining`, `aborted` or `takeover` state. In drain mode `to` writes
`asks/handoff.json` so the watcher wakes the coordinator at the deadline (delete it once the drain ends; `abort` does).

`manifest` reads this runtime's open handoff on the control item and the live open items, groups them into
dependency-closed sets and fills templates/handoff-manifest.md: references only, secret-scanned, one post. With
--post it re-reads the record before each attempt and posts `offered` only while no post for that handoff id
exists, so a retry is never a second handoff; once acked it posts nothing. `reconcile` is the incoming side's
read-only plan for the offered manifest (docs/handoff.md reconcile table): per set `adopt`, `hold` (a head or stage
tag moved since the manifest) or `skip` (all claimed here), then `gone` items, `rerun` for kept or stopped runs and
for `stale` pass markers posted in transit, `missed` crew items and `rule` differences.

`ack` (incoming) re-reads, reconciles and posts `acked` with the plan once per handoff id (a takeover's post carries
the manifest from live state); a rule difference refuses until the owner answers (`--rules-confirmed`). `stopped`
(outgoing, after the ack) is the whole prompt stop: it re-runs itself detached from the crew session (log
`handoff-stop.log`), disarms the watcher, runs `mdstack down` keeping every worktree (retrying while the land lock is
held), and posts `stopped` with the kept worktree names once no watcher and no session remain. `--foreground` runs
those steps in this process, for a shell outside the session. `lift` (incoming, after the ack)
removes `crew:hold` from the manifest's `holds_added` only once `stopped` is posted, the owner confirms, or the
outgoing release reads the record (v3.0.0, #210); `--keep` leaves a diverged set's hold.
"""
import contextlib
import datetime
import glob
import json
import os
import re
import signal
import subprocess
import sys
import time
from argparse import Namespace

from crew_shared import CREW_BIN, HERE, commands, crew_render, ownership_module, post_title, profile, runs, tmux

LIMIT = 65536  # GitHub's comment size
LINKS = r"(?i:\b(?:depends on|closes|fixes|resolves)) (?:#(?P<n>\d+)%s)"
SHA = re.compile(r"[0-9a-f]{40}")
ID_DEFAULT = crew_render.crew_config.ID_DEFAULT  # without a declared item pattern, links are `#<digits>` only
STAGES = ("ready", "in-review", "changes", "approved", "hold", "escalated", "needs-md")
RUNTIME_ID = r"[a-z][a-z0-9-]*@[a-z0-9-]{1,63}"
DOWN_RETRY, DOWN_TRIES = 30, 60  # seconds between mdstack down attempts while the land lock is held; 30 minutes in all
GUARDED = (3, 0, 0)  # the first release whose guards read the ownership record (#210)
TEMPLATE = os.path.join(os.path.dirname(HERE), "templates", "handoff-manifest.md")


def register(sub):
    p = sub.add_parser("handoff")
    p.add_argument("action", choices=["to", "abort", "takeover", "manifest", "reconcile", "ack", "stopped", "lift"])
    p.add_argument("runtime", nargs="?", help="target runtime id for to; outgoing runtime id for takeover")
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--mode", choices=["drain", "stop"], default="drain")
    p.add_argument("--post", action="store_true")
    p.add_argument("--signature", default="")
    p.add_argument("--deadline", type=int, default=30, help="drain deadline in minutes (default 30)")
    p.add_argument("--dry-run", action="store_true", help="to/abort/takeover/ack/stopped: print the post instead")
    p.add_argument("--rules-confirmed", action="store_true", help="ack: the owner answered the rule differences")
    p.add_argument("--owner-confirmed", action="store_true", help="lift: the owner confirmed the old wake sources are gone")
    p.add_argument("--foreground", action="store_true", help="stopped: tear down in this process, not detached")
    p.add_argument("--keep", action="append", default=[], help="lift: leave crew:hold on this item (12, #12 or OPS-12)")


def gh(values, path):
    url = "repos/%s/%s/%s" % (values["repo.owner"], values["repo.name"], path)
    r = subprocess.run(["gh", "api", "--paginate", "--slurp", url], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("crew: handoff: gh api %s failed" % path)
    pages = json.loads(r.stdout)
    return [x for page in pages for x in page] if isinstance(pages[0], list) else pages[0]


def record(values):
    """Trusted control-item posts through the read-item binding, and the owner function over them."""
    trusted = ownership_module.trusted(values)
    try:
        comments = [c for c in ownership_module.read_posts(values) if c["author"] in trusted]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RuntimeError(failed(values) if values["backends.markers.name"] == "github" else
                           "crew: handoff: read-item failed (%s)" % e) from e
    return comments, ownership_module.owner_record(comments, trusted)


def failed(values):
    return "crew: handoff: gh api issues/%s/comments failed" % values["repo.control_item"]


def write(values, body):
    """Post on the control item through the write-item binding: None when posted, else why the post is uncertain."""
    try:
        if ownership_module.write_item(values, body):
            return None
    except (OSError, ValueError, KeyError) as e:
        raise RuntimeError("crew: handoff: write-item unbound (%s); nothing posted" % e) from e
    return failed(values) if values["backends.markers.name"] == "github" else "crew: handoff: write-item failed"


def op(values, name, **fill):
    """Run a recorded live-read binding (`name` is concern.operation) with `fill` placeholders; its stdout."""
    try:
        argv = ownership_module.bound(values, name, {"<%s>" % k: v for k, v in fill.items()})
    except (OSError, KeyError, ValueError) as e:
        raise RuntimeError("crew: handoff: %s unbound (%s); run mdstack up with it mapped" % (name, e)) from e
    r = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("crew: handoff: %s failed" % name)
    return r.stdout


def array(values, name, **fill):
    """A JSON array operation output (pages flattened) of objects."""
    try:
        data = json.loads(op(values, name, **fill))
    except ValueError as e:
        raise RuntimeError("crew: handoff: %s printed no JSON" % name) from e
    flat = [x for page in data for x in page] if isinstance(data, list) and data and all(
        isinstance(p, list) for p in data) else data
    if not isinstance(flat, list) or not all(isinstance(x, dict) for x in flat):
        raise RuntimeError("crew: handoff: %s printed no array of objects" % name)
    return flat


def head(values, name, **fill):
    sha = op(values, name, **fill).strip()
    if not SHA.fullmatch(sha):
        raise RuntimeError("crew: handoff: %s printed no full head SHA" % name)
    return sha


def branch_head(values):
    """The default-branch head SHA: `commits/<branch>` on GitHub, else `change.read-branch-head`."""
    branch = values["repo.default_branch"]
    if ownership_module.native(values):
        return head(values, "change.read-branch-head", branch=branch)
    return gh(values, "commits/" + branch)["sha"]


def ident(x):
    return str(x["id"] if "id" in x else x["number"])


def ref(n):
    """A manifest reference: `#<n>` for a number, as today, else the native id itself."""
    return "#" + n if n.isdigit() else n


def unref(r):
    return r[1:] if r.startswith("#") else r


def order(n):
    return len(n), n  # numbers in numeric order, as today


def native_id(values, key="ids.item", group="id"):
    """`|(?P<id>...)`: the declared item (or change) pattern as an alternative to `#<digits>`, or nothing without one."""
    pattern = values.get(key, ID_DEFAULT) if ownership_module.native(values) else ID_DEFAULT
    return "|(?P<%s>(?:%s))" % (group, pattern) if pattern != ID_DEFAULT else ""


def links(values, body):
    return [m.group("n") or m.group("id") for m in re.finditer(LINKS % native_id(values), body or "")]


def first_ref(values, text, claim=False):
    """The first reference in a run record's item (`#<digits>`, a native item id or a native change id) or a claim
    name (digits or a native item id right after `issue`, digits or a native change id right after `pr`)."""
    if claim:
        m = re.search(r"issue(?:(?P<n>\d+)%s)|pr(?:(?P<p>\d+)%s)" % (
            native_id(values), native_id(values, "ids.change", "c")), text)
    else:
        m = re.search(r"#(?P<n>\d+)%s%s" % (native_id(values), native_id(values, "ids.change", "c")), text)
    return m and next((g for g in m.groupdict().values() if g), None)


def item(i):
    return {"labels": [lb if isinstance(lb, str) else lb["name"] for lb in i.get("labels") or []],
            "assignees": i.get("assignees") or [], "milestone": i.get("milestone"), "body": i.get("body")}


def markers(comments):
    """(post, fields) for each handoff marker in post order; record() already dropped untrusted posts."""
    for c in comments:
        for line in ownership_module.LINE.findall(c["body"] or ""):
            m = dict(kv.split("=", 1) for kv in line.split() if "=" in kv)
            if m.get("pass") == "handoff" and m.get("role") == "coordinator":
                yield c, m


def posted(comments, hid, state):
    return next((c for c, m in markers(comments) if m.get("handoff") == hid and m.get("state") == state), None)


def block(comment):
    found = re.search(r"```json\n(.*?)\n```", (comment or {}).get("body") or "", re.S)
    return json.loads(found.group(1)) if found else None


def last_ack(comments, owner, frm=None):
    """The ack that made `owner` the owning runtime (optionally from `frm`), or None."""
    acks = [m for _, m in markers(comments) if m.get("state") == "acked" and m.get("to") == owner]
    return next((m for m in reversed(acks) if frm in (None, m.get("from"))), None)


def open_items(values):
    """Open items by string id: `tracker.list-items` (open only) for a non-GitHub install, else `gh api`."""
    if ownership_module.native(values):
        return {ident(i): item(i) for i in array(values, "tracker.list-items")
                if str(i.get("state", "open")).lower() == "open"}
    return {str(i["number"]): item(i) for i in gh(values, "issues?state=open&per_page=100")}


def live(values):
    """Open items, open change heads and native change ids by item, dependency-closed sets of crew items, and the open
    items outside every set. Ids are strings. A non-GitHub install reads `tracker.list-items`, `change.list-open` and
    `change.read-head`; a change belongs to the first open item it links."""
    changes, items = {}, open_items(values)
    if ownership_module.native(values):
        heads = {}
        for c in array(values, "change.list-open"):
            linked = [str(x) for x in c.get("items", [])] + [ident(x) for x in c.get("closingIssuesReferences", [])]
            n = next((n for n in linked if n in items), None)
            if n is not None and n not in changes:
                changes[n] = ident(c)
                heads[n] = head(values, "change.read-head", n=changes[n])
    else:
        heads = {str(p["number"]): p["head"]["sha"] for p in gh(values, "pulls?state=open&per_page=100")}
    edges = {n: {m for m in links(values, i["body"]) if m in items} for n, i in items.items()}
    for n in items:
        for m in edges[n]:
            edges[m].add(n)
    seen, sets = set(), []
    for n in sorted(items, key=order):
        if n not in seen and (n in heads or any(lb.startswith("crew:") for lb in items[n]["labels"])):
            group, todo = set(), [n]
            while todo:
                m = todo.pop()
                if m not in group:
                    group.add(m)
                    todo += edges[m]
            seen |= group
            sets.append(sorted(group, key=order))
    return items, heads, changes, sets, [n for n in sorted(items, key=order) if n not in seen]


def milestone(m):
    return (m.get("html_url") or m.get("url") or "none") if isinstance(m, dict) else (m or "none")


def cells(s, key, width):
    return " ".join(str(i[key] or "-")[:width] for i in s["items"])


def manifest(values, state, opened, mode, signature):
    items, heads, changes, sets, backlog = live(values)
    by_change = {c: n for n, c in changes.items()}
    runs = {}
    for path in sorted(glob.glob(os.path.join(state, "runs", "*.json"))):
        with open(path) as f:
            r = json.load(f)
        n = first_ref(values, r["item"])  # the first reference names the item: "issue #10, PR #21" is #10
        runs.setdefault(by_change.get(n, n), []).append(
            {"role": r["role"], "pass": r["pass"], "end": "kept", "worktree": os.path.basename(r["worktree"])})
    branch = values["repo.default_branch"]
    sha = branch_head(values)
    version = os.path.join(os.path.dirname(HERE), "VERSION")
    data = {"schema": "crew-handoff/1", "handoff": opened["handoff"], "from": opened["from"], "to": opened["to"],
            "repo": "%s/%s" % (values["repo.owner"], values["repo.name"]), "mode": mode,
            "eng_crew_version": open(version).read().strip() if os.path.exists(version) else "unreleased",
            "default_branch": {"name": branch, "sha": sha}, "sets": [], "holds_added": [],
            "rules": [{"key": k, "value": v} for k, v in sorted(values.items())
                      if k.startswith("flavor.") or k == "runtime.options.merge_grant"],
            "backlog": [ref(n) for n in backlog]}
    for k, group in enumerate(sets, 1):
        data["sets"].append({"id": "s%d" % k, "order": k, "items": [dict({
            "item": ref(n), "pr": n in heads, "head": heads.get(n),
            "stage": stage(items[n]),
            "labels": sorted(items[n]["labels"]),
            "depends_on": [ref(m) for m in links(values, items[n]["body"])],
            "runs": runs.get(n, [])}, **({"change": changes[n]} if n in changes else {})) for n in group]})
    with open(TEMPLATE) as f:
        template = f.read()
    row = next(line for line in template.splitlines() if "<set>" in line)  # repeated once per set
    template = template.replace(row, "\n".join(
        row.replace("<set>", s["id"]).replace("<set-items>", cells(s, "item", 9)).replace(
            "<set-stages>", cells(s, "stage", 9)).replace("<set-heads>", cells(s, "head", 7)) for s in data["sets"]))
    for shrink in (False, True):
        if shrink:  # one link per milestone instead; an open item is never dropped
            data["backlog"] = sorted({milestone(items[n]["milestone"]) for n in backlog})
        fill = {"CoordinatorBot": values["identities.coordinator.name"], "handoff-id": opened["handoff"],
                "from": opened["from"], "to": opened["to"], "items": str(sum(map(len, sets))),
                "sets": str(len(sets)), "mode": mode, "backlog": str(len(backlog)),
                "default-branch-head-sha": sha, "manifest": json.dumps(data, indent=1), "signature": signature}
        post = re.sub(r"<([A-Za-z-]+)>", lambda m: fill.get(m.group(1), m.group(0)), template.replace(
            "<title:coordinator/handoff>", post_title(values, "coordinator", "handoff")))
        if len(post) <= LIMIT:
            break
    else:
        raise RuntimeError("crew: handoff: manifest exceeds %d characters" % LIMIT)
    reasons = crew_render.crew_config.token_reasons(post)
    if reasons:
        raise RuntimeError("crew: handoff: secret scan refused the manifest: " + "; ".join(reasons))
    return post


def run(args):
    try:
        return handoff(args)
    except RuntimeError as e:  # a failed read or a refused manifest; nothing was posted
        print(e)
        return 1


def handoff(args):
    values, session, state = profile(args)
    runtime = values["runtime.name"] + "@" + values.get("runtime.instance", "")
    if not values.get("repo.control_item") or args.post and not args.signature:
        print("crew: handoff: needs repo.control_item, and --signature with --post")
        return 1
    if args.action in ("to", "abort", "takeover"):
        return command(values, state, runtime, args)
    if args.action == "reconcile":
        return reconcile(values, state, runtime)
    if args.action in ("ack", "stopped") and not args.signature and not args.dry_run:
        print("crew: handoff: %s needs --signature" % args.action)
        return 1
    if args.action == "ack":
        return ack(values, state, runtime, args)
    if args.action == "stopped":
        return stopped(values, state, session, runtime, args)
    if args.action == "lift":
        return lift(values, runtime, args)
    for attempt in range(1, 4):
        _, (owner, phase, opened) = record(values)
        if opened is None and owner not in (None, runtime):
            print("crew: handoff: owned by %s; nothing to post" % owner)
            return 0
        if opened is None or opened["from"] != runtime or phase == "takeover":
            print("crew: handoff: no open handoff from %s" % runtime)
            return 1
        if phase == "offered":
            print("crew: handoff: %s already offered; waiting for the ack" % opened["handoff"])
            return 0
        post = manifest(values, state, opened, args.mode, args.signature)
        if not args.post:
            print(post)
            return 0
        error = write(values, post)
        if error:
            print("%s; re-reading (attempt %d)" % (error, attempt))
    return 1


def plan(values, state, comments, opened, phase):
    """The reconcile table's lines for this open handoff; reads only."""
    data = block(posted(comments, opened["handoff"], "offered"))
    if phase == "takeover" and data is None:  # nothing offered: every live set is missed and adopted
        data = {"schema": "crew-handoff/1", "sets": []}
    if not data or data.get("schema") != "crew-handoff/1":
        raise RuntimeError("crew: handoff: no crew-handoff/1 manifest for %s; ask the owner" % opened["handoff"])
    opener = posted(comments, opened["handoff"], "takeover" if phase == "takeover" else "offered")
    items, heads, changes, sets, _ = live(values)
    claims = os.listdir(os.path.join(state, "claims")) if os.path.isdir(os.path.join(state, "claims")) else []
    mine = {first_ref(values, c, claim=True) for c in claims} - {None}
    out, extra, listed = [], [], set()
    for s in data["sets"]:
        open_ = [i for i in s["items"] if unref(i["item"]) in items]
        listed |= {unref(i["item"]) for i in s["items"]}
        extra += ["gone %s close-out" % i["item"] for i in s["items"] if i not in open_]
        moved = [i["item"] for i in open_ if i["pr"] and heads.get(unref(i["item"]), i["head"]) != i["head"]]
        tags = [i["item"] for i in open_ if stage(items[unref(i["item"])]) != i["stage"]]
        verb = "skip" if all(unref(i["item"]) in mine or i.get("change") in mine for i in open_) else \
            "hold" if moved or tags else "adopt"
        why = (["moved:", *moved] if moved else []) + (["tags:", *tags] if tags else []) if verb == "hold" else []
        out.append(" ".join([s["id"], verb, *(i["item"] for i in open_), *why]))
        extra += ["rerun %s %s %s %s %s" % (i["item"], r["role"], r["pass"], r["end"], r["worktree"])
                  for i in open_ for r in i["runs"] if r["end"] in ("stopped", "kept")]
    since = (opener or {}).get("created")
    for n in sorted(heads, key=order) if since else []:  # a pass marker posted in transit satisfies nothing (handoff.md)
        for at, body in change_posts(values, n, changes):
            for line in ownership_module.LINE.findall(body or "") if at and at > since else []:
                p = dict(kv.split("=", 1) for kv in line.split() if "=" in kv).get("pass")
                if p and p != "handoff":
                    extra.append("stale %s pass=%s rerun at head" % (ref(n), p))
    extra += ["missed %s adopt" % ref(n) for n in sorted({n for group in sets for n in group} - listed, key=order)]
    extra += ["rule %s %s != %s" % (r["key"], r["value"], values.get(r["key"]))
              for r in data.get("rules", []) if values.get(r["key"]) != r["value"]]
    return out + extra


def change_posts(values, n, changes):
    """(time, body) of every post on item n's open change; `markers.read` for a native change, refused unreadable."""
    if n not in changes:
        return [(r.get("submitted_at"), r.get("body")) for r in gh(values, "pulls/%s/reviews" % n)] + \
            [(c.get("created_at"), c.get("body")) for c in gh(values, "issues/%s/comments" % n)]
    try:
        return [(p["created"], p["body"]) for p in ownership_module.posts(op(values, "markers.read", n=changes[n]))]
    except (ValueError, KeyError, TypeError) as e:
        raise RuntimeError("crew: handoff: markers.read unreadable for %s; reconcile refused" % ref(n)) from e


def stage(item):
    return next((lb[5:] for lb in item["labels"] if lb[5:] in STAGES), "build" if item["assignees"] else "none")


def reconcile(values, state, runtime):
    comments, (_, phase, opened) = record(values)
    if not opened or opened["to"] != runtime or phase not in ("offered", "takeover"):
        print("crew: handoff: no offered handoff to %s" % runtime)
        return 1
    print("\n".join(plan(values, state, comments, opened, phase)))
    return 0


def post(values, body, args):
    if args.dry_run:
        print(body, end="")
        return True
    error = write(values, body)
    if error:
        print("%s; re-reading" % error)
    return not error


def handoff_title(values, st, frm, to, hid):
    return post_title(values, "coordinator", "handoff", "%s %s → %s (%s)" % (st, frm, to, hid))


def state_post(values, st, opened, reason, signature, sha, extra=""):
    return "%s\n%s\n%s\n<!-- crew:v1 role=coordinator pass=handoff handoff=%s state=%s " \
        "from=%s to=%s cmd-id=n/a sha=%s round=n/a verdict=n/a -->\n%s\n" % (
            handoff_title(values, st, opened["from"], opened["to"], opened["handoff"]), reason, extra,
            opened["handoff"], st, opened["from"], opened["to"], sha, signature)


def ack(values, state, runtime, args):
    for _ in range(3):  # re-read before every attempt, so a retried ack is never a second one
        comments, (owner, phase, opened) = record(values)
        if opened is None and owner == runtime:
            print("crew: handoff: %s owns; already acked" % runtime)
            return 0
        if not opened or opened["to"] != runtime or phase not in ("offered", "takeover"):
            print("crew: handoff: no offered or takeover handoff to %s" % runtime)
            return 1
        lines = plan(values, state, comments, opened, phase)
        rules = [line for line in lines if line.startswith("rule ")]
        if rules and not args.rules_confirmed:
            print("crew: handoff: refusing ack: rule differences need an owner answer first:\n" + "\n".join(rules))
            return 1
        extra = ""
        if phase == "takeover":  # the record holds a manifest either way
            extra = "\n" + re.search(r"```json\n.*?\n```", manifest(values, state, opened, "takeover", ""), re.S).group(0) + "\n"
        sha = branch_head(values)
        body = state_post(values, "acked", opened, "Reconciled against live state: %s." % "; ".join(lines),
                          args.signature, sha, extra)
        if crew_render.crew_config.token_reasons(body):
            raise RuntimeError("crew: handoff: secret scan refused the ack")
        if post(values, body, args):
            if not args.dry_run:
                print("crew: handoff: posted acked %s" % opened["handoff"])
            return 0
    return 1


def stopped(values, state, session, runtime, args):
    comments, (owner, _, _) = record(values)
    acked = last_ack(comments, owner, runtime) if owner != runtime else None
    if acked is None:
        print("crew: handoff: no acked handoff from %s" % runtime)
        return 1
    if posted(comments, acked["handoff"], "stopped"):
        print("crew: handoff: %s already stopped" % acked["handoff"])
        return 0
    if args.dry_run:
        sha = branch_head(values)
        print(state_post(values, "stopped", acked, stop_reason([]), args.signature, sha), end="")
        return 0
    if not args.foreground:  # mdstack down kills window 0, so the actor that posts must outlive the session
        argv = [sys.executable, CREW_BIN, "handoff", "stopped", "--foreground", "--project",
                args.project, "--signature", args.signature] + (["--org-profile", args.org_profile] if args.org_profile else [])
        log = os.path.join(state, "handoff-stop.log")
        with open(log, "a") as f:
            subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=f, stderr=subprocess.STDOUT, start_new_session=True)
        print("crew: handoff: stopping wake sources outside the session; it posts stopped (log %s)" % log)
        return 0
    kept = sorted({os.path.basename(rec["worktree"]) for _, rec in runs(state)})
    pidfile = os.path.join(state, "wake", "watcher.pid")
    for _ in range(DOWN_TRIES):
        if pid := commands()["watch"].armed(pidfile):
            with contextlib.suppress(ProcessLookupError):  # it exited after the read (#1757)
                os.kill(pid, signal.SIGTERM)
        down = commands()["down"].run(Namespace(project=args.project, org_profile=args.org_profile, keep_work=True))
        if down == 0 and not tmux.has_session(session) and not commands()["watch"].armed(pidfile):
            break
        time.sleep(DOWN_RETRY)
    else:
        print("crew: handoff: refusing stopped: the watcher or %s is still running" % session)
        return 1
    sha = branch_head(values)
    if not post(values, state_post(values, "stopped", acked, stop_reason(kept), args.signature, sha), args):
        return 1
    print("crew: handoff: posted stopped %s" % acked["handoff"])
    return 0


def stop_reason(kept):
    return "Wake sources stopped: watcher disarmed, crew session down. Worktrees kept on this host: %s." % (
        ", ".join(kept) or "none")


def lift(values, runtime, args):
    comments, (owner, phase, opened) = record(values)
    acked = last_ack(comments, runtime) if owner == runtime and not opened else None
    if acked is None:
        print("crew: handoff: refusing lift: %s has not acked a handoff it owns" % runtime)
        return 1
    data = block(posted(comments, acked["handoff"], "offered")) or block(posted(comments, acked["handoff"], "acked")) or {}
    version = re.match(r"v?(\d+)\.(\d+)\.(\d+)", data.get("eng_crew_version", ""))
    if not (posted(comments, acked["handoff"], "stopped") or args.owner_confirmed or
            version and tuple(map(int, version.groups())) >= GUARDED):
        print("crew: handoff: refusing lift: wait for stopped, the owner's confirmation or a guarded release")
        return 1
    items, keep = open_items(values), {unref(k) for k in args.keep}
    for added in data.get("holds_added", []):
        n = unref(added)
        if n in keep or "crew:hold" not in items.get(n, {}).get("labels", []):
            continue
        if ownership_module.native(values):  # tracker.unlabel <n> crew:hold; unbound refuses
            try:
                op(values, "tracker.unlabel", n=n, tag="crew:hold")
                lifted = True
            except RuntimeError as e:
                print(e)
                lifted = False
        else:
            lifted = subprocess.run(["gh", "api", "-X", "DELETE", "repos/%s/%s/issues/%s/labels/crew:hold" % (
                values["repo.owner"], values["repo.name"], n)], capture_output=True, text=True).returncode == 0
        print("crew: handoff: %s crew:hold on %s" % ("lifted" if lifted else "failed to lift", ref(n)))
        if not lifted:
            return 1
    return 0


def transition(args, me, owner, phase, opened, now):
    """(state, handoff id, from, to, reason line, drain deadline or None) for the command, or a refusal string."""
    if args.action != "abort" and not re.fullmatch(RUNTIME_ID, args.runtime or ""):
        return "needs a runtime id <runtime>@<instance>"
    if args.action == "to":
        if owner != me or opened:
            return "only the owning runtime with no open handoff may hand off (owner %s)" % owner
        if args.runtime == me or args.deadline < 1:
            return "target must be another runtime and the deadline at least 1 minute"
        until = (now + datetime.timedelta(minutes=args.deadline)).strftime("%Y-%m-%dT%H:%M:%SZ")
        tail = ", deadline %d min (%s)" % (args.deadline, until) if args.mode == "drain" else ""
        return ("draining", "%s-%s" % (now.strftime("%Y%m%d"), os.urandom(3).hex()), me, args.runtime,
                "Owner command (chat): handoff to %s, mode %s%s." % (args.runtime, args.mode, tail),
                until if args.mode == "drain" else None)
    if args.action == "abort":
        if not opened or me != (opened["from"] if opened["state"] == "draining" else opened["to"]):
            return "no open handoff opened by %s" % me
        return "aborted", opened["handoff"], opened["from"], opened["to"], "Owner command (chat): handoff abort.", None
    reuse = opened and opened["from"] == args.runtime and opened["to"] == me
    if owner != args.runtime or me == args.runtime or (opened and not reuse):
        return "takeover needs %s to own the repo and no other open handoff (owner %s)" % (args.runtime, owner)
    return ("takeover", opened["handoff"] if reuse else "%s-%s" % (now.strftime("%Y%m%d"), os.urandom(3).hex()),
            args.runtime, me, "Owner command (chat): takeover from %s." % args.runtime, None)


def command(values, state, me, args):
    if not args.signature and not args.dry_run:
        print("crew: handoff: %s needs --signature" % args.action)
        return 1
    result = transition(args, me, *record(values)[1], datetime.datetime.now(datetime.timezone.utc))
    if isinstance(result, str):
        print("crew: handoff: refusing %s: %s" % (args.action, result))
        return 1
    st, hid, frm, to, reason, until = result
    sha = branch_head(values)
    body = "%s\n%s\n\n<!-- crew:v1 role=coordinator pass=handoff handoff=%s state=%s " \
        "from=%s to=%s cmd-id=chat sha=%s round=n/a verdict=n/a -->\n%s\n" % (
            handoff_title(values, st, frm, to, hid), reason, hid, st, frm, to, sha, args.signature)
    if args.dry_run:
        print(body, end="")
        return 0
    error = write(values, body)
    if error:
        print("%s; re-read the record and retry (handoff %s)" % (error, hid))
        return 1
    asks = os.path.join(state, "asks", "handoff.json")
    if until:
        os.makedirs(os.path.dirname(asks), exist_ok=True)
        with open(asks, "w") as f:
            json.dump({"deadline": until.replace("Z", "+00:00"), "handoff": hid}, f)
    elif st == "aborted" and os.path.exists(asks):
        os.remove(asks)
    print("crew: handoff: posted %s %s" % (st, hid))
    return 0
