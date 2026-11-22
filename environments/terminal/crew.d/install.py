"""`mdstack install` puts a stable `mdstack` on the user's PATH for the release bundle it runs from (#1317).

Usage: mdstack install [--name NAME] [--dry-run]

Run it from a bundle extracted into <root>/releases/, root being ~/.mdstack by default or any other root (#1324).
It points that root's releases/current at the bundle and writes the launcher <root>/bin/mdstack, a shell script
that runs releases/current/cli/mdstack, so a later `mdstack upgrade --version` moves the launcher with no PATH
change. When <root>/bin is not on PATH, it links mdstack into the first directory on PATH under your home that it
can write and that holds no other mdstack (for example ~/.local/bin), else prints the one line to add to your
shell profile. It never edits a shell rc file. --name NAME names the launcher and its PATH link NAME instead, so a
second root does not take the first root's `mdstack`; it never replaces another root's command. --dry-run prints
the plan and writes nothing. Doctor reports a missing or stale launcher and a PATH that resolves its name to
something else. A launcher for a root other than ~/.mdstack sets CREW_ROOT=<root>, so a bare command reads that
root's config.toml (#2023). Re-running is idempotent and rewrites a stale launcher.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
from crew_shared import crew_render, ROOT


def home():
    """The default root: $CREW_ROOT, else ~/.mdstack (#1316, #1324)."""
    return Path(crew_render.crew_config.user_root())


LAUNCHER_HEAD = "#!/bin/sh\n# mdstack launcher, written by mdstack install (#1317): runs the current release.\n"


def launcher_text(root):
    """A root other than ~/.mdstack pins CREW_ROOT, so a bare command reads <root>/config.toml (#2023); an explicit
    --project, $CREW_PROJECT or $MDSTACK_CONFIG still wins. The ~/.mdstack launcher's bytes are unchanged."""
    pin = "" if os.path.realpath(root) == os.path.realpath(Path.home() / ".mdstack") else (
        "CREW_ROOT=%s " % shlex.quote(str(root)))
    return LAUNCHER_HEAD + '%sexec %s "$@"\n' % (pin, shlex.quote(str(root / "releases" / "current" / "cli" / "mdstack")))


def bundle_root():
    """The root of the user-level install this bundle runs from (<root>/releases/<bundle>, releases/current present),
    else None (a checkout or a bundle outside a releases directory)."""
    root, bundle = Path(ROOT).parent.parent, Path(ROOT).resolve()
    releases = root / "releases"
    return root if bundle.parent == releases.resolve() and (releases / "current").is_symlink() else None


def named_root(text, root):
    """The spelling of root a launcher's exec line names, when it is root by realpath (a re-exec'd bundle path is
    resolved, the launcher's need not be), else root."""
    words = shlex.split(text.splitlines()[-1]) if text.strip() else []
    target = next((w for w in words if w.endswith("/releases/current/cli/mdstack")), "")
    named = Path(target.removesuffix("/releases/current/cli/mdstack") or root)
    return named if os.path.realpath(named) == os.path.realpath(root) else root


def stale_launchers(root):
    """(launcher, its root spelling) for every launcher mdstack install wrote in <root>/bin, under any --name, whose
    text is not that root's launcher_text (#2023)."""
    found = []
    for path in sorted((root / "bin").glob("*")):
        text = path.read_text(errors="replace") if path.is_file() and not path.name.startswith(".") else ""
        if not text.startswith(LAUNCHER_HEAD):
            continue
        spelled = named_root(text, root)
        if text != launcher_text(spelled):
            found.append((spelled / "bin" / path.name, spelled))
    return found


def write_launcher(launcher, root):
    launcher.parent.mkdir(parents=True, exist_ok=True)
    tmp = launcher.with_name("." + launcher.name + ".tmp")
    tmp.write_text(launcher_text(root))
    tmp.chmod(0o755)
    os.replace(tmp, launcher)


def path_hint(root):
    shown = str(root / "bin")
    if shown.startswith(os.path.expanduser("~") + os.sep):
        shown = "$HOME" + shown[len(os.path.expanduser("~")):]
    return 'add to your shell profile: export PATH="%s:$PATH"' % shown


def flip(releases, bundle):
    """Point releases/current at bundle (a sibling, linked relatively) in one rename."""
    tmp = releases / ".current.tmp"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(bundle.name, target_is_directory=True)
    os.replace(tmp, releases / "current")


def path_dir(launcher):
    """(directory on PATH that resolves mdstack to the launcher, True), else (a directory under your home it can
    write, to link it there, False), else (None, False). Any other command of that name on PATH leaves (None, False)."""
    dirs = [Path(e) for e in os.environ.get("PATH", "").split(os.pathsep) if e and Path(e).is_absolute()]
    dirs = [d for d in dirs if d.is_dir()]
    for d in dirs:
        target = d / launcher.name
        if d.resolve() == launcher.parent.resolve() or target.is_symlink() and target.resolve() == launcher.resolve():
            return d, True
        if target.exists() or target.is_symlink():
            return None, False  # it shadows any later link; doctor reports it
    user = Path.home().resolve()
    return next(((d, False) for d in dirs if d.resolve().is_relative_to(user) and os.access(d, os.W_OK)), (None, False))


UP_STEP = "Run mdstack up --project "  # the tmux human step every install.json records with its project path


def recorded_project(manifest, record):
    """The project file an install.json names: `project`, else (a record from before #1317) the path in its
    `Run mdstack up --project` step whose bytes still equal the state's config.toml copy; None when neither holds."""
    if record.get("project"):
        file = crew_render.crew_config.split_ref(record["project"])[0]  # FILE or FILE#<repo> (#1344)
        return record["project"] if Path(file).is_file() else None
    copy = manifest.parent / "config.toml"
    for step in record.get("pending_human_steps", []):
        path = Path(step.removeprefix(UP_STEP))
        if step.startswith(UP_STEP) and path.is_file() and copy.is_file() and path.read_bytes() == copy.read_bytes():
            return str(path)
    return None


def served(project, releases):
    """(other project files, install.json paths whose project cannot be recovered) for every install under the same
    state root as project that runs from a bundle in releases: what `mdstack upgrade --version` re-renders after
    project before it moves releases/current (#1317)."""
    values, problems = crew_render.resolve(project, None)
    if problems:
        return [], []
    found, unknown = [], []
    for manifest in sorted(Path(values["paths.state_dir"]).absolute().glob("*/install.json")):
        record = json.loads(manifest.read_text())
        if Path(record.get("source") or "/").resolve().parent != releases.resolve():
            continue
        other = recorded_project(manifest, record)
        if other is None:
            unknown.append(str(manifest))
        elif Path(other).resolve() != Path(project).resolve():
            found.append(other)
    return found, unknown


def follow(args, bundle, argv, env):
    """After `mdstack upgrade --version` upgraded --project from bundle: run the same upgrade for every other
    project this install serves, then flip releases/current to bundle. No user-level install (no current link),
    a dry run, a failed project or an install whose project cannot be recovered flips nothing."""
    releases = bundle.parent
    if not (releases / "current").is_symlink():
        return 0
    projects, unknown = served(args.project, releases)
    failed = []
    for project in projects:
        print("crew upgrade: also upgrading " + project, flush=True)
        argv[argv.index("--project") + 1] = project
        if subprocess.run(argv, env=env).returncode:
            failed.append(project)
    if failed or unknown:
        print("crew upgrade: releases/current not moved; failed: " + ", ".join(failed) if failed else
              "crew upgrade: releases/current not moved; no project file found for " + ", ".join(unknown) +
              ": run mdstack upgrade --version %s --project <its config.toml> --yes, then re-run" % args.version)
        return 1
    if not args.dry_run:
        flip(releases, bundle)
        print("crew upgrade: releases/current -> " + bundle.name)
    return 0


def register(sub):
    p = sub.add_parser("install", help="put a stable mdstack launcher on PATH for this release bundle")
    p.add_argument("--name", default="mdstack", help="the launcher's command name on PATH (default mdstack)")
    p.add_argument("--dry-run", action="store_true", help="print the plan; write nothing")


def run(args):
    try:
        return install(args)
    except OSError as e:
        print("crew install: " + str(e))
        return 1


def install(args):
    root, bundle = Path(ROOT).parent.parent, Path(ROOT).resolve()  # the bundle's own root (#1324)
    releases = root / "releases"
    if bundle.parent != releases.resolve() or not (bundle / "VERSION").is_file():
        print("crew install: run mdstack install from a release bundle extracted into %s/" % (home() / "releases"))
        return 1
    if os.sep in args.name or args.name in ("", ".", ".."):
        print("crew install: --name must be a plain command name")
        return 1
    launcher = root / "bin" / args.name
    current = releases / "current"
    plan = []
    if not current.is_symlink() or current.resolve() != bundle:
        plan.append(("link", "%s -> %s" % (current, bundle.name)))
    if not launcher.is_file() or launcher.read_text() != launcher_text(root):
        plan.append(("launcher", str(launcher)))
    directory, linked = path_dir(launcher)
    if directory and not linked:
        plan.append(("PATH link", "%s -> %s" % (directory / launcher.name, launcher)))
    for step, detail in plan:
        if args.dry_run:
            pass
        elif step == "link":
            flip(releases, bundle)
        elif step == "launcher":
            write_launcher(launcher, root)
        else:
            (directory / launcher.name).symlink_to(launcher)
        print("crew install: %s %s %s" % ("would write" if args.dry_run else "wrote", step, detail))
    if not plan:
        print("crew install: no changes")
    if not directory:
        print("crew install: %s is not on PATH; %s" % (launcher.name, path_hint(root)))
    return 0
