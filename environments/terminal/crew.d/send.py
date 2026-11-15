"""`mdstack send` messages a role window by reference: a refs-only inbox line and a fixed nudge, typed once with its
submit confirmed (earlier nudges stacked in the composer cleared, `Enter` retried, exit 4 when it never submits; no
key at all into a window showing a dialog, #315). An unsubmitted nudge's id goes to inbox/<window>.undelivered.
The window lookup and inbox append share the queue lock with route's synthesizer check and reap.
Solo findings/CI/merge-up refs are never delivered to builder windows. An `unblocked` to the coordinator that matches an
earlier `blocked` message's refs is recorded in its inbox without a nudge (#578). A run on a role host gets the message
through its host's `send` verb, which appends the inbox line and types the nudge there; an unreachable host fails
after the bounded call (exit 1), never queued, and `--wait-ack` reads the ack from the pulled status mirror (#346).
Each local inbox line and queued builder message carries this project's closed `context` work envelope, naming the
change and head of refs `#n <sha>` (a role host's inbox line keeps its refs-only shape); `--context` passes an upstream envelope on and refuses, with nothing written or
sent, one that is malformed or not this project's (#1856). A team's `(team, pool)` lead has its inbox and acks at the
team root; a builder window may carry its repo tag (`<name>-<issue>-<owner>__<repo>`, #1858).

Usage: mdstack send WINDOW KIND REF... [--wait-ack SECS] --project FILE
"""
import contextlib
import json
import os
import re
import time
from crew_shared import (BUSY, commands, COMPOSER, coordinator_window, crew_render, dialog, lead_state, NAMES, probe,
                         profile, queue_lock, remote_run, tmux, wait_ack, runs, synthesizer_work, window_alias,
                         work_context)


WORKER = r"-\d+(?:-[a-z0-9_-]+)?"  # a builder window: <name>-<issue>, in a team with its repo tag (#1858)


# mdstack send (tmux.md C3): refs only. A ref is an issue/PR number, a full SHA, an https link or a path; no whitespace,
# so no diff or log fits, and lines that open a diff hunk or a traceback are refused outright.
KIND = re.compile(r"[a-z][a-z0-9-]{0,31}")
REF = re.compile(r"#\d+|[0-9a-f]{40}|https://[^\s]+|[\w.~/-]+")
MARKER = re.compile(r"^(---|\+\+\+|@@)|Traceback")
MAX_REF, MAX_LINE = 200, 1024
# Verified nudge (#308): a composer's first row opens with a harness adapter's prompt glyph (Codex `›`, Claude Code
# `❯` and a no-break space) and later rows are indented two spaces; a stale nudge is a whole composer line
# `inbox: <msg-id>`.
GLYPH = COMPOSER
NUDGE = re.compile(r"inbox: \d{8}T\d{6}Z-[0-9a-f]{6}")
RETRIES, PAUSE = 3, 0.5


def composer_draft(screen, at):
    """The composer rows from the prompt-glyph row down to the cursor row at (column, row), glyph and indent
    stripped; None when the cursor is not in a composer (no glyph row above it through blank or indented rows)."""
    rows = screen.split("\n")
    if not at or at[1] >= len(rows):
        return None
    for top in range(at[1], -1, -1):
        if GLYPH.match(rows[top]):
            return [GLYPH.sub("", rows[top], 1).strip()] + [r.strip() for r in rows[top + 1:at[1] + 1]]
        if rows[top].strip() and not rows[top].startswith("  "):
            return None
    return None


def stale_nudges(screen, at):
    """The earlier nudge lines a composer holds when they are all it holds and the cursor ends them; else [] (an
    empty composer, other text, a cursor inside the draft or an unknown screen: nothing is cleared)."""
    lines, rows = composer_draft(screen, at), screen.split("\n")
    below = rows[at[1] + 1] if lines is not None and at[1] + 1 < len(rows) else ""
    if not lines or at[0] < len(rows[at[1]].rstrip()) or below.startswith("  ") and below.strip():
        return []
    text = [line for line in lines if line]
    return lines if text and all(NUDGE.fullmatch(line) for line in text) else []


def nudge(session, index, text):
    """Type the nudge once and confirm the submit (firstmate's pattern): clear earlier nudges stacked in the
    composer, type, Enter, and while the nudge is still in the composer retry Enter only, never retyping. None when
    submitted (or no composer is on screen to tell), else why not. A dialog on screen gets no key at all: a
    permission or approval prompt preselects yes, so the nudge's Enter could approve it (#315)."""
    def view():
        return tmux.capture(session, index), tmux.cursor(session, index)
    if dialog(session, index):
        return "dialog: a prompt is on its screen; nothing typed"
    if "doorbell" in tmux.CAPABILITIES:
        return tmux.doorbell(session, index, text)
    stale = stale_nudges(*view())
    if stale:
        tmux.press(session, index, *["C-u"] * (2 * len(stale)))  # C-u clears a line, then joins it to the one above
        time.sleep(PAUSE)
        if any(NUDGE.fullmatch(line) for line in composer_draft(*view()) or []):
            return "its composer still holds earlier inbox lines after the clear; nothing typed"
        print("crew: cleared %d earlier inbox line(s) from the composer" % sum(1 for line in stale if line))
    tmux.send_keys(session, index, text)
    for retry in range(RETRIES + 1):
        time.sleep(PAUSE)
        if text not in (composer_draft(*view()) or []):
            return None
        if retry < RETRIES:
            if dialog(session, index):
                return "dialog: a prompt came up after the nudge was typed; Enter not retried"
            tmux.press(session, index, "Enter")
    return "`%s` is still in its composer after %d Enter retries" % (text, RETRIES)


# Delivery (#1850): delivery, worker and disposition are separate axes. runs/<window>.delivery.jsonl is the durable
# ledger (removed with the run): one `recorded` event per message, with the run identity and the status file's size at
# send, then one `submitted` or `failed` per nudge. Only an `ack: <id>` past that size discharges a message.
def ledger(state, window):
    return os.path.join(state, "runs", window + ".delivery.jsonl")


def note(state, window, msg_id, event, **kv):
    """Append one ledger event; a partial last line (a writer killed mid-append) is ended first, never extended."""
    os.makedirs(os.path.join(state, "runs"), exist_ok=True)
    line = json.dumps(dict(id=msg_id, event=event, at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **kv))
    with open(ledger(state, window), "ab+") as f:
        f.seek(max(f.seek(0, 2) - 1, 0))
        f.write((b"\n" if f.read(1) not in (b"", b"\n") else b"") + line.encode() + b"\n")


def lines(path):
    """The JSON objects of a JSONL file; a missing file or a partial line (a writer killed mid-append) adds none."""
    found = []
    with contextlib.suppress(FileNotFoundError):
        with open(path, encoding="utf-8") as f:
            for line in f:
                with contextlib.suppress(ValueError):
                    found += [m for m in [json.loads(line)] if isinstance(m, dict)]
    return found


def run_id(rec):
    return commands()["watch"].run_identity(rec) if rec else None


def recorded(state, window, msg_id, rec):
    """Record a new message in the ledger: the run it goes to and the status size an ack must follow."""
    status = os.path.join(state, "status", window + ".status")
    note(state, window, msg_id, "recorded", run=run_id(rec), status=os.path.getsize(status) if os.path.exists(status) else 0)


def submitted(state, window, msg_id, rec, failed):
    note(state, window, msg_id, "failed" if failed else "submitted", run=run_id(rec), **{"reason": failed} if failed else {})


def ack_after(state, window, msg_id, offset):
    """The target's own `ack: <id>` line written after offset (a shorter, rewritten file is read whole)."""
    try:
        with open(os.path.join(state, "status", window + ".status"), "rb") as f:
            data = f.read()
    except FileNotFoundError:
        return False
    text = data[offset if offset <= len(data) else 0:].decode("utf-8", "replace")
    return any(line.split()[:2] == ["ack:", msg_id] for line in text.splitlines())


def worker(session, name, rec, windows):
    """The worker axis: busy|idle|dead|missing|ambiguous|quota|unreachable. Busy and idle come only from the adapters'
    declared screens (a BUSY line, else a composer row); a screen showing neither is ambiguous, never idle."""
    if rec is None:
        return "ambiguous"
    if not tmux.has_session(session):
        return "unreachable"
    cls = probe(session, name, rec, windows)
    if cls != "alive":
        return cls
    screen = tmux.capture(session, rec["index"])
    if any(b.search(screen.lower()) for b in BUSY):
        return "busy"
    return "idle" if any(GLYPH.match(row) for row in screen.splitlines()) else "ambiguous"


def ours(project, org_profile, values):
    """Whether a message's envelope is this project's; a message without one is not."""
    config, ctx = crew_render.crew_config, work_context(project, values)
    return lambda env: env is not None and not config.envelope_problem(
        env, ctx, lambda ref: config.project_identity(ref, org_profile))


def delivery(state, session, window, msg_id, rec, windows, mine):
    """The delivery record D of msg_id in window's inbox, or None when the inbox has no such message or its envelope
    fails mine. Disposition and action follow D2.1-D2.3: only the actual ack dispatches; busy waits under the same id;
    dead/missing/quota take the run's one restart; idle takes one re-nudge per run; anything else escalates, untyped."""
    msgs = lines(os.path.join(state, "inbox", window + ".jsonl"))
    msg = next((m for m in msgs if m.get("id") == msg_id), None)
    if msg is None or not mine(msg.get("context")):
        return None
    found = [e for e in lines(ledger(state, window)) if e.get("id") == msg_id]
    first = next((e for e in reversed(found) if e.get("event") == "recorded"), {})  # the latest run it was recorded for
    tries = [e for e in found if e.get("event") in ("submitted", "failed") and e.get("run") == run_id(rec)]
    ack, who = ack_after(state, window, msg_id, first.get("status", 0)), worker(session, window, rec, windows)
    later = [m for m in msgs[msgs.index(msg) + 1:] if m.get("kind") == msg["kind"] and
             m.get("refs", [])[:1] == msg["refs"][:1] and mine(m.get("context"))]  # another project's never supersedes
    refs = set(re.findall(r"#\d+", " ".join([msg["refs"][0], str((rec or {}).get("item", ""))])))
    restarts = (rec or {}).get("restarts", 0)
    if ack:
        disposition, action, why = "dispatched", "none", "acked"
    elif later:
        disposition, action, why = "superseded", "none", "superseded by " + later[-1]["id"]
    elif who == "busy":
        disposition, action, why = "pending", "wait", "worker busy; same id kept"
    elif refs & commands()["watch"].held(state):
        disposition, action, why = "pending", "wait", "item held"
    elif who in ("dead", "missing", "quota"):
        disposition, action, why = ("pending", "restart", "worker " + who) if not restarts else \
            ("blocked", "escalate", "worker %s after its one restart" % who)
    elif who == "idle" and len(tries) < 2:
        disposition, action, why = "pending", "nudge", "worker idle, unacked after %d nudge(s)" % len(tries)
    else:
        disposition, action, why = "blocked", "escalate", "idle-unacked after one re-nudge" if who == "idle" else \
            "worker %s; nothing typed" % who
    return {"id": msg_id, "window": window, "context": msg.get("context"), "kind": msg["kind"], "refs": msg["refs"],
            "run": first.get("run"), "ledger": bool(first), "inbox": True, "submit": tries[-1]["event"] if tries else None, "ack": ack,
            "delivery": "acked" if ack else tries[-1]["event"] if tries else "recorded", "worker": who,
            "disposition": disposition, "action": action, "reason": why, "nudges": len(tries), "restarts": restarts,
            "observed": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def pending(state, session, name, rec, windows, mine):
    """Delivery records of name's ledger-recorded messages that are neither acked nor superseded (the watcher's
    token-free re-probe, D2.4)."""
    ids = dict.fromkeys(e["id"] for e in lines(ledger(state, name)) if e.get("event") == "recorded" and "id" in e)
    found = [delivery(state, session, name, i, rec, windows, mine) for i in ids]
    return [d for d in found if d and d["disposition"] in ("pending", "blocked")]


def carry(state, name):
    """name's unacked inbox messages, for a restart that removes the run's files (#1850, D2.3)."""
    status = os.path.join(state, "status", name + ".status")
    acks = {line.split()[1] for line in lines_text(status) if line.split()[:1] == ["ack:"] and len(line.split()) > 1}
    return [m for m in lines(os.path.join(state, "inbox", name + ".jsonl")) if m.get("id") not in acks]


def lines_text(path):
    with contextlib.suppress(FileNotFoundError):
        with open(path, encoding="utf-8") as f:
            return f.read().splitlines()
    return []


def restore(state, name, messages, rec):
    """Put carried messages back in the successor's inbox under their original ids, each recorded for the new run."""
    if not messages:
        return
    os.makedirs(os.path.join(state, "inbox"), exist_ok=True)
    with queue_lock(state), open(os.path.join(state, "inbox", name + ".jsonl"), "a", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m) + "\n")
            recorded(state, name, m["id"], rec)
    print("crew: kept %d pending inbox message(s) for %s: %s" % (len(messages), name, " ".join(m["id"] for m in messages)))


def remote_send(values, state, args, rec, msg):
    """mdstack send to a run on a role host: one bounded call (retried with its request id while unreachable)."""
    # The envelope was checked here; a role host's send verb keeps its closed {id, kind, refs, from, ts} shape.
    reply = remote_run.send(values, args.window, rec, {k: v for k, v in msg.items() if k != "context"})
    if reply["result"] != "ok":
        print("crew: send to %s on %s failed: %s; not delivered%s" % (
            args.window, rec["host"], reply["result"] + ": " + (reply.get("reason") or reply.get("error") or ""),
            "; probe the run" if reply["result"] == "unreachable" else ""))
        return 1
    if reply.get("nudge"):
        print("crew: nudge not submitted: %s to %s on %s: %s; the message is in its inbox there; treat %s as ambiguous"
              % (msg["id"], args.window, rec["host"], reply["nudge"], args.window))
        return 4
    print("crew: sent %s to %s on %s" % (msg["id"], args.window, rec["host"]))
    return wait_ack(state, args.window, msg["id"], args.wait_ack, remote_run.refresh(values, state, args.window, rec)) \
        if args.wait_ack is not None else 0


def register(sub):
    p = sub.add_parser("send")
    p.add_argument("window")
    p.add_argument("kind")
    p.add_argument("refs", nargs="+")
    p.add_argument("--wait-ack", type=float, help="seconds to wait for ack: <msg-id> in the status file")
    p.add_argument("--context", help="the work envelope (JSON) this message carries; refused unless it is this project's")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    values, session, state = profile(args)
    args.window = window_alias(values, args.window)
    bad = [r for r in args.refs if len(r) > MAX_REF or not REF.fullmatch(r) or MARKER.search(r)]
    if not KIND.fullmatch(args.kind) or bad:
        print("crew: refusing send: refs only (issue/PR #n, full SHA, https link, path; max %d chars each): %s" %
              (MAX_REF, ", ".join(repr(r[:40]) for r in bad) or "bad kind %r" % args.kind[:40]))
        return 2
    config, given = crew_render.crew_config, getattr(args, "context", None)
    if given is None:  # refs `#n <sha>` name change n at that head, as route reads a builder message's refs
        change = len(args.refs) > 1 and re.fullmatch(r"#\d+", args.refs[0]) and re.fullmatch(r"[0-9a-f]{40}", args.refs[1])
        env = config.envelope(work_context(args.project, values), change=int(args.refs[0][1:]) if change else None,
                              head=args.refs[1] if change else None)
    else:
        try:
            env = json.loads(given) if isinstance(given, str) else given
        except ValueError:
            env = None
        problem = config.envelope_problem(env, work_context(args.project, values),
                                          lambda ref: config.project_identity(ref, args.org_profile))
        if problem:
            print("crew: refusing send: %s; nothing written" % problem)
            return 2
    builder = values.get("identities.builder.name", NAMES["builder"]).lower()
    if re.fullmatch(re.escape(builder) + WORKER, args.window) and args.kind in ("fix", "ci-red", "merge-up") and \
            re.fullmatch(r"#\d+", args.refs[0]):
        if commands()["lead"].solo(values, pr=int(args.refs[0][1:])):
            print("crew: solo item; skip builder delivery; post findings/CI on the PR for the owner's session")
            return 0
    msg = {"id": "%s-%s" % (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()), os.urandom(3).hex()), "kind": args.kind,
           "refs": args.refs, "from": os.environ.get("CREW_ID") or os.environ.get("CREW_ROLE") or "coordinator",
           "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    line = json.dumps(msg) + "\n"
    if len(line.encode()) > MAX_LINE:
        print("crew: refusing send: message is %d bytes, over %d; send fewer refs" % (len(line.encode()), MAX_LINE))
        return 2
    msg["context"] = env  # outside the refs-only bound: the durable envelope (team §9.3)
    line = json.dumps(msg) + "\n"
    rec = dict(runs(state)).get(args.window, {})
    if remote_run.host_of(rec):
        return remote_send(values, state, args, rec, msg)
    queue = state  # a builder message queues for this repo's route; a team lead's inbox is at the team root (#1858)
    if args.window in dict(commands()["lead"].records(state)):
        state = lead_state(state)
    with queue_lock(state):
        windows = dict((n, i) for i, n in tmux.list_windows(session)) if tmux.has_session(session) else {}
        index = windows.get(args.window)
        if index is None:
            builder = values.get("identities.builder.name", NAMES["builder"]).lower()
            if re.fullmatch(re.escape(builder) + WORKER, args.window) and args.kind in ("fix", "ci-red") and \
                    len(args.refs) >= 2 and re.fullmatch(r"#\d+", args.refs[0]) and re.fullmatch(r"[0-9a-f]{40}", args.refs[1]):
                with open(os.path.join(queue, "wake", "queue.jsonl"), "a") as f:
                    f.write(json.dumps(dict(event="builder-message", window=args.window, kind=args.kind,
                                           refs=args.refs, reason="send", id=msg["id"], context=env)) + "\n")
                print("crew: queued builder message %s for route" % msg["id"])
                return 0
            print("crew: refusing send: no window %s in %s" % (args.window, session))
            return 1
        os.makedirs(os.path.join(state, "inbox"), exist_ok=True)
        inbox = os.path.join(state, "inbox", args.window + ".jsonl")
        # A worker's pending message with the same kind, refs and envelope keeps its id: a duplicate send never adds a
        # second message (#1850, D2.2).
        same = [m["id"] for m in lines(inbox) if [m.get("kind"), m.get("refs"), m.get("context")] == [args.kind, args.refs, env]]
        prior = rec and same and delivery(state, session, args.window, same[-1], rec, windows,
                                                  ours(args.project, args.org_profile, values))
        prior = prior if prior and prior["disposition"] in ("pending", "blocked") else None
        resolved = False
        if args.kind == "unblocked" and args.window == coordinator_window(values) and \
                os.path.exists(inbox):
            with open(inbox, encoding="utf-8") as f:
                resolved = any(m["kind"] == "blocked" and m["refs"] == args.refs for m in map(json.loads, f))
        if not prior:  # the ledger first: an interrupted send leaves no inbox message the watcher cannot see
            if rec:
                recorded(state, args.window, msg["id"], rec)
            with open(inbox, "a", encoding="utf-8") as f:
                f.write(line)
        elif not prior["ledger"]:  # an inbox line from before the ledger: record it now, under its id
            recorded(state, args.window, prior["id"], rec)
        if dict(runs(state)).get(args.window, {}).get("role") == "synthesizer":
            synthesizer_work(state, args.window)
    if resolved:  # a self-resolved block closes its own blocked message; the coordinator reads it on its next wake
        print("crew: recorded %s to %s; block resolved itself, no nudge" % (msg["id"], args.window))
        return 0
    if prior and prior["action"] == "wait":  # busy (or held): no Enter, no duplicate, no fault; the same id waits
        print("crew: pending %s to %s: %s; not sent again, nothing typed" % (prior["id"], args.window, prior["reason"]))
        return wait_ack(state, args.window, prior["id"], args.wait_ack) if args.wait_ack is not None else 0
    if prior and prior["action"] != "nudge":
        print("crew: nudge not submitted: %s to %s: %s (%s); the message is in the inbox; treat %s as ambiguous" % (
            prior["id"], args.window, prior["reason"], prior["action"], args.window))
        return 4
    msg_id = prior["id"] if prior else msg["id"]
    failed = nudge(session, index, "inbox: " + msg_id)  # a nudge only; the inbox file is the message
    if rec:
        submitted(state, args.window, msg_id, rec, failed)
    if failed:  # kept until the window acks it or the operator clears it: mdstack upgrade waits on it (#1618)
        with open(os.path.join(state, "inbox", args.window + ".undelivered"), "a", encoding="utf-8") as f:
            f.write(msg_id + "\n")
        print("crew: nudge not submitted: %s to %s: %s; the message is in the inbox; treat %s as ambiguous" % (
            msg_id, args.window, failed, args.window))
        return 4
    print("crew: sent %s to %s%s" % (msg_id, args.window, " (pending id kept)" if prior else ""))
    return wait_ack(state, args.window, msg_id, args.wait_ack) if args.wait_ack is not None else 0
