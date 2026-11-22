#!/usr/bin/env python3
"""Install-time profile (config.toml) tool for mdstack. Python 3.11+ stdlib only.

Usage: crew-config.py validate FILE [--install] [--pack-manifest FILE] (profile or pack manifest)
       crew-config.py resolve --project FILE [--org-profile FILE] [--install] [--pack-manifest FILE]
       crew-config.py sensitive --project FILE [--org-profile FILE] [--diff | --paths-only] < paths.txt (diff.txt with --diff)
       crew-config.py class-flavor --project FILE [--org-profile FILE] [--express] < paths.txt
       crew-config.py precheck-scope --project FILE [--org-profile FILE] < paths.txt
`validate` checks one profile against the schema; `resolve` merges the config
layers and prints each key with the layer that set it (per-key provenance).
Both also load the tracker and change backend maps' [ids] patterns; `resolve`
prints them as ids.item and ids.change, plus the change map's ids.marker_key
when declared (docs/handoff.md#id-declaration).
Every problem prints as `file:key: reason`; exit 1 if any, else 0.
`precheck-scope` classifies each changed path by builder.precheck.owners and
prints JSON; a path absent from the working directory is `removed`, never queried.
Exit 3 on unowned code, 4 on an owners query failure (stop).
`sensitive --diff` reads a `git diff --no-renames` unified diff and adds content rule matches (#879);
`sensitive` exits 3 on incomplete input: a path list with content rules, or an unreadable diff.
With a bound classify.sensitive extension it also runs that command on the same stdin and unions its matches,
fail-closed (#880).
paths.pack records an org pack directory relative to the project file.
Without --project, the project file is $CREW_PROJECT, else $MDSTACK_CONFIG, else <root>/config.toml, root being
$CREW_ROOT or ~/.mdstack (#1316, #1324).
Schema: docs/profile.md and docs/flavors.md (flavor presets, compositions and floor).
"""
import argparse
import glob
import importlib.util
import os
import re
import subprocess
import sys
import tomllib
import types
import urllib.parse

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location("secret_patterns", os.path.join(_ROOT, "core", "secret-patterns.py"))
secret_patterns = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(secret_patterns)
_spec = importlib.util.spec_from_file_location("path_glob", os.path.join(_ROOT, "core", "path-glob.py"))
path_glob = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(path_glob)
_spec = importlib.util.spec_from_file_location(  # harness adapters: engine choices and install pointers
    "crew_harness", os.path.join(_ROOT, "harnesses", "crew-harness.py"))
harnesses = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harnesses)
_spec = importlib.util.spec_from_file_location(  # session adapters: the tmux runtime's session_backend choices
    "crew_session", os.path.join(_ROOT, "environments", "terminal", "crew-session.py"))
sessions = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sessions)

ROLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "roles", "eng")


def load_roles(directory):
    """Each <directory>/<role>.toml is one role's authored definition (docs/roles-registry.md), its file stem the role
    ID. The registry is their union in rank order, unranked roles after by ID, without each file's schema_version."""
    roles = {}
    for path in glob.glob(os.path.join(directory, "*.toml")):
        with open(path, "rb") as f:
            roles[os.path.basename(path)[:-5]] = {k: v for k, v in tomllib.load(f).items() if k != "schema_version"}
    return dict(sorted(roles.items(), key=lambda kv: ("rank" not in kv[1], kv[1].get("rank", 0), kv[0])))


ROLE_REGISTRY = load_roles(ROLES_DIR)

REQUIRED = object()
# Render-time note roles (runtime.options.notes.render): every registry role and the pool leads.
NOTE_ROLES = list(ROLE_REGISTRY) + ["builder-lead", "reviewer-lead", "synthesizer-lead"]
# Registry identities a profile may leave out; resolve fills gh_user from the coordinator's author login (#584).
OPTIONAL_IDENTITIES = [r["identity_key"].removeprefix("identities.") for r in ROLE_REGISTRY.values() if r.get("identity_optional")]
# tmux role caps (runtime.options.<cap>): each capped role's default, and the caps that may be 0 to run no such role.
ROLE_CAPS = {r["cap_key"].removeprefix("runtime.options."): (int, r["cap_default"]) for r in ROLE_REGISTRY.values() if "cap_default" in r}
ZERO_CAPS = [r["cap_key"].removeprefix("runtime.options.") for r in ROLE_REGISTRY.values() if r.get("cap_min", 1) == 0]
SENSITIVE_PATHS = [".github/workflows/**", "**/auth/**", "auth/**", "**/secrets/**", "secrets/**",
                   "**/permissions/**", "permissions/**", "**/access-control/**", "access-control/**",
                   "**/migrations/**", "migrations/**", "**/deletions/**", "deletions/**"]
SPEC_PATHS = ["docs/specs/**"]  # spec globs when [spec] paths is unset (docs/protocol.md §7 spec change, #398)
MERGE_GRANT_SCOPES = ["approved", "spec"]  # runtime.options.merge_grant_scope values
# Operation names per concern, from docs/interfaces.md.
OPERATIONS = {
    "change": ["open", "push", "read-head", "read-diff-paths", "update-from-base", "land", "close",
               "list-open", "read-state", "read-default-branch", "delete-branch",
               "cli-name", "cli-repo-flag", "cli-unscoped"],
    "review": ["post-verdict", "post-narrative", "list-verdicts", "request-rereview"],
    "tracker": ["create-item", "assign", "link", "milestone", "board-status", "list-items", "label", "comment",
                "close-item"],
    "state-tags": ["set-clear-read", "set-approved", "set-changes"],
    "markers": ["write", "read", "write-item", "read-item", "edit-status"],
    "ci": ["check-status", "failing-jobs"],
    "events": ["subscribe-or-poll"],
    "owner-channel": ["ask", "notify"],
    "release": ["cut", "approve-check", "record-release", "notify"],
}
OPTIONAL_CONCERNS = ["release", "classify", "status"]  # a backend or profile may leave these out (docs/interfaces.md)
# Extension concerns (docs/interfaces.md#bindable-sensitivity-design): core runs the bound command beside its own
# rules, so no backend map replaces them as <op:> tokens, and bootstrap and a team's pack never bind them.
EXTENSION_OPERATIONS = {"classify": ["sensitive"]}
# The shared-status concern (docs/specs/shared-status.md §7, #1313): optional, run by the runtime's status commands
# through the bound backend map's [status] commands; not an <op:> token, and bootstrap and a team's pack never bind it.
STATUS_OPERATIONS = {"status": ["read-records", "publish-record"]}
CONCERNS = dict(OPERATIONS, **EXTENSION_OPERATIONS, **STATUS_OPERATIONS)
# The knowledge concern (docs/interfaces.md#knowledge, #1229): a connector manifest may declare it, alone or beside the
# core concerns; no profile binds it, since sources and credentials live in the install's private config.
KNOWLEDGE_OPERATIONS = {"knowledge": ["read", "propose-edit"]}
# Operations only an async land needs (docs/interfaces.md#asynchronous-land-design); a sync manifest leaves them out.
# change.read-branch-head and tracker.unlabel: only mdstack handoff with repo.control_item and a non-GitHub backend runs
# them (docs/handoff.md). read-diff: needed only by a profile with [[sensitive.content]] rules
# (docs/interfaces.md#change, #879).
# read-landed: only an async land whose status mapping names `landed` without a revision group (#1042).
# land-stack and stack-status: only a backend declaring land.stack, the session stack land (#1605); read-revision-id
# only a change.land-stack using <stack-revisions> (#1722).
# land-delete-arg: the land argument that also deletes an eligible head branch (#395); without it, close-out deletes.
CONDITIONAL_OPERATIONS = {"change": ["publish", "land-status", "read-branch-head", "read-diff", "read-landed",
                                     "land-stack", "stack-status", "read-revision-id", "land-delete-arg"],
                          "tracker": ["unlabel"]}
LAND_FIELDS = {"mode": (str, "sync"), "opens_draft": (bool, False), "serializes": (bool, False),
               "tests_against_tip": (bool, False), "change_placeholder": (str, "n"), "head_guard": (bool, True),
               "status": (dict, None), "stack": (bool, False), "stack_tests_against_tip": (bool, False),
               "stack_status": (str, "stack")}
LAND_STATES = ["none", "queued", "landing", "landed", "failed"]
STRATEGY_FIELDS = {"update_from_base": (str, "merge"), "retains_prior_heads": (bool, False)}
ASYNC_RUNTIMES = ["tmux", "session"]  # runtimes with an async land binding; others refuse land.mode = "async"
RELEASE_GATE_OPS = ["approve-check", "record-release"]  # a profile with [release] must keep these
BACKENDS = ["github"]
RUNTIME_OPTIONS = {"grok-bot": {"max_active_milestones": (int, 1)},
                   "tmux": {"max_active_milestones": (int, 1), "session": (str, None), "session_backend": (str, "tmux"), **ROLE_CAPS,
                                        "tmux_server": (str, "default"), "present_builders": (int, None), "present_reviewers": (int, None),
                                        "idle_builder_ttl": (int, 1800), "max_suites": (int, None), "max_load": ("number", None),
                                        "load_high": ("number", 6.0), "load_low": ("number", 4.0), "error_high": (int, 3), "memory_high": (str, None),
                                        "schedule_interval": (int, 120), "schedule_ramp": (int, 2), "stuck_after": (int, 1800), "poll_interval": (int, 60), "host_scan_interval": (int, 15),
                                        "land_poll_interval": (int, 60), "land_timeout": (int, 3600), "train_min": (int, 2), "train_window": (int, 600),
                                        "merge_grant": (str, "none"), "merge_grant_scope": ("list[str]", None), "lone_pr_land": (str, "train"),
                                        "release_delegation": (str, "none"),
                                        "train_local_checks": (bool, False), "mirror_deferral": (str, "none"),
                                        "mirror": (str, "live-copy"),
                                        "hold_label_blocks": (bool, True), "permission_mode": (str, "bypass"),
                                        "confinement": (str, "off"), "sandbox_env": (str, ""), "notes": (dict, {}), "launch": (dict, None),
                                        "role_runtime": (dict, None),
                                        "slack_webhook_env": (str, None), "slack_digest_interval": (int, 3600)},
                   # Hosted or hand-started coordinator with native-subagent or CLI workers (docs/runtimes/session.md, #914).
                   "session": {"max_active_milestones": (int, 1), "session_backend": (str, "native"), "builders": (int, 5),
                               "reviewers": (int, 2), "researchers": (int, 0), "present_builders": (int, None),  # opt-in sweep (#1724)
                               "present_reviewers": (int, None), "merge_grant": (str, "none"),
                               "merge_grant_scope": ("list[str]", None), "release_delegation": (str, "none"),
                               "lone_pr_land": (str, "train"), "train_min": (int, 2), "train_window": (int, 600),
                               "land_poll_interval": (int, 60), "land_timeout": (int, 3600),  # async land (#1351)
                               "train_local_checks": (bool, False), "mirror_deferral": (str, "none"),
                               "mirror": (str, "live-copy"), "hold_label_blocks": (bool, True), "notes": (dict, {}),
                               # mdstack up's coordinator launch (#1548): its tmux session, harness flags and topology
                               "session": (str, None), "permission_mode": (str, "bypass"), "launch": (dict, None),
                               "role_runtime": (dict, None),  # one role from another runtime's templates (#1055)
                               "isolation": (str, "worktree")}}  # assigned-checkout: pre-provisioned checkouts (#1959)
SESSION_BACKENDS = {"tmux": sessions.CHOICES, "session": ["native", "cli", "hosted"]}  # runtime.options.session_backend
LAUNCH_SESSION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")  # launch.resume: a harness conversation id
TRIAGE_MODES = ["shadow", "apply"]  # [triage] mode (docs/triage.md Shadow mode and calibration)
# [report] status set and its neutral fallbacks (docs/roles.md Report skeleton, #431); emoji = false drops every emoji.
REPORT_STATUS = {"pass": "✅", "changes": "🔁", "landed": "🚢", "escalated": "⛔", "blocked": "🚧"}
DOCS_DEFAULTS = {"enabled": False, "interval_days": 7, "stale_days": 90, "size_budget": 500}  # [docs] (#1024)
SPEC_EXTERNAL = re.compile(r"[a-zA-Z][a-zA-Z0-9+.-]*://[^\s`<>]+")  # [docs] specs_external: a URL (#1725)
DOCS_ESSENTIALS = ["overview", "agent_guide", "architecture", "runbook", "decisions", "specs"]  # docs/project-doc-set.md
INSTALL_SOURCES = ["github", "url", "mirror", "git"]  # [install] source (docs/bootstrap.md Release sources, #882)
TRACKER_REPO = re.compile(r"[A-Za-z0-9_.<>-]+/[A-Za-z0-9_.<>-]+")  # <owner>/<repo> before install
PERMISSION_MODES = ["bypass", "auto", "safe"]  # tmux role-window launch (docs/runtimes/tmux.md, #293)
ENGINES = harnesses.ENGINES  # tier orders, fallback and pack capabilities; the coordinator needs harnesses.LAUNCHABLE
EFFORTS = ["low", "medium", "high"]
TIER_EFFORT = {"trivial": "low", "default": "medium", "deep": "high"}
CAPABILITY = re.compile(r"supported|unsupported|emulated \(.*\S.*\)")
TYPE_NAMES = {str: "string", int: "integer", bool: "boolean", float: "float", list: "list", dict: "table"}
# Host inventory and project affinity (docs/runtimes/multi-device.md, #204).
HOST_NAME = re.compile(r"[a-z0-9-]{1,63}")
HOST_ADDRESS = re.compile(r"(?=.{1,253}$)[a-z0-9-]{1,63}(\.[a-z0-9-]{1,63})*\.[a-z-][a-z0-9-]{0,62}")  # a DNS name, no IP
CONNECT_TRANSPORTS = ["ssh", "mosh", "et"]
HOST_OS, HOST_ARCH = ["linux", "macos"], ["x86_64", "arm64"]
DEVICES = ["ios-simulator", "ios-device", "android-emulator", "android-device"]
PLACED_PASSES = {r: v["placement"] for r, v in ROLE_REGISTRY.items() if "placement" in v}  # mdstack spawn passes
# Pack harness pointer registry (docs/bootstrap.md#pack-harness-pointers-design, #883): adapters whose
# install pointer bootstrap implements, and the Q4 built-in targets no entry may claim.
HARNESS_INSTALLS = harnesses.INSTALLS
HARNESS_BUILTINS = harnesses.INSTALL_BUILTINS
HARNESS_ROOTS = ["project", "home"]  # a file entry's target root (#1032): home is the per-user agent home, $HOME
# Backend map [ids] (docs/handoff.md#id-declaration, #936): item from the tracker map, change from the change map.
ID_CONCERNS = {"item": "tracker", "change": "change"}
ID_MARKER_KEYS = ["change", "item"]  # the change map's marker_key: selfgate keys on pr= or issue= (#876, #1031)
ID_DEFAULT = "[1-9][0-9]*"
# Canonical state tags (docs/protocol.md §4) a project's repo.labels may rename on its tracker (team §9.8).
STATE_TAGS = ["crew:ready", "crew:in-review", "crew:changes", "crew:approved", "crew:escalated", "crew:needs-md",
              "crew:hold", "crew:external", "crew:spec", "crew:needs-mirror", "crew:express"]
ID_UNSAFE = set(" \t\r\n<>=\"'`")  # an id must never break a marker line or a command argument
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
_spec = importlib.util.spec_from_file_location("status_record", os.path.join(_ROOT, "core", "status-record.py"))
status_record = importlib.util.module_from_spec(_spec)  # shared-status record S and [status] patterns (#1313)
_spec.loader.exec_module(status_record)
# [status] (docs/specs/shared-status.md §2): key -> (type, default); bounds checked in validate.
STATUS_FIELDS = {"enabled": (bool, False), "destination": (str, None), "instance_id": (str, None),
                 "decision_log": (str, None), "publish_interval": (int, 300), "stale_after": (int, 900)}


def backend_ids(profile, pack_base, err, backends=BACKENDS):
    """{key: (pattern, map name or None)} from the tracker and change backend maps; None is the default.

    A declared marker_key in the change map adds marker_key: (value, map name); undeclared, it is absent.

    A map is the pack's render/backends/<name>.toml, else templates/backends/<name>.toml. err(name, key, reason)."""
    out, maps, markers = {key: (ID_DEFAULT, None) for key in ID_CONCERNS}, {}, {}
    table = profile.get("backends") if isinstance(profile.get("backends"), dict) else {}
    for key, concern in ID_CONCERNS.items():
        name = table[concern].get("name") if isinstance(table.get(concern), dict) else None
        if name not in backends:
            continue
        if name not in maps:
            maps[name] = {}
            paths = ([os.path.join(pack_base, "render", "backends", name + ".toml")] if pack_base else []) + \
                [os.path.join(TEMPLATES_DIR, "backends", name + ".toml")]
            path = next((p for p in paths if os.path.isfile(p)), None)
            if path is None:  # no map: the defaults stand
                continue
            try:
                with open(path, "rb") as f:
                    ids = tomllib.load(f).get("ids", {})
            except (OSError, tomllib.TOMLDecodeError) as e:
                err(name, "(file)", "cannot read backend map %s (%s)" % (path, e))
                continue
            maps[name] = check_table(lambda k, reason: err(name, k, reason), "ids", ids,
                                     dict({k: (str, None) for k in ID_CONCERNS}, marker_key=(str, None),
                                          **{"status-destination": (str, None)}))
            maps[name].pop("status-destination", None)  # the status map's own key (status_destination)
            marker = maps[name].pop("marker_key", None)
            check_choice(lambda k, reason: err(name, k, reason), "ids.marker_key", marker, ID_MARKER_KEYS)
            if marker in ID_MARKER_KEYS:
                markers[name] = marker
            for k, pattern in list(maps[name].items()):
                try:
                    unsafe = [c for c in [""] + sorted(ID_UNSAFE) if re.fullmatch(pattern, c)]
                except re.error as e:
                    unsafe = None
                    err(name, "ids." + k, "pattern does not compile (%s)" % e)
                if unsafe:
                    err(name, "ids." + k, "pattern matches %r; an id must be nonempty with no whitespace or %s"
                        % (unsafe[0], " ".join(sorted(ID_UNSAFE - set(" \t\r\n")))))
                if unsafe is None or unsafe:
                    del maps[name][k]
        if key in maps[name]:
            out[key] = (maps[name][key], name)
        if concern == "change" and name in markers:
            out["marker_key"] = (markers[name], name)
    return out


def status_map(name, pack_base):
    """The status backend's map path: the pack's render/backends/<name>.toml, else the bundled one; None if neither."""
    paths = ([os.path.join(pack_base, "render", "backends", name + ".toml")] if pack_base else []) + \
        [os.path.join(TEMPLATES_DIR, "backends", name + ".toml")]
    return next((p for p in paths if os.path.isfile(p)), None)


def status_destination(profile, pack_base, err):
    """(status-destination pattern, map name) from the bound status backend's map [ids], or None: no [status]
    table, no map or no declared pattern (docs/specs/shared-status.md §2). err(name, key, reason)."""
    if not isinstance(profile.get("status"), dict):
        return None
    table = profile.get("backends") if isinstance(profile.get("backends"), dict) else {}
    name = (table.get("status") if isinstance(table.get("status"), dict) else {}).get("name", "github")
    path = status_map(name, pack_base) if isinstance(name, str) else None
    if path is None:
        return None
    try:
        with open(path, "rb") as f:
            ids = tomllib.load(f).get("ids", {})
    except (OSError, tomllib.TOMLDecodeError) as e:
        err(name, "(file)", "cannot read backend map %s (%s)" % (path, e))
        return None
    pattern = ids.get("status-destination") if isinstance(ids, dict) else None
    if pattern is None:
        return None
    try:
        re.compile(pattern)
    except (re.error, TypeError) as e:
        err(name, "ids.status-destination", "pattern does not compile (%s)" % e)
        return None
    return pattern, name


def validate_status(table, err, destination=None):
    """[status] (docs/specs/shared-status.md §2); destination is the bound map's (pattern, name), else None."""
    st = check_table(err, "status", table, STATUS_FIELDS)
    if "instance_id" in st and not status_record.INSTANCE_ID.fullmatch(st["instance_id"]):
        err("status.instance_id", "expected [a-z0-9][a-z0-9-]{0,62}, got %s" % json.dumps(st["instance_id"]))
    if "decision_log" in st and status_record.url_problem(st["decision_log"], ["issues"], None):
        err("status.decision_log", "expected an issue URL https://github.com/<owner>/<repo>/issues/<n>, got %s"
            % json.dumps(st["decision_log"]))
    if "destination" in st and destination is None:
        err("status.destination", "the status backend's map declares no [ids] status-destination pattern")
    elif "destination" in st and not re.fullmatch(destination[0], st["destination"]):
        err("status.destination", "%s does not match the status-destination pattern %s (status backend %s)"
            % (json.dumps(st["destination"]), destination[0], destination[1]))
    interval = st.get("publish_interval", 300)
    if not 60 <= interval <= 3600:
        err("status.publish_interval", "must be 60-3600 seconds, got %d" % interval)
    stale = st.get("stale_after", 900)
    if not 2 * interval <= stale <= 86400:
        err("status.stale_after", "must be 2 x publish_interval (%d) to 86400 seconds, got %d" % (2 * interval, stale))
    if st.get("enabled"):
        for key in ("destination", "instance_id", "decision_log"):
            if key not in table:
                err("status." + key, "missing; enabled = true needs destination, instance_id and decision_log")


def type_name(value):
    return TYPE_NAMES.get(type(value), type(value).__name__)


def token_reasons(value):
    """Secret-scan reasons for one string, using core/secret-patterns.py (shared with check-repo.py)."""
    reasons = [reason for _, rx, reason in secret_patterns.PATTERNS if rx.search(value)]
    if any(not secret_patterns.is_placeholder(m.group(1)) for m in secret_patterns.BEARER.finditer(value)):
        reasons.append("bearer auth header with a literal value")
    if any(not (secret_patterns.is_placeholder(m.group(1)) and secret_patterns.is_placeholder(m.group(2)))
           for m in secret_patterns.URL_CRED.finditer(value)):
        reasons.append("URL with embedded credentials")
    return reasons


def scan_tokens(err, path, value):
    if isinstance(value, dict):
        for k, v in value.items():
            scan_tokens(err, "%s.%s" % (path, k) if path else k, v)
    elif isinstance(value, list):
        for i, v in enumerate(value):
            scan_tokens(err, "%s[%d]" % (path, i), v)
    elif isinstance(value, str):
        for reason in token_reasons(value):
            err(path, "token-shaped value (%s); refer to credentials by mechanism" % reason)


def scan_install_placeholders(profile, err):
    renderer_spec = importlib.util.spec_from_file_location(
        "install_renderer", os.path.join(os.path.dirname(os.path.abspath(__file__)), "crew-render.py"))
    renderer = importlib.util.module_from_spec(renderer_spec)
    renderer_spec.loader.exec_module(renderer)

    def scan(value, path=""):
        if isinstance(value, dict):
            for key, child in value.items():
                scan(child, "%s.%s" % (path, key) if path else key)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                scan(child, "%s[%d]" % (path, i))
        elif isinstance(value, str):
            for match in renderer.TOKEN.finditer(value):
                if match.group(1) not in renderer.KEPT:
                    err(path, "unfilled install-time placeholder <%s>" % match.group(1))
    scan(profile)


def check_table(err, path, table, fields):
    """Check keys of one table against {key: (type, default-or-REQUIRED)}; return checked values."""
    if not isinstance(table, dict):
        err(path, "expected table, got %s" % type_name(table))
        return {}
    for key in sorted(table.keys() - fields.keys()):
        err("%s.%s" % (path, key), "unknown key")
    out = {}
    for key, (typ, default) in fields.items():
        sub = "%s.%s" % (path, key)
        if key not in table:
            if default is REQUIRED:
                err(sub, "missing required key")
            continue
        value = table[key]
        if typ == "list[str]":
            if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
                err(sub, "expected list of strings, got %s" % type_name(value))
                continue
        elif typ == "number":
            if type(value) not in (int, float):
                err(sub, "expected number, got %s" % type_name(value))
                continue
        elif isinstance(typ, tuple):
            if type(value) not in typ:
                err(sub, "expected %s, got %s" % (" or ".join(TYPE_NAMES[t] for t in typ), type_name(value)))
                continue
        elif type(value) is not typ:
            err(sub, "expected %s, got %s" % (TYPE_NAMES[typ], type_name(value)))
            continue
        out[key] = value
    return out


def check_choice(err, path, value, choices):
    if value is not None and value not in choices:
        err(path, "unknown value %r (expected one of: %s)" % (value, ", ".join(choices)))


def check_choices(err, path, values, choices):
    for i, value in enumerate(values):
        check_choice(err, "%s[%d]" % (path, i), value, choices)


def check_platform(err, path, table, fields):
    """os, arch and devices of a host's capabilities or a placement rule's needs."""
    out = check_table(err, path, table, dict({"os": (str, None), "arch": (str, None), "devices": (list, None)}, **fields))
    check_choice(err, path + ".os", out.get("os"), HOST_OS)
    check_choice(err, path + ".arch", out.get("arch"), HOST_ARCH)
    check_choices(err, path + ".devices", out.get("devices", []), DEVICES)
    return out


def validate_connect(err, path, table):
    """hosts.<name>.connect: the owner's `mdstack connect` alias, transport, proxy command and fixed options."""
    c = check_table(err, path, table, {"alias": (str, None), "transport": (str, None), "proxy": (str, None),
                                       "options": ("list[str]", None)})
    if "alias" in c and not HOST_NAME.fullmatch(c["alias"]):
        err(path + ".alias", "expected [a-z0-9-], 1-63 characters")
    check_choice(err, path + ".transport", c.get("transport"), CONNECT_TRANSPORTS)
    if c.get("transport") == "et" and "proxy" in c:
        err(path + ".proxy", "et takes its ProxyCommand from your SSH config; set proxy only for ssh or mosh")


def validate_hosts(profile, top, err):
    """[hosts.<name>] and [placement]: hosts by overlay network name, or a DNS `address`, never an IP (spec R1)."""
    hosts = {}
    for name, table in top.get("hosts", {}).items():
        path = "hosts." + name
        if not HOST_NAME.fullmatch(name):
            err(path, "expected an overlay network name ([a-z0-9-], 1-63 characters); no IP literal, user@ or :port")
        h = check_table(err, path, table, {"primary": (bool, False), "forge": (bool, True), "capabilities": (dict, REQUIRED),
                                            "max_runs": (int, REQUIRED), "roles": (list, None), "root": (str, None),
                                            "toolchain_bin": (str, None), "address": (str, None), "checkout": (str, None),
                                            "connect": (dict, None)})
        if "address" in h and not HOST_ADDRESS.fullmatch(h["address"]):
            err(path + ".address", "expected a dotted DNS name ([a-z0-9-] labels); no IP literal, user@ or :port")
        if "connect" in h:
            validate_connect(err, path + ".connect", h["connect"])
        forge = h.get("forge", True)
        check_choice(err, path + ".checkout", h.get("checkout"), ["mirror", "command"])
        caps = check_platform(err, path + ".capabilities", h["capabilities"], {"os": (str, REQUIRED), "arch": (str, REQUIRED),
                              "engines": ("list[str]", REQUIRED if forge else None)}) if "capabilities" in h else {}
        check_choices(err, path + ".capabilities.engines", caps.get("engines", []), ENGINES)
        check_choices(err, path + ".roles", h.get("roles", []), list(PLACED_PASSES))
        if h.get("max_runs", 1) < 1:
            err(path + ".max_runs", "must be >= 1, got %d" % h["max_runs"])
        if not forge and h.get("primary"):
            err(path + ".forge", "a forge-less host cannot be the primary")
        if not forge and h.get("roles"):
            err(path + ".roles", "a forge-less host takes runner jobs only; expected no roles")
        hosts[name] = dict(caps, primary=h.get("primary", False), forge=forge,
                           roles=h.get("roles", list(PLACED_PASSES)) if forge else [])
    aliases = list(hosts) + [t["connect"]["alias"] for n, t in top.get("hosts", {}).items() if isinstance(t, dict)
                             and isinstance(t.get("connect"), dict) and t["connect"].get("alias") not in (None, n)]
    for alias in sorted({a for a in aliases if aliases.count(a) > 1}):
        err("hosts", "connect alias %r names more than one host" % alias)
    rt = profile.get("runtime")
    if "hosts" in top and isinstance(rt, dict) and rt.get("name") not in (None, "tmux", "session"):
        err("hosts", "a host inventory needs runtime tmux or session, got %r" % rt.get("name"))
    if "placement" in top and isinstance(rt, dict) and rt.get("name") == "session":  # host check only (#1122)
        err("placement", "placement needs runtime tmux, got 'session'")
    primaries = [n for n, h in hosts.items() if h["primary"]]
    if "hosts" in top and len(primaries) != 1:
        err("hosts", "expected exactly one host with primary = true, got %d" % len(primaries))
    if "placement" in top and "hosts" not in top:
        return err("placement", "needs a [hosts] table")
    pl = check_table(err, "placement", top["placement"], {"hosts": ("list[str]", None), "rules": (list, None)}) \
        if "placement" in top else {}
    affinity = pl.get("hosts", primaries[:1])
    for i, name in enumerate(pl.get("hosts", [])):
        if name not in hosts:
            err("placement.hosts[%d]" % i, "names no host in [hosts]: %r" % name)
        elif not hosts[name]["forge"]:
            err("placement.hosts[%d]" % i, "names a forge-less host: %r" % name)
    for role in PLACED_PASSES if hosts else []:
        if not any(role in hosts[n]["roles"] for n in affinity if n in hosts):
            err("placement.hosts", "no host here takes role %s (default: the primary host)" % role)
    for i, rule in enumerate(pl.get("rules", [])):
        path = "placement.rules[%d]" % i
        r = check_table(err, path, rule, {"role": (str, REQUIRED), "pass": (str, None), "paths": ("list[str]", None),
                                          "needs": (dict, REQUIRED)})
        check_choice(err, path + ".role", r.get("role"), list(PLACED_PASSES))
        if r.get("role") in PLACED_PASSES:
            check_choice(err, path + ".pass", r.get("pass"), PLACED_PASSES[r["role"]])
        needs = check_platform(err, path + ".needs", r["needs"], {}) if "needs" in r else None
        if needs is not None and r.get("role") in PLACED_PASSES and not any(
                r["role"] in h["roles"] and all(h.get(k) == needs[k] for k in ("os", "arch") if k in needs)
                and all(d in h.get("devices", []) for d in needs.get("devices", [])) for h in hosts.values()):
            err(path + ".needs", "no host taking role %s meets these needs" % r["role"])


def check_capabilities(err, path, table, concern, required):
    fields = {op: (str, REQUIRED if required else None) for op in dict(CONCERNS, **KNOWLEDGE_OPERATIONS)[concern]}
    fields.update({op: (str, None) for op in CONDITIONAL_OPERATIONS.get(concern, [])})
    caps = check_table(err, path, table, fields)
    for op, value in caps.items():
        if not CAPABILITY.fullmatch(value):
            err("%s.%s" % (path, op), "expected supported, unsupported or emulated (<how>)")
        elif concern in EXTENSION_OPERATIONS and value.startswith("emulated"):
            err("%s.%s" % (path, op), "expected supported or unsupported (an extension runs or does not)")


# semver.org 2.0.0, no leading v; the same shape as changelog-cut.py's SEMVER.
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$")


def check_land(err, land, change_caps, runtime=None):
    """The [land] declaration against the change capabilities that must back it (docs/interfaces.md#declaration)."""
    def unsupported(op):
        return change_caps.get(op, "unsupported") == "unsupported"
    mode = land.get("mode", "sync")
    if mode == "async" and unsupported("land-status"):
        err("land.mode", "async needs change.land-status supported or emulated")
    if mode == "async" and runtime is not None and runtime not in ASYNC_RUNTIMES:
        err("land.mode", "runtime %s has no async land binding; expected sync" % runtime)
    if land.get("opens_draft") and unsupported("publish"):
        err("land.opens_draft", "needs change.publish supported or emulated")
    per_change = land.get("stack") and land.get("stack_status") == "per-change"
    # a sync stack binding fills its own change placeholder; its per-change readback maps native status (#1722)
    allowed = {"change_placeholder": land.get("stack"), "status": per_change}
    for key in ("opens_draft", "serializes", "tests_against_tip", "change_placeholder", "status"):
        if mode == "sync" and land.get(key) and not allowed.get(key):
            err("land." + key, "only valid with mode = \"async\"")
    if mode == "sync" and land.get("head_guard") is False:
        err("land.head_guard", "only valid with mode = \"async\"")
    placeholder = land.get("change_placeholder", "n")
    if not isinstance(placeholder, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", placeholder):
        err("land.change_placeholder", "expected a placeholder name ([a-z][a-z0-9-]*, no angle brackets)")
    status = land.get("status")
    for pattern, state in (status.items() if isinstance(status, dict) else []):
        try:
            re.compile(pattern)
        except re.error as e:
            err("land.status", "pattern %r is not a regular expression (%s)" % (pattern, e))
        check_choice(err, "land.status.%s" % pattern, state, LAND_STATES)
    if landed_needs_read(status) and unsupported("read-landed"):
        err("land.status", "a landed pattern without a (?P<revision>...) group needs change.read-landed supported "
            "or emulated")
    check_choice(err, "land.stack_status", land.get("stack_status", "stack"), ["stack", "per-change"])
    readback = "land-status" if per_change else "stack-status"
    for op in ("land-stack", readback):  # session stack land (docs/interfaces.md#stack-land, #1605, #1722)
        if land.get("stack") and unsupported(op):
            err("land.stack", "needs change.%s supported or emulated" % op)
    if land.get("stack_tests_against_tip") and not land.get("stack"):
        err("land.stack_tests_against_tip", "only valid with stack = true")
    if "stack_status" in land and not land.get("stack"):
        err("land.stack_status", "only valid with stack = true")
    if per_change and land.get("stack_tests_against_tip"):
        err("land.stack_tests_against_tip", "per-change readback names no combined-stack check; expected false")


def landed_needs_read(status):
    """True when a declared land.status pattern maps to landed and captures no revision (docs/interfaces.md)."""
    def groups(pattern):
        try:
            return re.compile(pattern).groupindex
        except re.error:
            return {"revision": 0}
    return isinstance(status, dict) and any(
        state == "landed" and "revision" not in groups(pattern) for pattern, state in status.items())


def check_strategy(err, strategy):
    """The [strategy] declaration: rebase only with every earlier head kept readable (docs/interfaces.md#declaration-2)."""
    rebase = strategy.get("update_from_base", "merge") == "rebase"
    if rebase and strategy.get("retains_prior_heads") is not True:
        err("strategy.update_from_base", "rebase needs retains_prior_heads = true")
    if not rebase and strategy.get("retains_prior_heads"):
        err("strategy.retains_prior_heads", "only valid with update_from_base = \"rebase\"")


def pack_file(err, path, pack_dir, name):
    """A pack-relative file that resolves, symlinks followed, to a regular UTF-8 file inside the pack; its text."""
    root = os.path.realpath(pack_dir)
    real = os.path.realpath(os.path.join(root, name))
    if os.path.commonpath([root, real]) != root:
        return err(path, "escapes the pack directory: %r" % name)
    if not os.path.isfile(real):
        return err(path, "not a regular file in the pack: %r" % name)
    try:
        with open(real, encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return err(path, "cannot read as UTF-8: %r" % name)


def validate_harness_registry(err, name, pack_dir):
    """pack.harness: the [[pointer]] registry's static checks; bootstrap repeats the file checks at install."""
    text = pack_file(err, "pack.harness", pack_dir, name)
    if text is None:
        return
    try:
        registry = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        return err("pack.harness", "invalid TOML in %s (%s)" % (name, e))
    targets = set()
    for i, entry in enumerate(check_table(err, "pack.harness", registry, {"pointer": (list, REQUIRED)}).get("pointer", [])):
        path = "pack.harness.pointer[%d]" % i
        note = isinstance(entry, dict) and "launch_note" in entry
        fields = {"harness": (str, REQUIRED), "launch_note": (str, REQUIRED)} if note else {
            "harness": (str, REQUIRED), "target": (str, REQUIRED), "source": (str, REQUIRED), "mode": (str, None),
            "root": (str, None)}
        e = check_table(err, path, entry, fields)
        harness = e.get("harness")
        if note and harness is not None and harness not in harnesses.LAUNCH_NOTES:
            err(path + ".harness", "a launch note is for %s only, got %r" % (
                ", ".join(harnesses.LAUNCH_NOTES), harness))
        elif harness in ENGINES and harness not in HARNESS_INSTALLS:
            err(path + ".harness", "adapter %s has no install pointer bootstrap implements (expected one of: %s)"
                % (harness, ", ".join(HARNESS_INSTALLS)))
        else:
            check_choice(err, path + ".harness", harness, HARNESS_INSTALLS)
        check_choice(err, path + ".mode", e.get("mode"), ["copy", "pointer"])
        check_choice(err, path + ".root", e.get("root"), HARNESS_ROOTS)
        target, root = e.get("target"), e.get("root", "project")
        if target is None:
            pass
        elif target.startswith(("/", "~")):
            err(path + ".target", "expected a %s-relative path, got %r" % (root, target))
        elif any(part in ("", ".", "..", ".git") for part in target.split("/")):
            err(path + ".target", "expected a normalized path with no empty, ., .. or .git component, got %r" % target)
        elif (root, target) in targets:
            err(path + ".target", "duplicate target %r" % target)
        elif root == "project" and target in HARNESS_BUILTINS:
            err(path + ".target", "collides with a built-in bootstrap target: %r" % target)
        targets.add((root, target))
        for key in ("source", "launch_note"):
            if key in e:
                pack_file(err, "%s.%s" % (path, key), pack_dir, e[key])


def validate_manifest(manifest, err, pack_dir=None, external_pin=True):
    """A pack manifest (connectors/<name>/manifest.toml): the backend's full capability declaration.

    pack_dir, the manifest's directory, resolves the pack.harness registry and its sources. external_pin = False is a
    connector inside a pack.toml pack, whose framework range replaces pack.mdstack_version (docs/packs.md). The
    optional [actions] table is the connector's actions/ binding, checked by the conformance kit (actions/contract.py)."""
    top = check_table(err, "", manifest, {"pack": (dict, REQUIRED), "capabilities": (dict, REQUIRED),
                                          "land": (dict, None), "strategy": (dict, None), "actions": (dict, None)})
    if "pack" in top:
        pack = check_table(err, "pack", top["pack"], {"name": (str, REQUIRED), "commands": (str, REQUIRED),
                                                     "mdstack_version": (str, None), "version": (str, None),
                                                     "harness": (str, None)})
        if "harness" in pack and pack_dir is None:
            err("pack.harness", "cannot check the registry without the manifest's directory")
        elif "harness" in pack:
            validate_harness_registry(err, pack["harness"], pack_dir)
        if "version" in pack and not SEMVER.match(pack["version"]):
            err("pack.version", "expected a SemVer version (MAJOR.MINOR.PATCH, no leading v)")
        if "name" in pack and not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", pack["name"]):
            err("pack.name", "expected a backend name ([a-z0-9], separated by hyphens)")
        if external_pin and pack.get("name") not in BACKENDS and not pack.get("mdstack_version"):
            err("pack.mdstack_version", "required for an external backend")
    if "capabilities" in top:
        # A knowledge-only connector (docs/interfaces.md#knowledge) declares no core concern.
        knowledge_only = bool(top["capabilities"]) and set(top["capabilities"]) <= set(KNOWLEDGE_OPERATIONS)
        fields = {c: (dict, None if c in OPTIONAL_CONCERNS or knowledge_only else REQUIRED) for c in CONCERNS}
        concerns = check_table(err, "capabilities", top["capabilities"],
                               dict(fields, **{c: (dict, None) for c in KNOWLEDGE_OPERATIONS}))
        for concern, table in concerns.items():
            check_capabilities(err, "capabilities." + concern, table, concern, True)
    if "land" in top:
        land = check_table(err, "land", top["land"], LAND_FIELDS)
        check_choice(err, "land.mode", land.get("mode"), ["sync", "async"])
        change = top.get("capabilities", {}).get("change", {})
        check_land(err, land, change if isinstance(change, dict) else {})
    if "strategy" in top:
        strategy = check_table(err, "strategy", top["strategy"], STRATEGY_FIELDS)
        check_choice(err, "strategy.update_from_base", strategy.get("update_from_base"), ["merge", "rebase"])
        check_strategy(err, strategy)
    scan_tokens(err, "", manifest)



# Rigor order and presets from docs/flavors.md; resource knobs do not count as lowering.
FLAVOR_ORDER = {
    "review": ["full", "thin", "light", "off"], "validation": ["always", "behaviour", "off"],
    "diversity": ["required", "waivable"], "evidence": ["typed", "inline"],
    "merge": ["per-change", "docs", "auto"], "precheck": ["on", "off"],
    "lighter_lane": ["off", "docs", "docs+tests"], "validation_scope": ["repo", "bounded"], "builder": ["crew", "solo"],
}
FLAVOR_PRESETS = {
    "thorough": dict(zip(FLAVOR_ORDER, ["full", "always", "waivable", "typed", "docs", "on", "docs", "repo", "crew"]), caps=[3, 3]),
    "standard": dict(zip(FLAVOR_ORDER, ["thin", "behaviour", "waivable", "typed", "docs", "on", "docs", "bounded", "crew"]), caps=[3, 3]),
    "fast": dict(zip(FLAVOR_ORDER, ["thin", "off", "waivable", "inline", "auto", "off", "docs+tests", "bounded", "crew"]), caps=[2, 2]),
    "solo": dict(zip(FLAVOR_ORDER, ["thin", "behaviour", "waivable", "typed", "docs", "on", "docs", "bounded", "solo"]), caps=[3, 3]),
    # Item-only (crew:express); never a project, class or custom base. review = off is valid only here (docs/express-lane.md).
    "express": dict(zip(FLAVOR_ORDER, ["off", "off", "waivable", "typed", "auto", "on", "docs", "bounded", "crew"]), caps=[3, 3],
                    selfgate_engine="different"),
}
UNSET_FLAVOR = "standard"  # flagged by resolve (#632)
SELFGATE_ENGINES = ["different", "same"]  # strictest first; only express reads it
# These are forbidden controls, not optional floor switches.
FLAVOR_FLOOR = {
    "ci": (1, "CI never waived"), "ci_waiver": (1, "CI never waived"),
    "land": (3, "only the synthesizer lands"), "landing_role": (3, "only the synthesizer lands"),
    "audit": (4, "audit trail on the tool of record"), "record": (4, "audit trail on the tool of record"),
    "hold": (5, "the owner can always hold"), "hold_label_blocks": (5, "the owner can always hold"),
    "gate_changes": (6, "gate-contract changes need the owner"), "flavor_changes": (6, "flavor changes need the owner"),
    "sensitive_merge": (7, "crew:sensitive needs per-change merge-ok"),
}


def validate_flavor(profile, err):
    flavor = check_table(err, "flavor", profile["flavor"],
                         {"name": (str, None), "goal": (str, "quality"), "custom": (dict, None), "classes": (list, None),
                          "selfgate_engine": (str, None)})
    check_choice(err, "flavor.goal", flavor.get("goal"), ["quality", "speed", "cost"])
    check_choice(err, "flavor.selfgate_engine", flavor.get("selfgate_engine"), SELFGATE_ENGINES)

    def item_only(path, value):
        if value == "express":
            err(path, "express is an item flavor only (record plus crew:express); never a project, class or base")
    resolved = copy.deepcopy(FLAVOR_PRESETS)
    fields = dict({k: (str, None) for k in FLAVOR_ORDER}, base=(str, REQUIRED), caps=(list, None),
                  parallelism=(dict, None), engines=(dict, None))
    for name, table in flavor.get("custom", {}).items():
        path = "flavor.custom." + name
        if name in FLAVOR_PRESETS:
            err(path, "custom name shadows a preset")
        knobs = check_table(err, path, table, fields)
        check_choice(err, path + ".base", knobs.get("base"), list(FLAVOR_PRESETS))
        item_only(path + ".base", knobs.get("base"))
        for key, choices in FLAVOR_ORDER.items():
            check_choice(err, path + "." + key, knobs.get(key), choices)
        caps = knobs.get("caps", [3, 3])
        if len(caps) != 2 or any(type(v) is not int or not 1 <= v <= 3 for v in caps):
            err(path + ".caps", "expected two integers, each 1–3")
        if len(caps) == 2 and type(caps[1]) is int and caps[1] < 1:
            err(path + ".caps[1]", "floor F1: CI never waived; CI-fix cap must be at least 1")
        resources = check_table(err, path + ".parallelism", knobs.get("parallelism", {}),
                                {"builders": (int, None), "reviewers": (int, None)})
        runtime = profile.get("runtime", {})
        runtime = runtime if isinstance(runtime, dict) else {}
        options = runtime.get("options", {})
        options = options if isinstance(options, dict) else {}
        for key, value in resources.items():
            pool = RUNTIME_OPTIONS.get(runtime.get("name"), {})
            cap = options.get(key, pool[key][1]) if key in pool else 5
            if type(cap) is int and not 1 <= value <= cap:
                err(path + ".parallelism." + key, "must be 1–%d (runtime cap)" % cap)
        engines = check_table(err, path + ".engines", knobs.get("engines", {}), {t: (dict, None) for t in TIER_EFFORT})
        for tier, table in engines.items():
            route = check_table(err, path + ".engines." + tier, table, {"order": ("list[str]", None), "effort": (str, None)})
            check_choice(err, path + ".engines." + tier + ".effort", route.get("effort"), EFFORTS)
            if tier == "deep" and route.get("effort", "high") != "high":
                err(path + ".engines.deep.effort", "security and release work stays deep/high")
            for i, entry in enumerate(route.get("order", [])):
                if entry.partition("/")[0] not in ENGINES or not entry.partition("/")[2]:
                    err(path + ".engines.%s.order[%d]" % (tier, i), "expected an allowed <engine>/<model>; never Cursor")
        if knobs.get("base") in FLAVOR_PRESETS and name not in FLAVOR_PRESETS:
            resolved[name] = dict(FLAVOR_PRESETS[knobs["base"]], **{k: v for k, v in knobs.items() if k != "base"})
    check_choice(err, "flavor.name", flavor.get("name"), list(resolved))
    item_only("flavor.name", flavor.get("name"))
    project = resolved.get(flavor.get("name", UNSET_FLAVOR), FLAVOR_PRESETS[UNSET_FLAVOR])
    for i, table in enumerate(flavor.get("classes", [])):
        path = "flavor.classes[%d]" % i
        rule = check_table(err, path, table, {"paths": ("list[str]", REQUIRED), "flavor": (str, REQUIRED), "reason": (str, None)})
        check_choice(err, path + ".flavor", rule.get("flavor"), list(resolved))
        item_only(path + ".flavor", rule.get("flavor"))
        for pattern in rule.get("paths", []):
            if not pattern.strip() or pattern.startswith("/") or ".." in pattern.split("/"):
                err(path + ".paths", "expected nonempty repo-relative globs without ..")
        chosen = resolved.get(rule.get("flavor"))
        if chosen:
            lower = any(FLAVOR_ORDER[k].index(chosen[k]) > FLAVOR_ORDER[k].index(project[k])
                        for k in FLAVOR_ORDER if k != "builder" and chosen[k] in FLAVOR_ORDER[k] and project[k] in FLAVOR_ORDER[k])
            lower = lower or any(a < b for a, b in zip(chosen["caps"], project["caps"]) if type(a) is int and type(b) is int)
            if lower and not rule.get("reason", "").strip():
                err(path + ".reason", "required when class lowers a rigor knob")

    def floor_scan(value, path):
        if isinstance(value, dict):
            for key, child in value.items():
                sub = path + "." + key
                if key in FLAVOR_FLOOR and (path == "flavor" or path.startswith("flavor.custom.") or path.startswith("flavor.classes[")):
                    number, item = FLAVOR_FLOOR[key]
                    err(sub, "floor F%d: %s" % (number, item))
                if key == "review" and child == "off":
                    err(sub, "floor F4: audit trail requires a review/verdict record")
                for reason in token_reasons(key):
                    err(sub, "floor F2: no secrets (%s)" % reason)
                floor_scan(child, sub)
        elif isinstance(value, list):
            for i, child in enumerate(value):
                floor_scan(child, "%s[%d]" % (path, i))
        elif isinstance(value, str):
            for reason in token_reasons(value):
                err(path, "floor F2: no secrets (%s)" % reason)
    floor_scan(profile["flavor"], "flavor")


def validate_install(table, err):
    """[install] release source: each source's required keys, and a refusal for each key it does not use (#943)."""
    inst = check_table(err, "install", table, {"source": (str, "github"), "location": (str, None),
                                               "sha256sums_digest": (str, None), "git_commit": (str, None)})
    check_choice(err, "install.source", inst.get("source"), INSTALL_SOURCES)
    source = inst.get("source", "github")
    if not isinstance(table, dict) or "source" in table and "source" not in inst or source not in INSTALL_SOURCES:
        return  # check_table already reported the bad table or source
    location = inst.get("location")
    if source == "github":
        if "location" in inst:
            err("install.location", "not used by source github")
    elif location is None or not location.strip():
        err("install.location", "required for source %s" % source)
    elif source == "url":
        url = urllib.parse.urlsplit(location)
        if not (url.scheme == "https" and url.hostname or
                url.scheme == "http" and url.hostname in ("localhost", "127.0.0.1", "::1")):
            err("install.location", "expected an https URL (http only to a loopback host), got %r" % location)
    if "sha256sums_digest" in inst:
        if source not in ("url", "mirror"):
            err("install.sha256sums_digest", "not used by source %s (url and mirror only)" % source)
        elif not re.fullmatch(r"[0-9a-f]{64}", inst["sha256sums_digest"]):
            err("install.sha256sums_digest", "expected 64 lowercase hex characters")
    if source == "git":
        if "git_commit" not in inst:
            err("install.git_commit", "required for source git (the full commit the tag must resolve to)")
        elif not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", inst["git_commit"]):
            err("install.git_commit", "expected a full commit: 40 or 64 lowercase hex characters")
    elif "git_commit" in inst:
        err("install.git_commit", "not used by source %s (git only)" % source)


def validate_project(profile, err):
    """The closed project keys under [repo] (team §9.1, §9.8): labels, milestones and doc_home."""
    repo, backends = profile["repo"] if isinstance(profile["repo"], dict) else {}, profile.get("backends")
    tracker = backends.get("tracker") if isinstance(backends, dict) and isinstance(backends.get("tracker"), dict) else {}
    labels = repo.get("labels")
    if isinstance(labels, dict):
        effective = {tag: labels[tag].strip() if isinstance(labels.get(tag), str) else tag for tag in STATE_TAGS}
        for tag, label in sorted(labels.items()):
            if tag not in STATE_TAGS:
                err("repo.labels." + tag, "unknown state tag (expected one of: %s)" % ", ".join(STATE_TAGS))
            elif not isinstance(label, str) or not label.strip():
                err("repo.labels." + tag, "expected a nonempty tracker label")
            elif other := next((t for t in STATE_TAGS if t != tag and effective[t] == effective[tag]), None):
                err("repo.labels." + tag, "label %r is also %s's label; each state tag needs its own" % (label, other))
    milestones = repo.get("milestones")
    if isinstance(milestones, list):
        github = tracker.get("name") == "github"  # GitHub milestone numbers; another binding may use a safe string id
        if not milestones:
            err("repo.milestones", "expected a nonempty list (omit it for the tracker's own milestone order)")
        for i, m in enumerate(milestones):
            if not (type(m) is int and m >= 1 or not github and isinstance(m, str) and m and not ID_UNSAFE & set(m)):
                err("repo.milestones[%d]" % i, "expected a milestone %s" % ("number >= 1" if github else "id"))
            elif m in milestones[:i]:
                err("repo.milestones[%d]" % i, "duplicate milestone %s" % json.dumps(m))
        caps = tracker.get("capabilities") if isinstance(tracker.get("capabilities"), dict) else {}
        if caps.get("milestone", "unsupported") == "unsupported":
            err("repo.milestones", "needs the tracker backend's milestone capability")
    home = repo.get("doc_home")
    if isinstance(home, str) and (not home.strip() or os.path.isabs(home) or home.startswith("~")
                                  or ".." in home.replace("\\", "/").split("/")):
        err("repo.doc_home", "expected a nonempty project-relative directory without .. (no escape from the checkout)")


def validate(profile, err, backends=BACKENDS, pack_dir=None, item=None, status_ids=None):
    """item: the tracker backend's declared [ids] item pattern as (pattern, map name), None when undeclared;
    status_ids: the status backend's [ids] status-destination as (pattern, map name), None when undeclared."""
    if "pack" in profile:
        return validate_manifest(profile, err, pack_dir)
    req = (dict, REQUIRED)
    top = check_table(err, "", profile, dict({k: req for k in ["repo", "runtime", "backends", "identities", "engines", "paths"]},
                                             hosts=(dict, None), placement=(dict, None), sensitive=(dict, None), spec=(dict, None), tools=(dict, None),
                                             size_budget=(dict, None), builder=(dict, None), flavor=(dict, None),
                                             release=(dict, None), triage=(dict, None), install=(dict, None),
                                             docs=(dict, None), reflection=(dict, None), ci=(dict, None),
                                             report=(dict, None), status=(dict, None)))
    if "status" in top:  # shared status (docs/specs/shared-status.md §2, #1313)
        validate_status(top["status"], err, status_ids)
    if "flavor" in top:
        validate_flavor(profile, err)
    if "report" in top:
        report = check_table(err, "report", top["report"], {"emoji": (bool, True), "status": (dict, None)})
        if "status" in report:
            check_table(err, "report.status", report["status"], {k: (str, None) for k in REPORT_STATUS})
    if "size_budget" in top:
        budgets = check_table(err, "size_budget", top["size_budget"],
                              {r: (int, 16384) for r in ROLE_REGISTRY})
        for role, budget in budgets.items():
            if budget < 1:
                err("size_budget." + role, "must be >= 1")
    if "builder" in top:
        builder = check_table(err, "builder", top["builder"], {"precheck": (dict, None)})
        if "precheck" in builder:
            precheck = check_table(err, "builder.precheck", builder["precheck"],
                                  {"enabled": (bool, False), "lint": (str, None), "test": (str, None),
                                   "docs": (str, None), "max_fix_attempts": (int, 2), "owners": (str, None),
                                   "no_owner_ok": ("list[str]", None)})
            if precheck.get("max_fix_attempts", 2) < 1:
                err("builder.precheck.max_fix_attempts", "must be >= 1")
            if "owners" in precheck and not precheck["owners"].strip():
                err("builder.precheck.owners", "expected a nonempty shell command")
            for i, pattern in enumerate(precheck.get("no_owner_ok", [])):
                if not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
                    err("builder.precheck.no_owner_ok[%d]" % i, "expected a nonempty repo-relative glob without ..")
    if "tools" in top:
        for name, table in top["tools"].items():
            path = "tools." + name
            tool = check_table(err, path, table, {"running": ("list[str]", REQUIRED),
                                                "installed": ("list[str]", REQUIRED), "pin": (str, None)})
            for key in ("running", "installed"):
                if key in tool and any(not arg.strip() for arg in tool[key]):
                    err(path + "." + key, "command arguments must not be empty")
            if "pin" in tool and not re.fullmatch(r"v?\d+\.\d+\.\d+", tool["pin"]):
                err(path + ".pin", "expected X.Y.Z or vX.Y.Z minimum version")
    if "release" in top:
        rel = check_table(err, "release", top["release"], {"changelog": (str, "CHANGELOG.md"),
                                                           "fragments": (str, "changes/unreleased"),
                                                           "versioning": (str, "semver"), "release_id": (str, "tag")})
        check_choice(err, "release.versioning", rel.get("versioning"), ["semver"])
        check_choice(err, "release.release_id", rel.get("release_id"), ["tag", "commit"])
    if "triage" in top:  # always-on triage sweep (docs/triage.md, #748)
        tri = check_table(err, "triage", top["triage"], {"enabled": (bool, False), "interval_hours": (int, 6),
                                                        "repos": ("list[str]", None), "rules": (str, None),
                                                        "mode": (str, "shadow"), "trackers": ("list[str]", None)})
        check_choice(err, "triage.mode", tri.get("mode"), TRIAGE_MODES)
        if tri.get("interval_hours", 6) < 1:
            err("triage.interval_hours", "must be >= 1, got %d" % tri["interval_hours"])
        for i, repo in enumerate(tri.get("repos", [])):
            if not TRACKER_REPO.fullmatch(repo):
                err("triage.repos[%d]" % i, "expected owner/name, got %r" % repo)
        for i, tracker in enumerate(tri.get("trackers", [])):  # a non-GitHub tracker's list-items <tracker> (#1404)
            if not re.fullmatch(r"\S+", tracker):
                err("triage.trackers[%d]" % i, "expected a nonempty tracker id without spaces, got %r" % tracker)
        if "trackers" in tri and isinstance(top.get("backends"), dict) and \
                (top["backends"].get("tracker") or {}).get("name") == "github":
            err("triage.trackers", "needs a non-GitHub tracker backend; name GitHub repositories in triage.repos")
        if "rules" in tri and not tri["rules"].strip():
            err("triage.rules", "expected a nonempty file path")
    if "ci" in top:  # the expected-check baseline a green CI read needs at head (#1536)
        ci = check_table(err, "ci", top["ci"], {"required_checks": ("list[str]", None)})
        names = ci.get("required_checks", [])
        for i, name in enumerate(names):
            if not name.strip() or name in names[:i]:
                err("ci.required_checks[%d]" % i, "expected a nonempty, unique check name, got %r" % name)
    if "reflection" in top:  # scheduled protocol reflection (docs/self-improve.md#reflection, #1521)
        check_table(err, "reflection", top["reflection"], {"enabled": (bool, False)})
    if "docs" in top:  # project docs pass opt-in (docs/project-docs.md Profile opt-in, #1024)
        fields = {k: (type(v), v) for k, v in DOCS_DEFAULTS.items()}
        doc = check_table(err, "docs", top["docs"], dict(fields, repos=("list[str]", None), homes=(dict, None),
                                                        specs_external=(str, None)))
        for key in ("interval_days", "stale_days", "size_budget"):
            if doc.get(key, 1) < 1:
                err("docs." + key, "must be >= 1, got %d" % doc[key])
        for i, repo in enumerate(doc.get("repos", [])):
            if not TRACKER_REPO.fullmatch(repo):
                err("docs.repos[%d]" % i, "expected owner/name, got %r" % repo)
        homes = check_table(err, "docs.homes", doc["homes"], {k: (str, None) for k in DOCS_ESSENTIALS}) \
            if "homes" in doc else {}
        for key, home in homes.items():
            path, _, anchor = home.partition("#")
            if not path or path.startswith("/") or ".." in path.split("/") or "#" in home and not anchor:
                err("docs.homes." + key, "expected a repo-relative path or path#anchor, got %r" % home)
            elif key == "specs" and "#" in home:
                err("docs.homes.specs", "expected a repo-relative directory, got %r" % home)
        if "specs_external" in doc:  # a reference to a tracker item or document, never a path or command (#1725)
            if not SPEC_EXTERNAL.fullmatch(doc["specs_external"]):
                err("docs.specs_external", "expected an absolute URL, got %r" % doc["specs_external"])
            elif "specs" in homes:
                err("docs.specs_external", "conflicts with docs.homes.specs; name one specs home")
    if "install" in top:
        validate_install(top["install"], err)
    if "sensitive" in top:
        rules = check_table(err, "sensitive", top["sensitive"], {"paths": (list, []), "content": (list, None)})
        for i, pattern in enumerate(rules.get("paths", [])):
            if not isinstance(pattern, str) or not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
                err("sensitive.paths[%d]" % i, "expected a nonempty repo-relative glob without ..")
        names = set()
        for i, table in enumerate(rules.get("content", [])):  # content rules (#879): docs/profile.md
            path = "sensitive.content[%d]" % i
            rule = check_table(err, path, table, {"name": (str, REQUIRED), "pattern": (str, REQUIRED),
                                                  "paths": ("list[str]", None), "reason": (str, REQUIRED)})
            for key in ("name", "reason"):
                if key in rule and not rule[key].strip():
                    err(path + "." + key, "expected a nonempty string")
            if rule.get("name", "").strip() in names:
                err(path + ".name", "duplicate content rule name %r" % rule["name"])
            elif rule.get("name", "").strip():
                names.add(rule["name"].strip())
            if "pattern" in rule:
                try:
                    re.compile(rule["pattern"])
                except re.error as e:
                    err(path + ".pattern", "invalid regex (%s)" % e)
            for j, pattern in enumerate(rule.get("paths", [])):
                if not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
                    err("%s.paths[%d]" % (path, j), "expected a nonempty repo-relative glob without ..")
    if "spec" in top:
        rules = check_table(err, "spec", top["spec"], {"paths": (list, None)})
        for i, pattern in enumerate(rules.get("paths", [])):
            if not isinstance(pattern, str) or not pattern or pattern.startswith("/") or ".." in pattern.split("/"):
                err("spec.paths[%d]" % i, "expected a nonempty repo-relative glob without ..")
    if "repo" in top:
        check_table(err, "repo", top["repo"], {"owner": (str, REQUIRED), "name": (str, REQUIRED), "default_branch": (str, "main"),
                                               "control_item": ((int, str), None), "labels": (dict, None),
                                               "milestones": (list, None), "doc_home": (str, None)})
        validate_project(profile, err)
    if "runtime" in top:
        rt = check_table(err, "runtime", top["runtime"], {"name": (str, REQUIRED), "options": (dict, {}), "timezone": (str, None), "instance": (str, None)})
        check_choice(err, "runtime.name", rt.get("name"), list(RUNTIME_OPTIONS))
        if rt.get("name") in RUNTIME_OPTIONS and "options" in rt:
            opts = check_table(err, "runtime.options", rt["options"], RUNTIME_OPTIONS[rt["name"]])
            check_choice(err, "runtime.options.permission_mode", opts.get("permission_mode"), PERMISSION_MODES)
            check_choice(err, "runtime.options.confinement", opts.get("confinement"), ["enforce", "off"])
            check_choice(err, "runtime.options.session_backend", opts.get("session_backend"),
                         SESSION_BACKENDS.get(rt["name"], []))
            check_choice(err, "runtime.options.tmux_server", opts.get("tmux_server"), ["default", "dedicated"])
            check_choice(err, "runtime.options.isolation", opts.get("isolation"), ["worktree", "assigned-checkout"])
            check_choice(err, "runtime.options.lone_pr_land", opts.get("lone_pr_land"), ["train", "direct"])
            check_choices(err, "runtime.options.merge_grant_scope", opts.get("merge_grant_scope", []), MERGE_GRANT_SCOPES)
            if "spec" in opts.get("merge_grant_scope", []) and opts.get("merge_grant", "none") == "none":
                err("runtime.options.merge_grant_scope", "spec needs a standing merge_grant; merge_grant is none")
            if opts.get("release_delegation", "none") not in ("none", None) and "https://" not in opts["release_delegation"]:
                err("runtime.options.release_delegation", "expected the owner's recorded words with a https:// link to the record")
            check_choice(err, "runtime.options.mirror", opts.get("mirror"), ["live-copy", "none"])
            check_choice(err, "runtime.options.memory_high", opts.get("memory_high"), ["warn", "critical"])
            if opts.get("mirror") == "none" and opts.get("mirror_deferral", "none") != "none":
                err("runtime.options.mirror", '"none" conflicts with mirror_deferral %s; an install with no live copy '
                    'has nothing to defer' % json.dumps(opts["mirror_deferral"], ensure_ascii=False))
            notes = check_table(err, "runtime.options.notes", opts.get("notes", {}),
                                dict({r: (list, []) for r in ROLE_REGISTRY}, render=(dict, {})))
            render = check_table(err, "runtime.options.notes.render", notes.pop("render", {}),
                                 {r: (list, []) for r in NOTE_ROLES})
            for prefix, table in (("runtime.options.notes.", notes), ("runtime.options.notes.render.", render)):
                for role, paths in table.items():
                    for i, path in enumerate(paths):
                        if not isinstance(path, str) or not path.strip():
                            err("%s%s[%d]" % (prefix, role, i), "expected a nonempty file path")
            role_runtime = check_table(err, "runtime.options.role_runtime", opts.get("role_runtime", {}),
                                       {r: (str, None) for r in ROLE_REGISTRY})
            for role, other in role_runtime.items():
                check_choice(err, "runtime.options.role_runtime." + role, other, [n for n in RUNTIME_OPTIONS if n != rt["name"]])
                if role == "researcher" and other == "session":  # a sweep-only brief, not a full researcher (#1404)
                    err("runtime.options.role_runtime.researcher", "the session researcher brief runs only the "
                        "triage sweep; it cannot replace the %s researcher brief" % rt["name"])
            if "launch" in opts:
                launch = check_table(err, "runtime.options.launch", opts["launch"], {
                    "coordinator": (str, "tmux"), "roles": (str, "tmux"), "resume": (str, "fresh"), "reconcile": (str, "backend")})
                check_choice(err, "runtime.options.launch.coordinator", launch.get("coordinator"), ["tmux", "none"])
                check_choice(err, "runtime.options.launch.roles", launch.get("roles"), ["tmux", "hosted", "none"])
                check_choice(err, "runtime.options.launch.reconcile", launch.get("reconcile"), ["backend"])
                if launch.get("resume", "fresh") not in ("fresh", "ask") and not LAUNCH_SESSION_ID.fullmatch(launch["resume"]):
                    err("runtime.options.launch.resume", "expected fresh, ask or a session id ([A-Za-z0-9._:-])")
                if rt["name"] == "tmux" and launch.get("coordinator") == "none" and launch.get("roles", "tmux") == "tmux":
                    err("runtime.options.launch.roles", "roles = tmux needs coordinator = tmux (role windows join its session)")
            for key, minimum in (("present_builders", 1), ("present_reviewers", 1), *((k, 0) for k in ZERO_CAPS),
                                 ("max_active_milestones", 1), ("train_min", 2), ("train_window", 1),
                                 ("max_suites", 1), ("idle_builder_ttl", 0), ("slack_digest_interval", 1),
                                 ("error_high", 1), ("schedule_interval", 1), ("schedule_ramp", 1),
                                 ("stuck_after", 1), ("land_poll_interval", 1), ("land_timeout", 1), ("host_scan_interval", 1)):
                if key in opts and opts[key] < minimum:
                    err("runtime.options." + key, "must be >= %d, got %d" % (minimum, opts[key]))
            if rt["name"] == "session":  # tmux clamps an over-cap present limit at admission instead (#1053)
                for key in ("builders", "reviewers"):
                    full = opts.get(key, RUNTIME_OPTIONS["session"][key][1])
                    if opts.get("present_" + key, full) > full:
                        err("runtime.options.present_" + key, "must be <= %s (%d), got %d" % (key, full, opts["present_" + key]))
            if opts.get("land_timeout", 3600) < opts.get("land_poll_interval", 60):
                err("runtime.options.land_timeout", "must be >= land_poll_interval (%d), got %d"
                    % (opts.get("land_poll_interval", 60), opts.get("land_timeout", 3600)))
            for key in ("max_load", "load_high", "load_low"):
                if opts.get(key, 1) <= 0:
                    err("runtime.options." + key, "must be > 0, got %s" % opts[key])
            if opts.get("load_low", 4.0) >= opts.get("load_high", 6.0) > 0:
                err("runtime.options.load_low", "must be < load_high (%s), got %s"
                    % (opts.get("load_high", 6.0), opts.get("load_low", 4.0)))
    if "backends" in top:
        concerns = check_table(err, "backends", top["backends"],
                               {c: (dict, None) if c in OPTIONAL_CONCERNS else req for c in CONCERNS})
        for concern, table in concerns.items():
            be = check_table(err, "backends." + concern, table, {"name": (str, REQUIRED), "capabilities": (dict, {})})
            check_choice(err, "backends.%s.name" % concern, be.get("name"),
                         backends + (["slack"] if concern == "owner-channel" else []))
            check_capabilities(err, "backends.%s.capabilities" % concern, be.get("capabilities", {}), concern, False)
            if concern == "owner-channel" and be.get("name") == "slack":
                if profile.get("runtime", {}).get("name") != "tmux":
                    err("backends.owner-channel.name", "slack requires runtime tmux")
                env = profile.get("runtime", {}).get("options", {}).get("slack_webhook_env")
                if not isinstance(env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
                    err("runtime.options.slack_webhook_env", "required environment variable name for slack (never a URL)")
    if "identities" in top:
        roles = [r["identity_key"].removeprefix("identities.") for r in ROLE_REGISTRY.values()]
        ids = check_table(err, "identities", top["identities"], dict({"owners": ("list[str]", REQUIRED), "team": (str, "")},
                                                                    **{r: (dict, None) if r in OPTIONAL_IDENTITIES else req for r in roles}))
        if ids.get("team") and not re.fullmatch(r"[a-z0-9-]{1,63}", ids["team"]):  # window 0 is <coordinator>-<team> (#1329)
            err("identities.team", "expected a team name ([a-z0-9-], 1-63 characters) or empty, got %r" % ids["team"])
        for role in roles:
            if role in ids:
                check_table(err, "identities." + role, ids[role], {"gh_user": (str, REQUIRED), "name": (str, None),
                                                                   "title": (str, None), "emoji": (str, None)})
    if "engines" in top:
        sources = list(dict.fromkeys(r["engine_source"] for r in ROLE_REGISTRY.values() if r["engine_source"] != "tier"))
        eng = check_table(err, "engines", top["engines"], dict({s: (str, "claude-code") for s in sources},
                                                               fallback_engine=(str, None), roles=(dict, None),
                                                               **{t: req for t in TIER_EFFORT}))
        for source in sources:
            check_choice(err, "engines." + source, eng.get(source), harnesses.LAUNCHABLE)
        check_choice(err, "engines.fallback_engine", eng.get("fallback_engine"), ENGINES)
        for tier in TIER_EFFORT:
            if tier in eng:
                t = check_table(err, "engines." + tier, eng[tier], {"order": ("list[str]", REQUIRED), "effort": (str, None)})
                check_choice(err, "engines.%s.effort" % tier, t.get("effort"), EFFORTS)
                for i, entry in enumerate(t.get("order", [])):
                    if entry.partition("/")[0] not in ENGINES or not entry.partition("/")[2]:
                        err("engines.%s.order[%d]" % (tier, i), "unknown engine %r (expected <engine>/<model>, engine one of: %s)"
                            % (entry.partition("/")[0], ", ".join(ENGINES)))
        spawned = [r for r, v in ROLE_REGISTRY.items() if v["engine_source"] == "tier"]
        overrides = check_table(err, "engines.roles", eng.get("roles", {}), {r: (dict, None) for r in spawned})
        for role, table in overrides.items():  # a role's order beats its tier's (#597)
            t = check_table(err, "engines.roles." + role, table, {"order": ("list[str]", REQUIRED)})
            for i, entry in enumerate(t.get("order", [])):
                if entry.partition("/")[0] not in ENGINES or not entry.partition("/")[2]:
                    err("engines.roles.%s.order[%d]" % (role, i), "unknown engine %r (expected <engine>/<model>, engine one of: %s)"
                        % (entry.partition("/")[0], ", ".join(ENGINES)))
    if "paths" in top:
        check_table(err, "paths", top["paths"], {"state_dir": (str, REQUIRED), "worktree_root": (str, REQUIRED), "toolchain_bin": (str, None),
                                                  "live_dir": (str, None), "mdstack": (str, None), "pack": (str, None),
                                                  "checkout": (str, None), "root": (str, None)})
        pack = top["paths"].get("pack")
        if isinstance(pack, str) and not pack.strip():
            err("paths.pack", "expected a nonempty pack directory")
    if isinstance(profile.get("repo"), dict) and "control_item" in profile["repo"]:
        value = profile["repo"]["control_item"]
        if type(value) is int and value < 1:
            err("repo.control_item", "must be >= 1")
        elif type(value) is str and item is None:
            err("repo.control_item", "a string id needs the tracker backend's [ids] item pattern")
        elif type(value) is str and (not re.fullmatch(item[0], value) or ID_UNSAFE & set(value)):
            err("repo.control_item", "%s does not match item pattern %s (tracker backend %s)"
                % (json.dumps(value, ensure_ascii=False), item[0], item[1]))
        runtime = profile.get("runtime")
        instance = runtime.get("instance", "") if isinstance(runtime, dict) else ""
        if not isinstance(instance, str) or not re.fullmatch(r"[a-z0-9-]{1,63}", instance):
            err("runtime.instance", "control_item needs an instance label ([a-z0-9-], 1-63 characters)")
    validate_hosts(profile, top, err)
    scan_tokens(err, "", profile)


# --- resolve (13.11, #123): layered profile with per-key provenance. ---
import copy  # noqa: E402  (kept with the resolve block)
import json  # noqa: E402

DEFAULT_PROFILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "profiles", "default.toml")


def user_root():
    """The single root a command defaults to: $CREW_ROOT, else ~/.mdstack (#1316), so a second crew on the same
    machine is one variable away (#1324)."""
    return os.path.abspath(os.path.expanduser(os.environ.get("CREW_ROOT") or os.path.join("~", ".mdstack")))


def default_config():
    """The project file a command uses without --project: $CREW_PROJECT (a role window's own config), else
    $MDSTACK_CONFIG, else <user_root>/config.toml (#1316, #1324). An explicitly named file always wins."""
    return (os.environ.get("CREW_PROJECT") or os.environ.get("MDSTACK_CONFIG")
            or os.path.join(user_root(), "config.toml"))


def installed_config():
    """The installed team's file for a bare `mdstack attach` (#1942): default_config(), except that a missing
    <user_root>/config.toml falls back to the root's only <team>.toml team file (the 7.0.0 home layout, #1348)."""
    found = default_config()
    if os.environ.get("CREW_PROJECT") or os.environ.get("MDSTACK_CONFIG") or os.path.exists(found):
        return found
    teams = []
    for path in sorted(glob.glob(os.path.join(user_root(), "*.toml"))):
        try:
            if team_repos(path):
                teams.append(path)
        except (OSError, ValueError):
            continue
    return teams[0] if len(teams) == 1 else found


CORE_DEFAULTS = {"repo": {"default_branch": "main"},
                 "size_budget": {r: 16384 for r in ROLE_REGISTRY},
                 "builder": {"precheck": {"enabled": False, "max_fix_attempts": 2}},
                 "triage": {"enabled": False, "interval_hours": 6, "mode": "shadow"},
                 "reflection": {"enabled": False},
                 "identities": {r["identity_key"].removeprefix("identities."): dict(r["identity_defaults"])
                                for r in ROLE_REGISTRY.values()},
                 "engines": dict({"coordinator": "claude-code"}, **{t: {"effort": e} for t, e in TIER_EFFORT.items()})}
# Top-level tables whose keys protect an invariant (docs/interfaces.md); a later layer may not drop them.
INVARIANT_TABLES = ["identities", "backends", "engines"]
# Invariants (I1-I5) each operation protects, from the docs/interfaces.md tables.
PROTECTS = {
    "change": {"open": "5", "push": "3", "read-head": "3", "read-diff-paths": "3", "update-from-base": "3",
               "land": "34", "close": "5"},
    "review": {"post-verdict": "123", "post-narrative": "5", "list-verdicts": "134", "request-rereview": "23"},
    "tracker": {op: "5" for op in OPERATIONS["tracker"]},
    "state-tags": {"set-clear-read": "45"},
    "markers": {"write": "135", "read": "135", "write-item": "45", "read-item": "45"},
    "ci": {"check-status": "3", "failing-jobs": "3"},
    "events": {"subscribe-or-poll": "14"},
    "owner-channel": {"ask": "5", "notify": "5"},
}


def leaves(value, path=""):
    if isinstance(value, dict) and value:
        for k, v in value.items():
            yield from leaves(v, "%s.%s" % (path, k) if path else k)
    else:
        yield path, value


def source(prov, key):
    """Layer that set key, its nearest ancestor table or a key under it; None if no layer did."""
    up = key
    while up not in prov and "." in up:
        up = up.rsplit(".", 1)[0]
    return prov.get(up) or next((v for q, v in prov.items() if q.startswith(key + ".")), None)


def merge(dst, src, prov, layer, err, path=""):
    """Tables merge by key; scalars and arrays replace. Dropping an invariant-protecting key is an error."""
    for k, v in src.items():
        p = "%s.%s" % (path, k) if path else k
        if isinstance(dst.get(k), dict) and isinstance(v, dict):
            merge(dst[k], v, prov, layer, err, p)
            continue
        if isinstance(dst.get(k), dict):
            for q, _ in leaves(dst[k], p):
                if q.split(".")[0] in INVARIANT_TABLES:
                    err(layer, q, "cannot remove invariant-protecting key (set by %s)" % source(prov, q))
        dst[k] = copy.deepcopy(v)
        for q, _ in leaves(v, p):
            prov[q] = layer


def cross_check(profile, err):
    """Checks that need the whole resolved profile (docs/interfaces.md, #111)."""
    caps = {(c, op): v for c in OPERATIONS for op, v in profile["backends"].get(c, {}).get("capabilities", {}).items()}
    kept, lost = set(), {}
    for concern, ops in PROTECTS.items():
        for op, invariants in ops.items():
            for i in invariants:
                if caps.get((concern, op), "unsupported") == "unsupported":
                    word = "unsupported" if (concern, op) in caps else "undeclared (counts as unsupported)"
                    lost.setdefault(i, ("backends.%s.capabilities.%s" % (concern, op), word))
                else:
                    kept.add(i)
    for i in sorted(lost.keys() - kept):
        err(lost[i][0], "%s leaves I%s with no other operation keeping it; profile unsupported "
            "(docs/interfaces.md)" % (lost[i][1], i))
    if "release" in profile:
        for op in RELEASE_GATE_OPS:
            if caps.get(("release", op), "unsupported") == "unsupported":
                err("backends.release.capabilities." + op, "%s with a [release] table leaves the release gate "
                    "unkept; profile unsupported for release (docs/interfaces.md)"
                    % ("unsupported" if ("release", op) in caps else "undeclared (counts as unsupported)"))
    if profile.get("sensitive", {}).get("content") and \
            caps.get(("change", "read-diff"), "unsupported") == "unsupported":
        err("backends.change.capabilities.read-diff", "%s with [[sensitive.content]] rules leaves roles without a "
            "checkout no diff to classify (docs/interfaces.md#change)"
            % ("unsupported" if ("change", "read-diff") in caps else "undeclared (counts as unsupported)"))
    ids = profile["identities"]
    if ids["reviewer"]["gh_user"] == ids["builder"]["gh_user"] and \
            not caps.get(("review", "post-verdict"), "").startswith("emulated"):
        err("backends.review.capabilities.post-verdict", "reviewer gh_user equals builder gh_user; "
            "a single-identity profile must declare emulated (<how>) (#111)")
    for key, value in profile["runtime"].get("options", {}).items():
        if type(value) is int and value < (0 if key in ZERO_CAPS else 1):  # researchers = 0: no researcher (#926)
            err("runtime.options." + key, "must be >= 1, got %d" % value)
    if profile["runtime"].get("options", {}).get("researchers") == 0 and profile.get("triage", {}).get("enabled"):
        err("runtime.options.researchers", "0 runs no researcher, but triage.enabled = true needs one for its sweep; "
            "set researchers >= 1 (the session default is 0, #1724)")


# --- pack manifests (13.15, #127): each backend's capability declaration, under every layer. ---
CONNECTORS_DIR = os.path.join(os.path.dirname(os.path.dirname(DEFAULT_PROFILE)), "connectors")


def load_pack(path, err):
    try:
        with open(path, "rb") as f:
            manifest = tomllib.load(f)
    except OSError as e:
        err("(file)", "cannot read (%s)" % e.strerror)
        return None
    except tomllib.TOMLDecodeError as e:
        err("(toml)", "invalid TOML (%s)" % e)
        return None
    validate_manifest(manifest, err, os.path.dirname(os.path.abspath(path)))
    return manifest


def fold_manifests(merged, prov, files, err, external=None, land=None, strategy=None, connectors=None):
    """Fill each backend's undeclared operations from connectors/<name>/manifest.toml; a layer's value wins.

    land and strategy, when given, receive the change backend's [land] and [strategy] tables with the layer
    that declared them. connectors maps a pack.toml pack's connector names to their manifests."""
    backends = merged.get("backends")
    for concern, be in (backends.items() if isinstance(backends, dict) else []):
        if not isinstance(be, dict) or concern not in CONCERNS:
            continue
        name = be.get("name")
        if concern == "owner-channel" and name == "slack":
            caps = be.setdefault("capabilities", {})
            if isinstance(caps, dict):
                for op, value in {"ask": "emulated (recorded GitHub ask)", "notify": "supported"}.items():
                    if op not in caps:
                        caps[op], prov["backends.owner-channel.capabilities." + op] = value, "core"
            continue
        layer = "pack:" + str(name)
        if external and name == external["pack"]["name"]:
            layer = "external-pack"
        elif name in BACKENDS:
            files[layer] = os.path.join(CONNECTORS_DIR, name, "manifest.toml")
        elif connectors and name in connectors:
            files[layer] = connectors[name]
        else:
            continue
        try:
            with open(files[layer], "rb") as f:
                data = tomllib.load(f)
        except OSError:
            continue  # no manifest: its operations stay undeclared
        except tomllib.TOMLDecodeError as e:
            return err(layer, "(toml)", "invalid TOML (%s)" % e)
        declared = data.get("capabilities")
        if concern == "change" and land is not None and isinstance(data.get("land"), dict):
            land.update({key: (value, layer) for key, value in data["land"].items()})
        if concern == "change" and strategy is not None and isinstance(data.get("strategy"), dict):
            strategy.update({key: (value, layer) for key, value in data["strategy"].items()})
        declared = declared.get(concern) if isinstance(declared, dict) else None
        caps = be.setdefault("capabilities", {}) if isinstance(declared, dict) and declared else None
        if not isinstance(caps, dict):
            continue
        for op, value in declared.items():
            if op not in caps:
                caps[op], prov["backends.%s.capabilities.%s" % (concern, op)] = value, layer


# --- team files (#634): <config-home>/teams/<team>.toml, a [team] table plus one small [repos.<name>] per repo. ---
# Profile tables a team holds; a repo section may set only REPO_KEYS (key -> dotted profile key).
TEAM_TABLES = ["runtime", "backends", "identities", "engines", "paths", "hosts", "placement", "sensitive", "spec",
               "tools", "size_budget", "builder", "flavor", "report"]
REPO_KEYS = dict({"default_branch": "repo.default_branch", "precheck": "builder.precheck", "sensitive": "sensitive.paths",
                  "spec": "spec.paths", "checkout": "paths.checkout",  # checkout: the repo's clone (#1287)
                  # closed project keys (team §9.8); flavor is a table with only name, checked in team_layers
                  "control_item": "repo.control_item", "labels": "repo.labels", "milestones": "repo.milestones",
                  "doc_home": "repo.doc_home", "flavor": "flavor"},
                 **{k: "runtime.options." + k for k in ("merge_grant", "merge_grant_scope", "mirror_deferral", "mirror",
                                                        "lone_pr_land", "train_min", "train_window",
                                                        "train_local_checks")})


def split_ref(project):
    """A project reference is FILE or a team file's repo section, FILE#<repo>."""
    base = os.path.basename(project)
    if "#" not in base:
        return project, None
    name, _, repo = base.partition("#")
    return project[:len(project) - len(base)] + name, repo or None


def is_team(data):
    return isinstance(data, dict) and ("team" in data or "repos" in data)


def team_layers(data, file, repo, err):
    """(team profile, repo profile, repo name, team name) in the legacy profile shape; err(layer, key, reason) on a problem."""
    for key in sorted(data.keys() - {"team", "repos", "status"}):  # [status] is team-level, beside [team] (#1313)
        err("team", key, "unknown key in a team file (team settings go in [team], repo settings in [repos.<name>])")
    team, repos = data.get("team", {}), data.get("repos", {})
    if not isinstance(team, dict) or not isinstance(repos, dict) or not repos:
        return err("team", "repos", "a team file needs a [team] table and at least one [repos.<name>] table")
    name = team.get("name")  # explicit identity, else the file name (#1348)
    if name is not None and not (isinstance(name, str) and re.fullmatch(r"[a-z0-9-]{1,63}", name)):
        err("team", "team.name", "expected [a-z0-9-] (1-63 characters)")
    elif name is None:
        name = os.path.splitext(os.path.basename(file))[0]
        if not re.fullmatch(r"[a-z0-9-]{1,63}", name):
            err("team", "(file)", "team file name must be <team>.toml with [a-z0-9-] (1-63 characters), "
                "or set team.name")
    seen = {}
    for section_name, section in repos.items():  # one canonical repo per team, whichever section is selected
        value = section.get("repo") if isinstance(section, dict) else None
        key = value.strip().lower() if isinstance(value, str) else None  # normalized once, then compared
        if key in seen:
            err("team", "repos.%s.repo" % section_name, "%s is repos.%s's repo too; a team holds each repo once"
                % (value, seen[key]))
        elif key is not None:
            seen[key] = section_name
    if repo is None and len(repos) > 1:
        return err("team", "repos", "lists %d repos; select one as %s#<repo>" % (len(repos), file))
    repo = repo or next(iter(repos))
    if repo not in repos or not isinstance(repos[repo], dict):
        return err("team", "repos", "names no repo %r (repos: %s)" % (repo, ", ".join(repos)))
    out = {"status": copy.deepcopy(data["status"])} if "status" in data else {}
    for key, value in team.items():
        if key in ("name", "pack", "personas", "accounts"):
            continue
        if key in TEAM_TABLES:
            out[key] = copy.deepcopy(value)
            options = value.get("options") if key == "runtime" and isinstance(value, dict) else None
            for grant in sorted(set(options or {}) & {"merge_grant", "merge_grant_scope"} if isinstance(options, dict) else []):
                err("team", "team.runtime.options." + grant, "a landing grant is per repo; set it in [repos.<name>] "
                    "so its scope never spans the team")
        else:
            err("team", "team." + key, "unknown team key" + (" (per-repo; set it in [repos.<name>])"
                                                             if key in REPO_KEYS or key == "repo" else ""))
    roles = [r["identity_key"].removeprefix("identities.") for r in ROLE_REGISTRY.values()]
    if "pack" in team and not isinstance(team["pack"], str):
        err("team", "team.pack", "expected string, got %s" % type_name(team["pack"]))
    if isinstance(team.get("pack"), str):  # the pack's backend fills every concern the team leaves unset
        backends = out.setdefault("backends", {})
        for concern in OPERATIONS:
            backends.setdefault(concern, {}).setdefault("name", team["pack"])
    for key, field in (("personas", "name"), ("accounts", "gh_user")):
        table = team.get(key, {})
        if not isinstance(table, dict):
            err("team", "team." + key, "expected table, got %s" % type_name(table))
            continue
        for role, value in sorted(table.items(), key=lambda kv: kv[0] == "all"):  # a named role beats all
            if role != "all" and role not in roles:
                err("team", "team.%s.%s" % (key, role), "unknown role (expected all or one of: %s)" % ", ".join(roles))
            for r in (roles if role == "all" else [role] if role in roles else []):
                out.setdefault("identities", {}).setdefault(r, {}).setdefault(field, value)
    section, mine = repos[repo], {}
    for key, value in section.items():
        if key == "repo":
            owner, _, rname = value.partition("/") if isinstance(value, str) else ("", "", "")
            if not owner or not rname or "/" in rname:
                err("team", "repos.%s.repo" % repo, "expected <owner>/<name>")
            mine.setdefault("repo", {}).update(owner=owner, name=rname)
        elif key == "flavor":
            mine["flavor"] = check_table(lambda k, reason: err("team", "repos.%s.%s" % (repo, k), reason), "flavor",
                                         value, {"name": (str, REQUIRED)})
        elif key in REPO_KEYS:
            table, _, leaf = REPO_KEYS[key].rpartition(".")
            node = mine
            for part in table.split("."):
                node = node.setdefault(part, {})
            node[leaf] = copy.deepcopy(value)
        else:
            err("team", "repos.%s.%s" % (repo, key), "not allowed in a repo section (team-only; allowed: repo, %s)"
                % ", ".join(REPO_KEYS))
    if "repo" not in section:
        err("team", "repos.%s.repo" % repo, "missing required key")
    return out, mine, repo, name


def project_relaxation(layers, merged, err):
    """A repo section's flavor may tighten, never relax, its floor (team §9.1): knob-wise the strictest flavor any lower
    layer names (core, pack, org, team), so a nearer weaker layer never hides a stricter one. A looser rigor knob or a
    lower cap under the existing comparison is refused with the key and the floor's flavor and layer."""
    mine = dict(layers).get("repo", {}).get("flavor", {}).get("name")
    if mine is None:
        return
    named = dict(FLAVOR_PRESETS, **{n: dict(FLAVOR_PRESETS[k["base"]], **{a: b for a, b in k.items() if a != "base"})
                                    for n, k in merged.get("flavor", {}).get("custom", {}).items()})
    floors = [(d["flavor"]["name"], n) for n, d in layers if n != "repo" and isinstance(d.get("flavor"), dict)
              and d["flavor"].get("name") in named] or [(UNSET_FLAVOR, "core")]
    if mine not in named:
        return
    a = named[mine]
    for key in [k for k in FLAVOR_ORDER if k != "builder"]:
        below, layer = min(floors, key=lambda f: FLAVOR_ORDER[key].index(named[f[0]][key]))
        if FLAVOR_ORDER[key].index(a[key]) > FLAVOR_ORDER[key].index(named[below][key]):
            err("repo", "flavor.name", "%s relaxes %s from %s (flavor %s, set by %s) to %s; a project may only tighten"
                % (mine, key, named[below][key], below, layer, a[key]))
    for i, cap in enumerate(a["caps"]):
        below, layer = max(floors, key=lambda f: named[f[0]]["caps"][i])
        if cap < named[below]["caps"][i]:
            err("repo", "flavor.name", "%s relaxes caps[%d] from %d (flavor %s, set by %s) to %d; a project may only "
                "tighten" % (mine, i, named[below]["caps"][i], below, layer, cap))


def doc_home_escape(merged, project, err):
    """repo.doc_home must stay inside the checkout after symlinks resolve (team §9.8); checked when the path exists."""
    home, paths = merged["repo"].get("doc_home"), merged.get("paths", {})
    base = os.path.dirname(os.path.abspath(project))
    checkout = os.path.join(base, os.path.expanduser(paths["checkout"])) if paths.get("checkout") else base
    if not isinstance(home, str) or re.search(r"<[^<>]+>", checkout):
        return
    root = os.path.realpath(checkout)
    if os.path.commonpath([root, os.path.realpath(os.path.join(root, home))]) != root:
        err("repo.doc_home", "%s resolves outside the checkout %s" % (home, root))


# --- project context (team §9.3, D1): identity (resolved team, canonical repo); FILE#selector is only a locator. ---
ENVELOPE = ("team", "project", "repo", "item", "change", "head", "pass", "round")
ENVELOPE_PASS = re.compile(r"[a-z][a-z0-9-]{0,31}")
FULL_SHA = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def context(project, team, owner, name):
    """{team, project, repo}: the canonical repo (compared case-insensitively), the resolved team or a one-repo
    config's derived singleton team `repo:<owner>/<name>`, and the real file path (plus #<repo>, the sole repo when the
    selector is omitted), so aliases and symlinks to one file give one context."""
    file, selector = split_ref(project)
    real, repo = os.path.realpath(file), ("%s/%s" % (owner, name)).lower()
    if team is None:
        return {"team": "repo:" + repo, "project": real, "repo": repo}
    return {"team": team, "project": "%s#%s" % (real, selector or team_repos(real)[0]), "repo": repo}


def project_identity(project, org_profile=None):
    """(team, repo) a project reference resolves to; ValueError naming the first problem when it does not resolve."""
    meta = {}
    merged, _, problems, _ = resolve_profile(project, org_profile, meta=meta)
    if problems:
        raise ValueError(problems[0])
    found = context(project, meta.get("team.name", (None,))[0], merged["repo"]["owner"], merged["repo"]["name"])
    return found["team"], found["repo"]


def envelope(ctx, item=None, change=None, head=None, pass_=None, round_=None):
    """The closed durable work envelope (team §9.3): an id that does not apply is an explicit null, and a new build
    has no change or head yet, never a guessed SHA."""
    return {"team": ctx["team"], "project": ctx["project"], "repo": ctx["repo"], "item": item, "change": change,
            "head": head, "pass": pass_, "round": round_}


def envelope_problem(env, ctx, resolve=project_identity):
    """Why env may not act in the project whose context is ctx, or None. The shape is closed; team and repo must be
    ctx's; another project reference must resolve to that same identity (an alias), and one that does not resolve
    refuses."""
    if not isinstance(env, dict) or sorted(env) != sorted(ENVELOPE):
        return "work envelope missing or not the closed key set (%s)" % ", ".join(ENVELOPE)

    def ident(v):
        return v is None or type(v) is int and v >= 1 or isinstance(v, str) and v != "" and not ID_UNSAFE & set(v)
    bad = [k for k in ("team", "project", "repo") if not isinstance(env[k], str) or not env[k]]
    bad += [k for k in ("item", "change") if not ident(env[k])]
    bad += ["head"] * (env["head"] is not None and not (isinstance(env["head"], str) and FULL_SHA.fullmatch(env["head"])
                                                         and env["change"] is not None))
    bad += ["pass"] * (env["pass"] is not None and not (isinstance(env["pass"], str) and ENVELOPE_PASS.fullmatch(env["pass"])))
    bad += ["round"] * (env["round"] is not None and not (type(env["round"]) is int and env["round"] >= 1))
    if bad:
        return "work envelope has an invalid %s" % ", ".join(bad)
    if (env["team"], env["repo"]) != (ctx["team"], ctx["repo"]):
        return "work envelope names %s in team %s, not %s in team %s" % (env["repo"], env["team"], ctx["repo"], ctx["team"])
    if env["project"] != ctx["project"]:
        try:
            found = resolve(env["project"])
        except (ValueError, OSError) as e:
            return "work envelope project %s does not resolve (%s)" % (env["project"], e)
        if found != (ctx["team"], ctx["repo"]):
            return "work envelope project %s is %s in team %s, not %s" % (env["project"], found[1], found[0], ctx["repo"])
    return None


def team_repos(file):
    """Repo names of a team file, or None if file is not one."""
    with open(file, "rb") as f:
        data = tomllib.load(f)
    return list(data["repos"]) if is_team(data) and isinstance(data.get("repos"), dict) else None


def release_pairing(merged, prov, files, external, err):
    """The optional release concern binds whole with an external pack (#910): a [release] table on the bundled
    default [backends.release] while the pack declares release, or a pack-bound row without the table, fails."""
    pack, bound = external["pack"]["name"], prov.get("backends.release.name")
    has_table = "release" in merged
    if has_table and bound == "default" and external["capabilities"].get("release"):
        layer = source(prov, "release")
        err(layer, "backends.release", "[release] table here, but [backends.release] is the bundled default (%s, "
            "name = %s) while pack %s declares release capabilities (%s); add [backends.release] name = \"%s\" to %s "
            "(docs/interfaces.md)" % (files["default"], json.dumps(merged["backends"]["release"]["name"]), pack,
                                      files["external-pack"], pack, files[layer]))
    elif not has_table and bound != "default" and merged["backends"].get("release", {}).get("name") == pack:
        err(bound, "release", "[backends.release] binds pack %s here, but no layer sets a [release] table; add "
            "[release] to %s (docs/interfaces.md)" % (pack, files[bound] if bound == "org" else
                                                      "%s or the pack's profile.toml" % files[bound]))


BACKEND_MAPS = os.path.join(os.path.dirname(CONNECTORS_DIR), "templates", "backends")
MAP_PLACEHOLDER = re.compile(r"<([A-Za-z][A-Za-z0-9_.:-]*)>")  # <cli>, <op:concern.operation>


def classify_binding(merged, prov, files, pack_dir, err):
    """The bound sensitivity extension command (docs/interfaces.md#bindable-sensitivity-design), or None.

    The command comes from the backend map: the pack's render/backends/<name>.toml overlay, else the bundled one."""
    be = merged["backends"]["classify"]
    name, layer = be["name"], source(prov, "backends.classify.name")
    cap = be.get("capabilities", {}).get("sensitive", "unsupported")
    if cap != "supported":
        return err(layer, "backends.classify.name", "binds %s, whose classify.sensitive is %s; an extension must be "
                   "supported (omit [backends.classify] for the built-in classifier alone)"
                   % (name, cap if "sensitive" in be.get("capabilities", {}) else "undeclared"))
    base = os.path.dirname(os.path.abspath(files["org"])) if files["org"] else pack_dir
    overlay = os.path.join(base, "render", "backends", name + ".toml") if base else None
    files["backend-map"] = overlay if overlay and os.path.isfile(overlay) else os.path.join(BACKEND_MAPS, name + ".toml")
    try:
        with open(files["backend-map"], "rb") as f:
            table = tomllib.load(f).get("classify")
    except (OSError, tomllib.TOMLDecodeError):
        table = None
    cmd = table.get("sensitive") if isinstance(table, dict) else None
    if not isinstance(cmd, str) or not cmd.strip():
        return err("backend-map", "classify.sensitive", "no command for the %s sensitivity extension" % name)
    placeholder = MAP_PLACEHOLDER.search(cmd)
    if placeholder:
        return err("backend-map", "classify.sensitive", "unfilled placeholder <%s>" % placeholder.group(1))
    return cmd


def status_binding(merged, prov, files, pack_base, err):
    """The bound status backend's {operation: command} from its map [status], or None (docs/specs/shared-status.md
    §2, §7). enabled = true needs both operations supported; a set destination needs read-records supported;
    emulated counts as not supported. With destination unset the concern is not checked."""
    st, be = merged["status"], merged["backends"]["status"]
    if "destination" not in st and not st.get("enabled"):
        return None
    layer, caps = source(prov, "backends.status.name"), be.get("capabilities", {})
    ops = STATUS_OPERATIONS["status"] if st.get("enabled") else ["read-records"]
    for op in ops:
        if caps.get(op, "unsupported") != "supported":
            return err(layer, "backends.status.name", "binds %s, whose status.%s is %s; %s needs it supported "
                       "(docs/specs/shared-status.md)" % (be["name"], op, caps.get(op, "undeclared"),
                                                          "enabled = true" if st.get("enabled") else "a destination"))
    path = status_map(be["name"], pack_base)
    try:
        with open(path, "rb") as f:
            table = tomllib.load(f).get("status")
    except (OSError, TypeError, tomllib.TOMLDecodeError):
        table = None
    files["status-map"] = path or "backends/%s.toml" % be["name"]
    cmds = {}
    for op in STATUS_OPERATIONS["status"]:
        cmd = table.get(op) if isinstance(table, dict) else None
        if op in ops and (not isinstance(cmd, str) or not cmd.strip()):
            return err("status-map", "status." + op, "no command for the %s status backend" % be["name"])
        if isinstance(cmd, str) and MAP_PLACEHOLDER.search(cmd):
            return err("status-map", "status." + op, "unfilled placeholder <%s>" % MAP_PLACEHOLDER.search(cmd).group(1))
        if isinstance(cmd, str) and cmd.strip():
            cmds[op] = cmd
    return cmds


ROOT_CHILDREN = ("state_dir", "worktree_root", "live_dir", "mdstack", "checkout")


def resolve_root(paths, prov, repo=None):
    """paths.root, which a set CREW_ROOT overrides: each relative ROOT_CHILDREN value resolves under it, so moving
    the whole layout changes one value (#1178). Without paths.root nothing changes; a <placeholder> stays as it is.
    `<owner>` and `<repo>` in a ROOT_CHILDREN value take [repo] owner and name, so the shipped default layout needs
    only [repo] filled in (#1316)."""
    if not isinstance(paths, dict) or not isinstance(paths.get("root"), str):
        return
    names = {k: v for k, v in (("owner", (repo or {}).get("owner")), ("repo", (repo or {}).get("name")))
             if isinstance(v, str) and not re.search(r"<[^<>]+>", v)}
    for key in ROOT_CHILDREN:
        if isinstance(paths.get(key), str) and names:
            paths[key] = re.sub(r"<(owner|repo)>", lambda m: names.get(m.group(1), m.group(0)), paths[key])
    root = os.environ.get("CREW_ROOT") or paths["root"]
    if re.search(r"<[^<>]+>", root):
        return
    paths["root"] = os.path.abspath(os.path.expanduser(root))
    if os.environ.get("CREW_ROOT"):
        prov["paths.root"] = "env CREW_ROOT"
    for key in ROOT_CHILDREN:
        value = paths.get(key)
        if isinstance(value, str) and value and not re.search(r"<[^<>]+>", value):
            paths[key] = os.path.normpath(os.path.join(paths["root"], os.path.expanduser(value)))


_PACK_LOADER = []


def plugin_pack(directory, files, report):
    """A pack.toml pack in the pack directory (docs/packs.md#pack-plug-ins), loaded by core/crew-pack.py: its
    connectors and environment defaults join resolve, its harness adapters join harnesses; None without pack.toml."""
    if not directory or not os.path.exists(os.path.join(directory, "pack.toml")):
        return None
    if not _PACK_LOADER:
        spec = importlib.util.spec_from_file_location("crew_pack", os.path.join(_ROOT, "core", "crew-pack.py"))
        _PACK_LOADER.append(importlib.util.module_from_spec(spec))
        spec.loader.exec_module(_PACK_LOADER[0])
    files["pack-toml"] = os.path.join(directory, "pack.toml")
    pack, problems = _PACK_LOADER[0].load(directory, types.SimpleNamespace(**globals()), harnesses)
    for problem in problems:
        report(problem)
    if pack:
        try:
            harnesses.add(pack["harnesses"])
        except ValueError as e:
            return report("%s:provides.harnesses: %s" % (files["pack-toml"], e))
    return pack


def resolve_profile(project, org_profile=None, pack_manifest=None, meta=None):
    """Layered effective profile: (merged, provenance, problems, layer names).

    provenance maps each leaf key of merged (as `leaves` yields it) to the layer that set it.
    meta, when given, receives the external pack's (else pack.toml's) pack.version, the change backend's declared
    land.* and strategy.* keys and a bound classify.sensitive extension command as {key: (value, layer)}, outside merged.
    On any problem, merged and provenance are None. A team file (or FILE#<repo>) resolves as
    core < default < org < team < repo; its state root is <paths.state_dir>/<team>.
    """
    project, repo = split_ref(project)
    files = {"core": "core", "default": DEFAULT_PROFILE, "org": org_profile, "project": project,
             "team": project, "repo": "%s[repos.%s]" % (project, repo), "external-pack": pack_manifest,
             "pack": None, None: "(resolved)"}
    problems = []
    team = None
    pack_dir = None

    def err(layer, key, reason):
        problems.append("%s:%s: %s" % (files[layer], key, reason))

    layers = [("core", copy.deepcopy(CORE_DEFAULTS))]
    for name in ["default", "project", "org"]:
        if files[name] is None or (name == "default" and not os.path.exists(files[name])):
            continue
        try:
            with open(files[name], "rb") as f:
                data = tomllib.load(f)
            if name == "project" and repo and not is_team(data):
                err("project", "(file)", "not a team file; %s#%s needs [team] and [repos.<name>]" % (project, repo))
                continue
            if name == "project" and is_team(data):
                split = team_layers(data, project, repo, err)
                if split is None:
                    continue
                data, mine, repo, team = split
                files["repo"] = "%s[repos.%s]" % (project, repo)
                layers += [("team", data), ("repo", mine)]
            else:
                layers.append((name, data))
            paths = data.get("paths")
            pack = paths.get("pack") if isinstance(paths, dict) else None
            if name == "project" and files["org"] is None and isinstance(pack, str) and pack.strip():
                directory = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(project)),
                                                        os.path.expanduser(pack)))
                if not os.path.isdir(directory):
                    err("project", "paths.pack", "pack directory missing or unreadable")
                else:
                    pack_dir = directory
                    org = os.path.join(directory, "profile.toml")
                    if os.path.exists(org):
                        files["org"] = org
        except OSError as e:
            err(name, "(file)", "cannot read (%s)" % e.strerror)
        except tomllib.TOMLDecodeError as e:
            err(name, "(toml)", "invalid TOML (%s)" % e)
    layers.sort(key=lambda layer: ["core", "default", "org", "project", "team", "repo"].index(layer[0]))
    plugin = plugin_pack(os.path.dirname(os.path.abspath(files["org"])) if files["org"] else pack_dir, files, problems.append)
    if plugin and plugin["environments"]:  # environment defaults: the pack layer under the org profile
        runtime = next((d["runtime"].get("name") for _, d in reversed(layers)
                        if isinstance(d.get("runtime"), dict) and d["runtime"].get("name")), None)
        if runtime in plugin["environments"]:
            files["pack"] = plugin["items"]["environments"][runtime]
            layers.insert(next((i for i, (n, _) in enumerate(layers) if n not in ("core", "default")), len(layers)),
                          ("pack", copy.deepcopy(plugin["environments"][runtime])))
    if pack_manifest is None and (files["org"] or pack_dir):
        adjacent = os.path.join(os.path.dirname(os.path.abspath(files["org"])) if files["org"] else pack_dir,
                                "manifest.toml")
        if os.path.exists(adjacent):
            pack_manifest = adjacent
    files["external-pack"] = pack_manifest
    external = load_pack(pack_manifest, lambda key, reason: err("external-pack", key, reason)) if pack_manifest else None
    merged, prov = {}, {}
    if not problems:
        for name, data in layers:
            merge(merged, data, prov, name, err)
        rt = merged.get("runtime")
        if isinstance(rt, dict) and rt.get("name") in RUNTIME_OPTIONS and isinstance(rt.setdefault("options", {}), dict):
            for key, (_, default) in RUNTIME_OPTIONS[rt["name"]].items():
                if default is not None and key not in rt["options"]:
                    rt["options"][key], prov["runtime.options." + key] = default, "core"
            if rt["name"] in ("tmux", "session"):
                for key in ("builders", "reviewers"):
                    present = "present_" + key
                    if present not in rt["options"] and type(rt["options"][key]) is int and rt["options"][key] >= 1:
                        rt["options"][present], prov["runtime.options." + present] = rt["options"][key], "core"
        repo_table, triage = merged.get("repo"), merged.get("triage")
        if isinstance(triage, dict) and "repos" not in triage and isinstance(repo_table, dict) and \
                {"owner", "name"} <= repo_table.keys():  # triage sweeps the project's own repo unless set (#748)
            triage["repos"], prov["triage.repos"] = ["%s/%s" % (repo_table["owner"], repo_table["name"])], "core"
        docs = merged.get("docs")
        if isinstance(docs, dict):  # [docs] defaults apply only when the table is present (#1024)
            for key, default in DOCS_DEFAULTS.items():
                if key not in docs:
                    docs[key], prov["docs." + key] = default, "core"
            if "repos" not in docs and isinstance(repo_table, dict) and {"owner", "name"} <= repo_table.keys():
                docs["repos"], prov["docs.repos"] = ["%s/%s" % (repo_table["owner"], repo_table["name"])], "core"
        ids = merged.get("identities")
        if isinstance(ids, dict) and isinstance(ids.get("coordinator"), dict) and "gh_user" in ids["coordinator"]:
            for role in OPTIONAL_IDENTITIES:  # e.g. the researcher posts as the author identity unless set (#584)
                if isinstance(ids.get(role), dict) and "gh_user" not in ids[role]:
                    ids[role]["gh_user"], prov["identities.%s.gh_user" % role] = ids["coordinator"]["gh_user"], "core"
        if team:  # one instance per team: one session, one state root with a subfolder per repo
            paths = merged.get("paths")
            if isinstance(paths, dict) and isinstance(paths.get("state_dir"), str):
                paths["state_dir"], prov["paths.state_dir"] = os.path.join(paths["state_dir"], team), "team"
            if isinstance(rt, dict) and rt.get("name") == "tmux" and isinstance(rt.get("options"), dict) \
                    and "session" not in rt["options"]:
                rt["options"]["session"], prov["runtime.options.session"] = "crew-team-" + team, "team"
        status = merged.get("status")
        if isinstance(status, dict):  # [status] defaults and the bundled binding apply only with the table (#1313)
            for key, (_, default) in STATUS_FIELDS.items():
                if default is not None and key not in status:
                    status[key], prov["status." + key] = default, "core"
            backends = merged.get("backends")
            if isinstance(backends, dict) and "status" not in backends:
                backends["status"], prov["backends.status.name"] = {"name": "github"}, "default"
        land, strategy = {}, {}
        connectors = plugin["items"]["connectors"] if plugin else {}
        fold_manifests(merged, prov, files, err, external, land, strategy, connectors)

        def verr(key, reason):
            key = key.lstrip(".")
            err(source(prov, re.sub(r"\[\d+\]", "", key)), key, reason)
        count = len(problems)
        names = BACKENDS + ([external["pack"]["name"]] if external else []) + list(connectors)
        pack_base = os.path.dirname(os.path.abspath(files["org"] or pack_manifest)) if files["org"] or pack_manifest \
            else pack_dir
        ids = backend_ids(merged, pack_base, lambda name, key, reason: problems.append(
            "backend-map:%s:%s: %s" % (name, key, reason)), names)
        status_ids = status_destination(merged, pack_base, lambda name, key, reason: problems.append(
            "backend-map:%s:%s: %s" % (name, key, reason)))
        validate(merged, verr, names, item=ids["item"] if ids["item"][1] else None, status_ids=status_ids)
        if len(problems) == count and team:
            project_relaxation(layers, merged, err)
        if len(problems) == count:
            cross_check(merged, verr)
        if len(problems) == count:
            resolve_root(merged.get("paths"), prov, merged.get("repo"))
            doc_home_escape(merged, project, verr)
        if len(problems) == count:  # one resolved copy for every consumer; a profile layer cannot set [ids]
            if status_ids:
                ids["status-destination"] = status_ids
            merged["ids"] = {key: pattern for key, (pattern, _) in ids.items()}
            prov.update({"ids." + key: "backend-map:" + name if name else "core" for key, (_, name) in ids.items()})
        if len(problems) == count and external:
            release_pairing(merged, prov, files, external, err)
        if len(problems) == count and land:  # effective change capabilities and runtime (docs/interfaces.md#declaration)
            layer = next(iter(land.values()))[1]
            check_land(lambda key, reason: err(layer, key, reason), {k: v for k, (v, _) in land.items()},
                       merged["backends"]["change"].get("capabilities", {}), merged["runtime"]["name"])
        if len(problems) == count and strategy:
            layer = next(iter(strategy.values()))[1]
            check_strategy(lambda key, reason: err(layer, key, reason), {k: v for k, (v, _) in strategy.items()})
        versioned = external["pack"] if external and "version" in external["pack"] else plugin
        if meta is not None and versioned and "version" in versioned:  # external manifest, else pack.toml (#1350)
            meta["pack.version"] = (versioned["version"], "pack:" + versioned["name"])
        if meta is not None and team:  # resolved team.name, else the file name: the signature's team (#1291)
            meta["team.name"] = (team, "team")
        if meta is not None:
            meta.update({"land." + key: entry for key, entry in land.items()})
            meta.update({"strategy." + key: entry for key, entry in strategy.items()})
        if len(problems) == count and isinstance(merged.get("status"), dict):
            cmds = status_binding(merged, prov, files, pack_base, err)
            if meta is not None and cmds:
                meta.update({"status." + op: (cmd, "pack:" + merged["backends"]["status"]["name"])
                             for op, cmd in cmds.items()})
        if len(problems) == count and "classify" in merged["backends"]:
            cmd = classify_binding(merged, prov, files, pack_dir, err)
            if meta is not None and cmd is not None:
                meta["classify.sensitive"] = (cmd, "pack:" + merged["backends"]["classify"]["name"])
    names = [name for name, _ in layers]
    if problems:
        return None, None, problems, names
    if "name" not in merged.get("flavor", {}):
        merged.setdefault("flavor", {})["name"] = UNSET_FLAVOR
        prov["flavor.name"] = "core (unset: flagged)"
    return merged, {key: source(prov, key) or "core" for key, _ in leaves(merged)}, [], names


def resolve_main(args):
    meta = {}
    merged, provenance, problems, layers = resolve_profile(args.project, args.org_profile, args.pack_manifest, meta)
    if not problems and args.install:
        def install_err(key, reason):
            layer = source(provenance, re.sub(r"\[\d+\]", "", key))
            file = {"default": DEFAULT_PROFILE, "project": args.project, "team": split_ref(args.project)[0],
                    "repo": args.project, "org": args.org_profile}.get(layer) or "(resolved)"
            problems.append("%s:%s: %s" % (file, key, reason))
        scan_install_placeholders(merged, install_err)
    for p in problems:
        print(p)
    if problems:
        print("crew-config: FAILED (%d problem%s)" % (len(problems), "" if len(problems) == 1 else "s"), file=sys.stderr)
        return 1
    for key, value in leaves(merged):
        print("%s = %s  # %s" % (key, json.dumps(value, ensure_ascii=False), provenance[key]))
    for key, (value, layer) in meta.items():
        print("%s = %s  # %s" % (key, json.dumps(value, ensure_ascii=False), layer))
    print("crew-config: OK (layers: %s)" % ", ".join(layers), file=sys.stderr)
    return 0


def sensitive_matches(profile, paths):
    """Match repo-relative diff paths against mandatory defaults plus profile additions."""
    rules = SENSITIVE_PATHS + profile.get("sensitive", {}).get("paths", [])
    return {path: [rule for rule in rules if path_glob.glob_regex(rule).fullmatch(path)]
            for path in sorted(set(paths)) if any(path_glob.glob_regex(rule).fullmatch(path) for rule in rules)}


EXTENSION_TIMEOUT = 120  # seconds a bound sensitivity extension may run (docs/interfaces.md#bindable-sensitivity-design)


def content_record_ok(rec):
    """One shared-contract content record (docs/profile.md#content-rules-proposed-879)."""
    return isinstance(rec, dict) and all(isinstance(rec.get(k), str) and rec[k] for k in ("rule", "path")) \
        and rec.get("side") in ("old", "new") and type(rec.get("line")) is int and rec["line"] >= 1


def run_extension(pack, cmd, stdin):
    """(matches, content, error) from a bound sensitivity extension, rule names prefixed <pack>:.

    Any failure returns no matches and one error line naming the pack and the cause; the caller reads it as
    sensitive, so a broken extension never yields a clean result."""
    try:
        proc = subprocess.run(["sh", "-c", cmd], input=stdin, capture_output=True, timeout=EXTENSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        return {}, [], "%s: timed out after %ds" % (pack, EXTENSION_TIMEOUT)
    except OSError as e:
        return {}, [], "%s: cannot run (%s)" % (pack, e.strerror)
    if proc.returncode:
        return {}, [], "%s: exit %d" % (pack, proc.returncode)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = None
    if not isinstance(out, dict):
        return {}, [], "%s: stdout is not one JSON object" % pack
    matches, content = out.get("matches"), out.get("content", [])
    if out.get("label", "") not in (None, "crew:sensitive"):
        return {}, [], "%s: label is not null or crew:sensitive" % pack
    if not isinstance(matches, dict) or not all(
            path and isinstance(rules, list) and rules and all(isinstance(r, str) and r for r in rules)
            for path, rules in matches.items()):
        return {}, [], "%s: matches is not an object of path to rule-name lists" % pack
    if not isinstance(content, list) or not all(content_record_ok(rec) for rec in content):
        return {}, [], "%s: malformed content record" % pack
    if out["label"] and not matches and not content:
        return {}, [], "%s: label crew:sensitive with no match to record" % pack
    return ({path: ["%s:%s" % (pack, r) for r in rules] for path, rules in matches.items()},
            [dict(rec, rule="%s:%s" % (pack, rec["rule"])) for rec in content], None)


def sensitive_result(profile, paths, extension=None, stdin=b"", content=None):
    """The shared JSON result: built-in path rules and content records, plus a bound (pack, command) extension's
    matches, content and errors."""
    matches = sensitive_matches(profile, paths)
    result = {"label": None, "matches": matches}
    if content is not None:
        result["content"] = content
    if extension:
        ext_matches, ext_content, error = run_extension(extension[0], extension[1], stdin)
        for path, rules in ext_matches.items():
            matches[path] = matches.get(path, []) + rules
        result["matches"] = dict(sorted(matches.items()))
        if ext_content:
            result["content"] = sorted(result.get("content", []) + ext_content,
                                       key=lambda r: (r["path"], r["side"], r["line"], r["rule"]))
        result["errors"] = [error] if error else []
    if result["matches"] or result.get("content") or result.get("errors"):
        result["label"] = "crew:sensitive"
    return result


HUNK = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
HEADER_KINDS = (("--- ", "---"), ("+++ ", "+++"), ("index ", "index"), ("Binary files ", "binary"),
                ("GIT binary patch", "binary"), ("old mode ", "old-mode"), ("new mode ", "new-mode"))
EMPTY_BLOBS = ("e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",  # SHA-1 and SHA-256 ids of the empty blob
               "473a0f4c3be8a93681a267e3b1e9a7dcda1185436fe141f7749120a303721813")
EMPTY_INDEX = re.compile(r"index (0+\.\.([0-9a-f]+)|([0-9a-f]+)\.\.0+)(?: \d+)?")


def header_kind(raw):
    """Kind of a pre-hunk header line; an index line that adds or deletes the empty blob is `empty`."""
    m = EMPTY_INDEX.fullmatch(raw)
    if m and any(blob.startswith(m[2] or m[3]) for blob in EMPTY_BLOBS):
        return "empty"
    return next((kind for prefix, kind in HEADER_KINDS if raw.startswith(prefix)), "other")


def finish_file(path, seen, hunked):
    """Accept only a complete file block: a text patch (---, +++ and a hunk), a binary change, an empty blob
    added or deleted, or a mode-only change. Any other block was cut inside its header."""
    if not ({"---", "+++"} <= seen and hunked or "binary" in seen or "empty" in seen
            or seen == {"old-mode", "new-mode"}):
        raise ValueError("file header of %s is incomplete" % path)


def parse_diff(text):
    """Split a `git diff --no-renames` unified diff into (paths, [(path, side, line, text)]) for changed lines.

    Hunk counts bound each hunk, so a changed line that looks like a header stays content. A rename or copy
    (rename folding was on), a quoted or asymmetric path, a stray line or a short hunk raises ValueError."""
    if not text.strip():
        raise ValueError("empty diff")
    paths, lines, path, old, new, hunked, seen = [], [], None, 0, 0, False, set()
    for raw in text.split("\n")[:-1] if text.endswith("\n") else text.split("\n"):
        if old or new:
            tag, body = raw[:1], raw[1:]
            if tag in (" ", "-"):
                if tag == "-":
                    lines.append((path, "old", old_no, body))
                old, old_no = old - 1, old_no + 1
            if tag in (" ", "+"):
                if tag == "+":
                    lines.append((path, "new", new_no, body))
                new, new_no = new - 1, new_no + 1
            if tag not in (" ", "-", "+", "\\") or old < 0 or new < 0:
                raise ValueError("malformed hunk line in %s: %r" % (path, raw))
        elif raw.startswith("diff --git "):
            if path is not None:
                finish_file(path, seen, hunked)
            pair = raw[len("diff --git "):]
            half = pair[:(len(pair) - 1) // 2]
            if not half.startswith("a/") or pair != half + " b/" + half[2:]:
                raise ValueError("unreadable file header (quoted or renamed path): %r" % raw)
            path, hunked, seen = half[2:], False, set()
            paths.append(path)
        elif raw.startswith("@@") and path is not None:
            m = HUNK.match(raw)
            if not m or "+++" not in seen:
                raise ValueError("malformed hunk header in %s: %r" % (path, raw))
            old_no, old, new_no, new, hunked = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1), True
        elif path is None:
            raise ValueError("expected a `diff --git` file header: %r" % raw)
        elif raw.startswith(("rename from ", "copy from ")) or hunked and not raw.startswith("\\"):
            raise ValueError("unexpected line in %s (a diff made with --no-renames is required): %r" % (path, raw))
        else:
            seen.add(header_kind(raw))
    if old or new:
        raise ValueError("diff ends inside a hunk of %s" % path)
    finish_file(path, seen, hunked)
    return paths, lines


def content_matches(profile, lines):
    """Content rule records (#879) for changed diff lines, sorted by path, side, line and rule."""
    records = []
    for rule in profile.get("sensitive", {}).get("content", []):
        scope, pattern = rule.get("paths"), re.compile(rule["pattern"])
        records += [{"rule": rule["name"], "path": path, "side": side, "line": number}
                    for path, side, number, body in lines
                    if (scope is None or any(path_glob.glob_regex(g).fullmatch(path) for g in scope))
                    and pattern.search(body)]
    return sorted(records, key=lambda r: (r["path"], r["side"], r["line"], r["rule"]))


def spec_matches(profile, paths):
    """{path: [matching spec globs]}; [spec] paths replaces the default globs, [] leaves only the crew:spec label."""
    rules = profile.get("spec", {}).get("paths", SPEC_PATHS)
    return {path: [rule for rule in rules if path_glob.glob_regex(rule).fullmatch(path)]
            for path in sorted(set(paths)) if any(path_glob.glob_regex(rule).fullmatch(path) for rule in rules)}


def stricter(a, b):
    """True when flavor a beats flavor b on any rigor knob or cap."""
    return any(FLAVOR_ORDER[k].index(a[k]) < FLAVOR_ORDER[k].index(b[k]) for k in FLAVOR_ORDER if k != "builder") \
        or any(x > y for x, y in zip(a["caps"], b["caps"]))


def class_flavor(profile, paths, express=False):
    """Return strictest rigor and matched rule indexes for repo-relative paths.

    express: the newest item record names express and the change carries crew:express. Express knobs
    then apply unless a path matches a class stricter than the project flavor (a tightening class).
    """
    flavor = profile.get("flavor", {})
    named = copy.deepcopy(FLAVOR_PRESETS)
    for name, knobs in flavor.get("custom", {}).items():
        named[name] = dict(named[knobs["base"]], **{k: v for k, v in knobs.items() if k != "base"})
    project = flavor.get("name", UNSET_FLAVOR)
    paths = sorted(set(paths))
    matches, choices = {}, []
    for path in paths:
        if not path.strip() or path.startswith("/") or any(p in ("", ".", "..") for p in path.split("/")):
            raise ValueError("expected nonempty repo-relative paths without . or ..: %r" % path)
        indexes = [i for i, rule in enumerate(flavor.get("classes", []))
                   if any(path_glob.glob_regex(pattern).fullmatch(path) for pattern in rule["paths"])]
        matches[path] = indexes
        choices.extend(named[flavor["classes"][i]["flavor"]] for i in indexes)
        if not indexes:
            choices.append(named[project])
    choices = choices or [named[project]]
    rigor = {key: min((choice[key] for choice in choices), key=order.index)
             for key, order in FLAVOR_ORDER.items() if key != "builder"}
    rigor["caps"] = [max(choice["caps"][i] for choice in choices) for i in range(2)]
    tightening = sorted({i for indexes in matches.values() for i in indexes
                         if stricter(named[flavor["classes"][i]["flavor"]], named[project])})
    lane = "express" if express and not tightening else "crew"
    if lane == "express":
        rigor = {k: v for k, v in named["express"].items() if k != "builder"}
        rigor["selfgate_engine"] = flavor.get("selfgate_engine", "different")
    return {"project": project, "rigor": rigor, "matches": matches, "lane": lane, "tightening": tightening}


def precheck_scope(precheck, paths):
    """Classify changed paths (#881): owned (owning test targets), no-owner-ok (reasoned n/a), unowned code,
    or removed: absent at head under the working directory (deleted or a rename source; #1345), never queried.

    The owners command gets one path as a single shell argument, so spaces survive. Returns (result, exit code);
    a failed query raises RuntimeError, never n/a."""
    entries = []
    for path in sorted(set(p for p in paths if p)):
        if not os.path.lexists(path):
            entries.append({"path": path, "class": "removed", "targets": []})
            continue
        run = subprocess.run(["sh", "-c", precheck["owners"] + ' "$1"', "sh", path], capture_output=True, text=True)
        if run.returncode:
            raise RuntimeError("owners query failed (exit %d) for %r: %s" % (run.returncode, path, run.stderr.strip()))
        targets = [t.strip() for t in run.stdout.splitlines() if t.strip()]
        ok = any(path_glob.glob_regex(g).fullmatch(path) for g in precheck.get("no_owner_ok", []))
        entries.append({"path": path, "class": "owned" if targets else "no-owner-ok" if ok else "unowned",
                        "targets": targets})
    unowned = [e["path"] for e in entries if e["class"] == "unowned"]
    owned = [e for e in entries if e["class"] == "owned"]
    tests = "fail" if unowned else "run" if owned else "n/a"
    return {"tests": tests, "targets": sorted({t for e in owned for t in e["targets"]}),
            "no_owner_ok": [e["path"] for e in entries if e["class"] == "no-owner-ok"],
            "unowned": unowned, "removed": [e["path"] for e in entries if e["class"] == "removed"],
            "paths": entries}, 3 if unowned else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    vp = sub.add_parser("validate", help="validate a config.toml profile or pack manifest")
    vp.add_argument("file")
    vp.add_argument("--install", action="store_true", help="reject unfilled install-time placeholders")
    vp.add_argument("--pack-manifest", help="external pack manifest declaring an additional backend")
    rp = sub.add_parser("resolve", help="print the layered effective profile with the layer that set each key")
    rp.add_argument("--project")
    rp.add_argument("--org-profile")
    rp.add_argument("--install", action="store_true", help="reject unfilled install-time placeholders")
    rp.add_argument("--pack-manifest", help="external pack manifest declaring an additional backend")
    sp = sub.add_parser("sensitive", help="classify newline-separated diff paths from stdin; print JSON")
    sp.add_argument("--project")
    sp.add_argument("--org-profile")
    mode = sp.add_mutually_exclusive_group()
    mode.add_argument("--diff", action="store_true", help="stdin is a `git diff --no-renames` unified diff (#879)")
    mode.add_argument("--paths-only", action="store_true",
                      help="triage: path rules on an issue's named paths, content rules not applied (#879)")
    fp = sub.add_parser("class-flavor", help="combine path class rigor; stdin paths, JSON output")
    fp.add_argument("--project")
    fp.add_argument("--org-profile")
    fp.add_argument("--express", action="store_true",
                    help="the newest item record names express and the change carries crew:express")
    pp = sub.add_parser("precheck-scope", help="classify stdin diff paths by builder.precheck.owners; print JSON")
    pp.add_argument("--project")
    pp.add_argument("--org-profile")
    args = ap.parse_args(argv)
    if getattr(args, "project", "") is None:
        args.project = default_config()
    if args.cmd in ("sensitive", "class-flavor", "precheck-scope"):
        meta = {}
        profile, _, problems, _ = resolve_profile(args.project, args.org_profile, meta=meta)
        if problems:
            print("\n".join(problems), file=sys.stderr)
            return 1
        content = None
        if args.cmd == "sensitive" and args.diff:
            raw = sys.stdin.buffer.read()
            try:
                paths, lines = parse_diff(raw.decode("utf-8", "replace"))
            except ValueError as e:
                print("sensitive: incomplete diff input, classification stopped: %s" % e, file=sys.stderr)
                return 3
            if profile.get("sensitive", {}).get("content"):
                content = content_matches(profile, lines)
        else:
            text = sys.stdin.read()
            paths, raw = text.splitlines(), text.encode()
        if args.cmd == "precheck-scope":
            precheck = profile.get("builder", {}).get("precheck", {})
            if not precheck.get("owners"):
                print("precheck-scope: builder.precheck.owners is not set", file=sys.stderr)
                return 1
            try:
                result, code = precheck_scope(precheck, paths)
            except RuntimeError as e:
                print("precheck-scope: " + str(e), file=sys.stderr)
                return 4
            print(json.dumps(result))
            return code
        if args.cmd == "class-flavor":
            try:
                result = class_flavor(profile, paths, args.express)
            except ValueError as e:
                print(str(e), file=sys.stderr)
                return 1
        else:
            if content is None and profile.get("sensitive", {}).get("content") and not args.paths_only:
                print("sensitive: content rules need a unified diff (--diff, #879); a path list leaves "
                      "classification incomplete", file=sys.stderr)
                return 3
            bound = meta.get("classify.sensitive")
            result = sensitive_result(profile, paths, bound and (profile["backends"]["classify"]["name"], bound[0]),
                                      raw, content)
        print(json.dumps(result))
        return 0
    if args.cmd == "resolve":
        return resolve_main(args)
    problems = []

    def err(key, reason):
        problems.append("%s:%s: %s" % (args.file, key.lstrip("."), reason))

    try:
        def pack_err(key, reason):
            problems.append("%s:%s: %s" % (args.pack_manifest, key.lstrip("."), reason))
        external = load_pack(args.pack_manifest, pack_err) if args.pack_manifest else None
        with open(args.file, "rb") as f:
            profile = tomllib.load(f)
            names = BACKENDS + ([external["pack"]["name"]] if external and not problems else [])
            pack = profile.get("paths", {}).get("pack") if isinstance(profile.get("paths"), dict) else None
            pack_base = os.path.dirname(os.path.abspath(args.pack_manifest)) if args.pack_manifest else \
                os.path.join(os.path.dirname(os.path.abspath(args.file)), os.path.expanduser(pack)) \
                if isinstance(pack, str) and pack.strip() else None
            ids = backend_ids(profile, pack_base, lambda name, key, reason: problems.append(
                "backend-map:%s:%s: %s" % (name, key, reason)), names)
            status_ids = status_destination(profile, pack_base, lambda name, key, reason: problems.append(
                "backend-map:%s:%s: %s" % (name, key, reason)))
            validate(profile, err, names, os.path.dirname(os.path.abspath(args.file)),
                     item=ids["item"] if ids["item"][1] else None, status_ids=status_ids)
            if args.install:
                scan_install_placeholders(profile, err)
    except OSError as e:
        err("(file)", "cannot read (%s)" % e.strerror)
    except tomllib.TOMLDecodeError as e:
        err("(toml)", "invalid TOML (%s)" % e)
    for p in problems:
        print(p)
    if problems:
        print("crew-config: FAILED (%d problem%s)" % (len(problems), "" if len(problems) == 1 else "s"), file=sys.stderr)
        return 1
    print("crew-config: OK (%s)" % args.file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
