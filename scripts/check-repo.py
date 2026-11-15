#!/usr/bin/env python3
"""Repo guard for mdstack (spec R1, R6): secret scan, required docs/sections,
relative markdown links, crew marker SHAs, optional name denylist,
deliverables manifest coverage, spec slice status, design headers naming an
open milestone, CHANGELOG fragments,
per-script docs, index files (inventory fresh, entries sorted, docs index
complete), no committed evidence directory, the campaign scenario index
(one file per scenario, index generated and complete), markdown lint (check-markdown.py on every tracked *.md
file), tests per module, and the team spec's dependency rules with the
runtime-word lint, core memory (layout, size limits, no personal data), role routines and
campaign scenarios (campaign-lint.py: unhandled assertions, required cases kept against origin/main).
In a git work tree it also warns on stderr, naming them, about non-ignored
untracked files, which the path checks skip (exit code unchanged).
Python 3 stdlib only, no network.

Usage: check-repo.py [--root DIR] [--config FILE] [--fix] [--only secrets|docs|links|markers|blockers|shapes|denylist|deliverables|spec-status|design-headers|fragments|script-docs|index|evidence|scenarios|markdown|test-layout|deps|memory|routines|campaign]...
Every failure prints `file:line: [rule] reason`; exit 1 if any, else 0.
"""
import argparse
import ast
import datetime
import importlib.util
import io
import json
import os
import posixpath
import re
import subprocess
import sys
import tokenize
from urllib.parse import unquote

SKIP_DIRS = {".git"}  # only used by the fallback walk; see walk()
CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core")


def _load_core(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(CORE, file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Shared with the shipped core/crew-config.py and scripts/docs-scan.py (#281).
secret_patterns = _load_core("secret_patterns", "secret-patterns.py")
markdown_scan = _load_core("markdown_scan", "markdown-scan.py")
path_glob = _load_core("path_glob", "path-glob.py")
PLACEHOLDER, PATTERNS, BEARER, URL_CRED = (secret_patterns.PLACEHOLDER, secret_patterns.PATTERNS,
                                           secret_patterns.BEARER, secret_patterns.URL_CRED)
is_placeholder = secret_patterns.is_placeholder
LINK_OPEN, REFDEF, FENCE_OPEN, FENCE_CLOSE = (markdown_scan.LINK_OPEN, markdown_scan.REFDEF,
                                              markdown_scan.FENCE_OPEN, markdown_scan.FENCE_CLOSE)
scan_fences, unfenced = markdown_scan.scan_fences, markdown_scan.unfenced
strip_code_spans, strip_html_comments = markdown_scan.strip_code_spans, markdown_scan.strip_html_comments
link_destinations = markdown_scan.link_destinations
glob_regex = path_glob.glob_regex
# A `crew:v1` marker, possibly wrapped over several lines; group `body` excludes
# the `<!--` / `-->` delimiters. Its `key=value` fields are whitespace-separated;
# a value is a run of non-space characters and `<...>` placeholders (which may
# contain spaces but not `<`, `>` or `=`, so a placeholder never crosses into the
# next field). A stray `<` with no closing `>` before the next `<`, `>` or `=` is
# an ordinary value character, so the value runs to the next whitespace and any
# junk tail is checked.
MARKER = re.compile(r"<!--\s*crew:v1\b(?P<body>.*?)-->", re.S)
MARKER_FIELD = re.compile(r"(?<!\S)(?P<key>[^\s=<]+)=(?P<value>(?:<[^<>=]*>|<(?![^<>=]*>)|[^\s<])*)")
PLACEHOLDER_VALUE = re.compile(r"<[^<>=]*>")
FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHORT_SHA_NAME = re.compile(r"sha7|short", re.I)


def read_lines(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    if b"\0" in data:
        return None  # binary
    return data.decode("utf-8", "replace").splitlines()


def git_paths(root, *ls_args):
    """Paths from `git ls-files -z <ls_args>` when root is the top of a git
    work tree, else None (e.g. the test temp dirs)."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

    def git(*args):
        return subprocess.run(["git", "-C", root, *args], capture_output=True, env=env, check=True).stdout

    try:
        top = git("rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
        if os.path.realpath(top) != os.path.realpath(root):
            return None
        return sorted(p for p in git("ls-files", "-z", *ls_args).decode("utf-8", "replace").split("\0") if p)
    except (OSError, subprocess.CalledProcessError):
        return None


def tracked_files(root):
    """Paths from `git ls-files` when root is the top of a git work tree, else
    None (e.g. the test temp dirs)."""
    return git_paths(root)


def walk(root):
    """Yield (full path, repo-relative path) for every file to scan: the tracked
    files in a git work tree (so a tracked `node_modules/` is scanned and an
    untracked or ignored one is not), else everything except `.git/`."""
    names = tracked_files(root)
    if names is not None:
        for rel in names:
            yield os.path.join(root, rel), rel
        return
    for dirpath, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            full = os.path.join(dirpath, name)
            yield full, os.path.relpath(full, root).replace(os.sep, "/")


def check_evidence(root, fail):
    if os.path.lexists(os.path.join(root, "evidence")):
        fail("evidence/", 1, "inline-evidence", "evidence belongs inline in the change body or signed reviews, not in the repo")


SCENARIO_DIR, SCENARIO_DOC = "docs/campaign-scenarios", "docs/campaign-harness.md"
SCENARIO_BEGIN, SCENARIO_END = "<!-- scenarios:begin", "<!-- scenarios:end -->"
SCENARIO_HEAD = ["", "| ID | Source | Spec | Sandbox |", "|---|---|---|---|"]
SCENARIO_ID = re.compile(r"A\d\d")
SCENARIO_FIELD = re.compile(r"- (Source|Spec|Driver|Sandbox): (.+)")
SCENARIO_SPEC = "[`%s.json`](../../dev/tests/scripts/fixtures/campaign/%s.json)"
SCENARIO_ROW = re.compile(r"\| \[(A\d\d)\]")


def scenario_row(root, name, fail):
    """The index row of docs/campaign-scenarios/<name>, or None after a failure. The file opens with
    `# <Axx>` and the fields `- Source:`, `- Sandbox:` and exactly one of `- Spec:` (the committed
    `<Axx>.json`, whose `id` is Axx; sandbox fresh or shared) or `- Driver:` (a driver-only scenario with
    no committed spec, linking an existing driver; sandbox n/a)."""
    rel = SCENARIO_DIR + "/" + name
    sid = name[:-3] if name.endswith(".md") else name

    def bad(n, reason):
        fail(rel, n, "scenario-index", reason)

    if not name.endswith(".md") or not SCENARIO_ID.fullmatch(sid):
        return bad(1, "not a scenario file; name it <Axx>.md")
    lines = read_lines(os.path.join(root, rel)) or []
    if lines[:2] != ["# " + sid, ""]:
        return bad(1, "start with `# %s` and a blank line" % sid)
    fields = {}
    for n, line in enumerate(lines[2:], 3):
        m = SCENARIO_FIELD.fullmatch(line)
        if not m:
            break
        if m.group(1) in fields:
            return bad(n, "second `%s:` field" % m.group(1))
        fields[m.group(1)] = m.group(2)
    if "Source" not in fields or "Sandbox" not in fields or ("Spec" in fields) == ("Driver" in fields):
        return bad(3, "needs `- Source:`, `- Sandbox:` and exactly one of `- Spec:` or `- Driver:`")
    spec = os.path.join(root, CAMPAIGN, sid + ".json")
    if "Spec" in fields:
        if fields["Spec"] != SCENARIO_SPEC % (sid, sid):
            return bad(3, "Spec must be exactly %s" % (SCENARIO_SPEC % (sid, sid)))
        try:
            with open(spec, encoding="utf-8") as f:
                spec_id = json.load(f).get("id")
        except (OSError, ValueError, AttributeError):
            return bad(3, "dangling: no readable committed spec %s/%s.json" % (CAMPAIGN, sid))
        if spec_id != sid:
            return bad(3, "dangling: %s/%s.json has id %r" % (CAMPAIGN, sid, spec_id))
        if fields["Sandbox"] not in ("fresh", "shared"):
            return bad(3, "Sandbox of a committed spec is fresh or shared")
        return "| [%s](campaign-scenarios/%s) | %s | `%s.json` | %s |" % (sid, name, fields["Source"], sid, fields["Sandbox"])
    if os.path.exists(spec):
        return bad(3, "%s/%s.json is committed; use `- Spec:`, not `- Driver:`" % (CAMPAIGN, sid))
    targets = [t for t in link_destinations(fields["Driver"]) if "://" not in t]
    if not targets or not all(os.path.isfile(os.path.join(root, SCENARIO_DIR, unquote(t.split("#")[0])))
                              for t in targets):
        return bad(3, "dangling: Driver must link an existing driver file")
    if fields["Sandbox"] != "n/a":
        return bad(3, "Sandbox of a driver-only scenario is n/a")
    return "| [%s](campaign-scenarios/%s) | %s | driver | n/a |" % (sid, name, fields["Source"])


def check_scenarios(root, fail, fix):
    """Issue #1419 (one file per campaign scenario, so neither appends nor rewrites share lines): every
    committed campaign spec <Axx>.json has its own docs/campaign-scenarios/<Axx>.md, every scenario file
    resolves its spec or driver (scenario_row), and the index between the markers of
    docs/campaign-harness.md is generated from those files, sorted by ID: `--fix` rewrites it; a missing,
    duplicate or stale row fails. Skipped when the harness doc is absent."""
    lines = read_lines(os.path.join(root, SCENARIO_DOC))
    if lines is None:
        return
    d = os.path.join(root, SCENARIO_DIR)
    names = sorted(os.listdir(d)) if os.path.isdir(d) else []
    cd = os.path.join(root, CAMPAIGN)
    for spec in sorted(os.listdir(cd)) if os.path.isdir(cd) else []:
        if SCENARIO_ID.fullmatch(spec[:-5]) and spec.endswith(".json") and spec[:-5] + ".md" not in names:
            fail("%s/%s" % (CAMPAIGN, spec), 1, "scenario-index", "missing: no %s/%s.md for this committed spec"
                 % (SCENARIO_DIR, spec[:-5]))
    rows = [r for r in (scenario_row(root, n, fail) for n in names) if r]
    want = SCENARIO_HEAD + rows + [""]
    begin = next((i for i, l in enumerate(lines) if l.startswith(SCENARIO_BEGIN)), None)
    end = next((i for i, l in enumerate(lines) if l == SCENARIO_END), None)
    if begin is None or end is None or begin > end:
        fail(SCENARIO_DOC, 1, "scenario-index", "no '%s ...' and '%s' lines around the scenario index"
             % (SCENARIO_BEGIN, SCENARIO_END))
        return
    have = lines[begin + 1:end]
    if have == want:
        return
    if fix:
        lines[begin + 1:end] = want
        with open(os.path.join(root, SCENARIO_DOC), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return
    seen = set()
    for n, line in enumerate(have, begin + 2):
        m = SCENARIO_ROW.match(line)
        if m and m.group(1) in seen:
            fail(SCENARIO_DOC, n, "scenario-index", "duplicate row for %s" % m.group(1))
        elif m and line not in rows:
            fail(SCENARIO_DOC, n, "scenario-index", "stale row for %s: not generated from %s"
                 % (m.group(1), SCENARIO_DIR))
        seen.add(m.group(1) if m else None)
    for row in rows:
        if row not in have:
            fail(SCENARIO_DOC, begin + 1, "scenario-index", "missing row for %s" % SCENARIO_ROW.match(row).group(1))
    fail(SCENARIO_DOC, begin + 1, "scenario-index",
         "scenario index is not generated from %s; run `python3 scripts/check-repo.py --fix`" % SCENARIO_DIR)


def check_secrets(root, fail):
    for full, rel in walk(root):
        lines = read_lines(full)
        if lines is None:
            continue
        for n, line in enumerate(lines, 1):
            for rule, rx, reason in PATTERNS:
                if rx.search(line):
                    fail(rel, n, rule, reason + "; use a placeholder like <token>")
            for m in BEARER.finditer(line):
                if not is_placeholder(m.group(1)):
                    fail(rel, n, "bearer-header",
                         "bearer auth header with a literal value; use <token>")
            for m in URL_CRED.finditer(line):
                if not (is_placeholder(m.group(1)) and is_placeholder(m.group(2))):
                    fail(rel, n, "url-credentials",
                         "URL with embedded credentials; use <user>:<password>")


def check_markers(root, fail):
    """Lesson 2026-10-23 (`pass=watch` marker carried a 7-char SHA): every
    `crew:v1` marker's sha= is a full 40-hex SHA or a placeholder that does not
    name a short SHA (sha7, short). Fenced examples are checked too."""
    for full, rel in walk(root):
        if not rel.endswith(".md"):
            continue
        lines = read_lines(full)
        if lines is None:
            continue
        text = "\n".join(lines)
        for marker in MARKER.finditer(text):
            for m in MARKER_FIELD.finditer(marker.group("body")):
                if m.group("key") != "sha":
                    continue
                value = m.group("value")
                n = text.count("\n", 0, marker.start("body") + m.start()) + 1
                if PLACEHOLDER_VALUE.fullmatch(value):
                    if SHORT_SHA_NAME.search(value):
                        fail(rel, n, "marker-sha",
                             "sha= placeholder names a short SHA; use <head-sha> (full 40-char head SHA)")
                elif not FULL_SHA.fullmatch(value):
                    fail(rel, n, "marker-sha",
                         "sha= must be the full 40-char head SHA, got '%s'" % value)


BLOCKER_FILES = ("docs/protocol.md", "templates/runtimes/grok-bot/synthesizer.md")
BLOCKER_PATTERNS = [
    ("hold-until", re.compile(r"hold-until")),
    ("open rereview", re.compile(r"open\s+`?steer\s+cmd=rereview`?")),
]


def check_blockers(root, fail):
    """Lesson 2026-10-29 (synthesizer squashed past an open hold-until / rereview):
    protocol §7 and the synthesizer template both still name the two blockers.
    Static presence guard only; the live PR state is not checkable offline.
    A file that is absent from the root is skipped."""
    for rel in BLOCKER_FILES:
        lines = read_lines(os.path.join(root, rel))
        if lines is None:
            continue
        text = "\n".join(lines)
        for name, pat in BLOCKER_PATTERNS:
            if not pat.search(text):
                fail(rel, 1, "synthesizer-blockers",
                     "merge-gate text must name the '%s' blocker (see docs/lessons/2026-10-29-synthesizer-hold-race.md)" % name)


VERIFICATION_DOC = "docs/verification.md"
VERIFICATION_SHAPES = ("web", "cli", "service", "api", "mobile")


def check_shapes(root, fail):
    """Issue #83 (typed verification evidence): the shape table in the
    verification doc has a row for each of web, CLI, service, API and mobile.
    A row is a table line whose first cell is the shape name. Fenced code blocks and HTML comments are
    ignored: a `<!--` inside a fence opens nothing, and an unterminated `<!--`
    hides everything after it. A doc absent from the root is skipped."""
    lines = read_lines(os.path.join(root, VERIFICATION_DOC))
    if lines is None:
        return
    # Fences first (a `<!--` in a fence is not a comment), then comments, so a
    # commented-out row is not a row; an unterminated comment runs to EOF.
    visible, _ = scan_fences(lines, unclosed_as_text=False)
    first = set()
    for _, line in strip_html_comments(visible):
        if line.lstrip().startswith("|"):
            cell = line.strip().strip("|").split("|", 1)[0]
            first.add(cell.strip().strip("*`").strip().lower())
    for shape in VERIFICATION_SHAPES:
        if shape not in first:
            fail(VERIFICATION_DOC, 1, "verification-shapes",
                 "shape table lacks a row for '%s' (see docs/lessons/2026-10-29-typed-verify-evidence.md)" % shape)


SPEC_DOC = "docs/specs/portable.md"
SPEC_SECTION = "## 5. Milestones and slices"
SPEC_STATUSES = {"open", "done", "dropped"}


def table_cells(line):
    return [c.strip() for c in line.strip().strip("|").split("|")]


def check_spec_status(root, fail):
    """Issue #259 (spec bookends): every row of every slice table in the spec's
    section 5 has a Status cell of open, done or dropped. A table is a run of
    `|` lines; its header must have a `Status` column. Fenced code blocks and
    HTML comments are ignored. A spec absent from the root is skipped."""
    lines = read_lines(os.path.join(root, SPEC_DOC))
    if lines is None:
        return
    visible, _ = scan_fences(lines, unclosed_as_text=False)
    in_section, col, tables = False, None, 0
    for n, line in strip_html_comments(visible):
        if line.startswith("## "):
            in_section = line.rstrip() == SPEC_SECTION
            col = None
            continue
        if not in_section:
            continue
        if not line.lstrip().startswith("|"):
            col = None
            continue
        cells = table_cells(line)
        if col is None:
            tables += 1
            col = cells.index("Status") if "Status" in cells else -1
            if col < 0:
                fail(SPEC_DOC, n, "spec-status", "slice table header lacks a Status column")
            continue
        if col < 0 or all(set(c) <= set("-: ") for c in cells):
            continue
        value = cells[col] if col < len(cells) else ""
        if value not in SPEC_STATUSES:
            fail(SPEC_DOC, n, "spec-status",
                 "slice row Status must be open, done or dropped, got '%s'" % value)
    if tables == 0:
        fail(SPEC_DOC, 1, "spec-status", "no slice tables under '%s'" % SPEC_SECTION)


DESIGN_ALLOW = "scripts/design-headers.txt"
DESIGN_WORDING = re.compile(r"\(design\)|\bin design\b", re.I)
DESIGN_REF = re.compile(r"(?<![\w#/])#(\d+)\b|\b((?:M|R)\d+(?:\.\d+)?)\b")


def spec_milestones(lines):
    """Map issue numbers and milestone names in the spec's section 5 to a
    milestone, and each milestone to `open` (any row open) or `closed`."""
    visible, _ = scan_fences(lines, unclosed_as_text=False)
    in_section, milestone, refs, rows = False, None, {}, {}
    for _, line in strip_html_comments(visible):
        if line.startswith("## "):
            in_section = line.rstrip() == SPEC_SECTION
            continue
        if not in_section:
            continue
        if line.startswith("### "):
            milestone = line[4:].split(":")[0].strip()
            refs.setdefault(milestone.split()[0], milestone)
            continue
        cells = table_cells(line) if milestone and line.lstrip().startswith("|") else []
        if len(cells) < 3 or cells[0] == "ID" or all(set(c) <= set("-: ") for c in cells):
            continue
        rows.setdefault(milestone, set()).add(cells[-1])
        for issue in re.findall(r"#(\d+)", cells[1]):
            refs.setdefault("#" + issue, milestone)
    status = {m: "open" if "open" in s else "closed" for m, s in rows.items()}
    return {ref: (m, status[m]) for ref, m in refs.items() if m in status}


def check_design_headers(root, fail):
    """Issue #259: a doc whose H1 says '(design)' or 'in design' names, in the
    H1 or the blockquote banner under it, an issue or milestone of the spec's
    section 5 whose milestone is still open. The first reference the spec
    knows decides. A closed milestone or no known reference (unknown status)
    fails unless the doc is listed in scripts/design-headers.txt with a
    reason; a listed doc without a design header fails too. Docs under
    changes/ and dev/ are skipped, and so is the check when the spec is absent."""
    spec = read_lines(os.path.join(root, SPEC_DOC))
    if spec is None:
        return
    known = spec_milestones(spec)
    allowed = {}
    for n, line in enumerate(read_lines(os.path.join(root, DESIGN_ALLOW)) or [], 1):
        if line.strip() and not line.startswith("#"):
            path, _, reason = line.partition("\t")
            allowed[path.strip()] = n
            if not reason.strip():
                fail(DESIGN_ALLOW, n, "design-headers", "entry '%s' needs a tab and a reason" % path.strip())
    headed = set()
    for full, rel in walk(root):
        if not rel.endswith(".md") or rel.startswith(("changes/", "dev/")):
            continue
        visible, _ = scan_fences(read_lines(full) or [], unclosed_as_text=False)
        block, n = [], None
        for i, line in visible:
            if n is None and line.startswith("# "):
                n, block = i, [line]
            elif n is not None and (line.startswith(">") or (not line.strip() and len(block) == 1)):
                block.append(line)
            elif n is not None:
                break
        if n is None or not DESIGN_WORDING.search(block[0]):
            continue
        headed.add(rel)
        if rel in allowed:
            continue
        refs = ["#" + m.group(1) if m.group(1) else m.group(2) for m in DESIGN_REF.finditer(" ".join(block))]
        hit = next((known[r] for r in refs if r in known), None)
        if hit is None:
            fail(rel, n, "design-headers", "design header names no issue or milestone of %s section 5 "
                 "(unknown status); name one or list the doc in %s" % (SPEC_DOC, DESIGN_ALLOW))
        elif hit[1] != "open":
            fail(rel, n, "design-headers", "design header names %s, closed in %s; drop the design wording "
                 "or list the doc in %s" % (hit[0], SPEC_DOC, DESIGN_ALLOW))
    for path, n in sorted(allowed.items()):
        if path not in headed:
            fail(DESIGN_ALLOW, n, "design-headers", "'%s' has no design header; drop the entry" % path)


def check_denylist(root, fail):
    """Portable spec P6 (#127): no org-internal names in mdstack. The names live
    only in a file outside the repo, one per line (`#` comments and blank lines
    ignored), named by $CREW_DENYLIST; unset means skip. Case-insensitive
    whole-word match over the scanned files. A hit names the denylist line, never
    the term, so CI logs do not leak it either."""
    path = os.environ.get("CREW_DENYLIST")
    if not path:
        print("check-repo: denylist skipped (CREW_DENYLIST unset)", file=sys.stderr)
        return
    lines = read_lines(path)
    if lines is None:
        fail("$CREW_DENYLIST", 1, "denylist", "denylist file missing or unreadable")
        return
    terms = [(n, re.compile(r"(?<!\w)%s(?!\w)" % re.escape(t.strip()), re.I))
             for n, t in enumerate(lines, 1) if t.strip() and not t.strip().startswith("#")]
    for full, rel in walk(root):
        text = read_lines(full)
        for n, line in enumerate(text or [], 1):
            for entry, rx in terms:
                if rx.search(line):
                    fail(rel, n, "denylist", "matches $CREW_DENYLIST entry on line %d; remove the internal name" % entry)


MANIFEST = "scripts/deliverables.txt"
MANIFEST_CLASSES = {"deliverable", "internal"}
MANIFEST_RUNTIMES = {"all", "grok-bot", "tmux", "session", "n/a"}


def manifest_rows(lines):
    """(line number, tab-split columns) of each manifest row; blank and `#` lines are skipped."""
    return [(n, raw.split("\t")) for n, raw in enumerate(lines, 1) if raw.strip() and not raw.startswith("#")]


def check_deliverables(root, fail):
    """Issue #235 (docs/deliverables.md inventory): every tracked path matches
    exactly one row of the manifest (`glob<TAB>class<TAB>runtime`). Only a git
    work tree has tracked paths; elsewhere the check is skipped."""
    names = tracked_files(root)
    if names is None:
        print("check-repo: deliverables skipped (not a git work tree)", file=sys.stderr)
        return
    lines = read_lines(os.path.join(root, MANIFEST))
    if lines is None:
        fail(MANIFEST, 1, "deliverables-config", "manifest missing or unreadable")
        return
    rows = []
    for n, cols in manifest_rows(lines):
        if (len(cols) not in (3, 4) or not cols[0] or cols[1] not in MANIFEST_CLASSES
                or cols[2] not in MANIFEST_RUNTIMES or any("|" in c for c in cols)):
            fail(MANIFEST, n, "deliverables-config",
                 "bad row; expected glob<TAB>deliverable|internal<TAB>all|grok-bot|tmux|session|n/a[<TAB>why, no `|`]")
            continue
        rows.append((n, glob_regex(cols[0])))
    for rel in names:
        hits = [n for n, rx in rows if rx.match(rel)]
        if not hits:
            fail(rel, 1, "unclassified", "matches no row of %s; add one at its sorted place, then run "
                 "`python3 scripts/check-repo.py --fix` (docs/deliverables.md)" % MANIFEST)
        elif len(hits) > 1:
            fail(rel, 1, "double-classified", "matches %s rows %s; keep exactly one"
                 % (MANIFEST, ", ".join(map(str, hits))))


INVENTORY_DOC = "docs/deliverables.md"
INVENTORY_BEGIN, INVENTORY_END = "<!-- inventory:begin", "<!-- inventory:end -->"
INVENTORY_HEAD = ["", "| Path | Class | Runtime(s) | Why |", "|---|---|---|---|"]
DOCS_INDEX = "docs/README.md"
INDEX_ROW = re.compile(r"\| \[[^\]]*\]\(([^)\s]+)\)")


def inventory_lines(manifest):
    """The inventory table generated from the manifest: one row per manifest row, in file order."""
    return INVENTORY_HEAD + ["| `%s` | %s | %s | %s |" % (c[0], c[1].capitalize(), c[2], c[3] if len(c) > 3 else "")
                             for _, c in manifest_rows(manifest) if len(c) in (3, 4)] + [""]


def first_unsorted(entries):
    """Line number of the first (line number, text) entry that sorts before the one above it, else None."""
    return next((n for (_, a), (n, b) in zip(entries, entries[1:]) if b < a), None)


def check_index(root, config, fail, fix):
    """Issue #325 (no shared append point): (1) the inventory table between the
    markers of docs/deliverables.md is generated from the manifest: `--fix`
    rewrites it, a stale one fails; (2) the manifest, the required-docs config,
    the dependency baseline and the docs index rows are sorted, so a new entry lands at its own place,
    not at the end where every PR appends; (3) the docs index has one row per
    doc and a row for every deliverable doc. A file absent from the root is
    skipped."""
    manifest = read_lines(os.path.join(root, MANIFEST))
    doc = read_lines(os.path.join(root, INVENTORY_DOC))
    if manifest is not None and doc is not None:
        begin = next((i for i, l in enumerate(doc) if l.startswith(INVENTORY_BEGIN)), None)
        end = next((i for i, l in enumerate(doc) if l == INVENTORY_END), None)
        if begin is None or end is None or begin > end:
            fail(INVENTORY_DOC, 1, "index-stale", "no '%s ...' and '%s' lines around the inventory table"
                 % (INVENTORY_BEGIN, INVENTORY_END))
        elif doc[begin + 1:end] != inventory_lines(manifest):
            if not fix:
                fail(INVENTORY_DOC, begin + 1, "index-stale",
                     "inventory table is not generated from %s; run `python3 scripts/check-repo.py --fix`" % MANIFEST)
            else:
                doc[begin + 1:end] = inventory_lines(manifest)
                with open(os.path.join(root, INVENTORY_DOC), "w", encoding="utf-8") as f:
                    f.write("\n".join(doc) + "\n")
    index = read_lines(os.path.join(root, DOCS_INDEX))
    rows = [(n, l) for n, l in enumerate(index or [], 1) if INDEX_ROW.match(l)]
    config_rel = os.path.relpath(config, root).replace(os.sep, "/")
    for name, entries in [
            (MANIFEST, [(n, "\t".join(c)) for n, c in manifest_rows(manifest or [])]),
            (config_rel, [(n, l) for n, l in enumerate(read_lines(config) or [], 1) if l.strip() and not l.startswith("#")]),
            (DEPS_BASELINE, [(n, "\t".join(c)) for n, c in manifest_rows(read_lines(os.path.join(root, DEPS_BASELINE)) or [])]),
            (DOCS_INDEX, rows)]:
        n = first_unsorted(entries)
        if n:
            fail(name, n, "index-order", "sorts before the line above; keep the entries sorted (bytewise, whole "
                 "line) so a new one lands at its own place")
    indexed = {}
    for n, l in rows:
        path = posixpath.normpath(posixpath.join("docs", unquote(INDEX_ROW.match(l).group(1).split("#")[0])))
        if path in indexed:
            fail(DOCS_INDEX, n, "docs-index", "second row for %s (first at line %d); keep one row per doc"
                 % (path, indexed[path]))
        indexed.setdefault(path, n)
    names = tracked_files(root)
    if names is not None and index is not None and manifest is not None:
        globs = [(glob_regex(c[0]), c[1]) for _, c in manifest_rows(manifest) if len(c) in (3, 4)]
        for rel in names:
            if (rel.startswith("docs/") and rel.endswith(".md") and rel != DOCS_INDEX and rel not in indexed
                    and {cls for rx, cls in globs if rx.match(rel)} == {"deliverable"}):
                fail(DOCS_INDEX, 1, "docs-index", "no row for the deliverable doc %s; add one at its sorted place" % rel)


FRAGMENT_DIR = "changes/unreleased"
FRAGMENT_NAME = re.compile(r"([1-9]\d*)-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
FRAGMENT_FIELDS = ("type", "issue", "pr", "date", "box-skill")
FRAGMENT_TYPES = ("added", "changed", "removed", "fixed", "security")


class FragmentError(Exception):
    def __init__(self, line, reason):
        super().__init__(reason)
        self.line, self.reason = line, reason


def fragment_field_error(key, value, issue):
    """What a bad front matter value should be, or None if it is fine."""
    if key == "type" and value not in FRAGMENT_TYPES:
        return "one of " + ", ".join(FRAGMENT_TYPES)
    if key == "issue" and value != issue:
        return issue + ", the issue in the file name"
    if key == "pr" and value != "TBD" and not re.fullmatch(r"[1-9]\d*", value):
        return "a PR number or TBD"
    if key == "date":
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError(value)
            datetime.date.fromisoformat(value)
        except ValueError:
            return "a YYYY-MM-DD date"
    return None


def parse_fragment(name, lines):
    """Issue #264: parse a CHANGELOG fragment `<issue>-<slug>.md`: front matter
    with exactly the FRAGMENT_FIELDS (`pr: TBD` until the PR exists), then one
    paragraph of entry text. Returns the fields (issue and pr as int, pr None
    for TBD) plus `body`, the stripped text lines; raises FragmentError."""
    m = FRAGMENT_NAME.fullmatch(name)
    if not m:
        raise FragmentError(1, "name must be <issue>-<slug>.md (lowercase slug)")
    end = next((i for i in range(1, len(lines)) if lines[i].rstrip() == "---"), None)
    if end is None or lines[0].rstrip() != "---":
        raise FragmentError(1, "must start with front matter between '---' lines")
    out = {}
    for n in range(1, end):
        key, sep, value = (p.strip() for p in lines[n].partition(":"))
        if not sep or key not in FRAGMENT_FIELDS or key in out or not value:
            raise FragmentError(n + 1, "expected one '<field>: <value>' line per field: " + ", ".join(FRAGMENT_FIELDS))
        want = fragment_field_error(key, value, m.group(1))
        if want:
            raise FragmentError(n + 1, "%s must be %s, got '%s'" % (key, want, value))
        out[key] = value
    missing = [k for k in FRAGMENT_FIELDS if k not in out]
    if missing:
        raise FragmentError(end + 1, "front matter lacks " + ", ".join(missing))
    body = [l.strip() for l in lines[end + 1:]]
    filled = [i for i, l in enumerate(body) if l]
    if not filled:
        raise FragmentError(end + 1, "no entry text after the front matter")
    body = body[filled[0]:filled[-1] + 1]
    if "" in body:
        raise FragmentError(end + 2 + filled[0] + body.index(""), "entry text must be one paragraph (no blank lines)")
    out.update(issue=int(out["issue"]), pr=None if out["pr"] == "TBD" else int(out["pr"]), body=body)
    return out


def check_fragments(root, fail):
    """Issue #264: every file under changes/ is a valid fragment directly in
    changes/unreleased/ (see parse_fragment)."""
    for full, rel in walk(root):
        if not rel.startswith("changes/"):
            continue
        parent, _, name = rel.rpartition("/")
        lines = read_lines(full)
        try:
            if parent != FRAGMENT_DIR:
                raise FragmentError(1, "fragments live directly in %s/" % FRAGMENT_DIR)
            parse_fragment(name, lines or [])
        except FragmentError as e:
            fail(rel, e.line, "changelog-fragment", e.reason + " (CONTRIBUTING.md#changelog)")


# scripts/, the CLI, the code modules (#1222) and the tests per module (#1224).
SCRIPT_FILE = re.compile(r"scripts/[^/]+\.py|cli/mdstack"
                         r"|(?:core|harnesses|connectors|environments)/(?:[^/]+/)*[^/]+\.py"
                         r"|dev/tests/(?:[^/]+/test-[^/]+|crew_testlib)\.py")
MAIN_BLOCK = re.compile(r"""^if __name__ == ["']__main__["']\s*:""", re.M)
USAGE_LINE = re.compile(r"^Usage:", re.M)


def script_kind(rel, text):
    """Issue #325: the docs a SCRIPT_FILE owes. `script`: run directly (a
    __main__ block) or a crew command (crew.d/<cmd>.py, no leading `_`); it
    needs a docstring with a `Usage:` line, which its --help prints. `test`:
    test-*.py. `module`: imported by other scripts. Both need a docstring."""
    name = rel.rsplit("/", 1)[1]
    if "/crew.d/" in rel:
        return "module" if name.startswith("_") else "script"
    if name.startswith("test-"):
        return "test"
    return "script" if MAIN_BLOCK.search(text) else "module"


def check_script_docs(root, fail):
    """Issue #325 (no shared usage table to conflict on): each script under
    scripts/ or a code module documents itself in its module docstring (see script_kind)."""
    for full, rel in walk(root):
        if not SCRIPT_FILE.fullmatch(rel):
            continue
        text = "\n".join(read_lines(full) or [])
        kind = script_kind(rel, text)
        try:
            doc = ast.get_docstring(ast.parse(text))
        except SyntaxError:
            doc = None
        if not doc:
            fail(rel, 1, "script-doc", "no module docstring; say what this %s does there "
                 "(scripts/README.md#per-script-docs)" % kind)
        elif kind == "script" and not USAGE_LINE.search(doc):
            fail(rel, 1, "script-doc", "module docstring has no `Usage:` line, which --help prints "
                 "(scripts/README.md#per-script-docs)")



TEST_DIR = re.compile(r"dev/tests/(?P<module>[^/]+)/test-[^/]+\.py")
TEST_MODULES = {"actions", "cli", "connectors", "core", "environments", "harnesses", "protocols", "roles", "scripts"}


def check_test_layout(root, fail):
    """Issue #1224: every test is `dev/tests/<module>/test-*.py`, named for a
    module of the team spec layout (or `scripts` for code not moved yet), and a
    test name is unique across modules: run-tests, `mdstack train` and `mdstack
    runner` find tests there by that name. A `test-*.py` inside a `fixtures/`
    directory is test input, not a test."""
    seen = {}
    for _, rel in walk(root):
        name = rel.rsplit("/", 1)[-1]
        if not (name.startswith("test-") and name.endswith(".py")) or "/fixtures/" in "/" + rel:
            continue
        m = TEST_DIR.fullmatch(rel)
        if not m or m.group("module") not in TEST_MODULES:
            fail(rel, 1, "test-layout", "tests live in dev/tests/<module>/, module one of %s (scripts/README.md)"
                 % ", ".join(sorted(TEST_MODULES)))
        elif name in seen:
            fail(rel, 1, "test-layout", "test name also used by %s; a test name is unique across modules" % seen[name])
        else:
            seen[name] = rel


# Dependency rules D1-D9 and the runtime-word lint (docs/specs/team.md §5, REQ-11, REQ-23; #1224).
DEPS_BASELINE = "scripts/deps-baseline.txt"
DEP_MODULES = ("environments/terminal", "roles", "protocols", "actions", "connectors", "environments", "harnesses",
               "core", "cli", "dev", "docs")
BINDINGS = {"connectors", "environments", "harnesses"}
MODULE_REF = re.compile(r"(?<![\w./-])(roles|protocols|actions|connectors|environments|harnesses|core|cli|dev|docs)"
                        r"/(?=[\w.<>*{}-])")
# D5: session backends, inboxes, windows and the terminal's environment variables.
TERMINAL_WORD = re.compile(r"(?<![\w-])(?:tmux|herdr|inbox(?:es)?|windows?|TMUX\w*"
                           r"|CREW_(?:BIN|BRIEF|ID|IDENTITY|INBOX|ROLE|STATE|STATUS))(?![\w-])", re.I)
# REQ-11 adds the environment's CLI: `mdstack <command>`, its deprecated name `crew <command>` (#1233) and `$CREW_BIN`.
CLI_WORD = re.compile(r"(?<![\w/.-])(?:mdstack|crew) (?:[a-z][a-z-]+)\b|\$CREW_BIN\b")
# D6: the tool of record's CLI or API.
TOOL_WORD = re.compile(r"""["'`]gh["'`]|(?<![\w/.-])gh (?:api|auth|issue|label|pr|release|repo|run|search|workflow)\b"""
                       r"|api\.github\.com")
# D7: harness launch flags, hooks and trust settings.
HARNESS_WORD = re.compile(r"--(?:add-dir|approve|dangerously-[\w-]+|permission-mode|reasoning-effort|thinking|yolo)\b"
                          r"|\b(?:bypassPermissions|hasTrustDialogAccepted|skipDangerousModePermissionPrompt"
                          r"|trust_level)\b")


def dep_module(rel):
    return next((m for m in DEP_MODULES if rel.startswith(m + "/")), None)


PATH_LITERAL = re.compile(r"(?:include:)?(roles|protocols|actions|connectors|environments|harnesses|core|cli|dev|docs)"
                          r"/[\w./<>*{}-]*")


MODULE_NAMES = {"roles", "protocols", "actions", "connectors", "environments", "harnesses", "core", "cli", "dev", "docs"}
JOIN_CALLS = {"join", "joinpath", "Path", "PurePath", "PurePosixPath"}


def joined_module(value):
    """The top module a path segment passed to a join names, or None."""
    m = PATH_LITERAL.fullmatch(value)
    return m.group(1) if m else value if value in MODULE_NAMES else None


def python_view(text):
    """A Python file's (lines, module refs): the lines with comments and
    docstrings blanked, and (line, top module) for each reference: a string
    literal that is a whole repo path, an import of a module package
    (`from connectors.github import x`), or a module name or path joined into
    a path (`ROOT / "harnesses"`, `os.path.join(ROOT, "core", ...)`). A doc
    pointer in prose or a message is not a dependency."""
    lines = text.split("\n")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return lines, []
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and body and \
                isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and \
                isinstance(body[0].value.value, str):
            docs.add(id(body[0].value))
            for n in range(body[0].lineno - 1, body[0].end_lineno):
                lines[n] = ""
    refs = [(node.lineno, m.group(1)) for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs
            for m in [PATH_LITERAL.fullmatch(node.value)] if m]
    for node in ast.walk(tree):
        names, parts = [], []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            names = [node.module]
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            parts = [node.left, node.right]
        elif isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", None)) in JOIN_CALLS:
            parts = node.args
        refs += [(node.lineno, n.split(".")[0]) for n in names if n.split(".")[0] in MODULE_NAMES]
        refs += [(node.lineno, top) for part in parts
                 if isinstance(part, ast.Constant) and isinstance(part.value, str)
                 for top in [joined_module(part.value)] if top]
    refs.sort()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                n, col = tok.start
                lines[n - 1] = lines[n - 1][:col]
    except (tokenize.TokenError, IndentationError):
        pass
    return lines, refs


def dep_rules(module):
    """(rule, test on the referenced top-level module or None, word regex or None) applying to a module."""
    top = module.split("/")[0]
    rules = []
    if top == "roles":
        rules.append(("D1", lambda t: t not in ("roles", "protocols", "actions"), None))
    if top == "protocols":
        rules.append(("D2", lambda t: t not in ("protocols", "actions"), None))
    if top in BINDINGS:
        rules.append(("D3", lambda t: t in BINDINGS and t != top, None))
    if top == "core":
        rules.append(("D4", lambda t: t not in ("core", "docs"), None))
    if top == "cli":
        rules.append(("D8", lambda t: t in BINDINGS | {"roles", "protocols"}, None))
    if top not in ("docs", "dev"):
        rules.append(("D9", lambda t: t == "docs", None))
        if top in ("roles", "protocols"):
            rules.append(("runtime-word", None, TERMINAL_WORD))
            rules.append(("runtime-word", None, CLI_WORD))
        elif module != "environments/terminal":
            rules.append(("D5", None, TERMINAL_WORD))
        if top != "connectors":
            rules.append(("D6", None, TOOL_WORD))
        if top != "harnesses":
            rules.append(("D7", None, HARNESS_WORD))
    return rules


def is_python(rel, text):
    return rel.endswith(".py") or text.startswith("#!/usr/bin/env python")


def check_deps(root, fail):
    """Each file in a module of the team spec layout breaks no dependency rule
    (D1-D9) and, under roles/ and protocols/, names no runtime word; matches
    in Python comments and docstrings do not count. A (file, rule) pair listed
    in scripts/deps-baseline.txt is a known coupling and passes; a row that no
    longer matches fails, so the baseline only shrinks."""
    found = {}
    for full, rel in walk(root):
        module = dep_module(rel)
        if module is None or module in ("docs", "dev"):
            continue
        text = "\n".join(read_lines(full) or [])
        if is_python(rel, text):
            lines, refs = python_view(text)
        else:
            # A TOML comment is prose, like a Python comment.
            lines = [("" if rel.endswith(".toml") and line.lstrip().startswith("#") else line)
                     for line in text.split("\n")]
            refs = [(n, m.group(1)) for n, line in enumerate(lines, 1) for m in MODULE_REF.finditer(line)]
        for rule, refers, words in dep_rules(module):
            hit = next(((n, top + "/") for n, top in refs if refers(top)), None) if refers else \
                next(((n, m.group(0)) for n, line in enumerate(lines, 1) for m in [words.search(line)] if m), None)
            if hit and (rule, rel) not in found:
                found[(rule, rel)] = hit
    baseline = {}
    for n, cols in manifest_rows(read_lines(os.path.join(root, DEPS_BASELINE)) or []):
        if len(cols) != 3 or not cols[2]:
            fail(DEPS_BASELINE, n, "deps-baseline", "bad row; expected path<TAB>rule<TAB>why")
            continue
        baseline[(cols[1], cols[0])] = n
    for (rule, rel), (n, what) in sorted(found.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if (rule, rel) not in baseline:
            fail(rel, n, "deps", "%s: %s (docs/specs/team.md#5-dependency-rules)" % (rule, what[:80]))
    for key, n in sorted(baseline.items(), key=lambda kv: kv[1]):
        if key not in found:
            fail(DEPS_BASELINE, n, "deps-baseline", "%s no longer breaks %s; remove the row" % (key[1], key[0]))


def parse_config(path, fail):
    """Lines: `path` (file must exist) or `path :: ## Heading` (heading line
    must exist, exact text). `#` at line start and blank lines are ignored."""
    files, sections = [], []
    lines = read_lines(path)
    if lines is None:
        fail(os.path.basename(path), 1, "config", "required-docs config missing or unreadable")
        return files, sections
    rel = os.path.basename(path)
    for n, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "::" in line:
            doc, _, heading = (p.strip() for p in line.partition("::"))
            if not doc or not re.match(r"#{1,6} \S", heading):
                fail(rel, n, "config", "bad section line; expected `path :: ## Heading`")
                continue
            sections.append((n, doc, heading))
        else:
            files.append((n, line))
    return files, sections


def check_docs(root, config, fail):
    cfg_rel = os.path.relpath(config, root).replace(os.sep, "/")
    quiet = lambda f, n, r, why: fail(cfg_rel, n, r, why)
    files, sections = parse_config(config, quiet)
    for n, doc in files:
        if not os.path.isfile(os.path.join(root, doc)):
            fail(cfg_rel, n, "missing-file", "required file not found: " + doc)
    for n, doc, heading in sections:
        lines = read_lines(os.path.join(root, doc))
        if lines is None:
            fail(cfg_rel, n, "missing-file", "required file not found: " + doc)
            continue
        # Fail closed: an unclosed fence hides its heading-like lines (CommonMark)
        visible, unclosed = scan_fences(lines, unclosed_as_text=False)
        if not any(line.rstrip() == heading for _, line in strip_html_comments(visible)):
            hint = "" if unclosed is None else " (unclosed code fence at %s:%d)" % (doc, unclosed)
            fail(cfg_rel, n, "missing-section", "%s lacks required section '%s'%s" % (doc, heading, hint))


def check_links(root, fail):
    root_real = os.path.realpath(root)
    for full, rel in walk(root):
        if not rel.endswith(".md"):
            continue
        lines = read_lines(full)
        if lines is None:
            continue
        for n, line in unfenced(lines):
            text = strip_code_spans(line)
            targets = link_destinations(text)
            ref = REFDEF.match(text)
            if ref:
                targets.append(ref.group(1) if ref.group(1) is not None else ref.group(2))
            for t in targets:
                if re.match(r"^([a-z][a-z0-9+.-]*:|//|#)", t, re.I) or PLACEHOLDER.search(t):
                    continue  # external, fragment-only, or documented placeholder
                path = unquote(re.split(r"[#?]", t, maxsplit=1)[0])
                if not path:
                    continue
                if "\0" in path:
                    fail(rel, n, "broken-link", "relative link does not resolve: " + t)
                    continue
                base = root if path.startswith("/") else os.path.dirname(full)
                dest = os.path.realpath(os.path.join(base, path.lstrip("/")))
                inside = dest == root_real or dest.startswith(root_real + os.sep)
                if not inside:
                    fail(rel, n, "broken-link", "link escapes the repo: " + t)
                elif not os.path.exists(dest):
                    fail(rel, n, "broken-link", "relative link does not resolve: " + t)


def check_markdown(root, fail):
    """Issue #644: markdownlint parity without the binary (check-markdown.py);
    CI's markdownlint stays the authority."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-markdown.py")
    spec = importlib.util.spec_from_file_location("check_markdown", path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    for full, rel in walk(root):
        if rel.endswith(".md"):
            for n, rule, msg in md.lint_file(full) or []:
                fail(rel, n, "markdown", "%s %s" % (rule, msg))


def check_memory(root, fail):
    """Issue #1230: core memory under memory/ keeps its layout and size
    limits and holds no personal data (core/crew-memory.py, docs/memory.md)."""
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "core", "crew-memory.py")
    spec = importlib.util.spec_from_file_location("crew_memory", path)
    memory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memory)
    for rel, n, rule, reason in memory.lint(root):
        fail(rel, n, rule, reason)


EVENT_TYPE = re.compile(r"^\|[^|]*\| `([\w.-]+)` \|$")


def check_routines(root, fail):
    """Issue #1247: every role routine, roles/<team>/<role>/routines/*.toml,
    passes core/crew-routines.py and names only actions and event types of
    the actions contract (actions/contract.py, actions/README.md#events)."""
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mods = []
    for name, rel in (("crew_routines", "core/crew-routines.py"), ("actions_contract", "actions/contract.py")):
        spec = importlib.util.spec_from_file_location(name, os.path.join(here, rel))
        mods.append(importlib.util.module_from_spec(spec))
        spec.loader.exec_module(mods[-1])
    routines, contract = mods
    events = {m.group(1) for line in read_lines(os.path.join(root, "actions", "README.md")) or []
              for m in [EVENT_TYPE.match(line)] if m}
    _, problems = routines.load(os.path.join(root, "roles"), set(contract.ACTIONS), events)
    for rel, key, reason in problems:
        fail(rel, 1, "routines", "%s: %s (docs/routines.md)" % (key, reason))


CAMPAIGN = "dev/tests/scripts/fixtures/campaign"


def check_campaign(root, fail):
    """Issue #1412: every committed campaign step fails closed on an assertion and
    every required case at the merge base with origin/main is kept, given a
    disposition or retired with a reason (scripts/campaign-lint.py). A missing
    scenario directory is still compared with the base."""
    d = os.path.join(root, CAMPAIGN)
    base = subprocess.run(["git", "-C", root, "rev-parse", "--verify", "-q", "origin/main"], capture_output=True)
    if not os.path.isdir(d) and base.returncode:
        return  # no scenarios and no base to have deleted them from: not a campaign checkout
    spec = importlib.util.spec_from_file_location(
        "campaign_lint", os.path.join(os.path.dirname(os.path.abspath(__file__)), "campaign-lint.py"))
    lint = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lint)
    try:
        problems = lint.check(d, "origin/main", root)
    except (ValueError, subprocess.CalledProcessError) as e:
        problems = ["cannot check retained cases: %s" % e]
    for p in problems:
        fail(CAMPAIGN, 1, "campaign", p)


def main(argv=None):
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=os.path.dirname(here), help="repo root (default: parent of scripts/)")
    ap.add_argument("--config", help="required-docs config (default: <script dir>/required-docs.txt)")
    ap.add_argument("--only", action="append", choices=["secrets", "docs", "links", "markers", "blockers", "shapes", "denylist", "deliverables", "spec-status", "design-headers", "fragments", "script-docs", "index", "evidence", "scenarios", "markdown", "test-layout", "deps", "memory", "routines", "campaign"],
                    help="run only these checks (repeatable)")
    ap.add_argument("--fix", action="store_true", help="rewrite the generated inventory table (index check) and scenario index (scenarios check) in place")
    args = ap.parse_args(argv)
    root = os.path.abspath(args.root)
    config = os.path.abspath(args.config or os.path.join(here, "required-docs.txt"))
    checks = set(args.only or ["secrets", "docs", "links", "markers", "blockers", "shapes", "denylist", "deliverables", "spec-status", "design-headers", "fragments", "script-docs", "index", "evidence", "scenarios", "markdown", "test-layout", "deps", "memory", "routines", "campaign"])

    failures = []

    def fail(path, line, rule, reason):
        failures.append("%s:%d: [%s] %s" % (path, line, rule, reason))

    if "secrets" in checks:
        check_secrets(root, fail)
    if "evidence" in checks:
        check_evidence(root, fail)
    if "docs" in checks:
        check_docs(root, config, fail)
    if "links" in checks:
        check_links(root, fail)
    if "markers" in checks:
        check_markers(root, fail)
    if "blockers" in checks:
        check_blockers(root, fail)
    if "shapes" in checks:
        check_shapes(root, fail)
    if "denylist" in checks:
        check_denylist(root, fail)
    if "deliverables" in checks:
        check_deliverables(root, fail)
    if "spec-status" in checks:
        check_spec_status(root, fail)
    if "design-headers" in checks:
        check_design_headers(root, fail)
    if "fragments" in checks:
        check_fragments(root, fail)
    if "script-docs" in checks:
        check_script_docs(root, fail)
    if "index" in checks:
        check_index(root, config, fail, args.fix)
    if "scenarios" in checks:
        check_scenarios(root, fail, args.fix)
    if "markdown" in checks:
        check_markdown(root, fail)
    if "test-layout" in checks:
        check_test_layout(root, fail)
    if "deps" in checks:
        check_deps(root, fail)
    if "memory" in checks:
        check_memory(root, fail)
    if "routines" in checks:
        check_routines(root, fail)
    if "campaign" in checks:
        check_campaign(root, fail)

    untracked = git_paths(root, "--others", "--exclude-standard")
    if untracked:
        print("check-repo: warning: %d untracked file%s not checked (path checks read `git ls-files`; "
              "`git add` new files before claiming a pass): %s"
              % (len(untracked), "" if len(untracked) == 1 else "s", ", ".join(untracked)), file=sys.stderr)
    for f in failures:
        print(f)
    if failures:
        print("check-repo: FAILED (%d problem%s)" % (len(failures), "" if len(failures) == 1 else "s"),
              file=sys.stderr)
        return 1
    print("check-repo: OK (%s)" % ", ".join(sorted(checks)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
