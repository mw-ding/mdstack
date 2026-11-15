"""Long-lived pool leads, durable reference handoffs and token-free supervision.
Solo-labelled items skip builder build/fix/CI/merge-up handoffs. The synthesizer lead (window 1, #1569) is the
long-lived lander itself: its durable inbox is the land queue, and route hands it approval, self-gate, green-CI and
approved merge-up events.
In a team (team.json at the team root, #1858) each pool has one `(team, pool)` lead: its record, inbox, status and brief
live at the team root, every repo's route hands it enveloped messages, and a repo sees only its own messages there
(pending, waits, retries). Its brief lists each repo's rendered lead brief and `$CREW_PROJECT` is the team file, so a
command without the message's `context.project` refuses for a multi-repo team.

Usage: mdstack lead ensure|suites|handoff|report ROLE [KIND REF...] [--id ID] --project FILE
"""
import argparse
import json
import hashlib
import os
import shlex
import time
from crew_shared import (
    commands, coordinator_window, ENGINE_CMD, harness, identity, LAUNCH, lead_state, probe, proc, profile,
    queue_lock, remember_pr, refuse_paused, repo_id, require_ownership, runs, show_icon, stop_pane, team_module, tmux,
    wait_harness, window_env, work_context)


POOLS = {"builder": 2, "reviewer": 3, "synthesizer": 1}
DEFERRALS = {"capacity", "load", "suites", "probe-unavailable"}
BLOCKS = {"spawn-failure", "missing-dependency", "owner-decision", "lead-fault"}
WAITS = {"owner", "hold", "ci", "evidence"}  # typed waits a lead reports as `waiting: #<n> KIND id=<id>` (#1715, #1878)


def solo(values, issue=None, pr=None):
    """Read the lane label live, including a PR's linked issues; read failures stop dispatch."""
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    read = commands()["route"].gh
    if pr:
        change = read("pr", "view", str(pr), "-R", repo, "--json", "labels,closingIssuesReferences")
        if any(label["name"] == "crew:solo" for label in change["labels"]):
            return True
        issues = {item["number"] for item in change["closingIssuesReferences"]}
    else:
        issues = set()
    if issue:
        issues.add(issue)
    return any(any(label["name"] == "crew:solo" for label in
                   read("issue", "view", str(n), "-R", repo, "--json", "labels")["labels"])
               for n in sorted(issues))


def record_path(state, role):
    return os.path.join(lead_state(state), "leads", role + ".json")


def save_record(path, rec):
    with open(path + ".tmp", "w") as out:
        json.dump(rec, out)
    os.replace(path + ".tmp", path)


def records(state):
    for role in POOLS:
        path = record_path(state, role)
        if os.path.exists(path):
            with open(path) as f:
                rec = json.load(f)
            yield rec["name"], rec


def enabled(state, role):
    return role in POOLS and os.path.exists(os.path.join(state, "render", "runtime", role + "-lead.md"))


def recovery(liveness, restarts):
    return "none" if liveness == "alive" else "restart" if liveness in ("dead", "missing") and not restarts else "blocked"


def team_brief(home, role):
    """A `(team, pool)` lead's brief: the message's repo decides the rendered brief, project and state (#1858)."""
    data = team_module.read(home)
    rows = "".join("| %s | `%s` | `%s` | `%s` |\n" % (r, v["project"], v["state"], os.path.join(
        v["state"], "render", "runtime", role + "-lead.md")) for r, v in sorted(data["repos"].items()))
    return ("# Team %s lead: %s\n\nYou lead the %s pool of every repo of team `%s` (team §9.4). Your inbox and status "
            "are at the team root `%s`. Each inbox message carries a `context` work envelope: refuse one without it "
            "(`blocked:` with its id). For each message, follow the rendered lead brief of `context.repo` below, pass "
            "`context.project` as `--project` to every crew command and use that repo's state where the brief says "
            "`$CREW_STATE`. `$CREW_PROJECT` is the team file, which refuses without a repo for a multi-repo team. "
            "One repo's ownership, pause or holds never decide another repo's work.\n\n"
            "| Repo | --project | State | Lead brief |\n|---|---|---|---|\n%s" % (
                role, data.get("team", ""), role, data.get("team", ""), home, rows))


def bind_team(values, state, project):
    """A team repo records itself in team.json before any lead read, so its leads resolve to the team root."""
    if values.get("team.name"):
        team_module.bind(state, values["team.name"], repo_id(values), work_context(project, values)["project"])


def ensure(args, role):
    values, session, state = profile(args)
    if not require_ownership(values) or not enabled(state, role) or refuse_paused(state, "lead " + role):
        return 1
    bind_team(values, state, args.project)
    home = lead_state(state)
    path = record_path(state, role)
    with queue_lock(home):
        rec = dict(records(state)).get(values["identities.%s.name" % role].lower() + "-lead")
        windows = dict((n, i) for i, n in tmux.list_windows(session))
        name = values["identities.%s.name" % role].lower() + "-lead"
        index = POOLS[role]
        if rec:
            action = recovery(probe(session, name, rec, windows), rec.get("restarts", 0))
            if action == "none":
                return 0
            if action == "blocked":
                print("crew: blocked lead %s; coordinator must arrange owner-directed repair" % name)
                return 1
        elif name in windows:
            print("crew: blocked lead %s; window has no recorded identity" % name)
            return 1
        if index in windows.values() and windows.get(name) != index:
            print("crew: lead window %d occupied" % index)
            return 1
        if name in windows:
            if stop_pane(session, windows[name]):
                return 1
            tmux.kill_window(session, windows[name])
        engine, model, effort = commands()["spawn"].pick_engine(values, "default")
        cwd = os.path.dirname(os.path.abspath(args.project.partition("#")[0]))
        brief = os.path.join(home, "leads", role + ".brief.md")
        os.makedirs(os.path.dirname(brief), exist_ok=True)
        os.makedirs(os.path.join(home, "status"), exist_ok=True)  # a fresh lead appends its first ack here (#1176)
        with open(os.path.join(state, "render", "runtime", role + "-lead.md")) as f, open(brief, "w") as out:
            out.write(team_brief(home, role) if home != state else f.read())
        team_file = args.project.partition("#")[0] if home != state else None
        env = window_env(values, home, role, name, brief, team_file or args.project)
        env.update(CREW_ROLE=role + "-lead", CREW_POOL=role, **{"CREW_TEAM": os.path.abspath(team_file)} if team_file else {})
        argv = harness(engine, model, effort, cwd, state, values["runtime.options.permission_mode"], values)
        new = dict(name=name, index=index, role=role + "-lead", harness=ENGINE_CMD[engine],
                   restarts=1 if rec else 0, start=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        save_record(path, new)
        try:
            tmux.new_window(session, index, name, cwd, env, LAUNCH % (shlex.join(argv), "Read your brief at $CREW_BRIEF and follow it."))
            show_icon(values, session, index, role)
            wait_harness(session, index, name, new["harness"], getattr(args, "timeout", 15))
        except RuntimeError:
            tmux.kill_window(session, index)
            raise
        new.update(identity(session, index))
        save_record(path, new)
    print("crew: started lead %s; worker pool and inbox preserved" % name)
    return 0


def handoff(args, role, kind, refs):
    if role == "builder" and kind in ("build", "fix", "ci-red", "merge-up"):
        values, _, _ = profile(args)
        n = int(refs[0].lstrip("#"))
        if solo(values, **{"issue" if kind == "build" else "pr": n}):
            print("crew: solo item; skip builder handoff; post findings/CI on the PR for the owner's session")
            return 0
    if ensure(args, role):
        return 1
    values, session, state = profile(args)
    name = values["identities.%s.name" % role].lower() + "-lead"
    prior = next((m for m in pending(state, name) if m["kind"] == kind and m["refs"] == refs), None)
    if prior:  # a done (completed or withdrawn) message is never reused: a re-send starts a new handoff
        if commands()["send"].wait_ack(lead_state(state), name, prior["id"], 0) == 0:
            return 0
        if commands()["send"].nudge(session, POOLS[role], "inbox: " + prior["id"]):
            return 4
        return commands()["send"].wait_ack(lead_state(state), name, prior["id"], args.wait_ack) \
            if getattr(args, "wait_ack", None) is not None else 0
    if not require_ownership(values):
        return 1
    return commands()["send"].run(argparse.Namespace(project=args.project, org_profile=args.org_profile,
                                window=name, kind=kind, refs=refs, wait_ack=getattr(args, "wait_ack", None)))


def pending(state, name):
    """The lead's undone inbox messages; from a team repo's state, only messages whose envelope names that repo."""
    home = lead_state(state)
    inbox = os.path.join(home, "inbox", name + ".jsonl")
    status = os.path.join(home, "status", name + ".status")
    if not os.path.exists(inbox):
        return []
    done = set()
    if os.path.exists(status):
        with open(status) as f:
            done = {line.split()[1] for line in f if line.startswith("done: ")}
    mine = team_module.repo_of(state) if home != state else None
    with open(inbox) as f:
        return [m for m in map(json.loads, f) if m["id"] not in done and
                (home == state or (m.get("context") or {}).get("repo") == mine)]


def deferred_ids(state, name):
    """Handoff ids the lead acknowledged and then reported as an admission deferral (`deferred: ... id=<id>`)."""
    status = os.path.join(lead_state(state), "status", name + ".status")
    acked, found = set(), set()
    if os.path.exists(status):
        with open(status) as f:
            for line in f:
                words = line.split()
                if line.startswith("ack: ") and len(words) > 1:
                    acked.add(words[1])
                elif line.startswith("deferred: ") and words[-1].startswith("id="):
                    found |= {words[-1][3:]} & acked
    return found


def fingerprint(state, ref, kind=None):
    """Token-free fresh state for a waited ref: mdstack poll's observed PR state, head and CI, its hold, its
    owner-answer count and an open owner ask; an `evidence` wait adds poll's builder records at head, so a published
    note wakes it even if no event or `done:` arrives (#1878). Mergeability and verdict churn are not wait state
    (#1836)."""
    n = ref.lstrip("#")
    try:
        with open(os.path.join(state, "poll-state.json")) as f:
            poll = json.load(f)
    except (OSError, ValueError):
        poll = {}
    pr = poll.get("observed", {}).get(n)
    return [None if pr is None else [pr.get(k) for k in ("state", "head", "ci")], "#" + n in poll.get("held", []),
            poll.get("answers", {}).get("#" + n), os.path.exists(os.path.join(state, "asks", n + ".json"))] + \
        ([(poll.get("prs", {}).get(n) or {}).get("notes")] if kind == "evidence" else [])


def frees(seen, now):
    """Whether a waited ref's fresh state changed in a way that can free its id: any change except a hold appearing
    (with its first owner-answer count), which only confirms the hold the dispatcher parked on (#1836)."""
    return seen != now and not (now[1] and not seen[1] and [seen[0], seen[3:]] == [now[0], now[3:]] and
                                seen[2] in (None, now[2]))


def waits(state, name=None):
    """leads/waits.json: per lead, {id: {"line", "seen", "woke"}} for its acknowledged waits; one lead's with `name`."""
    try:
        with open(os.path.join(state, "leads", "waits.json")) as f:
            book = json.load(f)
    except (OSError, ValueError):
        book = {}
    return book if name is None else book.get(name, {})


def parked(state, name):
    """Ids of name's acknowledged waits the wait book holds unchanged (not woken), read without writing it: team
    admission leaves them out of demand, so one repo's parked waits never take another repo's budget (#1836)."""
    return {i for i, w in waits(state, name).items() if isinstance(w, dict) and not w.get("woke")}


def actionable(state, name):
    """Pending messages less acknowledged owner, hold, CI or evidence waits whose ref's fresh state is unchanged since
    their `waiting:` line. A changed state wakes the id until a later `waiting:` line; leads/waits.json keeps the record.
    For a team lead the messages, waits book and fingerprints are this repo state's own (#1858)."""
    messages = pending(state, name)
    status = os.path.join(lead_state(state), "status", name + ".status")
    acked, latest = set(), {}
    if os.path.exists(status):
        with open(status) as f:
            for i, line in enumerate(f):
                words = line.split()
                if line.startswith("ack: ") and len(words) > 1:
                    acked.add(words[1])
                elif len(words) == 4 and words[0] == "waiting:" and words[1].startswith("#") and \
                        words[2] in WAITS and words[3].startswith("id=") and words[3][3:] in acked:
                    latest[words[3][3:]] = [i, words[1], words[2]]
    book = waits(state)
    old, mine, waiting = book.get(name, {}), {}, set()
    for m in messages:
        if m["id"] not in latest:
            continue
        line, ref, kind = latest[m["id"]]
        now = fingerprint(state, ref, kind)
        rec = old.get(m["id"])
        rec = rec if rec and rec["line"] == line else {"line": line, "seen": now, "woke": False}
        rec = dict(rec, seen=now, woke=rec["woke"] or frees(rec["seen"], now))  # a copy; an absorbed hold's release wakes
        mine[m["id"]] = rec
        if not rec["woke"]:
            waiting.add(m["id"])
    if mine != old:
        book[name] = mine
        os.makedirs(os.path.join(state, "leads"), exist_ok=True)
        save_record(os.path.join(state, "leads", "waits.json"), book)
    return [m for m in messages if m["id"] not in waiting]


def retry_pending(args, name=None, recheck=False, admission=False):
    """Nudge each lead with its first actionable message (unchanged acknowledged waits are skipped on every path,
    #1715). On the lead backstop (`recheck`), acknowledged deferred
    handoffs are nudged only when a scheduler walk (writing only target progression) would admit their ref now (#1502); slot releases and
    other callers nudge them as before. `admission` (the watcher's 60 s admission recheck) checks only those deferred
    handoffs, so it never re-types other ids between their backed-off retries (#1715)."""
    _, session, state = profile(args)
    for worker, rec in records(state):
        if name is not None and worker != name:
            continue
        messages = actionable(state, worker)
        if messages and (recheck or admission):
            deferred = deferred_ids(state, worker)
            waiting = [m for m in messages if m["id"] in deferred]
            messages = [] if admission else [m for m in messages if m["id"] not in deferred]
            if not messages and waiting:
                admit = commands()["schedule"].admissible(args, rec["role"].removesuffix("-lead"))
                messages = [m for m in waiting if "#%s" % m["refs"][0].lstrip("#") in admit]
        if messages:
            if ensure(args, rec["role"].removesuffix("-lead")):
                raise RuntimeError("crew: cannot retry lead " + worker)
            if commands()["send"].nudge(session, rec["index"], "inbox: " + messages[0]["id"]):
                raise RuntimeError("crew: cannot nudge lead " + worker)


def event(args, role, wake):
    _, _, state = profile(args)
    key = hashlib.sha256(json.dumps(wake, sort_keys=True).encode()).hexdigest()[:20]
    path = os.path.join(state, "leads", role + "-events", key + ".json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(wake, f)
    return handoff(args, role, "work", [path])


def report(args):
    if args.role != "builder" or len(args.refs) < 2 or args.refs[0] not in DEFERRALS | BLOCKS:
        print("crew: report builder requires a deferral/block reason and refs")
        return 2
    values, _, state = profile(args)
    if not require_ownership(values, "write"):
        return 1
    reason, refs = args.refs[0], args.refs[1:]
    deferred = reason in DEFERRALS
    key = hashlib.sha256(json.dumps([reason, refs, args.detail]).encode()).hexdigest()[:20]
    path = os.path.join(state, "leads", "builder-admission.md" if deferred else "builder-blocks/" + key + ".md")
    coordinator = coordinator_window(values)
    sent_refs = refs + [path]
    inbox = os.path.join(state, "inbox", coordinator + ".jsonl")
    if not deferred and os.path.exists(inbox):
        with open(inbox) as f:
            if any(m["kind"] == "blocked" and m["refs"] == sent_refs for m in map(json.loads, f)):
                print("crew: identical block already reported: %s %s" % (reason, " ".join(refs)))
                return 0
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as out:
        out.write("# Builder %s\n\nReason: %s\nRefs: %s\n%s\n" % (
            "admission deferred" if deferred else "blocked", reason, " ".join(refs), args.detail))
    name = values["identities.builder.name"].lower() + "-lead"
    os.makedirs(os.path.join(lead_state(state), "status"), exist_ok=True)
    with open(os.path.join(lead_state(state), "status", name + ".status"), "a") as out:
        out.write("%s: %s %s %s%s\n" % ("deferred" if deferred else "blocked", " ".join(refs), reason, path,
                                       " id=" + args.id if deferred and args.id else ""))
    if deferred:
        print("crew: admission deferred locally: %s %s" % (reason, " ".join(refs)))
        return 0
    return commands()["send"].run(argparse.Namespace(project=args.project, org_profile=args.org_profile,
                                window=coordinator, kind="blocked", refs=sent_refs, wait_ack=None))


def suites(values, state, closed=None):
    """Live tool sessions of runs whose item is open; runs with a live session on a closed item go to `closed`."""
    count = 0
    repo = "%s/%s" % (values["repo.owner"], values["repo.name"])
    for name, rec in runs(state):
        if not rec.get("pane_pid") or not proc.live_child(rec["pane_pid"], rec["harness"]):
            continue
        last = os.path.join(state, "status", name + ".status")
        if os.path.exists(last):
            with open(last) as f:
                for line in f.read().splitlines():
                    remember_pr(rec, line)
        item = rec.get("pr") or rec.get("args", {}).get("pr")
        kind = "pr" if item else "issue"
        item = item or rec.get("args", {}).get("issue")
        if item and commands()["route"].gh(kind, "view", str(item), "-R", repo, "--json", "state")["state"] != "OPEN":
            if closed is not None:
                closed.append(dict(window=name, pid=rec["pane_pid"]))
            continue
        count += 1
    return count


def register(sub):
    p = sub.add_parser("lead")
    p.add_argument("action", choices=["ensure", "handoff", "suites", "report"])
    p.add_argument("role", choices=sorted(POOLS))
    p.add_argument("refs", nargs="*")
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--wait-ack", type=float)
    p.add_argument("--detail", default="", help="report: observed admission inputs or actionable block details")
    p.add_argument("--id", help="report: the deferred handoff's inbox id; its backstop nudge then waits for admission")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    if args.action == "report":
        return report(args)
    if args.action == "ensure":
        return ensure(args, args.role)
    if args.action == "handoff":
        if not args.refs:
            return 2
        return handoff(args, args.role, args.refs[0], args.refs[1:])
    values, _, state = profile(args)
    print(suites(values, state))
    return 0
