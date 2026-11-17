"""Bootstrap core: locate a pinned bundle, resolve, doctor, preview, apply and record (docs/bootstrap.md).

Usage: mdstack bootstrap --project FILE [--org-profile FILE] [--version vX.Y.Z] [--pre] [--dry-run] [--yes] [--dev] [--smoke] [--harness claude-code|codex]
       mdstack bootstrap --project FILE [--proposal FILE] [--runtime tmux|grok-bot] [--flavor thorough|standard|fast|solo]
       mdstack bootstrap --project FILE --uninstall [--dry-run] [--yes] [--remove-labels] [--routines-removed]

Runs doctor read-only before planning; any fail stops without writing an install. A fresh host may need
mdstack doctor --fix first. Apply requires confirmation. tmux keeps rendering and hooks in mdstack up; Grok Bot
deploys the preview to paths.live_dir; its plan notes that triage.enabled installs no Grok timer. Refuses tracked or
locally edited targets. With --harness, also installs the pack.harness registry's entries for the selected
harnesses as data (copy, pointer, Codex launch notes) under the same refusals. Records VERSION, config.toml, install.json and the mdstack link in per-repo state. Never starts
roles or changes credentials.
--version fetches the release from the profile's [install] source (gh for github, the default; url, mirror and git
never call gh), verifies SHA256SUMS (git: the tag against the pinned commit, then that commit's release-bundle.py
builds it), extracts beside this source and runs that bundle's bootstrap. Existing version
directories are never overwritten. Pre-releases require --pre and satisfy no pack pin; an org profile requires
its adjacent manifest.toml pin to match before installation; a pack.toml pack instead needs a framework range
that admits the tag and a clean git checkout, whose commit install.json records (docs/packs.md#pack-plug-ins).
After apply, validates the profile, re-renders every brief, checks path-normalized UTF-8 byte size budgets,
and checks deployed targets and doctor again.
Records failed checks in install.json. --smoke queues a real docs-only issue on a started crew, once per install;
it does not claim the asynchronous pipeline passed. Missing profiles are proposed from local git config,
confirmed (or supplied as edited TOML), and recorded once, including flavor.name; a tmux proposal adds the one-root
[paths] layout under $CREW_ROOT, else ~/.mdstack. By default the profile is $CREW_PROJECT, else
$MDSTACK_CONFIG, else that root's config.toml (#1316, #1324).
"""
import contextlib
from argparse import Namespace
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import tarfile
import tempfile
import tomllib
from crew_shared import checkout, commands, crew_render, git, HERE, load, placeholder_paths, POINTER, tmux
from crew_shared import harnesses as harnesses_module

crew_install = load("crew_install", "scripts/crew-install.py")
crew_pack = load("crew_pack", "core/crew-pack.py")

ROOT = Path(HERE).parent.resolve()


def release_tag(tag, pre):
    match = re.fullmatch(r"v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(-rc\.(0|[1-9]\d*))?", tag)
    if not match:
        raise ValueError("bootstrap needs a release tag vX.Y.Z (or vX.Y.Z-rc.N with --pre)")
    if match[4] and not pre:
        raise ValueError("pre-release tags require --pre and satisfy no pack pin")
    return tag


def source(dev, pre=False):
    if (ROOT / ".git").exists():
        if dev:
            return git(str(ROOT), "rev-parse", "HEAD")
        tag = git(str(ROOT), "describe", "--exact-match", "--tags", "HEAD")
    else:
        tag = (ROOT / "VERSION").read_text().strip()
    return release_tag(tag, pre)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_target(path, old, doctor, project, base=None):
    """Q4 refusals for one target. base, the target's root, bounds the symlink check: the project directory, or
    $HOME for a pack.harness home-root entry (#1032)."""
    parents = [p for p in path.parents if p.is_relative_to(base or project.parent)]
    if any(p.is_symlink() for p in (path, *parents)):
        raise ValueError("symlink target or parent: " + str(path))
    if path.exists() and old.get(str(path)) != digest(path):
        raise ValueError("target edited or unowned: " + str(path))
    root = project.parent if path.is_relative_to(project.parent) else path.parent
    if doctor.sh("git", "-C", str(root), "ls-files", "--error-unmatch", str(path.relative_to(root)))[0] == 0:
        raise ValueError("tracked target: " + str(path))


def spec_scaffold(values, repo):
    """{path: text} seeding the specs home from templates/spec.md when it holds no Markdown spec, else {}
    (docs/project-doc-set.md Specs, #1225). The seed is the owner's to commit: never owned, excluded or overwritten.
    An external specs home ([docs] specs_external, #1725) seeds nothing locally."""
    if values.get("docs.specs_external"):
        return {}
    home = repo / values.get("docs.homes.specs", "docs/specs/")
    if home.is_dir() and any(home.rglob("*.md")):
        return {}
    template = (ROOT / "templates" / "spec.md").read_text()
    return {home / "project.md": template.split("````markdown\n", 1)[1].rsplit("````\n", 1)[0]}


def missing_briefs(rendered, runtime):
    """Roles with native discovery whose brief is not rendered: briefs/<role>.md, else runtime/<discovery name>.md.
    A session profile renders the tmux names (#1541); other runtimes use the grok-bot names."""
    key = "tmux" if runtime in ("tmux", "session") else "grok-bot"
    return [role for role, v in crew_render.ROLES.items() if key in v.get("discovery", {}) and
            not (Path(rendered) / "briefs" / (role + ".md")).is_file() and
            not (Path(rendered) / "runtime" / (v["discovery"][key] + ".md")).is_file()]


def brief_pointer(live, preview, role):
    """The brief pointer naming a rendered role brief in live: briefs/<role>.md, else runtime/<role>.md."""
    relative = Path("briefs") / (role + ".md")
    if not (preview / relative).is_file():
        relative = Path("runtime") / (role + ".md")
    if not (preview / relative).is_file():
        raise ValueError("missing rendered brief: " + str(relative))
    return POINTER.replace("$CREW_BRIEF", str(live / relative))


def harness_launches(harnesses, project, live, preview, notes=()):
    """Each selected adapter's printed coordinator launch line, with the pack launch notes in order."""
    return [harnesses_module.ADAPTERS[h].install_launch(project, brief_pointer(live, preview, "coordinator"), notes)
            for h in harnesses_module.LAUNCH_NOTES if h in harnesses]


def harness_targets(harnesses, project, state, live, preview, old, doctor, notes=()):
    """The selected adapters' install pointers (docs/runtimes/harness-adapters.md Install pointer): their target files,
    each checked before it is read, and their launch lines."""
    targets = {}
    for h in harnesses_module.INSTALLS:
        adapter = harnesses_module.ADAPTERS[h]
        if h in harnesses and hasattr(adapter, "install_targets"):
            targets.update(adapter.install_targets(project, state, lambda role: brief_pointer(live, preview, role),
                                                   lambda path: check_target(path, old, doctor, project)))
    return targets, harness_launches(harnesses, project, live, preview, notes)


def profile_file(project):
    """The TOML file a project reference names: FILE for FILE#<repo> (docs/configuration/team-files.md)."""
    return Path(crew_render.crew_config.split_ref(str(project))[0])


def pack_manifest(org_profile, project=None):
    """The org pack's manifest.toml path, or None without a pack."""
    if org_profile:
        return Path(org_profile).absolute().parent / "manifest.toml"
    if project:
        with open(profile_file(project), "rb") as f:
            paths = tomllib.load(f).get("paths", {})
        pack = paths.get("pack") if isinstance(paths, dict) else None
        if isinstance(pack, str) and pack.strip():
            return profile_file(project).absolute().parent / Path(pack).expanduser() / "manifest.toml"
    return None


def pack_table(org_profile, project=None):
    """The pack's [pack] table, from pack.toml when the pack has one (docs/packs.md#pack-plug-ins), else from its
    manifest.toml; None without a pack."""
    manifest = pack_manifest(org_profile, project)
    if manifest and (manifest.parent / "pack.toml").exists():
        manifest = manifest.parent / "pack.toml"
    if manifest:
        with manifest.open("rb") as f:
            return tomllib.load(f).get("pack", {})
    return None


def target_root(entry, project):
    """A pack.harness file entry's (or harness_pointers record's) root: $HOME for root = "home" (#1032), resolved
    per user at bootstrap; else the project directory."""
    return Path.home() if entry.get("root") == "home" else project.parent


def pack_pointers(harnesses, org_profile, project, anchor=None):
    """The pack.harness registry entries of the selected harnesses (docs/bootstrap.md#pack-harness-pointers-design):
    {target: text}, Codex launch notes, and harness_pointers records. Sources are read as data, never run. anchor,
    whose directory roots project-relative targets, defaults to the project file."""
    targets, notes, owned = {}, [], {}
    manifest = pack_manifest(org_profile, project)
    pack = pack_table(org_profile, project) or {}
    if not harnesses or "harness" not in pack:
        return targets, notes, owned
    problems = []
    crew_render.crew_config.validate_harness_registry(
        lambda path, reason: problems.append("%s: %s" % (path, reason)), pack["harness"], str(manifest.parent))
    if problems:
        raise ValueError("\n".join(problems))
    root = Path(os.path.realpath(manifest.parent))
    for entry in tomllib.loads((root / pack["harness"]).read_text())["pointer"]:
        if entry["harness"] not in harnesses:
            continue
        if "launch_note" in entry:
            notes.append(str(root / entry["launch_note"]))
            continue
        mode, source = entry.get("mode", "copy"), root / entry["source"]
        path = target_root(entry, Path(anchor or project)) / entry["target"]
        targets[path] = source.read_bytes().decode() if mode == "copy" else "Read %s and follow it.\n" % source
        owned[str(path)] = dict(harness=entry["harness"], source=entry["source"], mode=mode)
        if "root" in entry:
            owned[str(path)]["root"] = entry["root"]
    return targets, notes, owned


def pack_record(org_profile, project=None):
    """install.json's pack identity when the manifest declares pack.version (#878); else None, no field. A pack.toml
    pack records its framework range and the commit its clean checkout is pinned at."""
    pack = pack_table(org_profile, project) or {}
    if "framework" in pack:
        return dict({"name": pack["name"]}, **({"version": pack["version"]} if "version" in pack else {}),
                    framework=pack["framework"], commit=crew_pack.commit(str(pack_manifest(org_profile, project).parent)))
    return {"name": pack.get("name"), "version": pack["version"]} if "version" in pack else None


def pack_pin(org_profile, tag, project=None):
    pack = pack_table(org_profile, project)
    if pack is not None and "framework" in pack:  # a pack.toml pack: its framework range, not a single pin
        reason = crew_pack.compatible(pack, tag) if crew_pack.parse_range(pack["framework"]) else \
            "pack %s: malformed framework %r" % (pack.get("name"), pack["framework"])
        if reason:
            raise ValueError(reason + "; install an mdstack release the pack supports, or upgrade the pack")
    elif pack is not None:
        pin = pack.get("mdstack_version")
        if pin != tag or not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
            raise ValueError("pack.mdstack_version must equal the stable installed tag %s; "
                             "follow docs/packs.md Version pin steps" % tag)


def install_table(values):
    """The profile's [install] keys (docs/bootstrap.md Release sources); {} is the github default."""
    return {k[len("install."):]: v for k, v in values.items() if k.startswith("install.")}


def same_source(record, install):
    """Whether install.json's transport names the profile's source kind and location; no field reads as github."""
    transport = record.get("transport") or {}
    return (transport.get("kind", "github"), transport.get("location")) == (
        install.get("source", "github"), install.get("location"))


def bundle_tree(root):
    """Relative path to bytes for every file under root; interpreter caches written by running the bundle are skipped."""
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if "__pycache__" not in p.relative_to(root).parts and not p.is_dir()}


def fetch(args):
    tag = release_tag(args.version, args.pre)
    pack_pin(args.org_profile, tag, args.project)
    install = {}
    if profile_file(args.project).is_file():
        values, problems = crew_render.resolve(args.project, args.org_profile)
        if problems:
            raise ValueError("\n".join(problems))
        install = install_table(values)
    name = crew_install.bundle_name(tag)
    destination = ROOT.parent / name
    if destination.is_symlink():
        raise ValueError("version directory is a symlink; move it aside: " + str(destination))
    if destination.exists():
        # A directory left by an earlier --dry-run or timed-out --yes is reused only once a fresh fetch matches it (#1089).
        with tempfile.TemporaryDirectory(prefix=".crew-refetch-", dir=destination.parent) as tmp:
            sha, sums_sha, commit = crew_install.fetch(install, tag, Path(tmp) / name)
            if bundle_tree(Path(tmp) / name) != bundle_tree(destination):
                raise ValueError("version directory already exists and differs from the verified %s; "
                                 "move it aside: %s" % (tag, destination))
        verb = "reusing matching"
    else:
        sha, sums_sha, commit = crew_install.fetch(install, tag, destination)
        verb = "extracted"
    print("crew bootstrap: verified %s %ssha256=%s; %s %s" % (
        tag, "commit=%s " % commit if commit else "", sha, verb, destination), flush=True)
    argv = [sys.executable, str(destination / "cli/mdstack"), getattr(args, "cmd", "bootstrap"), "--project", args.project]
    if args.org_profile:
        argv += ["--org-profile", args.org_profile]
    for harness in args.harness or []:
        argv += ["--harness", harness]
    for option in ("proposal", "runtime", "flavor"):
        if getattr(args, option) is not None:
            argv += ["--" + option, getattr(args, option)]
    for flag in ("pre", "dry_run", "yes", "smoke"):
        if getattr(args, flag):
            argv.append("--" + flag.replace("_", "-"))
    if getattr(args, "cmd", "bootstrap") == "upgrade":
        argv += ["--wait-timeout", str(args.wait_timeout), "--timeout", str(args.timeout)]
    env = dict(os.environ, CREW_BOOTSTRAP_BUNDLE_SHA256=sha)
    transport = crew_install.transport(install, sums_sha, commit)
    if transport:
        env["CREW_BOOTSTRAP_TRANSPORT"] = json.dumps(transport)
    code = subprocess.run(argv, env=env).returncode
    if code or getattr(args, "cmd", "bootstrap") != "upgrade":
        return code
    return commands()["install"].follow(args, destination, argv, env)  # the other projects, then releases/current


def register(sub, name="bootstrap"):
    p = sub.add_parser(name, help="preview and install this bundle for a project")
    p.add_argument("--project")
    p.add_argument("--org-profile")
    p.add_argument("--proposal", help="owner-edited TOML for a missing project file")
    p.add_argument("--runtime", choices=("tmux", "grok-bot"), help="proposed runtime; default is the bundle profile")
    p.add_argument("--flavor", choices=("thorough", "standard", "fast"),
                   help="record flavor.name in the proposal; default standard")
    p.add_argument("--version", help="fetch and run this release beside the current bundle")
    p.add_argument("--pre", action="store_true", help="allow rc tags; satisfies no pack pin")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--uninstall", action="store_true", help="pause, stop, remove owned targets and archive state")
    p.add_argument("--remove-labels", action="store_true", help="delete crew labels after stopping the runtime")
    p.add_argument("--routines-removed", action="store_true", help="confirm Grok Bot routines were removed manually")
    p.add_argument("--dev", action="store_true", help="record this clone's SHA; satisfies no version pin")
    p.add_argument("--harness", action="append", choices=harnesses_module.INSTALLS,
                   help="install harness pointers (repeat for both; tmux render only)")
    p.add_argument("--smoke", action="store_true", help="queue a real docs-only test issue; requires a started crew")
    return p


def size_budget(rendered, values):
    """Check path-normalized role Markdown against its byte budget; wiring is not loaded."""
    failed = False
    for path in sorted(Path(rendered).rglob("*.md")):
        role = path.stem.split("-")[0]
        if role not in crew_render.ROLES:
            continue
        size = len(path.read_bytes())
        budget = values["size_budget." + role]
        if size > budget:
            print("%s: %d path-normalized UTF-8 bytes exceeds %s budget %d bytes" %
                  (path.relative_to(rendered), size, role, budget))
            failed = True
    return int(failed)


def budget_render(project, org, values):
    """Render path-normalized briefs, which leave core memory out (it has its own limits), and check size_budget."""
    with tempfile.TemporaryDirectory(prefix="crew-size-budget-") as normalized:
        argv = ["--project", str(project), "--out", normalized] + (["--org-profile", org] if org else [])
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(out):
            code = crew_render.main(argv, normalize_paths=True)
        if code:
            print(out.getvalue(), end="")
            return code
        return size_budget(normalized, values)


def self_test(project, org, live, record, doctor):
    checks = {}

    def check(name, action):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(out):
            try:
                code = action()
            except (OSError, ValueError, RuntimeError) as e:
                print(e)
                code = 1
        checks[name] = "fail" if code else "ok"
        print("Self-test: %s %s" % (name, checks[name]))
        if code:
            print(out.getvalue(), end="")

    profile_argv = ["resolve", "--project", str(project)] + (["--org-profile", org] if org else [])
    check("profile", lambda: crew_render.crew_config.main(profile_argv))
    with tempfile.TemporaryDirectory(prefix="crew-self-test-") as tmp:
        argv = ["--project", str(project), "--out", tmp] + (["--org-profile", org] if org else [])
        check("render", lambda: crew_render.main(argv))
        if checks["render"] == "ok":
            values, _ = crew_render.resolve(str(project), org)
            check("size_budget", lambda: budget_render(project, org, values))
            check("briefs", lambda: int(bool(missing_briefs(tmp, record["runtime"]))))
            if live.is_dir():
                expected = {p.relative_to(tmp): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
                check("deploy", lambda: int(expected != {
                    p.relative_to(live): p.read_bytes() for p in live.rglob("*") if p.is_file()}))
            elif record["runtime"] == "tmux":
                checks["deploy"] = "pending mdstack up"
                print("Self-test: deploy pending mdstack up")
            else:
                checks["deploy"] = "fail"
                print("Self-test: deploy fail (live directory missing)")
    check("targets", lambda: int(any(digest(Path(p)) != sha for p, sha in record["targets"].items())))
    check("doctor", lambda: doctor.run(Namespace(project=str(project), org_profile=org, fix=False,
                                               dry_run=False, milestone=None)))
    return checks


def smoke(values, record, manifest):
    if record.get("smoke", {}).get("issue"):
        print("Smoke: already queued " + record["smoke"]["issue"])
        return
    if values["runtime.name"] == "tmux":
        session = values.get("runtime.options.session") or "crew-%s-%s" % (values["repo.owner"], values["repo.name"])
        if not tmux.has_session(session):
            raise ValueError("smoke requires a started crew; run mdstack up first, then repeat --smoke")
    body = """## Goal

Prove the crew pipeline with a docs-only no-op change; no product behaviour changes.

## Acceptance criteria

1. docs/crew-smoke-test.md has a heading and one sentence explaining this test.
2. Required checks are green at the PR head.
3. The PR body has Acceptance Evidence with one row per criterion.
4. Only docs/crew-smoke-test.md and the required changelog fragment change.

## Out of scope

Product code, workflows, labels and settings. Use eng-backend, trivial tier.
"""
    r = subprocess.run(["gh", "issue", "create", "-R", values["repo.owner"] + "/" + values["repo.name"],
                        "--title", "crew smoke test: add docs/crew-smoke-test.md", "--body-file", "-",
                        "--label", "crew:ready", "--assignee", values["identities.builder.gh_user"]],
                       input=body, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("smoke issue creation failed: " + r.stderr.strip())
    record["smoke"] = dict(issue=r.stdout.strip(), status="queued")
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    print("Smoke: queued " + record["smoke"]["issue"] + "; pipeline result pending")


def unchanged(previous, record, live, rendered):
    """Whether applying would write nothing (docs/bootstrap.md Q8): a healthy record equal to the planned one (its
    render_sha256 covers a render not yet deployed), every recorded target byte-equal on disk (a deselected harness's
    included) and any live render equal to this one (none yet for tmux before mdstack up)."""
    checks = previous.get("self_test", {})
    if previous.get("status") != "installed" or "fail" in checks.values() or \
            {k: v for k, v in previous.items() if k != "self_test"} != record:
        return False
    if any(Path(p).is_symlink() or not Path(p).is_file() or digest(Path(p)) != sha  # retained ones too (#1090 R1)
           for p, sha in record["targets"].items()):
        return False
    if not live.is_dir():
        return checks.get("deploy") == "pending mdstack up"
    return checks.get("deploy") == "ok" and {p: p.read_bytes() for p in live.rglob("*") if p.is_file()} == {
        p: text.encode() for p, text in rendered.items()}


def excluded(repo, exclude, lines):
    """Whether every planned exclude line is already in the repository's info/exclude."""
    if not lines:
        return True
    exclude = exclude or Path(git(str(repo), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
    return exclude.is_file() and set(lines) <= set(exclude.read_text().splitlines())


def run(args):
    try:
        if args.uninstall:
            from crew_shared import load
            return load("bootstrap_uninstall", "environments/terminal/crew.d/_bootstrap_uninstall.py").uninstall(args)
        if args.remove_labels or args.routines_removed:
            raise ValueError("--remove-labels and --routines-removed require --uninstall")
        return bootstrap(args)
    except (OSError, ValueError, RuntimeError, tarfile.TarError) as e:
        print("crew bootstrap: %s" % e, file=sys.stderr)
        return 1


def propose_project(args, project):
    if args.proposal:
        text = Path(args.proposal).read_text()
    else:
        repo_dir = project.parent if (project.parent / ".git").exists() else Path.cwd()  # a user-level config (#1316)
        remote = git(str(repo_dir), "config", "--local", "--get", "remote.origin.url")
        match = re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([\w.-]+)/([\w.-]+?)(?:\.git)?/?", remote)
        if not match:
            raise ValueError("local origin is not a recognized GitHub URL; supply --proposal with your binding")
        owner, repo = match.groups()
        runtime = args.runtime or tomllib.loads((ROOT / "profiles/default.toml").read_text())["runtime"]["name"]
        runtime_text = "name = %s\n" % json.dumps(runtime)
        if runtime == "tmux":
            runtime_text = (ROOT / "profiles/tmux.toml").read_text().split("[runtime]\n", 1)[1].split("[backends.", 1)[0]
        text = '[repo]\nowner = %s\nname = %s\n\n[runtime]\n%s' % (
            json.dumps(owner), json.dumps(repo), runtime_text)
        for concern in crew_render.crew_config.OPERATIONS:
            text += '\n[backends.%s]\nname = "github"\n' % concern
            if runtime == "tmux" and concern == "review":
                text += 'capabilities = { post-verdict = "emulated (COMMENT-review verdict + recorded owner merge-ok)" }\n'
        if runtime == "tmux":  # the one-root default layout (docs/runtimes/tmux.md#home-level-layout-1178, #1316)
            text += ('\n[paths]\nroot = %s\nstate_dir = "state"\nworktree_root = %s\nlive_dir = "live"\n'
                     'mdstack = %s\ncheckout = %s\n' % (json.dumps(os.environ.get("CREW_ROOT") or "~/.mdstack"),
                                                         json.dumps("runs/" + repo), json.dumps(
                         "state/%s__%s/mdstack" % (owner, repo)), json.dumps(str(repo_dir.absolute()))))
    if "flavor" not in tomllib.loads(text):
        text += '\n[flavor]\nname = %s\n' % json.dumps(args.flavor or "standard")
    print("Project proposal: %s\n%s" % (project, text), end="" if text.endswith("\n") else "\n")
    print("Review identities and paths inherited from the profile layers; edit with --proposal FILE.")
    if args.dry_run:
        print("crew bootstrap: dry-run; no profile or install written")
        return False
    if not args.yes:
        if not sys.stdin.isatty():
            raise ValueError("profile confirmation required; use --proposal FILE to edit, then --yes")
        answer = input("Record proposal? [y/N or edited TOML path] ").strip()
        if answer.lower() != "y":
            if answer.lower() in ("", "n"):
                raise ValueError("profile confirmation required")
            args.proposal = answer
            return propose_project(args, project)
    project.parent.mkdir(parents=True, exist_ok=True)  # a fresh home has no ~/.mdstack/ yet (#1316)
    with project.open("x") as f:
        f.write(text)
    print("crew bootstrap: recorded profile " + str(project))
    return True


def bootstrap(args):
    if args.version:
        if args.dev:
            raise ValueError("--version and --dev cannot be combined")
        return fetch(args)
    tag = source(args.dev, args.pre)
    reference = str(Path(args.project).absolute())  # FILE or FILE#<repo>, kept for resolve, doctor, render and record
    profile, selected = profile_file(reference), crew_render.crew_config.split_ref(reference)[1]
    if not profile.is_file() and selected is None:  # a missing FILE#<repo> fails in the resolver (#1344)
        if not propose_project(args, profile):
            return 0
    pack_pin(args.org_profile, tag, args.project)
    pack = pack_record(args.org_profile, args.project)  # a pack.toml pack must pin at a commit before any write
    values, problems = crew_render.resolve(reference, args.org_profile)
    if problems:
        raise ValueError("\n".join(problems))
    # project anchors repo-local targets by its directory: the profile, or for FILE#<repo> that repo's clone (#1344).
    project = Path(checkout(values, reference)) / profile.name if selected else profile
    tmux = values["runtime.name"] == "tmux"
    keys = ("state_dir", "worktree_root", "toolchain_bin", "mdstack" if tmux else "live_dir")
    problems = placeholder_paths(args, values, keys)
    if problems:
        raise ValueError("\n".join(problems))
    state = Path(values["paths.state_dir"]).absolute() / (values["repo.owner"] + "__" + values["repo.name"])
    doctor = commands()["doctor"]
    with contextlib.redirect_stdout(io.StringIO()) as report:
        code = doctor.run(Namespace(project=reference, org_profile=args.org_profile, fix=False,
                                    dry_run=False, milestone=None))
    print(report.getvalue(), end="")
    if code:
        return code
    human = report.getvalue().partition("Steps only a person can take:\n")[2].splitlines()
    pending = [line.removeprefix("- ") for line in human]
    pending += (["Create the routines from the rendered files (docs/bootstrap.md Q4)"]
                if values["runtime.name"] == "grok-bot" else ["Run mdstack up --project " + reference])
    manifest = state / "install.json"
    previous = json.loads(manifest.read_text()) if manifest.exists() else {}
    harnesses = args.harness if args.harness is not None else previous.get("harnesses", [])
    if harnesses and not tmux:
        raise ValueError("harness pointers need tmux role briefs; a session binding is not implemented")
    old = previous.get("targets", {})
    link = state / "mdstack"
    named = Path(values["paths.mdstack"]).absolute()
    # A team file's one paths.mdstack names one repo's link under the team state root; each repo still gets its own.
    shared = selected and named.name == "mdstack" and named.parent.parent == state.parent
    if tmux and named != link and not shared:
        raise ValueError("paths.mdstack must name the install link: " + str(link))
    if link.exists() or link.is_symlink():
        if not link.is_symlink() or str(link.resolve()) != previous.get("source"):
            raise ValueError("target edited or unowned: " + str(link))
    with tempfile.TemporaryDirectory(prefix="crew-bootstrap-") as tmp:
        preview = Path(tmp)
        argv = ["--project", reference, "--out", tmp]
        if args.org_profile:
            argv += ["--org-profile", args.org_profile]
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(out):
            code = crew_render.main(argv)
        if code:
            raise ValueError(out.getvalue())
        live = Path(values["paths.live_dir"]).absolute() if not tmux else state / "render"
        targets = {state / "VERSION": tag + "\n", state / "config.toml": profile.read_text()}
        rendered = {live / p.relative_to(preview): p.read_text() for p in preview.rglob("*") if p.is_file()}
        registry, notes, owned = pack_pointers(harnesses, args.org_profile, reference, project)
        pointers, launches = harness_targets(harnesses, project, state, live, preview, old, doctor, notes)
        bases = {Path(p): target_root(e, project) for p, e in {**previous.get("harness_pointers", {}),
                                                                **owned}.items()}
        refused = []
        for path in registry:
            if str(path) in old and path.is_file() and not path.is_symlink() and digest(path) != old[str(path)]:
                refused.append("drift: %s" % path)
                continue
            try:
                check_target(path, old, doctor, project, bases[path])
            except ValueError as e:
                refused.append(str(e))
        if refused:
            raise ValueError("\n".join(refused))
        pointers.update(registry)
        # Registry entries gone from the pack (docs/bootstrap.md#upgrade-and-removal): remove unchanged targets.
        stale = [Path(p) for p, entry in previous.get("harness_pointers", {}).items()
                 if entry["harness"] in harnesses and Path(p) not in registry]
        removals = []
        for path in stale:
            try:
                check_target(path, old, doctor, project, bases[path])
                if path.exists():
                    removals.append(path)
            except ValueError:
                pending.append("Remove or keep %s: dropped from the pack registry but edited since install; "
                               "no longer owned" % path)
        dropped = {path: "/" + str(path.relative_to(project.parent)) for path in removals
                   if path.is_relative_to(project.parent)}
        targets.update(pointers)
        if harnesses:
            targets.update(rendered)
        if not tmux:
            targets.update(rendered)
            existing = {p for p in live.rglob("*") if p.is_file() or p.is_symlink()}
            if existing - targets.keys():
                raise ValueError("live copy has extra files; reconcile before bootstrap")
        for path, text in targets.items():
            check_target(path, old, doctor, project, bases.get(path))
        repo = Path(checkout(values, reference))  # a non-git runtime home excludes in its checkout (#1178)
        scaffold = spec_scaffold(values, repo)
        for path in scaffold:
            check_target(path, {}, doctor, project)
        excludes = [".crew/"] if tmux else []
        excludes += ["/" + str(path.relative_to(project.parent)) for path in pointers
                     if repo == project.parent and path.is_relative_to(project.parent)]
        exclude = None
        if harnesses:
            exclude = Path(git(str(repo), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
            if exclude.is_symlink() or exclude.parent.is_symlink():
                raise ValueError("symlink exclude or parent: " + str(exclude))
        bundle_sha = os.environ.get("CREW_BOOTSTRAP_BUNDLE_SHA256")
        if not bundle_sha and previous.get("source") == str(ROOT):
            bundle_sha = previous.get("bundle_sha256")
        record = dict(tag=tag, source=str(ROOT), project=reference, bundle_sha256=bundle_sha,
                      runtime=values["runtime.name"],
                      targets={**{p: sha for p, sha in old.items() if Path(p) not in stale},
                               **{str(p): hashlib.sha256(text.encode()).hexdigest()
                                  for p, text in targets.items()}}, harnesses=harnesses,
                      launches=launches, pending_human_steps=pending, status="installed",
                      render_sha256=hashlib.sha256(json.dumps({str(p.relative_to(live)): text for p, text in
                                                              rendered.items()}, sort_keys=True).encode()).hexdigest())
        owned = {**{path: entry for path, entry in previous.get("harness_pointers", {}).items()
                    if entry["harness"] not in harnesses}, **owned}
        if owned:
            record["harness_pointers"] = owned
        transport = os.environ.get("CREW_BOOTSTRAP_TRANSPORT")
        transport = json.loads(transport) if transport else (
            previous.get("transport") if previous.get("source") == str(ROOT) else None)
        if transport:
            record["transport"] = transport
        if pack:
            record["pack"] = pack
        if "smoke" in previous:
            record["smoke"] = previous["smoke"]
        upgrade_deploys = tmux and not harnesses and getattr(args, "cmd", "bootstrap") == "upgrade"
        if (not (removals or scaffold or dropped) and link.is_symlink()
                and not (upgrade_deploys and not live.is_dir())
                and not (args.smoke and not previous.get("smoke", {}).get("issue"))
                and unchanged(previous, record, live, rendered)
                and excluded(repo, exclude, excludes)):
            print("crew bootstrap: no changes")
            if args.smoke:
                print("Smoke: already queued " + previous["smoke"]["issue"])
            return 0
        for path, text in {**targets, **rendered}.items():
            before = path.read_text() if path.exists() else ""
            print("".join(difflib.unified_diff(before.splitlines(True), text.splitlines(True),
                                             fromfile=str(path), tofile=str(path) + " (planned)")), end="")
        print("Plan: %s (%s); link %s -> %s" % (tag, values["runtime.name"], link, ROOT))
        if tmux and not harnesses:
            print("Render preview: %d files; mdstack up deploys render and hooks" %
                  sum(p.is_file() for p in preview.rglob("*")))
        for line in excludes:
            print("Repo operation: add %s to .git/info/exclude" % line)
        for path in registry:
            if not path.is_relative_to(project.parent):
                print("Home operation: write %s (pack.harness root = home; no exclude line)" % path)
        for path in scaffold:
            print("Repo operation: scaffold %s from templates/spec.md (yours to commit; never overwritten)" % path)
        for path in removals:
            print("Remove: %s (dropped from the pack registry)" % path)
            if path in dropped:
                print("Repo operation: remove %s from .git/info/exclude" % dropped[path])
        for launch in launches:
            print("Codex launch (from %s): %s" % (project.parent, launch))
        if not tmux and values.get("triage.enabled"):
            print("Triage: triage.enabled installs no Grok timer; triage stays coordinator dispositions")
        for step in pending:
            print("Human step: " + step)
        if args.smoke:
            print("Plan: queue docs-only smoke issue (crew must be started; pipeline result remains pending)")
        if args.dry_run:
            print("crew bootstrap: dry-run; no install written")
            return 0
        if not args.yes and (not sys.stdin.isatty() or input("Apply this plan? [y/N] ").lower() != "y"):
            raise ValueError("confirmation required; review --dry-run, then use --yes")
        if doctor.run(Namespace(project=reference, org_profile=args.org_profile, fix=True,
                                dry_run=False, milestone=None)):
            return 1
        if excludes:
            if exclude is None:
                exclude = Path(git(str(repo), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"))
            exclude.parent.mkdir(parents=True, exist_ok=True)
            text = exclude.read_text() if exclude.exists() else ""
            if dropped:
                text = "".join(line for line in text.splitlines(True) if line.rstrip("\n") not in dropped.values())
                exclude.write_text(text)
            missing = [line for line in excludes if line not in text.splitlines()]
            if missing:
                exclude.write_text(text + ("\n" if text and not text.endswith("\n") else "") +
                                   "\n".join(missing) + "\n")
        for path in removals:
            path.unlink()
        for path, text in scaffold.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x") as f:
                f.write(text)
        for path, text in targets.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        if link.is_symlink():
            link.unlink()
        link.symlink_to(ROOT, target_is_directory=True)
        manifest.write_text(json.dumps(record, indent=2) + "\n")
    if tmux and not harnesses and getattr(args, "cmd", "bootstrap") == "upgrade":
        for path, text in rendered.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    record["self_test"] = self_test(reference, args.org_profile, live, record, doctor)
    failed = [name for name, status in record["self_test"].items() if status == "fail"]
    record["status"] = "failed" if failed else "installed"
    manifest.write_text(json.dumps(record, indent=2) + "\n")
    if failed:
        raise ValueError("self-test failed: " + ", ".join(failed))
    print("crew bootstrap: installed " + str(manifest))
    if args.smoke:
        try:
            smoke(values, record, manifest)
        except (OSError, ValueError, RuntimeError):
            record["status"] = "failed"
            record["self_test"]["smoke"] = "fail"
            manifest.write_text(json.dumps(record, indent=2) + "\n")
            raise
    return 0
