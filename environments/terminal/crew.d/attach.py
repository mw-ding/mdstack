"""`mdstack attach` watches a window read-only (or a temporary tiled builders view), on this host or a run's role host.

A bare `mdstack attach` (#1942) is the owner's way in: it types into the coordinator window of the installed team,
starting the team first if it is down. It uses the installed team: $CREW_PROJECT, else $MDSTACK_CONFIG, else
<user root>/config.toml, else the root's only <team>.toml team file; an owner shell takes no project option and names
one repo with --repo KEY (#1965). A team file needs no #REPO: it runs as
`mdstack up --team` would, so the team's one session, persistent watcher included, starts if down. Then, as
`mdstack start` does, it attaches this terminal to window 0, or switches a client of the crew's tmux server there
instead of nesting. A crew pane or a client of another tmux server is refused before anything starts.
`mdstack attach coordinator` also takes a team file without #REPO; it stays read-only unless --rw.

Usage: mdstack attach [--project FILE[#REPO]] [--org-profile FILE]
       mdstack attach WINDOW|ROLE|builders [--rw] --project FILE [--org-profile FILE]
"""
import argparse
import os
import shlex
import sys
from crew_shared import BANDS, CREW_BIN, commands, crew_render, profile, remote_run, runs, tmux, window_alias


# Observe (#138): attach to a window, or tail a run's step summary (docs/observe.md).
ROLE_BANDS = dict(BANDS, coordinator=(0, 0))
# One pane of the builders view: the last lines of a window's screen (trailing blanks dropped), refreshed every second.
# Values are single-quoted: shlex.quote leaves "=" bare, which zsh (a common default-shell) expands.
SNAPSHOT = "while :; do out=$(tmux capture-pane -p -t '%s' | awk 'NF { n = NR } { l[NR] = $0 } " \
    "END { for (i = 1; i <= n; i++) print l[i] }' | tail -n \"$(($(tput lines) - 1))\"); " \
    "printf '\\033[H\\033[2J== %%s ==\\n%%s' '%s' \"$out\"; sleep 1; done"
# A remote builder's pane: its host's `capture` reply (multi-device.md#observability), every CAPTURE_EVERY seconds
# until the host scan interval lands (#346), so the view never polls a host every second.
CAPTURE_EVERY = 15
REMOTE_SNAPSHOT = "while :; do out=$(%s 2>&1); printf '\\033[H\\033[2J== %%s ==\\n%%s' '%s' \"$out\"; sleep %d; done"


def register(sub):
    p = sub.add_parser("attach")
    p.add_argument("target", nargs="?",
                   help="window name, role (builder, reviewer, synthesizer, coordinator) or builders; omitted, the "
                        "installed team's coordinator, interactive, starting the team if down")
    p.add_argument("--rw", action="store_true", help="interactive attach; read-only by default")
    p.add_argument("--project", default="")  # "", not None: the bare form picks its own default (#1942)
    p.add_argument("--org-profile")
    p.add_argument("--capture", action="store_true", help=argparse.SUPPRESS)  # one remote pane snapshot, for builders


def run(args):
    """Attach read-only (--rw to type) to a window, or to a role's only window; `builders` opens a temporary tiled
    view of the builder band in a separate session, killed on detach, so the mdstack layout never changes."""
    if args.target is None:
        return bare(args)
    args.project = args.project or crew_render.crew_config.default_config()
    if args.target == "coordinator":  # window 0 of the team's one session, whichever repo names it (#1942)
        args.project = team_ref(args.project)[1]
    values, session, state = profile(args)
    remote = {n: rec for n, rec in runs(state) if remote_run.host_of(rec)}
    if args.capture:
        return capture(values, args.target, remote.get(args.target))
    if args.target in remote:
        return attach_remote(values, args.target, remote[args.target], args.rw)
    far = [n for n, rec in remote.items() if rec["role"] == ("builder" if args.target == "builders" else args.target)]
    if not tmux.has_session(session) and not far:
        print("crew: %s not running" % session)
        return 1
    windows = sorted(tmux.list_windows(session)) if tmux.has_session(session) else []
    if args.target == "builders":
        band = [(i, n) for i, n in windows if BANDS["builder"][0] <= i <= BANDS["builder"][1]]
        if not band and not far:
            print("crew: no builder windows")
            return 1
        name = "%s-builders-%d" % (session, os.getpid())
        own = ["--project", os.path.abspath(args.project)] + (
            ["--org-profile", os.path.abspath(args.org_profile)] if args.org_profile else [])
        tmux.view(name, [SNAPSHOT % ("=%s:%d" % (session, i), n) for i, n in band] + [REMOTE_SNAPSHOT % (
            shlex.join([CREW_BIN, "attach", n, "--capture", *own]), "%s on %s" % (n, remote[n]["host"]), CAPTURE_EVERY)
            for n in far])
        try:
            return tmux.attach("=" + name, not args.rw)
        finally:
            tmux.kill_session(name)
    found = [(i, n) for i, n in windows if n == window_alias(values, args.target)]
    if not found and args.target in ROLE_BANDS:
        lo, hi = ROLE_BANDS[args.target]
        found = [(i, n) for i, n in windows if lo <= i <= hi]
        if len(found) + len(far) > 1:
            print("crew: %s has several windows (%s); name one" % (args.target, ", ".join([n for _, n in found] + far)))
            return 1
        if far:
            return attach_remote(values, far[0], remote[far[0]], args.rw)
    if not found:
        print("crew: no window %s in %s" % (args.target, session))
        return 1
    return tmux.attach("=%s:%d" % (session, found[0][0]), not args.rw)


def team_ref(project):
    """(team file, one repo's reference) for a team file named without #REPO; (None, project) otherwise or unreadable,
    so the profile read reports the problem."""
    if "#" in os.path.basename(project):
        return None, project
    try:
        names = crew_render.crew_config.team_repos(project)
    except (OSError, ValueError):
        names = None
    return (project, "%s#%s" % (project, names[0])) if names else (None, project)


def bare(args):
    """The bare form: mdstack start for the installed profile, as up --team for a team file (#1942)."""
    args.project = args.project or crew_render.crew_config.installed_config()
    print("mdstack: config " + os.path.abspath(args.project), file=sys.stderr)  # it may start the crew (#1324)
    team, ref = team_ref(args.project)
    up = commands()["up"]
    return up.up_attach(argparse.Namespace(role=None, project=None if team else args.project, team=team,
                                           org_profile=args.org_profile, inputs=up.TEMPLATES, coordinator_only=False,
                                           resume=None, attach=True), verb="attach", ref=ref if team else None)


def attach_remote(values, name, rec, rw):
    """This terminal on a remote run's pane, through its host's attach verb; read-only unless rw."""
    code = remote_run.attach(values, name, rec, rw)
    if code == 255:
        print("crew: %s unreachable" % rec["host"])
    return code


def capture(values, name, rec):
    """Print a remote run's pane screen once (one pane of the builders view)."""
    if rec is None:
        print("crew: no remote run %s" % name)
        return 1
    reply = remote_run.capture(values, name, rec)
    if reply["result"] != "ok":
        print("crew: %s %s: %s" % (rec["host"], reply["result"], reply.get("reason") or reply.get("error", "")))
        return 1
    print(reply["text"])
    return 0
