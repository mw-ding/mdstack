#!/usr/bin/env python3
"""Pack plug-in loader (docs/packs.md#pack-plug-ins): pack.toml, discovery, version range, floors, commit pin.

Usage: crew-pack.py discover [--project FILE] [--pack DIR]
       crew-pack.py check DIR [--framework vX.Y.Z]
       crew-pack.py lock CHECKOUT EXPORT

A pack directory with pack.toml declares the mdstack versions it supports (`framework`) and what it provides:
connectors/<name>/manifest.toml, harnesses/<name>/adapter.py, environments/<name>/defaults.toml (profile defaults for
runtime <name>) and skills/<name>/SKILL.md. Each item is checked with the loader the built-ins use (validate_manifest,
the harness discover(), the profile schema, the Agent Skills frontmatter); a pack name never shadows a built-in.
A pack may tighten rules but never loosen a core floor: its profile.toml and environment defaults are refused for a
floor control, a merge grant or a flavor below the core default. `discover` prints kind, name, source and path for
every built-in and pack item; `check` loads a pack (and with --framework checks its range); `lock` writes
EXPORT/pack.lock pinning an exported copy of a clean CHECKOUT (#1962). The conformance kit is actions/contract.py
(`mdstack pack test`). Exit 0 ok, 1 on any problem. Python 3.11+ stdlib only.
"""
import argparse
import glob
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KINDS = {"connectors": "manifest.toml", "harnesses": "adapter.py", "environments": "defaults.toml",
         "skills": "SKILL.md"}
SINGULAR = {"connectors": "connector", "harnesses": "harness", "environments": "environment", "skills": "skill"}
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
VERSION = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
COMPARATOR = re.compile(r"(>=|<=|>|<|==)\s*(\S+)")
LOCK = "pack.lock"
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, ">": lambda a, b: a > b, "<": lambda a, b: a < b,
       "==": lambda a, b: a == b}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_range(text):
    """[(op, (X, Y, Z))] from `>=5.3.0, <6.0.0`; None when malformed or empty."""
    out = []
    for part in text.split(","):
        m = COMPARATOR.fullmatch(part.strip())
        v = VERSION.fullmatch(m[2]) if m else None
        if not v:
            return None
        out.append((m[1], tuple(int(x) for x in v.groups())))
    return out or None


def compatible(pack, tag):
    """None when the stable release tag vX.Y.Z satisfies pack.framework, else the refusal reason."""
    v = re.fullmatch(r"v" + VERSION.pattern, tag or "")
    if not v:
        return "%s is not a stable release tag vX.Y.Z; pack %s supports mdstack %s" % (
            tag, pack.get("name"), pack.get("framework"))
    version = tuple(int(x) for x in v.groups())
    if not all(OPS[op](version, bound) for op, bound in parse_range(pack["framework"])):
        return "pack %s supports mdstack %s; %s is incompatible" % (pack.get("name"), pack["framework"], tag)
    return None


def skill_name(path):
    """The Agent Skills frontmatter (name, description) of a SKILL.md; None for a missing field."""
    with open(path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    fields = {}
    if lines and lines[0] == "---":
        for line in lines[1:]:
            if line == "---":
                break
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
    return fields.get("name"), fields.get("description")


def builtins(cfg, harnesses):
    """{kind: {name: (source, path)}} for the items this mdstack ships."""
    reg = {kind: {} for kind in KINDS}
    for path in sorted(glob.glob(os.path.join(cfg.CONNECTORS_DIR, "[!_]*", "manifest.toml"))):
        reg["connectors"][os.path.basename(os.path.dirname(path))] = ("core", path)
    for name, mod in harnesses.ADAPTERS.items():
        if name not in harnesses.PACKED:  # an adapter a pack added at resolve is not a built-in
            reg["harnesses"][name] = ("core", mod.__file__)
    for name in cfg.RUNTIME_OPTIONS:
        path = os.path.join(ROOT, "profiles", name + ".toml")
        reg["environments"][name] = ("core", path if os.path.exists(path) else os.path.join(ROOT, "core", "crew-config.py"))
    for path in sorted(glob.glob(os.path.join(ROOT, "templates", "**", "SKILL.md"), recursive=True)):
        reg["skills"].setdefault(skill_name(path)[0], ("core", path))
    return reg


def weaker(cfg, knobs):
    """The rigor knobs (and caps) on which a flavor's knobs are below the core default flavor."""
    floor = cfg.FLAVOR_PRESETS[cfg.UNSET_FLAVOR]
    worse = [k for k, order in cfg.FLAVOR_ORDER.items() if k != "builder" and knobs.get(k) in order
             and order.index(knobs[k]) > order.index(floor[k])]
    caps = knobs.get("caps", floor["caps"])
    return worse + (["caps"] if isinstance(caps, list) and any(
        type(a) is int and a < b for a, b in zip(caps, floor["caps"])) else [])


def custom_flavors(data):
    flavor = data.get("flavor") if isinstance(data.get("flavor"), dict) else {}
    custom = flavor.get("custom") if isinstance(flavor.get("custom"), dict) else {}
    return {name: table for name, table in custom.items() if isinstance(table, dict)}


def custom_problems(cfg, custom, where):
    """A custom flavor a pack defines, alone or merged across its layers, is never below the core default."""
    out = []
    for name, table in custom.items():
        knobs = dict(cfg.FLAVOR_PRESETS.get(table.get("base"), cfg.FLAVOR_PRESETS[cfg.UNSET_FLAVOR]), **table)
        worse = weaker(cfg, knobs)
        if worse:
            out.append("%s:flavor.custom.%s: loosens the core default flavor %s (%s); a pack may only tighten" % (
                where, name, cfg.UNSET_FLAVOR, ", ".join(worse)))
    return out


def floor_problems(cfg, data, where, custom=None):
    """A pack layer may tighten, never loosen: floor controls, merge grants and a flavor below the core default.
    custom is every custom flavor the pack defines across its layers; a pack selects only a preset or one of those.
    Floor controls live in the flavor table and runtime.options, so a key elsewhere named like one (backends.ci) is not
    a floor control (#1325)."""
    out = []

    def scan(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                sub = path + "." + key if path else key
                if key in cfg.FLAVOR_FLOOR and (path.split(".")[0] == "flavor" or path == "runtime.options") \
                        and not (key == "hold_label_blocks" and child is True):
                    number, rule = cfg.FLAVOR_FLOOR[key]
                    out.append("%s:%s: floor F%d: %s; a pack may tighten rules, never loosen a core floor" % (
                        where, sub, number, rule))
                if key == "merge_grant" and child != "none":
                    out.append("%s:%s: a merge grant is the owner's, never a pack's" % (where, sub))
                if key == "release_delegation" and child != "none":
                    out.append("%s:%s: a release delegation is the owner's, never a pack's" % (where, sub))
                scan(child, sub)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scan(child, "%s[%d]" % (path, i))
    scan(data, "")
    flavor = data.get("flavor") if isinstance(data.get("flavor"), dict) else {}
    custom = custom_flavors(data) if custom is None else custom
    out.extend(custom_problems(cfg, custom_flavors(data), where))
    named = [("flavor.name", flavor.get("name"))] + [
        ("flavor.classes[%d].flavor" % i, c.get("flavor")) for i, c in enumerate(flavor.get("classes", []))
        if isinstance(c, dict)]
    for path, name in named:
        if isinstance(name, str) and name not in cfg.FLAVOR_PRESETS and name not in custom:
            out.append("%s:%s: %s is neither a preset nor a flavor the pack defines; a pack selects only those" % (
                where, path, name))
            continue
        worse = weaker(cfg, cfg.FLAVOR_PRESETS[name]) if name in cfg.FLAVOR_PRESETS else []
        if worse:
            out.append("%s:%s: %s loosens the core default flavor %s (%s); a pack may only tighten" % (
                where, path, name, cfg.UNSET_FLAVOR, ", ".join(worse)))
    return out


def read_toml(path, problems):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except OSError as e:
        problems.append("%s: cannot read (%s)" % (path, e.strerror))
    except tomllib.TOMLDecodeError as e:
        problems.append("%s: invalid TOML (%s)" % (path, e))
    return None


def load(pack_dir, cfg, harnesses):
    """(pack, problems): pack.toml's [pack] table plus `items` {kind: {name: path}}, `harnesses` {name: module}
    and `environments` {name: defaults}. Every provided item is checked as a built-in of its kind is."""
    problems = []
    root = os.path.realpath(pack_dir)
    path = os.path.join(root, "pack.toml")
    data = read_toml(path, problems)
    if data is None:
        return None, problems

    def err(key, reason):
        problems.append("%s:%s: %s" % (path, key, reason))
    top = cfg.check_table(err, "", data, {"pack": (dict, cfg.REQUIRED), "provides": (dict, cfg.REQUIRED),
                                          "vcs": (dict, None)})
    if "vcs" in top:
        cfg.check_table(err, "vcs", top["vcs"], {"clean": ("list[str]", cfg.REQUIRED),
                                                 "commit": ("list[str]", cfg.REQUIRED)})
    pack = cfg.check_table(err, "pack", top.get("pack", {}), {"name": (str, cfg.REQUIRED), "version": (str, None),
                                                             "framework": (str, cfg.REQUIRED)})
    if "name" in pack and not NAME.fullmatch(pack["name"]):
        err("pack.name", "expected [a-z0-9] words separated by hyphens")
    if "version" in pack and not cfg.SEMVER.match(pack["version"]):
        err("pack.version", "expected a SemVer version (MAJOR.MINOR.PATCH, no leading v)")
    if "framework" in pack and parse_range(pack["framework"]) is None:
        err("pack.framework", "expected comparators such as \">=5.3.0, <6.0.0\" (>=, >, <=, <, ==; X.Y.Z)")
    provides = cfg.check_table(err, "provides", top.get("provides", {}), {k: ("list[str]", None) for k in KINDS})
    known = builtins(cfg, harnesses)
    pack = dict(pack, items={kind: {} for kind in KINDS}, harnesses={}, environments={})
    for kind, names in provides.items():
        for name in names:
            item = os.path.join(root, kind, name, KINDS[kind])
            key = "provides.%s" % kind
            if not NAME.fullmatch(name):
                err(key, "%r: expected [a-z0-9] words separated by hyphens" % name)
            elif name in known[kind] and kind != "environments":
                err(key, "%r shadows a built-in %s; a pack adds names, never replaces one" % (name, SINGULAR[kind]))
            elif kind == "environments" and name not in cfg.RUNTIME_OPTIONS:
                err(key, "%r: environment defaults apply to a runtime (%s)" % (name, ", ".join(cfg.RUNTIME_OPTIONS)))
            elif not os.path.realpath(item).startswith(root + os.sep) or not os.path.isfile(item):
                err(key, "%r: missing %s/%s/%s in the pack" % (name, kind, name, KINDS[kind]))
            else:
                pack["items"][kind][name] = item
    for name, item in pack["items"]["connectors"].items():
        manifest = read_toml(item, problems)
        if manifest is not None:
            cfg.validate_manifest(manifest, lambda k, reason: problems.append("%s:%s: %s" % (item, k, reason)),
                                  os.path.dirname(item), external_pin=False)
            if manifest.get("pack", {}).get("name") != name:
                problems.append("%s:pack.name: expected %r, the connector's directory" % (item, name))
    if pack["items"]["harnesses"]:
        try:
            adapter = next(iter(pack["items"]["harnesses"].values()))  # <pack>/<kind>/<name>/adapter.py
            found = harnesses.discover(os.path.dirname(os.path.dirname(adapter)))
            pack["harnesses"] = {n: m for n, m in found.items() if n in pack["items"]["harnesses"]}
        except Exception as e:  # pack code: any import failure refuses the pack
            problems.append("%s: harness adapter failed to load (%s: %s)" % (path, type(e).__name__, e))
    layers = []  # (file, data) for every pack config layer: environment defaults, then profile.toml
    for name, item in pack["items"]["environments"].items():
        defaults = read_toml(item, problems)
        if defaults is None:
            continue
        runtime = defaults.get("runtime")
        if not isinstance(runtime, dict) or runtime.get("name", name) != name:
            problems.append("%s:runtime.name: expected %r, the environment's directory" % (item, name))
        layers.append((item, defaults))
        pack["environments"][name] = defaults
    for name, item in pack["items"]["skills"].items():
        skill, description = skill_name(item)
        if skill != name or not description:
            problems.append("%s: frontmatter needs name: %s and a description (Agent Skills format)" % (item, name))
    profile = os.path.join(root, "profile.toml")
    data = read_toml(profile, problems) if os.path.exists(profile) else None
    layers += [(profile, data)] if data is not None else []
    custom = {}  # one flavor may be defined in parts across the layers, as resolve merges them
    for _, data in layers:
        for name, table in custom_flavors(data).items():
            custom[name] = dict(custom.get(name, {}), **table)
    for item, data in layers:
        problems.extend(floor_problems(cfg, data, item, custom))
    if not any("flavor.custom." in p for p in problems):
        problems.extend(custom_problems(cfg, custom, path))
    return (pack if not problems else None), problems


def discover(cfg, harnesses, pack_dir=None):
    """(registry, problems): every built-in item, then the pack's, as {kind: {name: (source, path)}}."""
    reg = builtins(cfg, harnesses)
    if not pack_dir or not os.path.exists(os.path.join(pack_dir, "pack.toml")):
        return reg, []
    pack, problems = load(pack_dir, cfg, harnesses)
    for kind, items in (pack["items"].items() if pack else []):
        for name, path in items.items():
            reg[kind][name] = (("core+pack:" if name in reg[kind] else "pack:") + pack["name"], path)
    return reg, problems


def sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def file_digests(pack_dir):
    """{relative path: sha256 hex} for every file under pack_dir except pack.lock."""
    files = {}
    for root, _, names in os.walk(pack_dir):
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), pack_dir).replace(os.sep, "/")
            if rel != LOCK:
                files[rel] = sha256_file(os.path.join(root, name))
    return files


def tree_digest(files):
    """The export's sha256: over each sorted relative path and its file's sha256, one line each."""
    return hashlib.sha256("".join("%s\0%s\n" % (p, files[p]) for p in sorted(files)).encode()).hexdigest()


def write_lock(checkout, export):
    """Write export/pack.lock pinning export as the clean checkout's content at its commit; ValueError unless every
    export file is byte-identical to the checkout's file at the same path. Returns the lock's path."""
    head = commit(checkout)
    files = file_digests(export)
    for rel in sorted(files):
        source = os.path.join(checkout, rel)
        if not os.path.isfile(source) or sha256_file(source) != files[rel]:
            raise ValueError("pack export %s: %s differs from checkout %s" % (export, rel, checkout))
    lines = ["commit = %s" % json.dumps(head), "sha256 = %s" % json.dumps(tree_digest(files)), "", "[files]"]
    lines += ["%s = %s" % (json.dumps(p), json.dumps(files[p])) for p in sorted(files)]
    path = os.path.join(export, LOCK)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return path


def verify_lock(pack_dir):
    """The commit pack_dir/pack.lock records; ValueError naming the first mismatched path unless the export's files
    are exactly the locked ones."""
    try:
        with open(os.path.join(pack_dir, LOCK), "rb") as f:
            lock = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        raise ValueError("pack %s: unreadable %s (%s)" % (pack_dir, LOCK, e))
    locked, head = lock.get("files"), lock.get("commit")
    if not (isinstance(head, str) and head and isinstance(locked, dict) and
            all(isinstance(v, str) for v in locked.values()) and lock.get("sha256") == tree_digest(locked)):
        raise ValueError("pack %s: %s needs commit, sha256 and files matching its sha256" % (pack_dir, LOCK))
    files = file_digests(pack_dir)
    for rel in sorted(set(files) | set(locked)):
        if files.get(rel) != locked.get(rel):
            state = "missing" if rel not in files else "not locked" if rel not in locked else "changed"
            raise ValueError("pack %s does not match its %s: %s is %s" % (pack_dir, LOCK, rel, state))
    return head


def commit(pack_dir):
    """The pack checkout's full commit; ValueError unless its working copy is clean, so the commit pins it. A pack
    whose version control is not git declares [vcs] clean (prints nothing when clean) and commit (prints the commit).
    A directory outside version control pins through its pack.lock, which must verify (#1962)."""
    try:
        with open(os.path.join(pack_dir, "pack.toml"), "rb") as f:
            vcs = tomllib.load(f).get("vcs")
    except (OSError, tomllib.TOMLDecodeError):
        vcs = None
    if vcs is None:
        vcs = {"clean": ["git", "status", "--porcelain", "--untracked-files=normal"],
               "commit": ["git", "rev-parse", "HEAD"]}
    if not isinstance(vcs, dict) or not all(isinstance(vcs.get(k), list) and vcs[k] and
                                            all(isinstance(a, str) for a in vcs[k]) for k in ("clean", "commit")):
        raise ValueError("pack %s: [vcs] needs clean and commit commands (lists of strings)" % pack_dir)

    def run(key):
        exported = key == "commit" and os.path.isfile(os.path.join(pack_dir, LOCK))
        try:
            proc = subprocess.run(vcs[key], cwd=pack_dir, capture_output=True, text=True)
        except OSError as e:
            if exported:
                return None
            raise ValueError("pack %s: [vcs] %s command failed to start (%s)" % (pack_dir, key, e.strerror))
        if proc.returncode:
            if exported:
                return None
            raise ValueError("pack %s is not a %s checkout; install pins a pack at a commit" % (pack_dir, vcs[key][0]))
        return proc.stdout.strip()
    head = run("commit")
    if head is None:
        return verify_lock(pack_dir)
    if not head:
        raise ValueError("pack %s: [vcs] commit printed no commit" % pack_dir)
    if run("clean"):
        raise ValueError("pack %s has uncommitted changes; commit them so the install pins the pack at a commit"
                         % pack_dir)
    return head


def project_pack(project):
    """The pack directory recorded as paths.pack in a project file, or None."""
    with open(project, "rb") as f:
        paths = tomllib.load(f).get("paths", {})
    pack = paths.get("pack") if isinstance(paths, dict) else None
    if isinstance(pack, str) and pack.strip():
        return os.path.join(os.path.dirname(os.path.abspath(project)), os.path.expanduser(pack))
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--project")
    d.add_argument("--pack")
    c = sub.add_parser("check")
    c.add_argument("dir")
    c.add_argument("--framework")
    lk = sub.add_parser("lock")
    lk.add_argument("checkout")
    lk.add_argument("export")
    args = parser.parse_args(argv)
    if args.cmd == "lock":
        try:
            print("crew-pack: wrote %s" % write_lock(args.checkout, args.export))
        except (OSError, ValueError) as e:
            print("crew-pack: %s" % e, file=sys.stderr)
            return 1
        return 0
    cfg = load_module("crew_config", "core/crew-config.py")
    harnesses = cfg.harnesses
    if args.cmd == "discover":
        try:
            pack_dir = args.pack or (project_pack(args.project) if args.project else None)
        except (OSError, tomllib.TOMLDecodeError) as e:
            print("crew-pack: cannot read %s (%s)" % (args.project, e))
            return 1
        reg, problems = discover(cfg, harnesses, pack_dir)
        for kind, items in reg.items():
            for name, (source, path) in sorted(items.items()):
                print("%s %s %s %s" % (kind, name, source, os.path.relpath(path, ROOT) if source == "core" else path))
    else:
        pack, problems = load(args.dir, cfg, harnesses)
        if pack and args.framework:
            reason = compatible(pack, args.framework)
            problems += [reason] if reason else []
    for problem in problems:
        print(problem)
    if problems:
        print("crew-pack: FAILED (%d problem%s)" % (len(problems), "" if len(problems) == 1 else "s"), file=sys.stderr)
        return 1
    if args.cmd == "check":
        print("crew-pack: OK (%s %s)" % (pack["name"], pack.get("version", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
