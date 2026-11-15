"""`mdstack restart` restarts a dead, missing or quota-stopped run once (a builder even after `done:`, as its PR's fix pass; `done:` is
terminal only for reviewer and synthesizer runs), in its own worktree when it holds unlanded work. A run on a role
host (#345) is probed, checked and relaunched there; a clean one is removed there and spawned again, so placement
runs again. A reflection run first rechecks its window's posted report and, when one is there, refuses (#1520); else it
restarts with the same run ID, log issue, input SHA and window. A run probing quota (its harness shows its adapter's
usage-limit line, #631) is stopped and relaunched in place, in its own worktree, claim and inbox at its head, on the next
eligible engine in its role's order, skipping every engine it has exhausted; the brief lists the inbox IDs it never
acknowledged. A reviewer whose PR head moved, or a run with no eligible engine left, refuses and stays for escalation.
Claude Code run copies keep the stable-parent startup and warn about missing trust before opening a window (#1792).
In a team, a relaunch in its own worktree takes a new team run ID and slot under the team lock and refuses, changing
nothing, when the run's window shows another process (pane, pid or start time differ) (#1858).

On the coordinator's window (window 0) it relaunches the live coordinator in place instead (#1544): the current
sandbox_env and CREW_* environment, resuming --resume ID (else launch.resume). It refuses while the land lock is held,
when run from window 0 itself (beneath its pane process), which the stop would kill first, and for a team reference.

Usage: mdstack restart WINDOW --project FILE [--org-profile FILE] [--resume ID]
"""
import json
import os
import re
import shlex
import subprocess
import time
from crew_shared import (
    BANDS, brief_src, commands, coordinator_harness, coordinator_window, CREW_BIN, crew_render, ENGINE_CMD, fetch, finished,
    harness, harnesses, heartbeat, identity, kill_run, LAUNCH, load, main, own_pane, POINTER, probe, profile, receipts, remote_run, repo_id, ROLES, runs,
    sandbox_env, refuse_paused, show_icon, stop_pane, team_module, tmux, unlanded, wait_harness, window_alias, window_env)

confine = load("crew_confine", "environments/terminal/crew.d/_confine.py")


def runs_under(pid):
    """Whether this process runs beneath pid (its parent or an ancestor), on ps's pid/ppid table: a pane id alone
    would match another tmux server's pane."""
    out = subprocess.run(["ps", "-axo", "pid=,ppid=,stat=,comm="], capture_output=True, text=True).stdout
    parents = {row[0]: row[1] for row in (line.split(None, 3) for line in out.splitlines()) if len(row) >= 2}
    node, seen = str(os.getppid()), set()
    while node and node not in seen:
        if node == str(pid):
            return True
        seen.add(node)
        node = parents.get(node)
    return False


def relaunch_coordinator(values, session, state, args):
    """Respawn window 0 in place with the current sandbox_env and CREW_* environment, resuming its conversation."""
    engine, resume = values["engines.coordinator"], args.resume or values.get("runtime.options.launch.resume", "fresh")
    pane = tmux.pane(session, 0)
    problem = ("a team coordinator is not relaunched here" if "#" in args.project
               else "--resume expects fresh, ask or a session id" if resume not in ("fresh", "ask") and
               not crew_render.crew_config.LAUNCH_SESSION_ID.fullmatch(resume)
               else "the land lock is held" if commands()["land-lock"].held(state)
               else "%s is not running" % session if not pane
               else "run it from the owner's terminal, not window 0" if runs_under(pane["pid"])
               else "%s cannot resume" % engine if resume != "fresh" and engine not in harnesses.RESUMABLE
               else "%s has no in-place reload" % tmux.name if "reload" not in tmux.CAPABILITIES else None)
    if problem:
        print("crew: refusing coordinator relaunch: " + problem)
        return 1
    project_dir = os.path.dirname(os.path.abspath(args.project))
    cmd = shlex.join(coordinator_harness(engine, project_dir, state, values["runtime.options.permission_mode"], values,
                                         resume))
    env = {"CREW_ROLE": "coordinator", "CREW_STATE": state, "CREW_IDENTITY": values["identities.coordinator.gh_user"],
           "CREW_BIN": CREW_BIN, "CREW_BRIEF": brief_src(state, "coordinator"),
           "CREW_PROJECT": os.path.abspath(args.project), **sandbox_env(values)}
    tmux.hold(session, 0)
    if stop_pane(session, 0):
        print("crew: refusing coordinator relaunch: window 0's process group survived the stop")
        return 1
    tmux.respawn(session, 0, project_dir, env,
                 LAUNCH.removesuffix(' "%s"') % cmd if resume == "ask" else LAUNCH % (cmd, POINTER))
    try:
        wait_harness(session, 0, coordinator_window(values), ENGINE_CMD[engine], args.timeout)
    except RuntimeError as e:
        print(e)
        return 1
    print("crew: relaunched %s in place (window 0, resume %s)" % (coordinator_window(values), resume))
    return 0


def next_engine(values, state, rec, exhausted):
    """The first eligible engine of the run's role order past every exhausted one, as spawn would pick it; a reviewer
    still avoids the PR's builder engines (#631). RuntimeError when none is left."""
    spawn, a = commands()["spawn"], rec["args"]
    avoid = set(exhausted)
    if "engine_independent_of" in ROLES[rec["role"]]:
        avoid |= spawn.builder_engines(values, state, rec["repo"], fetch(rec["repo"], values["repo.default_branch"]),
                                       rec["head"], a["pr"])
    return spawn.engine_order(values, a["tier"], avoid, rec["role"])[0]


def quota_relaunch(values, session, state, args, rec, exhausted):
    """Relaunch a quota run in place on the next eligible engine (#631): same worktree (so the same head, dirty or
    not), claim and inbox, never a fresh spawn; the brief names the engine and the inbox IDs never acknowledged."""
    name, wt = args.window, rec.get("worktree")
    try:
        if not wt or not os.path.isdir(wt):
            raise RuntimeError("its worktree %s is gone" % wt)
        if "engine_independent_of" in ROLES[rec["role"]]:
            live = fetch(rec["repo"], "pull/%d/head" % rec["args"]["pr"])
            if live != rec["head"]:
                raise RuntimeError("PR #%d head moved from %s to %s; reap the stale reviewer" % (
                    rec["args"]["pr"], rec["head"][:7], live[:7]))
        engine, model = next_engine(values, state, rec, exhausted)
    except RuntimeError as e:
        print("crew: refusing restart: %s is out of quota: %s; escalate" % (rec["engine"], e))
        return 1
    if stop_pane(session, rec["index"]):  # kill-window alone leaves Codex running (#139 F2)
        print("crew: refusing restart: %s's process group survived the stop" % name)
        return 1
    acks = receipts(state, name)
    inbox = os.path.join(state, "inbox", name + ".jsonl")
    pending = []
    if os.path.exists(inbox):
        with open(inbox) as f:
            pending = [m["id"] for m in map(json.loads, filter(str.strip, f)) if m["id"] not in acks]
    with open(os.path.join(state, "runs", name + ".brief.md"), "a", encoding="utf-8") as f:
        f.write("- Quota fallback: %s is out of quota; this session runs %s %s %s. Attribute that engine.\n" % (
            rec["engine"], engine, model, rec["effort"]) + "".join("- Pending: inbox: %s\n" % i for i in pending))
    rec.update(engine=engine, model=model, harness=ENGINE_CMD[engine], exhausted=exhausted)
    return relaunch(values, session, state, name, rec, ["quota fallback from %s" % exhausted[-1]], args.timeout,
                    args.project)


def relaunch(values, session, state, name, rec, items, timeout, project, restarts=1):
    """Restart a run whose worktree holds unlanded work: new window, same worktree, brief and claim."""
    brief = os.path.join(state, "runs", name + ".brief.md")
    adapter = harnesses.ADAPTERS[rec["engine"]]
    if rec["role"] == "builder" and hasattr(adapter, "builder_checks"):
        for status, check, detail, hint in adapter.builder_checks(values):
            if status != "ok":
                print("crew: warning before restart: %s: %s; %s" % (check, detail, hint))
    for index, n in tmux.list_windows(session):
        if n == name:
            tmux.kill_window(session, index)
    used = [i for i, _ in tmux.list_windows(session)]
    free = [i for i in range(BANDS[rec["role"]][0], BANDS[rec["role"]][1] + 1) if i not in used]
    if not free or not os.path.exists(brief):
        print("crew: refusing restart: %s" % ("band %d-%d full" % BANDS[rec["role"]] if not free else
                                             "no brief %s" % brief))
        return 1
    index = rec["index"] if rec["index"] in free else free[0]
    top = team_module.root(state)
    if top and rec.get("run_id"):  # a new execution generation: a new run ID and slot under the team lock (#1858)
        team_module.release(top, rec["run_id"], repo_id(values))
        with team_module.lock(top):
            alloc = team_module.allocate(top, BANDS[rec["role"]], used, {"repo": repo_id(values), "project": rec.get(
                "project"), "state": state, "window": name, "claim": rec["claim"]}, prefer=rec["index"])
        if alloc is None:
            print("crew: refusing restart: band %d-%d full across the team" % BANDS[rec["role"]])
            return 1
        index, rec["run_id"] = alloc["index"], alloc["run_id"]
        with open(os.path.join(state, "runs", name + ".json"), "w") as f:
            json.dump(rec, f, indent=2)
    wt, mode = rec["worktree"], values["runtime.options.permission_mode"]
    try:  # the relaunch's engine decides confinement again (#1252)
        confined, reason = confine.decide(values, rec["role"], harnesses.ADAPTERS[rec["engine"]], mode, False, state,
                                          rec["repo"], wt)
    except RuntimeError as e:
        print("%s; worktree, claim and run record kept" % e)
        return 1
    if rec["role"] == "builder":
        rec.pop("unconfined", None)
        rec.update({"confined": True} if confined else {"confined": False, "unconfined": reason})
    argv = harness(rec["engine"], rec["model"], rec["effort"], wt, state, mode, values, confined=confined)
    env = window_env(values, state, rec["role"], name, brief, project)
    if confined:
        env["TMPDIR"] = confine.tmpdir(wt)
    cwd = getattr(adapter, "role_cwd", lambda wt: wt)(wt)
    tmux.new_window(session, index, name, cwd, env, LAUNCH % (shlex.join(argv), POINTER))
    try:
        show_icon(values, session, index, rec["role"])
        wait_harness(session, index, name, rec["harness"], timeout)
    except RuntimeError as e:
        tmux.kill_window(session, index)
        print("%s; worktree, claim and run record kept" % str(e).replace("; cleaned up", ""))
        return 1
    rec.update(identity(session, index), index=index, restarts=restarts,
               start=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(os.path.join(state, "runs", name + ".json"), "w") as f:
        json.dump(rec, f, indent=2)
    print("crew: restarted %s (window %d) in its worktree %s, keeping unlanded work:\n  %s" % (
        name, index, wt, "\n  ".join(items)))
    return 0


def relaunch_remote(values, state, name, rec, items, restarts=1):
    """Restart a run on its role host in its own worktree, which holds unlanded work; the brief travels again."""
    reply = remote_run.spawn(values, state, name, rec, os.path.join(state, "runs", name + ".brief.md"))
    if reply["result"] != "ok":
        print("crew: refusing restart on %s: %s: %s; worktree, claim and run record kept" % (
            rec["host"], reply["result"], reply.get("reason") or reply.get("error")))
        return 1
    rec.update({k: reply[k] for k in ("pane_id", "pane_pid", "pane_start")}, restarts=restarts,
               start=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    with open(os.path.join(state, "runs", name + ".json"), "w") as f:
        json.dump(rec, f, indent=2)
    print("crew: restarted %s on %s in its worktree %s, keeping unlanded work:\n  %s" % (
        name, rec["host"], rec["worktree"], "\n  ".join(items)))
    return 0


def reflection_posted(values, r):
    """The URL of a posted report covering the reflection run's window on its log issue (or the open reflection:log
    issues when none was given), else None: a restart writes nothing over a finished report (#1520)."""
    route, repo = commands()["route"], "%s/%s" % (values["repo.owner"], values["repo.name"])
    logs = [r["log"]] if r.get("log") else [i["number"] for i in route.gh(
        "issue", "list", "-R", repo, "--label", "reflection:log", "--state", "open", "--json", "number")]
    want = set(r["window"].split("+"))
    for n in logs:
        for c in route.gh("issue", "view", str(n), "-R", repo, "--json", "comments")["comments"]:
            if any(m.get("role") == "researcher" and m.get("pass") == "reflection" and
                   want <= set(m.get("window", "").split("+")) for m in route.markers(c["body"])):
                return c["url"]
    return None


def register(sub):
    p = sub.add_parser("restart")
    p.add_argument("window")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--resume", metavar="ID", help="coordinator window: resume this conversation (fresh, ask or an id)")


def run(args):
    """Restart a dead or missing run once: fresh worktree when clean, else its own worktree (tmux.md Q7)."""
    values, session, state = profile(args, "worktree_root")
    if window_alias(values, args.window) == coordinator_window(values):
        return relaunch_coordinator(values, session, state, args)
    if refuse_paused(state, "restart " + args.window):  # window 0 above still restarts while paused (#1714)
        return 1
    rec = dict(runs(state)).get(args.window)
    if rec is None:
        print("crew: no run %s" % args.window)
        return 1
    host = remote_run.host_of(rec)
    cls = remote_run.probe(values, args.window, rec) if host else \
        probe(session, args.window, rec, dict((n, i) for i, n in tmux.list_windows(session)))
    last = heartbeat(state, args.window)[0]
    problem = ("%s is %s; only dead, missing or quota runs restart" % (args.window, cls) if cls not in ("dead", "missing", "quota")
               else "%s finished (%s); use mdstack kill" % (args.window, last) if finished(rec, last)
               else "%s already restarted once; escalate (crew:escalated, owner channel)" % args.window
               if rec.get("restarts") and not getattr(args, "unpause", False) else "a quota run on a role host is not relaunched here; escalate"
               if cls == "quota" and host else None)
    if problem or "args" not in rec:
        print("crew: refusing restart: " + (problem or "%s has no spawn arguments" % args.window))
        return 1
    wt, a = rec.get("worktree"), rec["args"]
    budget = rec.get("restarts", 0) if getattr(args, "unpause", False) else 1  # mdstack resume spends no restart
    exhausted = rec.get("exhausted", []) + [rec["engine"]] if cls == "quota" else []
    if exhausted:
        return quota_relaunch(values, session, state, args, rec, exhausted)
    if a.get("reflection"):
        try:
            url = reflection_posted(values, a["reflection"])
        except RuntimeError as e:
            print("crew: refusing restart: cannot recheck reflection %s's report: %s" % (a["reflection"]["window"], e))
            return 1
        if url:
            print("crew: refusing restart: reflection %s already posted at %s; use mdstack kill" % (
                a["reflection"]["window"], url))
            return 1
    done = rec["role"] == "builder" and re.match(r"done: #\d+ #(\d+)\b", last)
    if done:  # its PR is open: restart as that PR's fix pass, never a second build pass (#234 N2)
        a = {**a, "pr": int(done.group(1)), "pass": "fix"}
        rec.update({"args": a, "pass": "fix", "item": "issue #%s, PR #%d" % (a["issue"], a["pr"])})
    if host:  # the host stops the run, then removes the worktree only when it is clean
        reply = remote_run.kill(values, args.window, rec)
        if reply["result"] != "ok":
            print("crew: refusing restart on %s: %s: %s" % (host, reply["result"], reply.get("reason") or reply.get("error")))
            return 1
        items = reply["unlanded"]
    else:
        try:
            items = unlanded(values, rec, wt) if wt and os.path.isdir(wt) else []
        except RuntimeError as e:
            items = ["unchecked: %s" % e]
    foreign = [i for i, n in tmux.list_windows(session) if n == args.window and not own_pane(session, i, rec)]
    if items and not host and team_module.root(state) and foreign:  # a successor in its pane survives (#1858)
        print("crew: refusing restart: window %s is not this repo's run %s (another process in its pane); "
              "worktree, claim and run record kept" % (args.window, rec.get("run_id")))
        return 1
    if items:  # never delete unlanded work (#172): relaunch in the same worktree and claim instead
        if done:
            with open(os.path.join(state, "runs", args.window + ".brief.md"), "a", encoding="utf-8") as f:
                f.write("- Restarted after done: as Pass fix, Item %s\n" % rec["item"])
        if host:
            return relaunch_remote(values, state, args.window, rec, items, budget)
        return relaunch(values, session, state, args.window, rec, items, args.timeout, args.project, budget)
    carried = commands()["send"].carry(state, args.window)  # kill_run removes the inbox: pending ids survive (#1850)
    if kill_run(values, session, state, args.window):
        return 1
    mode = ["--train", str(a["train"])] if a.get("train") else ["--pass", a["pass"]]  # a train worker has no pass flag (#1391)
    argv = ["spawn", rec["role"], *mode, "--round", str(a["round"]), "--tier", a["tier"],
            "--project", args.project] + (["--org-profile", args.org_profile] if args.org_profile else [])
    argv += (["--issue", str(a["issue"])] if a["issue"] else []) + (["--pr", str(a["pr"])] if a["pr"] else [])
    argv += ["--handoff", rec["handoff"]] if rec.get("handoff") else []  # the durable lead handoff it answers (#1858)
    if rec.get("rereview_id"):  # same PR/head/pass/round keeps its steer; a moved head refuses as stale (#1477)
        argv += ["--rereview-id", rec["rereview_id"], "--head", rec["head"]]
    r = a.get("reflection")
    argv += ["--reflection", r["window"], "--run-id", r["run"], "--input-sha", r["sha"]] + (
        ["--log", str(r["log"])] if r["log"] else []) if r else []
    code = main(argv + ["--timeout", str(args.timeout)])
    for name, new in runs(state):
        if new.get("args") == a:
            new["restarts"] = budget
            with open(os.path.join(state, "runs", name + ".json"), "w") as f:
                json.dump(new, f, indent=2)
            commands()["send"].restore(state, name, carried, new)
    return code
