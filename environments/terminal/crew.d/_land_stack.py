"""Session stack land (docs/interfaces.md#stack-land, #1605), driven by `mdstack land stack|stack-done|resume`.

A change backend declaring land.stack = true lands a linear stack of changes in one atomic request:
change.land-stack with <stack> filled as space-separated <change>:<head-sha> pairs, base first; change.stack-status
reads it back with one line per member, in stack order, `<change> none|queued|landing|landed <revision>|failed
<reason>`, then, when the backend has run its combined-stack check, a last `check <reference>` line. Under
land.stack_tests_against_tip a landed stack without that line is unknown: the declaration alone is no receipt.

Atomic means every member reads the same state: all none (never requested), all queued or landing (poll), all
landed (each with a full revision), all failed. A mixed state, a missing, extra or reordered member line or a
malformed line is unknown, never none, and records no merge. The request runs only on all none, after
change.read-head returns each member's checked head; a lost acknowledgement is read back, never resent. The intent
land/stack/<base change>-<base head>.json is recorded before the first read; `landed` marks it and prints one merge
record line and marker per member; failed, a stale member head and a request reading none drop it; a timeout or an
unknown state keeps it for `mdstack land resume`, which never requests. stack-done clears an intent marked landed.

#1722: change.land-stack may name the stack by <stack-top> (the last member), <stack-changes> (member ids, base first)
and <stack-revisions> (each member's immutable backend revision id, same order) instead of <stack>. Revision ids come
from change.read-revision-id at each member's checked head, must be single safe tokens, and are recorded in the intent
before the first status read; a rerun or resume uses the recorded set, never a new one. land.stack_status =
"per-change" reads each member's change.land-status (mapped by land.status, change.read-landed for the revision) in
place of change.stack-status; members in different states, queued against landing included, are unknown.

#1859 (team §9.5): a member may be qualified `<owner>/<name>#<n>:<sha>`; the caller refuses the whole stack when
one names another repo. Each intent records the selected project's context, and request, resume and stack-done refuse
an intent naming another repo before any read, request or drop.
"""
import datetime
import glob
import json
import os
import re
import time

QUALIFIED = re.compile(r"(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)#)?(.*)")
MEMBER = re.compile(r"(\S+) (?:(none|queued|landing)|landed ([0-9a-f]{40}|[0-9a-f]{64})|failed (\S.*))")
CHECK = re.compile(r"check (\S+)")
SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
REVISION = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+@-]{0,127}")  # one shell-safe word, substituted into commands


def parse(text, qualified=False):
    """--stack N:SHA,N:SHA,... (base first) -> [(change, head)]; ValueError unless two or more distinct changes.
    qualified: members may carry an `<owner>/<name>#` prefix; returns (members, [lowercase qualifier or None])."""
    members, qualifiers = [], []
    for part in (text or "").split(","):
        repo, rest = QUALIFIED.fullmatch(part).groups() if qualified else (None, part)
        change, _, head = rest.partition(":")
        if not change.isdigit() or not SHA.fullmatch(head):
            raise ValueError("--stack member %r is not <n>:<full lowercase head sha>%s" % (
                part, ", optionally <owner>/<name>#-qualified" if qualified else ""))
        members.append((int(change), head))
        qualifiers.append(repo.lower() if repo else None)
    if len(members) < 2 or len({c for c, _ in members}) != len(members):
        raise ValueError("--stack needs two or more distinct changes, base first")
    return (members, qualifiers) if qualified else members


def tag(members):
    return "stack " + ", ".join("#%d @ %s" % (c, h[:7]) for c, h in members)


def intent_path(state, members):
    return os.path.join(state, "land", "stack", "%d-%s.json" % members[0])


def commands(renderer, members, single, revisions=None, member=None):
    """change.land-stack and, without member, change.stack-status with the stack placeholders filled, plus each
    member's change.read-head; single builds one member's command as `mdstack land` does. member(change, head) builds
    one member's per-change status commands. A land-stack naming <stack-revisions> with no revisions yet gets
    read-revision-id per member and land-stack None; the caller resolves them and builds again."""
    fill = {"<stack>": " ".join("%d:%s" % m for m in members), "<stack-top>": str(members[-1][0]),
            "<stack-changes>": " ".join(str(c) for c, _ in members)}
    if revisions is not None:
        if len(revisions) != len(members) or not all(isinstance(r, str) and REVISION.fullmatch(r) for r in revisions):
            raise ValueError("revision ids %r are not one safe token per member" % (revisions,))
        fill["<stack-revisions>"] = " ".join(revisions)
    cmds = {}
    for op, keys in (("land-stack", ("<stack>", "<stack-revisions>")),
                     ("stack-status", ("<stack>", "<stack-changes>", "<stack-revisions>"))):
        if op == "stack-status" and member:
            continue
        cmd = renderer.line("<op:change.%s>" % op)
        if not any(k in cmd for k in keys):
            raise ValueError("change.%s carries no %s placeholder" % (op, " or ".join(keys)))
        if "<stack-revisions>" in cmd and revisions is None:
            cmds["read-revision-id"] = {c: single("read-revision-id", c, h) for c, h in members}
            cmds[op] = None
            continue
        for key, value in fill.items():
            cmd = cmd.replace(key, value)
        left = re.search(r"<([^<>\s!/=-][^<>\n]*)>", cmd)
        if left:
            raise ValueError("change.%s keeps an unfilled placeholder %s" % (op, left.group(0)))
        cmds[op] = re.sub(r"\s*\n\s*", " ", cmd)
    cmds["read-head"] = {c: single("read-head", c, h) for c, h in members}
    if member:
        cmds["member"] = {c: member(c, h) for c, h in members}
    return cmds


def revision_ids(call, cmds, members):
    """Each member's revision id from change.read-revision-id at its checked head, or (None, why)."""
    found = []
    for change, _ in members:
        code, out = call(cmds["read-revision-id"][change])
        if code != 0 or not REVISION.fullmatch(out):
            return None, "#%d revision id read exit %d, output %r is not one safe token" % (change, code, out)
        found.append(out)
    return found, ""


def read_members(cmds, members, read_one):
    """land.stack_status = "per-change": each member's own status, atomic as a stack readback is."""
    states, details = [], []
    for change, _ in members:
        state, detail = read_one(cmds["member"][change])
        if state == "unknown":
            return "unknown", "#%d: %s" % (change, detail)
        states.append(state)
        details.append(detail)
    kinds = set(states)
    if kinds == {"landed"}:
        return "landed", (details, None)
    if kinds == {"none"}:
        return "none", ""
    if kinds in ({"queued"}, {"landing"}):
        return "landing", ""
    if kinds == {"failed"}:
        return "failed", details[0]
    return "unknown", "members disagree (%s); an atomic stack land never splits" % ", ".join(states)


def read(call, cmds, members, need_check, read_one=None):
    """("none"|"landing"|"failed", detail), ("landed", ([revision per member], check or None)) or ("unknown", why)."""
    if "member" in cmds:
        return read_members(cmds, members, read_one)
    code, out = call(cmds["stack-status"])
    if code != 0:
        return "unknown", "exit %d, output %r" % (code, out)
    lines = [ln.strip(" \t\r") for ln in out.split("\n")]
    check = CHECK.fullmatch(lines[-1]) if lines else None
    if check:
        lines = lines[:-1]
    if len(lines) != len(members):
        return "unknown", "readback names %d member lines, expected %d" % (len(lines), len(members))
    states = []
    for line, (change, _) in zip(lines, members):
        m = MEMBER.fullmatch(line)
        if not m or m.group(1) != str(change):
            return "unknown", "readback line %r is not #%d's state" % (line, change)
        states.append(m.group(2) or ("landed" if m.group(3) else "failed"))
    kinds = set(states)
    if kinds == {"landed"}:
        if need_check and not check:
            return "unknown", "landed, but no `check <reference>` line for the declared combined-stack test"
        revisions = [MEMBER.fullmatch(ln).group(3) for ln in lines]
        return "landed", (revisions, check.group(1) if check else None)
    if kinds == {"none"}:
        return "none", ""
    if kinds <= {"queued", "landing"}:
        return "landing", ""
    if kinds == {"failed"}:
        return "failed", MEMBER.fullmatch(lines[0]).group(4)
    return "unknown", "members disagree (%s); an atomic stack land never splits" % ", ".join(states)


def save(path, intent):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w") as f:
        json.dump(intent, f)
    os.replace(path + ".tmp", path)


def drop(path):
    if os.path.exists(path):
        os.remove(path)


def poll(call, cmds, members, values, need, state, detail, read_one=None):
    deadline = time.monotonic() + values["runtime.options.land_timeout"]
    while state == "landing":
        if time.monotonic() >= deadline:
            return "timeout", "after %ds, still landing" % values["runtime.options.land_timeout"]
        print("crew: land %s: landing" % tag(members), flush=True)
        time.sleep(values["runtime.options.land_poll_interval"])
        state, detail = read(call, cmds, members, need, read_one)
    return state, detail


def finish(path, intent, members, values, state, detail):
    """Report a terminal or given-up stack land; one merge record line and marker per member, exit 0, only on landed."""
    if state == "landed":
        revisions, check = detail
        save(path, dict(intent, landed=revisions, check=check))
        names = ", ".join("#%d" % c for c, _ in members)
        tested = ("; tested as a combined stack on `%s` by the backend's stack land check `%s` "
                  "(`land.stack_tests_against_tip`)" % (values["repo.default_branch"], check)) if check else ""
        for (change, head), revision in zip(members, revisions):
            print("crew: landed #%d @ %s as %s" % (change, head[:7], revision))
            print("record: #%d: Landed revision: `%s` (checked head `%s`); stack land of %d (%s)%s."
                  % (change, revision, head, len(members), names, tested))
            print("marker: #%d: <!-- crew:v1 role=synthesizer pass=merge pr=%d sha=%s round=n/a verdict=n/a "
                  "landed=%s -->" % (change, change, head, revision))
        return 0
    if state in ("timeout", "unknown"):
        print("blocked: land %s: %s %s; intent kept, mdstack land resume reads it back" % (tag(members), state, detail))
        return 1
    drop(path)
    print("blocked: land %s: %s%s" % (tag(members), state, ": " + detail if detail else ""))
    return 1


def recorded_intent(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return "unreadable"


def request(call, cmds, members, values, need, state_dir, build=None, read_one=None, bind=(None, None)):
    """cmds from commands(); build(revisions) rebuilds them once revision ids are known. bind: (the context the intent
    records, foreign(recorded intent) -> why it is not this repo's, or None)."""
    path = intent_path(state_dir, members)
    intent = {"members": [list(m) for m in members], "context": bind[0],
              "recorded": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if os.path.exists(path):
        recorded = recorded_intent(path)
        if bind[1] and bind[1](recorded):
            print("blocked: land %s: %s; nothing read, requested or dropped" % (tag(members), bind[1](recorded)))
            return 1
        if [tuple(m) for m in recorded.get("members", [])] != members:
            print("blocked: land %s: another stack intent from this base is recorded; mdstack land resume "
                  "reads it back" % tag(members))
            return 1
        if "read-revision-id" in cmds:  # the recorded set, never a newly resolved one
            if not recorded.get("revisions"):
                print("blocked: land %s: the recorded intent names no revision ids; mdstack land resume reads it "
                      "back" % tag(members))
                return 1
            intent["revisions"] = recorded["revisions"]
    elif "read-revision-id" in cmds:
        revisions, why = revision_ids(call, cmds, members)
        if revisions is None:
            print("blocked: land %s: %s; no request sent for any member, rerun the §7 gates" % (tag(members), why))
            return 1
        intent["revisions"] = revisions
        save(path, intent)  # the ids are recorded before the first status read or request
    else:
        save(path, intent)  # intent first: a restart reads the stack back before anything else
    if "revisions" in intent:
        try:
            cmds = build(intent["revisions"])
        except ValueError as e:
            print("blocked: land %s: %s; nothing requested, mdstack land resume reads it back" % (tag(members), e))
            return 1
    state, detail = read(call, cmds, members, need, read_one)
    if state == "none":
        for change, head in members:
            code, live = call(cmds["read-head"][change])
            if code != 0 or live != head:
                drop(path)
                print("blocked: land %s: stale head, #%d head is %r; no request sent for any member, rerun the §7 "
                      "gates at the new head" % (tag(members), change, live))
                return 1
        sent = call(cmds["land-stack"])[0] == 0  # a lost acknowledgement is read back, never resent
        state, detail = read(call, cmds, members, need, read_one)
        if state == "none":
            drop(path)
            print("blocked: land %s: request %s and %s is none; rerun the §7 gate check for every member "
                  "before a new request" % (tag(members), "sent" if sent else "failed",
                                            "every member's land-status" if read_one else "stack-status"))
            return 1
    state, detail = poll(call, cmds, members, values, need, state, detail, read_one)
    return finish(path, intent, members, values, state, detail)


def resume(call, build, values, need, state_dir, read_one=None, bind=(None, None)):
    """Read every recorded stack intent back; never requests. build(members, revisions) -> cmds, with the recorded
    revision ids."""
    code = 0
    for path in sorted(glob.glob(os.path.join(state_dir, "land", "stack", "*.json"))):
        problem = bind[1] and bind[1](recorded_intent(path))
        if problem:
            print("blocked: stack land intent %s: %s; nothing read, requested or dropped" % (
                os.path.basename(path), problem))
            code = 1
            continue
        try:
            with open(path) as f:
                intent = json.load(f)
            members = [(int(c), h) for c, h in intent["members"]]
            cmds = build(members, intent.get("revisions"))
            if "read-revision-id" in cmds:
                raise ValueError("no recorded revision ids")
        except (OSError, ValueError, KeyError, TypeError) as e:
            print("blocked: stack land intent %s unreadable (%s); nothing requested" % (os.path.basename(path), e))
            code = 1
            continue
        state, detail = read(call, cmds, members, need, read_one)
        if state == "none":
            drop(path)
            print("blocked: land %s: never requested at these heads; intent dropped, rerun the §7 gate check for "
                  "every member before a request" % tag(members))
            code = 1
            continue
        state, detail = poll(call, cmds, members, values, need, state, detail, read_one)
        code = finish(path, intent, members, values, state, detail) or code
    return code


def done(members, state_dir, foreign=None):
    path = intent_path(state_dir, members)
    try:
        with open(path) as f:
            intent = json.load(f)
    except (OSError, ValueError):
        intent = {}
    if foreign and isinstance(intent, dict) and intent and foreign(intent):
        print("crew: refusing stack-done %s: %s; intent kept" % (tag(members), foreign(intent)))
        return 1
    if not intent.get("landed") or [tuple(m) for m in intent.get("members", [])] != members:
        print("crew: refusing stack-done %s: no matching intent marked landed; only a confirmed landed stack "
              "completes a land" % tag(members))
        return 1
    drop(path)
    print("crew: land %s done; intent cleared" % tag(members))
    return 0
