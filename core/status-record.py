"""Shared-status record S, version 1 (docs/specs/shared-status.md §3, #1313): the closed pointer/count schema, the
slot body that carries it, its content identity and the [status] setting patterns. Pure: no file, network or clock;
the caller passes `now` (epoch seconds) for the future check. Imported by `core/crew-config.py` and the terminal
status commands; the secret scan uses `core/secret-patterns.py`. Python 3 stdlib only.

check_record(rec, runtimes, now) lists every problem as `field: reason` (empty when valid), runtimes being the
profile schema's runtime.name values (crew-config's RUNTIME_OPTIONS); parse_slot(body) splits a comment into
(object, problem); slot_body(rec) and content_sha256(rec) build the body and its identity.
"""
import calendar
import hashlib
import importlib.util
import json
import os
import re
import time

_spec = importlib.util.spec_from_file_location(
    "secret_patterns", os.path.join(os.path.dirname(os.path.abspath(__file__)), "secret-patterns.py"))
secret_patterns = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(secret_patterns)

MARKER = "<!-- mdstack-status v=1 -->"
INSTANCE_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,62}")
REGISTRATION_ID = re.compile(r"r-[0-9a-f]{32}")
REPO = re.compile(r"[A-Za-z0-9-]+/[A-Za-z0-9._-]+")
UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
# The bundled backend's URL rule (§3.4): no user info, port, query or fragment can match.
URL = re.compile(r"https://github\.com/(?P<repo>[A-Za-z0-9-]+/[A-Za-z0-9._-]+)/"
                 r"(?P<kind>issues|pull|milestone)/(?P<n>[1-9][0-9]*)")
REASONS = ["read-failed", "unsupported", "over-limit"]
STAGES = ["escalated", "held", "changes", "approved", "in-review", "other"]
KINDS = ["escalated", "main-red", "held"]
# section: (payload keys, item keys or None, list limit or None)
SECTIONS = {"milestones": (["items"], ["url", "completed", "total"], 20),
            "prs": (["items"], ["url", "stage"], 100),
            "owner_asks": (["items"], ["url", "deadline"], 50),
            "blockers": (["items"], ["url", "kind"], 50),
            "throughput": (["merged_24h"], None, None),
            "queue": (["depth", "target"], None, None)}
TOP = ["schema_version", "instance_id", "registration_id", "sequence", "observed_at", "published_at", "source",
       "sections"]
MAX_COUNT = 1_000_000
MAX_SEQUENCE = 2 ** 53 - 1
MAX_REPOS = 32
MAX_BODY = 60_000
FUTURE = 120  # seconds a time may run ahead of the checker's clock


def utc(value):
    """Epoch seconds of a `YYYY-MM-DDTHH:MM:SSZ` string that is a real calendar time, else None."""
    if not isinstance(value, str) or not UTC.fullmatch(value):
        return None
    try:
        parsed = time.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None
    return calendar.timegm(parsed) if time.strftime("%Y-%m-%dT%H:%M:%SZ", parsed) == value else None


def stamp(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(epoch)))


def is_int(value):
    return type(value) is int


def url_problem(value, kinds, repos):
    """Why value is not a URL of one of kinds (issues, pull, milestone) in one of repos (None: any repo), else None."""
    m = URL.fullmatch(value) if isinstance(value, str) else None
    if not m or m.group("kind") not in kinds:
        return "expected a %s URL (https://github.com/<owner>/<repo>/%s/<n>)" % (" or ".join(kinds), kinds[0])
    if repos is not None and m.group("repo").lower() not in repos:
        return "URL is not in a source repo"
    return None


def canonical(rec):
    return json.dumps(rec, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def content_sha256(rec):
    return hashlib.sha256(canonical(rec)).hexdigest()


def slot_body(rec):
    """The exact slot body (§3.1): the marker line, then one json fence holding the canonical record, with no final
    newline, so a backend that trims one returns the same bytes."""
    return "%s\n```json\n%s\n```" % (MARKER, canonical(rec).decode("utf-8"))


def _pairs(pairs):
    keys = [k for k, _ in pairs]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate key")
    return dict(pairs)


def _constant(name):
    raise ValueError("non-finite number %s" % name)


def parse_slot(body):
    """(None, None) for a comment that is not a status comment; (object, None) for a well-formed slot body whose
    JSON is an object (its schema still unchecked); (object or None, reason) for an invalid status comment."""
    if not isinstance(body, str) or body.split("\n", 1)[0].rstrip("\r") != MARKER:
        return None, None
    if len(body.encode("utf-8")) > MAX_BODY:
        return None, "slot body over %d bytes" % MAX_BODY
    lines = body[:-1].split("\n") if body.endswith("\n") else body.split("\n")
    if len(lines) < 4 or lines[0] != MARKER or lines[1] != "```json" or lines[-1] != "```" or \
            any(line.startswith("```") for line in lines[2:-1]):
        return None, "not exactly the marker line and one json fence"
    try:
        rec = json.loads("\n".join(lines[2:-1]), object_pairs_hook=_pairs, parse_constant=_constant)
    except ValueError as e:
        return None, "record is not JSON (%s)" % e
    if not isinstance(rec, dict):
        return None, "record is not a JSON object"
    return rec, None


def _count(problems, path, value):
    if not is_int(value) or not 0 <= value <= MAX_COUNT:
        problems.append("%s: expected an integer count 0-%d" % (path, MAX_COUNT))


def _keys(problems, path, value, keys):
    """True when value is an object with exactly keys; else one problem per missing or extra key."""
    if not isinstance(value, dict):
        problems.append("%s: expected an object" % path)
        return False
    for k in sorted(set(keys) - value.keys()):
        problems.append("%s.%s: missing" % (path, k))
    for k in sorted(value.keys() - set(keys)):
        problems.append("%s.%s: unknown field" % (path, k))
    return value.keys() == set(keys)


def _time(problems, path, value, now, future=True):
    t = utc(value)
    if t is None:
        problems.append("%s: expected a UTC time YYYY-MM-DDTHH:MM:SSZ" % path)
    elif future and now is not None and t > now + FUTURE:
        problems.append("%s: future time (more than %d s ahead)" % (path, FUTURE))
        return None
    return t


def _item(problems, path, name, item, repos):
    if name == "milestones":
        p = url_problem(item["url"], ["milestone"], repos)
        _count(problems, path + ".completed", item["completed"])
        _count(problems, path + ".total", item["total"])
        if is_int(item["completed"]) and is_int(item["total"]) and item["completed"] > item["total"]:
            problems.append("%s: completed > total" % path)
    elif name == "prs":
        p = url_problem(item["url"], ["pull"], repos)
        if item["stage"] not in STAGES:
            problems.append("%s.stage: expected one of %s" % (path, ", ".join(STAGES)))
    elif name == "owner_asks":
        p = url_problem(item["url"], ["issues", "pull"], repos)
        if item["deadline"] is not None:
            _time(problems, path + ".deadline", item["deadline"], None, future=False)
    else:
        p = url_problem(item["url"], ["issues", "pull"], repos)
        if item["kind"] not in KINDS:
            problems.append("%s.kind: expected one of %s" % (path, ", ".join(KINDS)))
    if p:
        problems.append("%s.url: %s" % (path, p))


def _section(problems, name, sec, repos, now):
    path = "sections." + name
    if not isinstance(sec, dict):
        problems.append("%s: expected an object" % path)
        return None
    payload, item_keys, limit = SECTIONS[name]
    state = sec.get("state")
    if state == "unknown":
        if _keys(problems, path, sec, ["state", "observed_at", "reason"]) and sec["reason"] not in REASONS:
            problems.append("%s.reason: expected one of %s" % (path, ", ".join(REASONS)))
    elif state == "known":
        if _keys(problems, path, sec, ["state", "observed_at"] + payload):
            if item_keys is None:
                for k in payload:
                    _count(problems, "%s.%s" % (path, k), sec[k])
            elif not isinstance(sec["items"], list):
                problems.append("%s.items: expected a list" % path)
            elif len(sec["items"]) > limit:
                problems.append("%s.items: %d items over the limit %d (report unknown over-limit)"
                                % (path, len(sec["items"]), limit))
            else:
                seen = set()
                for i, item in enumerate(sec["items"]):
                    ipath = "%s.items[%d]" % (path, i)
                    if _keys(problems, ipath, item, item_keys):
                        _item(problems, ipath, name, item, repos)
                        if name == "blockers" and item["url"] in seen:
                            problems.append("%s.url: duplicate blocker URL" % ipath)
                        seen.add(item["url"])
    else:
        problems.append("%s.state: expected known or unknown" % path)
        return None
    return _time(problems, path + ".observed_at", sec.get("observed_at"), now)


def secret_reasons(text):
    """Secret-scan reasons for serialized text, with the same patterns as profile validation and the repo guard."""
    reasons = [reason for _, rx, reason in secret_patterns.PATTERNS if rx.search(text)]
    if any(not secret_patterns.is_placeholder(m.group(1)) for m in secret_patterns.BEARER.finditer(text)):
        reasons.append("bearer auth header with a literal value")
    if list(secret_patterns.URL_CRED.finditer(text)):
        reasons.append("URL with embedded credentials")
    return reasons


def check_record(rec, runtimes, now=None):
    """Every §3.2-§3.4 problem of a parsed record; now None skips the future check (a receipt's pending body)."""
    problems = []
    if not _keys(problems, "record", rec, TOP):
        if not isinstance(rec, dict):
            return problems
    version = rec.get("schema_version")
    if "schema_version" in rec and (not is_int(version) or version != 1):
        problems.append("schema_version: unknown version %s" % json.dumps(version))
        return problems
    if "instance_id" in rec and not (isinstance(rec["instance_id"], str) and INSTANCE_ID.fullmatch(rec["instance_id"])):
        problems.append("instance_id: expected [a-z0-9][a-z0-9-]{0,62}")
    if "registration_id" in rec and not (isinstance(rec["registration_id"], str)
                                         and REGISTRATION_ID.fullmatch(rec["registration_id"])):
        problems.append("registration_id: expected r- and 32 lowercase hex digits")
    if "sequence" in rec and (not is_int(rec["sequence"]) or not 1 <= rec["sequence"] <= MAX_SEQUENCE):
        problems.append("sequence: expected an integer 1-%d" % MAX_SEQUENCE)
    repos = None
    source = rec.get("source")
    if "source" in rec and _keys(problems, "source", source, ["repos", "runtime", "decision_log"]):
        names = source["repos"]
        if not isinstance(names, list) or not 1 <= len(names) <= MAX_REPOS or \
                not all(isinstance(r, str) and REPO.fullmatch(r) for r in names):
            problems.append("source.repos: expected 1-%d <owner>/<name> strings" % MAX_REPOS)
        elif names != sorted(set(names)):
            problems.append("source.repos: expected sorted, distinct repos")
        else:
            repos = {r.lower() for r in names}
        if source["runtime"] not in runtimes:
            problems.append("source.runtime: expected one of %s" % ", ".join(runtimes))
        p = url_problem(source["decision_log"], ["issues"], None)
        if p:
            problems.append("source.decision_log: " + p)
    observed = []
    sections = rec.get("sections")
    if "sections" in rec and _keys(problems, "sections", sections, list(SECTIONS)):
        for name in SECTIONS:
            observed.append(_section(problems, name, sections[name], repos if repos is not None else set(), now))
    top_obs = _time(problems, "observed_at", rec.get("observed_at"), now) if "observed_at" in rec else None
    published = _time(problems, "published_at", rec.get("published_at"), now) if "published_at" in rec else None
    known = [t for t in observed if t is not None]
    if top_obs is not None and len(known) == len(SECTIONS) and top_obs != min(known):
        problems.append("observed_at: expected the earliest section observed_at (%s)" % stamp(min(known)))
    if published is not None and any(published < t for t in known + ([top_obs] if top_obs is not None else [])):
        problems.append("published_at: before an observed_at")
    reasons = secret_reasons(canonical(rec).decode("utf-8"))
    if reasons:
        problems.append("record: secret-pattern match (%s)" % "; ".join(reasons))
    return problems


def check_body(body, runtimes, now=None):
    """(record, problems) of a slot body: parse_slot, then check_record; a non-status comment is a problem too."""
    rec, problem = parse_slot(body)
    if problem or rec is None:
        return None, [problem or "not a status comment"]
    return rec, check_record(rec, runtimes, now)
