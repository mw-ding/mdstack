"""A29 bidirectional handoff between two full teams (docs/campaign-scenarios/A29.md, #1441), run by `a28/teams.py
--handoff` while both teams are up and ready. `seed` writes the fake forge's live records before `mdstack up`: team a's
`claimed` post on control item 1, a dependency set (#3, its PR #4, #5 depending on #3), a change in review round 1 (#7,
PR #8), a pending owner ask (#9, crew:needs-md) and a backlog item (#10). `roundtrip` runs the real `mdstack handoff`
commands a → b (drain) and b → a (stop) and checks the record: each state once per handoff id, exactly one ack each,
one writer at every step, the outgoing session and watcher gone before `stopped`, the same sets, stages and heads in
both manifests, the kept run named, the round and the ask untouched, and no other post or write on the forge."""
import json
import os
import re
import subprocess
import sys

STATES = ["claimed", "draining", "offered", "acked", "stopped", "draining", "offered", "acked", "stopped"]
SETS = [["#3", "#4", "#5"], ["#7", "#8"], ["#9"]]


def seed(gh, sha):
    claim = "<!-- crew:v1 role=coordinator pass=handoff handoff=20261109-a29a29 state=claimed from=none to=tmux@a " \
            "cmd-id=chat sha=%s round=n/a verdict=n/a -->" % sha
    verdict = "<!-- crew:v1 role=reviewer pass=verdict pr=8 sha=%s round=1 verdict=changes -->" % ("8" * 40)

    def iss(n, labels, body="", pr=False):
        return dict(number=n, labels=[{"name": x} for x in labels], body=body, assignees=[], milestone=None,
                    **({"pull_request": {}} if pr else {}))

    with open(os.path.join(gh, "api.json"), "w") as f:
        json.dump({"issues/1/comments": [dict(id=1, user={"login": "sandbox-coordinator"}, body=claim,
                                              created_at="2026-11-09T00:00:00.000000Z", probe=None)],
                   "commits/main": {"sha": sha},
                   "issues": [iss(3, ["crew:in-review"]), iss(4, ["crew:in-review"], "Closes #3", True),
                              iss(5, ["crew:ready"], "Depends on #3"), iss(7, ["crew:changes"]),
                              iss(8, ["crew:changes"], "Closes #7", True), iss(9, ["crew:needs-md"]), iss(10, [])],
                   "pulls": [dict(number=4, head={"sha": "4" * 40}), dict(number=8, head={"sha": "8" * 40})],
                   "pulls/8/reviews": [dict(body=verdict, submitted_at="2026-11-09T00:00:01Z")]}, f)


def roundtrip(src, teams, states, gh, ready, emit):
    """`states` maps each team to (session, state dir); `ready(name)` waits until that team's roles probe alive."""
    cli = [sys.executable, os.path.join(src, "cli", "mdstack")]
    flags = {t["name"]: ["--project", t["project"], "--org-profile", t["org_profile"]] for t in teams}
    with open(os.path.join(gh, "post-probe"), "w") as f:  # each post keeps which sessions and watchers were alive
        f.write("".join('tmux has-session -t "=%s" 2>/dev/null && printf "T%s=up " || printf "T%s=gone "\n'
                        'kill -0 "$(cat %s/wake/watcher.pid 2>/dev/null)" 2>/dev/null && printf "W%s=alive " || '
                        'printf "W%s=gone "\n' % (s, n.upper(), n.upper(), d, n.upper(), n.upper()) for n, (s, d) in sorted(states.items())))
    log, problems = [], []

    def run(team, *args):
        r = subprocess.run(cli + list(args) + flags[team], capture_output=True, text=True,
                           env=dict(os.environ, CREW_PROJECT=flags[team][1]))
        log.append("%s: mdstack %s: exit %d: %s" % (team, " ".join(args), r.returncode, (r.stdout + r.stderr).strip()))
        if r.returncode:
            problems.append("%s: mdstack %s: exit %d" % (team, " ".join(args[:2]), r.returncode))

    def writer():  # who may write now: one team, or nobody while ownership is in transit
        return "".join(t for t in "ab" if subprocess.run(
            cli + ["ownership", "--action", "write"] + flags[t], capture_output=True).returncode == 0) or "-"

    def leg(frm, to, mode):
        sig, writers = ["--signature", "s-" + frm], []
        for args in (("to", "tmux@" + to, "--mode", mode, *sig), ("manifest", "--post", "--mode", mode, *sig)):
            run(frm, "handoff", *args)
            writers.append(writer())
        run(to, "handoff", "reconcile")
        for _ in range(2):  # the repeated ack posts nothing: exactly one ack per handoff id
            run(to, "handoff", "ack", "--signature", "s-" + to)
        writers.append(writer())
        run(to, "up")  # the new owner starts its whole team: b ran read-only (coordinator only), a went down
        for pool in ("builder", "reviewer", "synthesizer"):  # as its coordinator does on wake; a no-op for a lead already alive
            run(to, "lead", "ensure", pool)
        problems.extend([] if ready(to) else ["%s: roles not alive after up" % to])
        run(frm, "handoff", "stopped", "--foreground", *sig)
        run(to, "handoff", "lift")
        writers.append(writer())
        if writers != [frm, "-", to, to]:  # draining, offered, acked, stopped
            problems.append("%s->%s writers %s" % (frm, to, writers))
        return writers

    run("a", "spawn", "builder", "--issue", "3", "--timeout", "10")  # in-flight work the handoff must keep
    writers = {"a->b": leg("a", "b", "drain"), "b->a": leg("b", "a", "stop")}
    with open(os.path.join(gh, "api.json")) as f:
        api = json.load(f)
    posts = [(m.group(1), m.group(2), c["probe"], c["body"]) for c in api["issues/1/comments"]
             for m in [re.search(r"pass=handoff handoff=(\S+) state=(\S+) ", c["body"])] if m]
    if [p[1] for p in posts] != STATES:
        problems.append("record states %s" % [p[1] for p in posts])
    ids = sorted({p[0] for p in posts if p[1] == "draining"})
    problems += ["%s: %d acks" % (h, n) for h in ids for n in [[p[:2] for p in posts].count((h, "acked"))] if n != 1]
    stops = [p[2] or "" for p in posts if p[1] == "stopped"]
    if len(ids) != 2 or len(stops) != 2 or not {"TA=gone", "WA=gone"} <= set(stops[0].split()) or \
            not {"TB=gone", "WB=gone"} <= set(stops[1].split()):
        problems.append("stopped posted before the outgoing session and watcher were gone: %s" % stops)
    manifests = [json.loads(re.search(r"```json\n(.*?)\n```", p[3], re.S).group(1)) for p in posts if p[1] == "offered"]
    sets = [[[i["item"] for i in s["items"]] for s in m["sets"]] for m in manifests]
    facts = [{i["item"]: (i["stage"], i["head"]) for s in m["sets"] for i in s["items"]} for m in manifests]
    if sets != [SETS, SETS] or facts[0] != facts[1] or facts[0]["#4"] != ("in-review", "4" * 40) or \
            facts[0]["#8"] != ("changes", "8" * 40) or facts[0]["#9"][0] != "needs-md":
        problems.append("sets, stages or heads moved: %s %s" % (sets, facts))
    kept = [r["end"] for s in manifests[0]["sets"] for i in s["items"] if i["item"] == "#3" for r in i["runs"]]
    if kept != ["kept"]:
        problems.append("#3 runs in the a->b manifest: %s" % kept)
    posted = sorted(k for k, v in api.items() if isinstance(v, list) and any("probe" in x for x in v
                                                                           if isinstance(x, dict)))
    with open(os.path.join(os.path.dirname(gh), "gh.log")) as f:
        writes = [x.strip() for x in f if re.match(r"(pr|issue) (comment|review|edit|create|merge)", x)]
    if len(api["pulls/8/reviews"]) != 1 or posted != ["issues/1/comments"] or writes:
        problems.append("round or forge changed: %d reviews, posts on %s, writes %s" % (
            len(api["pulls/8/reviews"]), posted, writes))
    return emit("handoff", problems, writers=writers, record=[p[:3] for p in posts], sets=sets[0] if sets else [],
                versions={m["from"]: m["eng_crew_version"] for m in manifests}, log=log)
