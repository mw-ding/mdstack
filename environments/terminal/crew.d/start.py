"""`mdstack start` is the owner's start-or-reattach command for a tmux crew (#1919): exactly `mdstack up --attach`
(#1845), which stays as its alias. It runs `mdstack up`, so a running crew gets no second session or watcher, then
attaches this terminal interactively to window 0 of the crew session on its configured server; from a client of that
server it switches the client there (`switch-client`) instead of nesting. A client of another tmux server (exit 1) or
a crew pane with `CREW_ROLE` set (exit 2) is refused before anything starts.

Without --project it uses the default config like other owner commands ($CREW_PROJECT, else $MDSTACK_CONFIG, else
<user root>/config.toml) and names it on stderr; a missing, invalid or ambiguous config (a team file with several
repos and no #REPO) refuses before anything starts. It takes no --team or ROLE. `<home>/start` from
`mdstack layout --write` runs it; --attach is accepted, redundant, for wrapper calls written before it.

Usage: mdstack start [--project FILE[#REPO]] [--org-profile FILE] [--inputs DIR] [--coordinator-only] [--resume ID]
"""
import argparse
from crew_shared import commands


def register(sub):
    p = sub.add_parser("start")
    p.add_argument("role", nargs="?", help=argparse.SUPPRESS)  # refused: start takes --project only
    which = p.add_mutually_exclusive_group()
    which.add_argument("--project")
    which.add_argument("--team", help=argparse.SUPPRESS)  # refused, as for up --attach
    p.add_argument("--org-profile")
    p.add_argument("--inputs", default=commands()["up"].TEMPLATES, help="render inputs dir (default: templates/)")
    p.add_argument("--coordinator-only", action="store_true", help="start no role windows (as launch.roles = none)")
    p.add_argument("--resume", metavar="ID", help="resume this coordinator conversation, or ask (as launch.resume)")
    p.add_argument("--attach", action="store_true", help=argparse.SUPPRESS)  # redundant: older <home>/start calls


def run(args):
    return commands()["up"].up_attach(argparse.Namespace(**dict(vars(args), attach=True)), verb="start")
