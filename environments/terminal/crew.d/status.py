"""`mdstack status` prints the coordinator's and each run's liveness (alive, dead, missing, ambiguous; a trust or Codex
hooks-review dialog on screen is ambiguous) from its pane identity, and the host placement chose for each run (- for
a record from before placement or a crew with no [hosts] inventory, #207). A run on a role host shows its host's probe
(#345), `unreachable` when the host does not answer, with `since <time>` once the watcher's pulls have failed 3 scans
in a row (#347).

Usage: mdstack status --project FILE [--org-profile FILE]
       mdstack status --all --project FILE [--org-profile FILE]
       mdstack status register --project FILE [--org-profile FILE]
       mdstack status publish [--check] --project FILE [--org-profile FILE]

Shared status (docs/specs/shared-status.md, #1313): `register` creates this install's one slot comment on the
[status] destination issue, once; `publish` writes one status record into it (the watcher's timer runs it every
[status] publish_interval while enabled); `--check` runs only the read phase and prints the record it would publish,
or the refusal. A refusal writes nothing and exits 1 with the reason on stderr; a usage error exits 2. `--all` reads
every instance's record from the destination, read-only and with no running session: one row per instance with its
age and fresh, stale, invalid or conflict state, then `diagnostic:` lines; exit 1 on an incomplete read (`partial:`),
2 on a usage or config error, 3 when [status] destination is unset.
"""
import subprocess
import time
from crew_shared import ENGINE_CMD, harness_up, heartbeat, load, probe, profile, remote_run, runs, tmux

status_shared = load("crew_status_shared", "environments/terminal/crew.d/_status_shared.py")


def register(sub):
    p = sub.add_parser("status")
    p.add_argument("action", nargs="?", choices=["register", "publish"], help="shared status: register or publish")
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--all", action="store_true", help="every registered instance's record from the destination")
    p.add_argument("--check", action="store_true", help="with publish: the read phase only; no write")


def run(args):
    """Table of role runs: window, role, host, item, head, last status line, heartbeat age, liveness."""
    if args.action or args.all or args.check:  # shared status (#1313); plain status is unchanged
        return status_shared.main(args)
    values, session, state = profile(args)
    windows = dict((n, i) for i, n in tmux.list_windows(session))
    rows = [("WINDOW", "ROLE", "HOST", "ITEM", "HEAD", "BEAT", "LIVENESS", "LAST")]
    p = tmux.pane(session, 0) if 0 in windows.values() else None
    if p:
        rows.append(([n for n, i in windows.items() if i == 0][0], "coordinator", "-", "-", "-", "-",
                     "dead" if p["dead"] == "1" else harness_up(session, 0, p, ENGINE_CMD.values()), "-"))
    for name, rec in runs(state):
        last, beat = heartbeat(state, name)
        head = subprocess.run(["git", "-C", rec.get("worktree") or "/nonexistent", "rev-parse", "--short=7", "HEAD"],
                              capture_output=True, text=True).stdout.strip() or "-"
        cls = remote_run.probe(values, name, rec) if remote_run.host_of(rec) else probe(session, name, rec, windows)
        since = remote_run.outage(state, rec["host"]) if cls == "unreachable" else None
        rows.append((name, rec["role"], rec.get("host") or "-", rec["item"], head, "%dm" % ((time.time() - beat) // 60),
                     cls + time.strftime(" since %Y-%m-%dT%H:%M:%SZ", time.gmtime(since)) if since else cls, last or "-"))
    widths = [max(len(r[i]) for r in rows) for i in range(7)]
    print("\n".join("  ".join(c.ljust(w) for c, w in zip(r, widths)) + "  " + r[7] for r in rows))
    return 0
