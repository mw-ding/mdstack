"""`mdstack acked` checks an `mdstack send` message by the `ack: <msg-id>` line in the window's status file; for a run
on a role host it pulls that file's new lines into the primary's mirror first (#346). `--delivery` (#1850) prints the
message's delivery record instead: one JSON line with its separate delivery, worker and disposition axes and the next
action, read only; exit 0 when acked, 3 when not, 2 (nothing written) for a message not in this project's local inbox.

Usage: mdstack acked WINDOW MSG-ID [--wait SECS | --delivery] --project FILE
"""
import json
from crew_shared import commands, profile, remote_run, runs, tmux, wait_ack


def register(sub):
    p = sub.add_parser("acked")
    p.add_argument("window")
    p.add_argument("id")
    p.add_argument("--wait", type=float, default=0.0, help="seconds to wait for the ack (default: check once)")
    p.add_argument("--delivery", action="store_true", help="print the message's delivery record (JSON), read only")
    p.add_argument("--project")
    p.add_argument("--org-profile")


def run(args):
    values, session, state = profile(args)
    rec = dict(runs(state)).get(args.window, {})
    if args.delivery:
        send = commands()["send"]
        windows = dict((n, i) for i, n in tmux.list_windows(session)) if tmux.has_session(session) else {}
        d = None if remote_run.host_of(rec) else send.delivery(
            state, session, args.window, args.id, rec or None, windows, send.ours(args.project, args.org_profile, values))
        if d is None:
            print("crew: refusing delivery read: no message %s for this project in %s's local inbox; nothing written" % (
                args.id, args.window))
            return 2
        print(json.dumps(d, sort_keys=True))
        return 0 if d["ack"] else 3
    return wait_ack(state, args.window, args.id, args.wait,
                    remote_run.refresh(values, state, args.window, rec) if remote_run.host_of(rec) else None)
