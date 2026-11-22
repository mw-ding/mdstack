"""Upgrade a tmux or session install from this bundle (or --version), previewing before restarting roles.

Usage: mdstack upgrade --project FILE [--version vX.Y.Z | --latest] [--dry-run] [--yes]
                     [--wait-timeout SECONDS] [--timeout SECONDS]

--version fetches from the profile's [install] source; a source change without --version is refused. --latest is
--version with the latest release's tag (github source only). Under a user-level install (mdstack install,
releases/current present), a --version upgrade also upgrades every other project whose install.json, under the
same state root, runs from that releases directory (a record from before #1317 by the project file in its
`Run mdstack up` step), then flips that root's releases/current, so its <root>/bin launcher follows and another root's stays (#1317,
#1324). Under a user-level install it also rewrites every stale launcher in that root's bin/ (#2023); --dry-run lists
them. A release already on disk is reused once a fresh fetch matches it: that is rollback.
A tmux install with no install.json is adopted first when its link, release VERSION (beside releases/current)
and profile copy verify; otherwise the refusal names the mismatch (#1616).
Run from a separate operator terminal with dispatch paused. Waits for every current pass to finish
before applying, then stops the watcher and starts the persistent one again after the reload (#1346); a timeout leaves the install and sessions untouched. Restarts preserve worktrees,
claims, inboxes and run metadata. Coordinator is last. Grok Bot routine reload remains manual.
A session profile (runtime.name = "session", #1541) applies the install with no in-flight wait or window reload, since
it has no role windows; restart the coordinator (exit it, then mdstack up) to load the new briefs.
A changed pack.harness registry or source re-plans even with an unchanged render and tag; edited
registry targets are reported as drift and never overwritten.
"""
from argparse import Namespace
import json
import os
from pathlib import Path
import shlex
import tempfile
import time
from crew_shared import (
    brief_src, BUSY, commands, coordinator_harness, crew_render, dialog, ENGINE_CMD, harness, harnesses, identity,
    LAUNCH, POINTER, proc, profile, receipts, require_ownership, role_notes, runs, stop_pane, tmux, unacked, wait_harness,
    window_env)


def register(sub):
    p = commands()["bootstrap"].register(sub, "upgrade")
    p.add_argument("--latest", action="store_true", help="--version of the latest release (github source)")
    p.add_argument("--wait-timeout", type=float, default=300)
    p.add_argument("--timeout", type=float, default=15)


def busy(values, state, session, windows):
    """The first window still running a pass, as `name: reason`, or None. A window whose harness adapter declares a
    COMPOSER is idle only on its idle screen: a row opening with that glyph, no mid-turn text, no dialog and no
    unsubmitted `inbox:` nudge on the composer (the coordinator's only delivery state), whatever processes live under
    the pane (a launcher wrapper's harness and MCP servers, #1618). Other adapters stay busy on a live child. A failed
    probe or an unrecognized screen stays busy."""
    records = dict(runs(state))
    leads = dict(commands()["lead"].records(state))
    for index, name in windows:
        if index != 0 and name not in records and name not in leads:
            return name + ": no run record"
        path = Path(state) / "status" / (name + ".status")
        lines = [s for s in path.read_text().splitlines() if not s.startswith("heartbeat:")] if path.exists() else []
        if name in records and (not lines or not lines[-1].startswith(("done:", "blocked:", "failed:"))):
            return name + ": status not finished"
        if name in records and unacked(state, name, lines):
            return name + ": unacknowledged inbox message"
        if name in leads and commands()["lead"].pending(state, name):
            return name + ": pending inbox message"
        undelivered = Path(state) / "inbox" / (name + ".undelivered")  # a failed send's nudge (the coordinator's too)
        acks = set(receipts(state, name))
        if undelivered.exists() and (ids := [i for i in undelivered.read_text().split() if i not in acks]):
            return name + ": undelivered inbox message %s (%s)" % (ids[0], undelivered)
        pane = tmux.pane(session, index)
        if not pane:
            return name + ": pane probe failed"
        screen = tmux.capture(session, index)
        if any(b.search(screen.lower()) for b in BUSY):
            return name + ": harness mid-turn"
        try:
            child = proc.live_child(pane["pid"], pane["command"])
        except RuntimeError as e:
            return name + ": " + str(e)
        rec = records.get(name) or leads.get(name)
        executable = rec.get("harness") if rec else ENGINE_CMD.get(values.get("engines.coordinator"))
        glyph = getattr(harnesses.BY_EXECUTABLE.get(executable), "COMPOSER", "")
        if glyph:
            rows = [row for row in screen.splitlines() if row.startswith(glyph)]
            if not rows or dialog(session, index):
                return name + ": no idle prompt on screen"
            if any(commands()["send"].NUDGE.search(row) for row in rows):
                return name + ": unsubmitted inbox nudge on screen"
        elif child:
            return name + ": live child process"
    return None


def reload(values, session, state, args, windows):
    records = dict(runs(state))
    leads = dict(commands()["lead"].records(state))
    for index, name in sorted(windows, key=lambda w: w[0] == 0):
        rec = records.get(name) or leads.get(name)
        role = rec["role"].removesuffix("-lead") if rec else "coordinator"
        src = Path(brief_src(state, role))
        if name in leads:
            src = Path(state) / "render/runtime" / (role + "-lead.md")
        brief = Path(state) / "runs" / (name + ".brief.md") if name in records else (
            Path(state) / "leads" / (role + ".brief.md") if name in leads else Path(state) / "coordinator.brief.md")
        tail = ""
        if name in records:
            before = brief.read_text()
            _, separator, tail = before.partition("\n## This run\n")
            if not separator:
                raise ValueError("missing run metadata: " + str(brief))
            tail = separator + tail.split("\n## Runtime note:", 1)[0]
        text = src.read_text() + tail + role_notes(values, state, role)
        tmux.hold(session, index)  # the harness is the window's only process: the stop must not destroy it (#1087)
        if stop_pane(session, index):
            raise RuntimeError("process group survived stop: " + name)
        brief.write_text(text)
        cwd = (rec.get("worktree") if rec else None) or str(Path(args.project).absolute().parent)
        engine, model, effort = (rec["engine"], rec["model"], rec["effort"]) if name in records else (
            commands()["spawn"].pick_engine(values, "default") if name in leads else
            (values["engines.coordinator"], "", ""))
        mode = values["runtime.options.permission_mode"]
        argv = harness(engine, model, effort, cwd, state, mode, values) if rec else \
            coordinator_harness(engine, cwd, state, mode, values)
        env = window_env(values, state, role, name, str(brief), args.project)
        if name in leads:
            env.update(CREW_ROLE=role + "-lead", CREW_POOL=role)
        tmux.respawn(session, index, cwd, env, LAUNCH % (shlex.join(argv), POINTER))
        wait_harness(session, index, name, ENGINE_CMD[engine], args.timeout)
        if rec:
            rec.update(identity(session, index))
            path = Path(state) / "runs" / (name + ".json") if name in records else Path(
                commands()["lead"].record_path(state, role))
            path.write_text(json.dumps(rec, indent=2) + "\n")
        print("crew upgrade: reloaded " + name)


def same_pointers(args, previous, live, preview):
    """Whether the pack.harness registry plans exactly the installed targets, contents and launch lines."""
    bootstrap = commands()["bootstrap"]
    harnesses = args.harness if args.harness is not None else previous.get("harnesses", [])
    project = Path(args.project).absolute()
    registry, notes, owned = bootstrap.pack_pointers(harnesses, args.org_profile, project)
    installed = {p for p, entry in previous.get("harness_pointers", {}).items() if entry["harness"] in harnesses}
    launches = bootstrap.harness_launches(harnesses, project, live, preview, notes)
    return (set(owned) == installed and launches == previous.get("launches", [])
            and all(previous["harness_pointers"][p] == owned[p] for p in installed)
            and all(path.is_file() and path.read_bytes() == text.encode() for path, text in registry.items()))


def adopt(args, values, state):
    """install.json for a running user-level install that has none (#1616): `mdstack install` + `layout --write` +
    `up` never write one. Adopts only a tmux install whose link, release VERSION and profile copy all verify."""
    bootstrap = commands()["bootstrap"]
    state, project = Path(state), Path(args.project).absolute()
    link, version, copy = state / "mdstack", state / "VERSION", state / "config.toml"
    bundle = link.resolve()
    if values["runtime.name"] != "tmux":
        problem = "runtime %s: adoption covers a tmux install only" % values["runtime.name"]
    elif not link.is_symlink():
        problem = "no install link at %s" % link
    elif Path(values["paths.mdstack"]).absolute() != link:
        problem = "paths.mdstack names %s, not the install link %s" % (values["paths.mdstack"], link)
    elif not (bundle / "VERSION").is_file() or not (bundle / "cli/mdstack").is_file():
        problem = "missing release: %s has no VERSION or cli/mdstack" % bundle
    elif not (bundle.parent / "current").is_symlink():
        problem = "foreign layout: %s has no releases/current link beside it" % bundle
    elif not version.is_file() or version.read_text() != (bundle / "VERSION").read_text():
        problem = "VERSION mismatch: %s does not match %s/VERSION" % (version, bundle)
    elif not copy.is_file() or copy.read_bytes() != bootstrap.profile_file(project).read_bytes():
        problem = "mismatched project: %s differs from %s" % (copy, project)
    else:
        problem = None
    if problem:
        raise ValueError("no install record in %s and the live install does not verify: %s; run mdstack bootstrap "
                         "--project %s" % (state, problem, project))
    tag = (bundle / "VERSION").read_text().strip()
    if args.dry_run or not args.yes:
        print("crew upgrade: would adopt the %s install at %s (no install.json yet)" % (tag, bundle))
        if args.dry_run:
            print("crew upgrade: dry-run; rerun with --yes to adopt it and upgrade")
            return 0
        raise ValueError("confirmation required; review --dry-run then use --yes")
    record = dict(tag=tag, source=str(bundle), project=str(project), bundle_sha256=None, runtime="tmux",
                  targets={str(version): bootstrap.digest(version), str(copy): bootstrap.digest(copy)},
                  harnesses=[], launches=[], pending_human_steps=[], status="installed", adopted=True)
    (state / "install.json").write_text(json.dumps(record, indent=2) + "\n")
    print("crew upgrade: adopted the %s install at %s into %s" % (tag, bundle, state / "install.json"), flush=True)
    return None


def run(args):
    bootstrap = commands()["bootstrap"]
    try:
        if args.uninstall or args.remove_labels or args.routines_removed or args.smoke:
            raise ValueError("use mdstack bootstrap for uninstall or smoke")
        values, session, state = profile(args, runtimes=("tmux", "session"))
        if session and "reload" not in tmux.CAPABILITIES:
            raise ValueError("%s: in-place upgrade unsupported; stop the crew and restart the updated install" % tmux.name)
        if not require_ownership(values):
            return 1
        manifest = Path(state) / "install.json"
        if not manifest.exists() and adopt(args, values, state) == 0:
            return 0
        if getattr(args, "latest", False):  # an in-process caller may build args without it
            if args.version or values.get("install.source", "github") != "github":
                raise ValueError("--latest needs the github source and no --version")
            args.version = bootstrap.crew_install.latest()
        if args.version:
            if args.dev:
                raise ValueError("--version and --dev cannot be combined")
            return bootstrap.fetch(args)
        installer = commands()["install"]
        root = installer.bundle_root()
        launchers = installer.stale_launchers(root) if root else []  # rewritten with the install (#2023)
        tag = bootstrap.source(args.dev, args.pre)
        bootstrap.pack_pin(args.org_profile, tag, args.project)
        previous = json.loads(manifest.read_text())
        install = bootstrap.install_table(values)
        # Set only by --version, which just fetched and verified this bundle from the profile's source (#1089).
        fetched = os.environ.get("CREW_BOOTSTRAP_BUNDLE_SHA256")
        if not fetched and previous.get("source") == str(bootstrap.ROOT) and not bootstrap.same_source(previous, install):
            raise ValueError("install source changed to %s; this bundle was not fetched from it: run mdstack upgrade "
                             "--version <tag> to fetch and verify it" % " ".join(
                                 filter(None, (install.get("source", "github"), install.get("location")))))
        with tempfile.TemporaryDirectory(prefix="crew-upgrade-") as tmp:
            argv = ["--project", args.project, "--out", tmp] + (["--org-profile", args.org_profile] if args.org_profile else [])
            if crew_render.main(argv):
                return 1
            if bootstrap.budget_render(args.project, args.org_profile, values):
                return 1
            desired = {p.relative_to(tmp): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
            live = Path(state) / "render" if session else Path(values["paths.live_dir"]).absolute()  # as bootstrap
            actual = {p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}
            if (desired == actual and previous["tag"] == tag and same_pointers(args, previous, live, Path(tmp))
                    and previous["source"] == str(bootstrap.ROOT) and bootstrap.same_source(previous, install)
                    and previous.get("bundle_sha256") == (fetched or previous.get("bundle_sha256"))
                    and previous.get("pack") == bootstrap.pack_record(args.org_profile, args.project)
                    and (Path(state) / "config.toml").read_bytes() == bootstrap.profile_file(args.project).read_bytes()
                    and not launchers):
                print("crew upgrade: no changes")
                return 0
            if bootstrap.run(Namespace(**{**vars(args), "dry_run": True})):
                return 1
            if args.dry_run:
                for launcher, _ in launchers:
                    print("crew upgrade: would write launcher %s" % launcher)
                return 0
            if not args.yes:
                raise ValueError("confirmation required; review --dry-run then use --yes")
            for launcher, spelled in launchers:
                installer.write_launcher(launcher, spelled)
                print("crew upgrade: wrote launcher %s" % launcher, flush=True)
            if not session:  # a session profile has no role windows to wait on or reload
                if not require_ownership(values) or bootstrap.run(args):
                    return 1
                print("crew upgrade: session runtime: restart the coordinator (exit it, then mdstack up) to load "
                      "the new briefs")
                return 0
            deadline = time.monotonic() + args.wait_timeout
            while active := busy(values, state, session, tmux.list_windows(session)):
                if time.monotonic() >= deadline:
                    raise ValueError("in-flight pass " + active + "; wait timed out; no install written")
                time.sleep(0.2)
            windows = tmux.list_windows(session)
            if pid := commands()["down"].stop_watcher(state):  # it would re-exec on half-written code (#1346)
                raise ValueError("the watcher (pid %s) is still armed; no install written" % (pid if pid > 0 else "unknown"))
            try:
                if not require_ownership(values) or bootstrap.run(args):
                    return 1
                reload(values, session, state, args, windows)
            finally:
                commands()["up"].watcher(args, state)  # the persistent watcher, on the installed code
        return 0
    except (OSError, ValueError, RuntimeError) as e:
        print("crew upgrade: " + str(e))
        return 1
