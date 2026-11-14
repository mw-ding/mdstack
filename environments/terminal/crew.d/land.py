"""`mdstack land status|request|resume|done` drives an asynchronous land (docs/interfaces.md#asynchronous-land-design,
#873 B2 and B3).

Usage: mdstack land status|request|done --project FILE [--org-profile FILE] --pr N --head SHA
       mdstack land resume --project FILE [--org-profile FILE]

Only for a change backend that declares land.mode = "async"; a sync backend is refused. Runs under a tmux or
session profile (#1351). The commands come from
the backend map's change.land-status, change.read-head and change.land, with the change placeholder
(land.change_placeholder, default <n>) and <head-sha> filled (#1042). change.land must carry <head-sha> unless the
manifest declares land.head_guard = false; the head re-read right before the request is kept either way.
A declared land.status maps native status output to the five states; change.read-landed reads the landed revision
when a landed pattern captures none. Output no declared pattern matches, or more than one, is unknown.
status: one land-status read for the change at the pinned head; prints the state, exit 1 when unknown.
request: run after the final §7 gate check. Reads land-status and requests only on `none`, and only while the
change head still equals --head. A failed request call (a lost acknowledgement) is resolved by reading the
status again, never by a resend. Then polls every runtime.options.land_poll_interval seconds until `landed`
(exit 0, prints the landed revision) or `failed`, an unknown status or runtime.options.land_timeout (exit 1,
`blocked:`). Takes no land lock and builds no train.
Intent: request records land/<pr>-<head>.json in the state dir before its first status read. `landed` marks it
landed and prints the merge record's landed-revision line and marker; `failed`, a stale head and a lost
acknowledgement reading `none` drop it; a timeout or an unknown status keeps it.
resume: on every wake, reads land-status for each recorded intent and never requests: `queued` or `landing` polls
as above, `landed` prints the pending record, `none` (never requested at that head) and `failed` drop the intent.
done: after the merge post, clears an intent marked landed; any other intent is refused.
stack, stack-done: a session profile whose change backend declares land.stack = true lands a linear stack in one
atomic request (`--stack N:SHA,N:SHA,...`, base first; _land_stack.py, #1605); resume reads stack intents back too.
#1722: land.change_placeholder fills every per-member stack command in either mode; change.read-revision-id must carry
<head-sha>; land.stack_status = "per-change" reads each member through land-status as `status` does.
#1859 (team §9.5): every intent records the selected project's context; request, resume and done refuse an intent
naming another repo before any read, request or drop, and a stack member may be qualified `<owner>/<name>#<n>:<sha>`:
one naming another repo refuses the whole stack with nothing written.
"""
import datetime
import glob
import json
import os
import re
import subprocess
import time
from crew_shared import crew_render, load, profile, refuse_paused, require_ownership

land_stack = load("crew_land_stack", "environments/terminal/crew.d/_land_stack.py")
repo_bind = load("crew_repo_bind", "environments/terminal/crew.d/_repo_bind.py")

STATUS = re.compile(r"(none|queued|landing)|landed ([0-9a-f]{40}|[0-9a-f]{64})|failed (\S.*)")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def register(sub):
    p = sub.add_parser("land")
    p.add_argument("action", choices=["status", "request", "resume", "done", "stack", "stack-done"])
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--pr", type=int)
    p.add_argument("--head")
    p.add_argument("--stack", help="N:SHA,N:SHA,... base first (stack, stack-done)")


def command(renderer, op, pr, head, land):
    """The backend map's change.<op> with install-time placeholders, the change placeholder and <head-sha> filled,
    on one line."""
    cmd = renderer.line("<op:change.%s>" % op)
    if op == "land" and land["head_guard"] and "<head-sha>" not in cmd:
        raise ValueError("change.land carries no <head-sha> guard; declare land.head_guard = false if the backend "
                         "has none")
    if op == "read-revision-id" and "<head-sha>" not in cmd:
        raise ValueError("change.read-revision-id carries no <head-sha>; a revision id binds a checked head")
    cmd = cmd.replace("<%s>" % land["change_placeholder"], str(pr)).replace("<head-sha>", head)
    left = crew_render.TOKEN.search(cmd)
    if left:
        raise ValueError("change.%s keeps an unfilled placeholder %s" % (op, left.group(0)))
    return re.sub(r"\s*\n\s*", " ", cmd)


def call(cmd):
    """(exit code, whole stdout less one trailing newline) of a backend command; a hung call counts as failed.
    Extra lines stay in the output, so a malformed multi-line status or head never matches."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return 124, ""
    out = r.stdout[:-1] if r.stdout.endswith("\n") else r.stdout
    return r.returncode, out.strip(" \t\r")


def read_status(cmds, status=None):
    """("none"|"queued"|"landing"|"landed"|"failed", detail), or ("unknown", why); unknown never means none.
    status: the declared land.status mapping {pattern: state}, which replaces the core grammar."""
    code, out = call(cmds["land-status"])
    if code != 0:
        return "unknown", "exit %d, output %r" % (code, out)
    if not status:
        m = STATUS.fullmatch(out)
        if not m:
            return "unknown", "exit %d, output %r" % (code, out)
        if m.group(1):
            return m.group(1), ""
        return ("landed", m.group(2)) if m.group(2) else ("failed", m.group(3))
    hits = [(m, state) for m, state in ((re.fullmatch(p, out), state) for p, state in status.items()) if m]
    if len(hits) != 1:
        return "unknown", "output %r matches %d declared land.status patterns" % (out, len(hits))
    m, state = hits[0]
    if state == "failed":
        return "failed", m.groupdict().get("reason") or out
    if state != "landed":
        return state, ""
    revision = m.groupdict().get("revision")
    if revision is None and "read-landed" not in cmds:
        return "unknown", "landed, but output %r captured no revision" % out
    if revision is None:
        code, revision = call(cmds["read-landed"])
        if code != 0:
            return "unknown", "landed, but change.read-landed exit %d, output %r" % (code, revision)
    if not SHA.fullmatch(revision):
        return "unknown", "landed, but revision %r is not a full commit SHA" % revision
    return "landed", revision


def intent_path(state, pr, head):
    return os.path.join(state, "land", "%d-%s.json" % (pr, head))


def save_intent(path, intent):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(intent, f)
    os.replace(path + ".tmp", path)


def drop_intent(path):
    if os.path.exists(path):
        os.remove(path)


def binder(args, values):
    """(the context an intent records, why a recorded intent is not this repo's or None)."""
    ctx, team = repo_bind.context(args.project, values), "team.name" in values
    return ctx, lambda intent: repo_bind.foreign(ctx, team, records=[("recorded land intent", intent)])


def poll(cmds, values, tag, state, detail, status):
    """Poll a queued or landing land to its end: ("landed", revision), ("timeout", why) or (state, detail)."""
    deadline = time.monotonic() + values["runtime.options.land_timeout"]
    while state in ("queued", "landing"):
        if time.monotonic() >= deadline:
            return "timeout", "after %ds, still %s" % (values["runtime.options.land_timeout"], state)
        print("crew: land %s: %s" % (tag, state), flush=True)
        time.sleep(values["runtime.options.land_poll_interval"])
        state, detail = read_status(cmds, status)
    return state, detail


def finish(path, intent, meta, values, tag, state, detail):
    """Report a terminal or given-up land and keep, mark or drop its intent; exit code 0 only on `landed`."""
    if state == "landed":
        save_intent(path, dict(intent, landed=detail))
        tested = ("; tested with `%s` by the backend's land check (`land.tests_against_tip`) on the landed revision"
                  % values["repo.default_branch"]) if meta.get("land.tests_against_tip", (False,))[0] else ""
        print("crew: landed %s as %s" % (tag, detail))
        print("record: Landed revision: `%s` (checked head `%s`)%s." % (detail, intent["head"], tested))
        print("marker: <!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a landed=%s -->"
              % (intent["pr"], intent["head"], detail))
        return 0
    if state in ("timeout", "unknown"):
        print("blocked: land %s: %s %s; intent kept, mdstack land resume reads it back" % (tag, state, detail))
        return 1
    drop_intent(path)
    print("blocked: land %s: %s%s" % (tag, state, ": " + detail if detail else ""))
    return 1


def commands_for(renderer, pr, head, land, ops=("land-status", "read-head", "land")):
    ops = list(ops)
    if crew_render.crew_config.landed_needs_read(land["status"]):
        ops.append("read-landed")
    return {op: command(renderer, op, pr, head, land) for op in ops}


def run(args):
    if args.action in ("stack", "stack-done"):
        return run_stack(args)
    values, _, state_dir = profile(args, runtimes=("tmux", "session"))  # session async land binding (#1351)
    if args.stack is not None:
        print("crew: --stack only goes with land stack or stack-done")
        return 1
    if args.action == "resume":
        if args.pr is not None or args.head is not None:
            print("crew: land resume takes no --pr or --head; it reads every recorded intent")
            return 1
    elif args.pr is None or args.head is None:
        print("crew: land %s needs --pr and --head" % args.action)
        return 1
    elif not SHA.fullmatch(args.head):
        print("crew: --head must be a full lowercase commit SHA, got %r" % args.head)
        return 1
    ctx, foreign = binder(args, values)
    if args.action == "done":
        path = intent_path(state_dir, args.pr, args.head)
        try:
            with open(path) as f:
                intent = json.load(f)
            landed = intent.get("landed")
        except (OSError, ValueError, AttributeError):
            intent = landed = None
        tag = "#%d @ %s" % (args.pr, args.head[:7])
        if landed and foreign(intent):
            print("crew: refusing done %s: %s; intent kept" % (tag, foreign(intent)))
            return 1
        if not landed:
            print("crew: refusing done %s: no intent marked landed; only a confirmed landed status completes a land"
                  % tag)
            return 1
        drop_intent(path)
        print("crew: land %s done (landed %s); intent cleared" % (tag, landed))
        return 0
    meta = {}
    crew_render.crew_config.resolve_profile(args.project, args.org_profile, meta=meta)
    stacked = args.action == "resume" and stack_declared(meta, values)
    if meta.get("land.mode", ("sync",))[0] != "async" and not stacked:
        tag = "#%d @ %s" % (args.pr, args.head[:7]) if args.pr is not None else "resume"
        print("crew: refusing land %s: the change backend's land.mode is sync; land with change.land" % tag)
        return 1
    land = {"change_placeholder": meta.get("land.change_placeholder", ("n",))[0],
            "head_guard": meta.get("land.head_guard", (True,))[0], "status": meta.get("land.status", ({},))[0]}
    if args.action == "request" and (not require_ownership(values, "land") or refuse_paused(state_dir, "land request")):
        return 1
    renderer = crew_render.Renderer(values, os.path.join(os.path.dirname(crew_render.HERE), "templates"),
                                    overlay=crew_render.pack_overlay(args.project, args.org_profile, values))
    if args.action == "resume":
        code = resume_stacks(renderer, values, meta, land, state_dir, ctx, foreign) if stacked else 0
        if meta.get("land.mode", ("sync",))[0] != "async":
            return code
        for path in sorted(glob.glob(os.path.join(state_dir, "land", "*.json"))):
            try:
                with open(path) as f:
                    intent = json.load(f)
                tag = "#%d @ %s" % (intent["pr"], intent["head"][:7])
                cmds = commands_for(renderer, intent["pr"], intent["head"], land)
            except (OSError, ValueError, KeyError, TypeError) as e:
                print("blocked: land intent %s unreadable (%s); nothing requested" % (os.path.basename(path), e))
                code = 1
                continue
            if foreign(intent):
                print("blocked: land intent %s: %s; nothing read, requested or dropped" % (
                    os.path.basename(path), foreign(intent)))
                code = 1
                continue
            state, detail = read_status(cmds, land["status"])
            if state == "none":
                drop_intent(path)
                print("blocked: land %s: never requested at this head; intent dropped, rerun the §7 gate check "
                      "before a request" % tag)
                code = 1
                continue
            state, detail = poll(cmds, values, tag, state, detail, land["status"])
            code = finish(path, intent, meta, values, tag, state, detail) or code
        return code
    tag = "#%d @ %s" % (args.pr, args.head[:7])
    try:
        cmds = commands_for(renderer, args.pr, args.head, land)
    except ValueError as e:
        print("crew: refusing land %s: %s" % (tag, e))
        return 1
    if args.action == "status":
        state, detail = read_status(cmds, land["status"])
        print(" ".join(filter(None, (state, detail))))
        return 1 if state == "unknown" else 0
    path = intent_path(state_dir, args.pr, args.head)
    intent = {"pr": args.pr, "head": args.head, "context": ctx,
              "recorded": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if os.path.exists(path):
        try:
            with open(path) as f:
                recorded = json.load(f)
        except (OSError, ValueError):
            recorded = "unreadable"
        if foreign(recorded):
            print("crew: refusing land %s: %s; nothing read, requested or dropped" % (tag, foreign(recorded)))
            return 1
    else:
        save_intent(path, intent)  # intent first: a restart reads this change and head back before anything else
    state, detail = read_status(cmds, land["status"])
    if state == "none":
        code, head = call(cmds["read-head"])
        if code != 0 or head != args.head:
            drop_intent(path)
            print("blocked: land %s: stale head, change head is %r; no request sent, rerun the §7 gates at the "
                  "new head" % (tag, head))
            return 1
        sent = call(cmds["land"])[0] == 0  # a lost acknowledgement is read back, never resent
        state, detail = read_status(cmds, land["status"])
        if state == "none":
            drop_intent(path)
            print("blocked: land %s: request %s and land-status is none; rerun the §7 gate check before a new "
                  "request" % (tag, "sent" if sent else "failed"))
            return 1
    state, detail = poll(cmds, values, tag, state, detail, land["status"])
    return finish(path, intent, meta, values, tag, state, detail)


def stack_declared(meta, values):
    return values["runtime.name"] == "session" and meta.get("land.stack", (False,))[0]


def stack_land(meta):
    return {"change_placeholder": meta.get("land.change_placeholder", ("n",))[0],
            "head_guard": meta.get("land.head_guard", (True,))[0], "status": meta.get("land.status", ({},))[0],
            "per_change": meta.get("land.stack_status", ("stack",))[0] == "per-change"}


def stack_commands(renderer, members, land, revisions=None):
    def single(op, pr, head):
        return command(renderer, op, pr, head, land)
    member = (lambda pr, head: commands_for(renderer, pr, head, land, ("land-status",))) if land["per_change"] else None
    return land_stack.commands(renderer, members, single, revisions, member)


def stack_reader(land):
    return (lambda cmds: read_status(cmds, land["status"])) if land["per_change"] else None


def resume_stacks(renderer, values, meta, land, state_dir, ctx, foreign):
    need = meta.get("land.stack_tests_against_tip", (False,))[0]
    land = stack_land(meta)
    return land_stack.resume(call, lambda members, revisions: stack_commands(renderer, members, land, revisions),
                             values, need, state_dir, stack_reader(land), (ctx, foreign))


def run_stack(args):
    """land stack|stack-done: the session stack land (#1605); refused unless the change backend declares land.stack."""
    values, _, state_dir = profile(args, runtimes=("session",))
    if args.pr is not None or args.head is not None:
        print("crew: land %s takes --stack, not --pr or --head" % args.action)
        return 1
    try:
        members, qualifiers = land_stack.parse(args.stack, qualified=True)
    except ValueError as e:
        print("crew: %s" % e)
        return 1
    ctx, foreign = binder(args, values)
    problem = repo_bind.foreign(ctx, "team.name" in values,
                                repos=[("stack member #%d" % c, q) for (c, _), q in zip(members, qualifiers)])
    if problem:  # a mixed-repo stack: refused whole, before any intent, read or request (team §9.5)
        print("crew: refusing land %s: %s; nothing written, read or requested" % (land_stack.tag(members), problem))
        return 1
    if args.action == "stack-done":
        return land_stack.done(members, state_dir, foreign)
    meta = {}
    crew_render.crew_config.resolve_profile(args.project, args.org_profile, meta=meta)
    if not stack_declared(meta, values):
        print("crew: refusing land %s: the change backend declares no land.stack; land each change alone"
              % land_stack.tag(members))
        return 1
    if not require_ownership(values, "land"):
        return 1
    land = stack_land(meta)
    renderer = crew_render.Renderer(values, os.path.join(os.path.dirname(crew_render.HERE), "templates"),
                                    overlay=crew_render.pack_overlay(args.project, args.org_profile, values))
    try:
        cmds = stack_commands(renderer, members, land)
    except ValueError as e:
        print("crew: refusing land %s: %s" % (land_stack.tag(members), e))
        return 1
    need = meta.get("land.stack_tests_against_tip", (False,))[0]
    return land_stack.request(call, cmds, members, values, need, state_dir,
                              lambda revisions: stack_commands(renderer, members, land, revisions), stack_reader(land),
                              (ctx, foreign))
