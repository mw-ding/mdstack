#!/usr/bin/env python3
"""Tests for check-repo.py. Python 3 stdlib only, no network.

Bad secret fixtures are stored defanged (a `~~` marker splits each token) so
the repo never contains a matching string; this runner strips the marker into a
temp dir and expects check-repo.py to fail with `file:3: [<rule>]`, where
<rule> is named on the fixture's `# expect:` line. Structural checks (missing
file/section, broken link) are built in temp dirs so no extra .md fixtures
exist for markdownlint/lychee to see.

Covers: bad fixtures per pattern, a good fixture,
fence/link/section/file-selection cases, denylist hit/miss/unset with a temp
denylist, deliverables match/unclassified/double match/bad row/missing manifest
in temp git repos and the current tree, spec-status valid/empty/unknown/missing
cell/no Status column/fenced/no tables and the current tree, design-headers
open/closed/unknown/allowlisted/stale allowlist and the current tree (#259), fragments
valid/`pr: TBD`/each malformed case with its line and the current tree,
script-docs (#325) each kind with and without its docstring or `Usage:` line,
an unparsable file and the current tree, `--help` printing the `Usage:` line
of every script in the current tree, two branches that each add a script
with its docs merging with no conflict (with a shared-table control that
conflicts), and index files (#325): the generated inventory table stale, fixed
by --fix, hand-edited or unmarked, an unsorted manifest, required-docs config
and docs index, a duplicate or missing docs index row, the manifest's why
column, the current tree, and two branches that each add a script, a doc and
their index rows merging with no conflict (with an appended-at-the-end control
that conflicts), and union merge attributes (#1112): present, missing, commented
out, skipped when the doc is absent, the current tree, and two branches that
each append a scenario line at the same place merging with both lines kept,
and core memory (#1230): clean, personal data, a stray file and the current tree,
and role routines (#1247): the contract's vocabulary, an action and event outside it, and the current tree,
and campaign scenarios (#1412): no origin/main, kept cases, an unhandled assertion and a deleted case, a deleted scenario directory, and the current tree,
and untracked files (#1414): a non-ignored one named as a warning, an ignored one quiet, and checked after `git add`.
and the lessons index (#1929, M60 X1): rows X1.1-X1.8 (each metadata key missing, empty, wrong or duplicate,
no or unclosed front matter, an unknown key, `mixed` misuse, stale, hand-edited, duplicated or out-of-order rows,
a pending file, bad markers, the migrated tree, and two same-base lesson PRs squash-landing with no conflict).
Run in CI.
"""
import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
CHECK = os.path.join(SCRIPTS, "check-repo.py")
FIX = os.path.join(TESTS, "scripts", "fixtures")
failed = []


def run(root, *extra):
    p = subprocess.run([sys.executable, CHECK, "--root", root, *extra],
                       capture_output=True, text=True)
    return p.returncode, p.stdout


def expect(name, ok, detail=""):
    print("%s %s" % ("ok  " if ok else "FAIL", name))
    if not ok:
        failed.append(name)
        print("     " + detail.replace("\n", "\n     "))


def assembled(src, dst_dir):
    with open(src, encoding="utf-8") as f:
        text = f.read().replace("~~", "")
    dst = os.path.join(dst_dir, os.path.basename(src))
    with open(dst, "w", encoding="utf-8") as f:
        f.write(text)
    return os.path.basename(src)


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


for name in sorted(os.listdir(os.path.join(FIX, "bad"))):
    src = os.path.join(FIX, "bad", name)
    rule = next(l.split(":", 1)[1].strip() for l in open(src) if l.startswith("# expect:"))
    with tempfile.TemporaryDirectory() as d:
        rel = assembled(src, d)
        rc, out = run(d, "--only", "secrets")
        want = "%s:3: [%s]" % (rel, rule)
        expect("bad/" + name + " fails with " + want, rc == 1 and want in out, out)

with tempfile.TemporaryDirectory() as d:
    for name in sorted(os.listdir(os.path.join(FIX, "good"))):
        assembled(os.path.join(FIX, "good", name), d)
    rc, out = run(d, "--only", "secrets")
    expect("good fixtures pass", rc == 0 and out.startswith("check-repo: OK"), out)

CFG = "R.md\nR.md :: ## Need\n"
with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n## Need\n\n[ok](other/x.md#frag) [web](https://example.invalid/x)\n")
    write(d, "other/x.md", "# X\n")
    rc, out = run(d, "--config", os.path.join(d, "cfg.txt"))
    expect("good tree passes", rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n## Need\n")
    os.remove(os.path.join(d, "R.md"))
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("missing file fails", rc == 1 and "cfg.txt:1: [missing-file]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n```\n## Need\n```\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("missing section fails (fenced heading ignored)",
           rc == 1 and "cfg.txt:2: [missing-section]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\nok\n\nsee [gone](missing.md) and `[code](nope.md)`\n\n```\n[fenced](nope.md)\n```\n")
    rc, out = run(d, "--only", "links")
    expect("broken link fails with file:line",
           rc == 1 and "R.md:5: [broken-link]" in out and out.count("broken-link") == 1, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "[up](../outside.md)\n")
    rc, out = run(d, "--only", "links")
    expect("link escaping repo fails", rc == 1 and "R.md:1: [broken-link]" in out, out)

# Fence handling (CommonMark): a fence closes only on the same character, at
# least as long as the opener, with nothing but whitespace after it.
with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\n```md\n~~~\n```\n\n[broken](missing.md)\n")
    rc, out = run(d, "--only", "links")
    expect("mixed fences: ~~~ inside ``` does not close it",
           rc == 1 and "R.md:7: [broken-link]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\n````md\n```\n[inside](nope.md)\n```\n````\n\n[broken](missing.md)\n")
    rc, out = run(d, "--only", "links")
    expect("longer opener: ``` lines inside ```` stay fenced",
           rc == 1 and "R.md:9: [broken-link]" in out and out.count("broken-link") == 1, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\n~~~\n```\n~~~ not a closer\n[inside](nope.md)\n  ~~~~  \n\n[broken](missing.md)\n")
    rc, out = run(d, "--only", "links")
    expect("closer needs same char, >= length, only whitespace after",
           rc == 1 and "R.md:9: [broken-link]" in out and out.count("broken-link") == 1, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n```md\n~~~\n## Need\n```\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("heading inside a mixed fence does not satisfy a section",
           rc == 1 and "cfg.txt:2: [missing-section]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n````\n```\n## Need\n```\n````\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("heading inside a longer fence does not satisfy a section",
           rc == 1 and "cfg.txt:2: [missing-section]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n```\ncode\n```\n\n## Need\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("heading after a closed fence satisfies a section", rc == 0, out)

# Link destinations: URL-decoding and balanced parentheses.
with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "[x](other%20file.md) [y](other(v1).md) [z](<other file.md>)\n")
    write(d, "other file.md", "# O\n")
    write(d, "other(v1).md", "# O\n")
    rc, out = run(d, "--only", "links")
    expect("%20 and (parenthesized) destinations resolve", rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "[x](gone%20file.md) [y](gone(v1).md) [z](bad%00.md)\n")
    rc, out = run(d, "--only", "links")
    expect("missing decoded/parenthesized destinations fail",
           rc == 1 and out.count("R.md:1: [broken-link]") == 3, out)

# Fences opened on list-item / block-quote lines (round-2 finding): the content
# indent is recognised, so the indented closer does not open a new fence.
LIST_FENCE = "- ```sh\n  echo hi\n  ```\n\nSee [c](missing.md).\n"
for label, body in [
    ("dash list item", LIST_FENCE),
    ("star list item", LIST_FENCE.replace("- ```", "* ```", 1)),
    ("plus list item", LIST_FENCE.replace("- ```", "+ ```", 1)),
    ("1. list item", "1. ```sh\n   echo hi\n   ```\n\nSee [c](missing.md).\n"),
    ("1) list item", "1) ```sh\n   echo hi\n   ```\n\nSee [c](missing.md).\n"),
    ("nested list item", "- a\n  - ```sh\n    echo hi\n    ```\n\nSee [c](missing.md).\n"),
    ("block quote", "> ```sh\n> echo hi\n> ```\n\nSee [c](missing.md).\n"),
    ("quoted list item", "> - ```sh\n>   echo hi\n>   ```\n\nSee [c](missing.md).\n"),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "R.md", body)
        rc, out = run(d, "--only", "links")
        expect("fence after " + label + " does not hide a broken link",
               rc == 1 and out.count("[broken-link]") == 1 and "R.md:" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "- ```sh\n  [inside](nope.md)\n  ```\n")
    rc, out = run(d, "--only", "links")
    expect("link inside a list-item fence is skipped", rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n- ```sh\n  echo hi\n  ```\n\n## Need\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("heading after a list-item fence satisfies a section", rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n- ```sh\n  ## Need\n  ```\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("heading inside a list-item fence does not satisfy a section",
           rc == 1 and "cfg.txt:2: [missing-section]" in out, out)

# Safety rule: an unclosed fence is plain text for the link check, so a stray
# fence line (e.g. the closer of a fence the scanner did not recognise) cannot
# hide the rest of the file. The section check stays CommonMark (fail closed)
# and says why.
with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\nintro\n\n```\n\nSee [c](missing.md).\n")
    rc, out = run(d, "--only", "links")
    expect("unclosed bare fence does not hide a broken link",
           rc == 1 and "R.md:7: [broken-link]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "# R\n\n```sh\necho hi\n\nSee [c](missing.md).\n")
    rc, out = run(d, "--only", "links")
    expect("unclosed fence with an info string does not hide a broken link",
           rc == 1 and "R.md:6: [broken-link]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "cfg.txt", CFG)
    write(d, "R.md", "# R\n\n```\n\n## Need\n")
    rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
    expect("unclosed fence: section stays unsatisfied and the report names the fence",
           rc == 1 and "[missing-section]" in out and "unclosed code fence at R.md:3" in out, out)

# Inline code spans: matched by backtick-run length; escaped backticks are literal.
for label, body, want in [
    ("escaped backticks are not a span", "Use \\` [broken](missing.md) \\` here.\n", 1),
    ("unmatched backtick is literal", "A ` stray [broken](missing.md) here.\n", 1),
    ("double-backtick span hides its link", "Use `` a ` [x](missing.md) `` here.\n", 0),
    ("single-backtick span hides its link", "Use `[x](missing.md)` here.\n", 0),
    ("span then real link", "`a` [x](missing.md) `b`\n", 1),
    ("run-length mismatch is not a span", "``[x](missing.md)` and [y](missing.md)\n", 2),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "R.md", body)
        rc, out = run(d, "--only", "links")
        expect("code span: " + label, out.count("[broken-link]") == want and rc == (1 if want else 0), out)

# HTML comments do not satisfy a required heading.
for label, body, ok in [
    ("multi-line comment", "# R\n\n<!--\n## Need\n-->\n", False),
    ("single-line comment", "# R\n\n<!-- ## Need -->\n", False),
    ("unclosed comment", "# R\n\n<!--\n## Need\n", False),
    ("heading after a closed comment", "# R\n\n<!--\nx\n-->\n\n## Need\n", True),
    ("comment marker inside a fence is text", "# R\n\n```\n<!--\n```\n\n## Need\n", True),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "cfg.txt", CFG)
        write(d, "R.md", body)
        rc, out = run(d, "--only", "docs", "--config", os.path.join(d, "cfg.txt"))
        expect("html comment: " + label,
               rc == 0 if ok else (rc == 1 and "cfg.txt:2: [missing-section]" in out), out)

# Reference definitions share the inline <dest> handling.
with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", '[ref]: <other file.md> "t"\n[ref2]: other%20file.md\n[ref3]: <>\n')
    write(d, "other file.md", "# O\n")
    rc, out = run(d, "--only", "links")
    expect("refdef <dest> with spaces resolves", rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", '[ref]: <gone file.md> "t"\n')
    rc, out = run(d, "--only", "links")
    expect("missing refdef <dest> with spaces fails whole",
           rc == 1 and "R.md:1: [broken-link]" in out and "gone file.md" in out, out)

# Marker SHA rule (lesson: the `pass=watch` marker carried a 7-char SHA, #69):
# every `crew:v1` marker's sha= is a full 40-hex SHA or a non-short placeholder.
FULL = "0123456789abcdef0123456789abcdef01234567"
for label, body, want in [
    ("7-char hex sha fails", "# R\n\n<!-- crew:v1 role=builder pass=watch pr=1 sha=0123abc round=n/a -->\n", 1),
    ("39-char hex sha fails", "<!-- crew:v1 pass=watch sha=" + FULL[:39] + " -->\n", 1),
    ("41-char hex sha fails", "<!-- crew:v1 pass=watch sha=" + FULL + "0 -->\n", 1),
    ("<sha7> placeholder fails", "<!-- crew:v1 pass=watch sha=<sha7> round=n/a -->\n", 1),
    ("<short-sha> placeholder fails", "<!-- crew:v1 pass=watch sha=<short-sha> -->\n", 1),
    ("40-hex sha passes", "<!-- crew:v1 pass=watch sha=" + FULL + " round=n/a -->\n", 0),
    ("<head-sha> placeholder passes", "<!-- crew:v1 pass=ack sha=<head-sha> round=n/a -->\n", 0),
    ("<new-head-sha> placeholder passes", "<!-- crew:v1 pass=verdict sha=<new-head-sha> -->\n", 0),
    ("<full-40-char-head-sha> placeholder passes", "<!-- crew:v1 pass=hold sha=<full-40-char-head-sha> -->\n", 0),
    ("wrapped <40-char head sha> placeholder passes", "<!-- crew:v1 role=<role> sha=<40-char\nhead sha> round=<k> -->\n", 0),
    ("short sha on a wrapped marker fails with its own line", "<!-- crew:v1 role=builder\n  pass=watch sha=abc1234\n  round=n/a -->\n", 1),
    ("marker inside a fence is still checked", "```md\n<!-- crew:v1 pass=watch sha=abc1234 -->\n```\n", 1),
    ("40-hex sha with no space before --> passes", "<!-- crew:v1 pass=watch sha=" + FULL + "-->\n", 0),
    ("short sha with no space before --> fails", "<!-- crew:v1 pass=watch sha=abc1234-->\n", 1),
    ("placeholder followed by trailing chars fails", "<!-- crew:v1 pass=watch sha=<head-sha>abc1234 -->\n", 1),
    ("full sha followed by unclosed < fails", "<!-- crew:v1 pass=watch sha=" + FULL + "<junk -->\n", 1),
    ("placeholder followed by unclosed < fails", "<!-- crew:v1 pass=watch sha=<head-sha><junk -->\n", 1),
    ("unclosed placeholder earlier in marker does not hide short sha", "<!-- crew:v1 pass=watch pr=<n sha=abc1234 round=<k> -->\n", 1),
    ("closed placeholder earlier in marker still checks short sha", "<!-- crew:v1 pass=watch pr=<n> sha=abc1234 round=<k> -->\n", 1),
    ("previous-sha= short value is not the sha", "<!-- crew:v1 pass=watch previous-sha=abc1234 sha=" + FULL + " -->\n", 0),
    ("only previous-sha= is not reported as sha", "<!-- crew:v1 pass=watch previous-sha=abc1234 -->\n", 0),
    ("non-marker comment is ignored", "<!-- note sha=abc1234 -->\n", 0),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "R.md", body)
        rc, out = run(d, "--only", "markers")
        expect("marker sha: " + label, out.count("[marker-sha]") == want and rc == (1 if want else 0), out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "<!-- crew:v1 role=builder\n  pass=watch sha=abc1234\n  round=n/a -->\n")
    rc, out = run(d, "--only", "markers")
    expect("marker sha: failure reports file:line of the sha=", "R.md:2: [marker-sha]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "<!-- crew:v1 pass=watch sha=abc1234 -->\n")
    rc, out = run(d)
    expect("marker sha: runs by default", rc == 1 and "[marker-sha]" in out, out)

# Synthesizer blockers: protocol and template must name hold-until and an open
# rereview; a file absent from the root is skipped.
GOOD = "A hold-until-X blocks. An open `steer cmd=rereview` at head blocks.\n"
for label, files, want in [
    ("both files name both blockers", {"docs/protocol.md": GOOD, "templates/runtimes/grok-bot/synthesizer.md": GOOD}, 0),
    ("template missing hold-until", {"docs/protocol.md": GOOD, "templates/runtimes/grok-bot/synthesizer.md": "open steer cmd=rereview\n"}, 1),
    ("protocol missing open rereview", {"docs/protocol.md": "hold-until\nsteer cmd=rereview\n", "templates/runtimes/grok-bot/synthesizer.md": GOOD}, 1),
    ("neither file present is skipped", {"R.md": "x\n"}, 0),
]:
    with tempfile.TemporaryDirectory() as d:
        for rel, body in files.items():
            write(d, rel, body)
        rc, out = run(d, "--only", "blockers")
        expect("blockers: " + label, out.count("[synthesizer-blockers]") == want and rc == (1 if want else 0), out)

# Verification shapes: the table in docs/verification.md has all five rows.
def shape_table(shapes):
    return "| Shape | Required when |\n|---|---|\n" + "".join("| %s | x |\n" % s for s in shapes)


ALL_SHAPES = ["Web", "CLI", "Service", "API", "Mobile"]
for label, files, want in [
    ("all five shapes present", {"docs/verification.md": shape_table(ALL_SHAPES)}, 0),
    ("mobile row missing", {"docs/verification.md": shape_table(ALL_SHAPES[:-1])}, 1),
    ("two rows missing", {"docs/verification.md": shape_table(["Web", "CLI", "API"])}, 2),
    ("shape only in prose does not count", {"docs/verification.md": shape_table(ALL_SHAPES[:-1]) + "\nMobile is TBD.\n"}, 1),
    ("commented-out row does not count", {"docs/verification.md": shape_table(ALL_SHAPES[:-1]) + "<!-- | Mobile | x |\n-->\n"}, 1),
    ("single-line commented row does not count", {"docs/verification.md": shape_table(ALL_SHAPES[:-1]) + "<!-- | Mobile | x | -->\n"}, 1),
    ("unterminated comment hides the row after it", {"docs/verification.md": shape_table(ALL_SHAPES[:-1]) + "<!--\n| Mobile | x |\n"}, 1),
    ("comment opener inside a fence is not a comment",
     {"docs/verification.md": "```\n<!--\n```\n" + shape_table(ALL_SHAPES) + "<!-- note -->\n"}, 0),
    ("doc absent is skipped", {"R.md": "x\n"}, 0),
]:
    with tempfile.TemporaryDirectory() as d:
        for rel, body in files.items():
            write(d, rel, body)
        rc, out = run(d, "--only", "shapes")
        expect("shapes: " + label, out.count("[verification-shapes]") == want and rc == (1 if want else 0), out)

# Spec status (#259): every slice row in portable.md section 5 has a Status cell.
SPEC_HEAD = "# Spec\n\n## 5. Milestones and slices\n\n### M1\n\n"
SPEC_TAIL = "\n## 6. Decisions\n\n| Date | Decision |\n|---|---|\n| d | x |\n"


def slice_table(*statuses, header="| ID | Issue | Status |"):
    return header + "\n|---|---|---|\n" + "".join("| 1.%d | #%d | %s |\n" % (i, i, s) for i, s in enumerate(statuses))


for label, body, want in [
    ("all statuses valid", SPEC_HEAD + slice_table("open", "done", "dropped") + SPEC_TAIL, 0),
    ("empty status fails", SPEC_HEAD + slice_table("done", "") + SPEC_TAIL, 1),
    ("unknown status fails", SPEC_HEAD + slice_table("closed", "wip") + SPEC_TAIL, 2),
    ("missing cell fails", SPEC_HEAD + slice_table("done") + "| 1.9 | #9 |\n" + SPEC_TAIL, 1),
    ("header without Status fails", SPEC_HEAD + slice_table("done", header="| ID | Issue | Scope |") + SPEC_TAIL, 1),
    ("second table is checked too", SPEC_HEAD + slice_table("done") + "\n### M2\n\n" + slice_table("todo") + SPEC_TAIL, 1),
    ("tables outside section 5 are ignored", "# Spec\n\n## 4. Layout\n\n| Path | X |\n|---|---|\n| a | b |\n\n"
     + SPEC_HEAD[len("# Spec\n\n"):] + slice_table("done") + SPEC_TAIL, 0),
    ("fenced table is ignored", SPEC_HEAD + slice_table("done") + "\n```\n| ID | Issue |\n| 1 | #1 |\n```\n" + SPEC_TAIL, 0),
    ("no slice tables fails closed", SPEC_HEAD + "No tables.\n" + SPEC_TAIL, 1),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "docs/specs/portable.md", body)
        rc, out = run(d, "--only", "spec-status")
        expect("spec-status: " + label, out.count("[spec-status]") == want and rc == (1 if want else 0), out)

with tempfile.TemporaryDirectory() as d:
    write(d, "R.md", "x\n")
    rc, out = run(d, "--only", "spec-status")
    expect("spec-status: spec absent is skipped", rc == 0, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "spec-status")
expect("spec-status: the current tree passes", rc == 0, out)

# Design headers (#259): a '(design)' or 'in design' H1 names an open spec milestone.
DESIGN_SPEC = (SPEC_HEAD + "| ID | Issue | Status |\n|---|---|---|\n| 1.1 | #11 | done |\n| 1.2 | #12 | open |\n"
               "\n### M2: later\n\n| ID | Issue | Status |\n|---|---|---|\n| 2.1 | #21 | done |\n| 2.2 | #22 | dropped |\n"
               + SPEC_TAIL)
ALLOW = "scripts/design-headers.txt"

for label, files, want in [
    ("open milestone via banner issue passes", {"docs/a.md": "# A (design)\n\n> - **Built:** #11\n\nBody.\n"}, 0),
    ("closed milestone fails", {"docs/a.md": "# A (design)\n\n> - **Built:** #21, #22\n"}, 1),
    ("closed milestone by name fails", {"docs/a.md": "# A in design (M2)\n"}, 1),
    ("open milestone by name passes", {"docs/a.md": "# A (design, M1)\n"}, 0),
    ("first known reference decides", {"docs/a.md": "# A (design)\n\n> #999 then #21 then #12\n"}, 1),
    ("no reference is unknown and fails", {"docs/a.md": "# A (design)\n\nBody names #12.\n"}, 1),
    ("unknown issue only fails", {"docs/a.md": "# A (design)\n\n> #999\n"}, 1),
    ("plain header is ignored", {"docs/a.md": "# A\n\n> #21\n", "docs/b.md": "# B\n\n## Part (design)\n"}, 0),
    ("changes/ and dev/ are skipped", {"changes/unreleased/x.md": "# X (design)\n", "dev/y.md": "# Y (design)\n"}, 0),
    ("allowlisted doc passes", {"docs/a.md": "# A (design)\n\n> #21\n", ALLOW: "# c\n\ndocs/a.md\tkept on purpose\n"}, 0),
    ("allowlist entry without reason fails", {"docs/a.md": "# A (design)\n\n> #21\n", ALLOW: "docs/a.md\n"}, 1),
    ("stale allowlist entry fails", {"docs/a.md": "# A\n", ALLOW: "docs/a.md\tno longer design\n"}, 1),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, "docs/specs/portable.md", DESIGN_SPEC)
        for rel, text in files.items():
            write(d, rel, text)
        rc, out = run(d, "--only", "design-headers")
        expect("design-headers: " + label, out.count("[design-headers]") == want and rc == (1 if want else 0), out)

with tempfile.TemporaryDirectory() as d:
    write(d, "docs/a.md", "# A (design)\n")
    rc, out = run(d, "--only", "design-headers")
    expect("design-headers: spec absent is skipped", rc == 0, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "design-headers")
expect("design-headers: the current tree passes", rc == 0, out)

# CHANGELOG fragments (#264): every file under changes/ is a valid fragment.
FRAG = "---\ntype: added\nissue: 7\npr: 9\ndate: 2026-10-31\nbox-skill: none\n---\n\nA change,\nwrapped.\n"
OK_FRAG = "changes/unreleased/7-a-b.md"
for label, rel, body, line in [
    ("valid fragment passes", OK_FRAG, FRAG, None),
    ("pr TBD passes", OK_FRAG, FRAG.replace("pr: 9", "pr: TBD"), None),
    ("bad name fails", "changes/unreleased/7_A.md", FRAG, 1),
    ("fragment outside changes/unreleased fails", "changes/7-a-b.md", FRAG, 1),
    ("nested fragment fails", "changes/unreleased/x/7-a-b.md", FRAG, 1),
    ("no front matter fails", OK_FRAG, "A change.\n", 1),
    ("unclosed front matter fails", OK_FRAG, "---\ntype: added\n", 1),
    ("unknown type fails", OK_FRAG, FRAG.replace("type: added", "type: misc"), 2),
    ("issue not the file name's fails", OK_FRAG, FRAG.replace("issue: 7", "issue: 8"), 3),
    ("bad pr fails", OK_FRAG, FRAG.replace("pr: 9", "pr: #9"), 4),
    ("bad date fails", OK_FRAG, FRAG.replace("2026-10-31", "2026-02-30"), 5),
    ("duplicate field fails", OK_FRAG, FRAG.replace("pr: 9", "pr: 9\npr: 10"), 5),
    ("missing field fails", OK_FRAG, FRAG.replace("box-skill: none\n", ""), 6),
    ("unknown field fails", OK_FRAG, FRAG.replace("box-skill: none", "box-skill: none\nowner: x"), 7),
    ("empty entry fails", OK_FRAG, FRAG.split("\nA change")[0] + "\n", 7),
    ("blank line in entry fails", OK_FRAG, FRAG.replace("A change,\n", "A change,\n\n"), 10),
]:
    with tempfile.TemporaryDirectory() as d:
        write(d, rel, body)
        rc, out = run(d, "--only", "fragments")
        ok = rc == 0 if line is None else (
            rc == 1 and "%s:%d: [changelog-fragment]" % (rel, line) in out and out.count("[changelog-fragment]") == 1)
        expect("fragments: " + label, ok, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "fragments")
expect("fragments: the current tree passes", rc == 0, out)

# File selection: in a git work tree only tracked files are scanned (a tracked
# node_modules is checked, an untracked one is not); elsewhere, everything.
GIT_ENV = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def git(d, *args):
    return subprocess.run(["git", "-C", d, *args], capture_output=True, env=GIT_ENV).returncode == 0


with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        write(d, "docs/node_modules/x.md", "[b](missing.md)\n")
        write(d, "untracked/node_modules/y.md", "[b](missing.md)\n")
        write(d, "untracked/z.md", "[b](missing.md)\n")
        git(d, "add", "docs/node_modules/x.md")
        rc, out = run(d, "--only", "links")
        expect("git tree: tracked node_modules is scanned, untracked is not",
               rc == 1 and "docs/node_modules/x.md:1:" in out and out.count("[broken-link]") == 1, out)
    else:
        print("skip git tree test (git unavailable)")

with tempfile.TemporaryDirectory() as d:
    write(d, "a/node_modules/x.md", "[b](missing.md)\n")
    write(d, ".git/y.md", "[b](missing.md)\n")
    rc, out = run(d, "--only", "links")
    expect("outside git: node_modules is scanned, .git is not",
           rc == 1 and "a/node_modules/x.md:1:" in out and out.count("[broken-link]") == 1, out)

# Denylist (#127): names come only from the file named by $CREW_DENYLIST, so
# none is committed. The fixture names here are made up.
def run_denylist(root, denylist):
    env = {k: v for k, v in os.environ.items() if k != "CREW_DENYLIST"}
    if denylist is not None:
        env["CREW_DENYLIST"] = denylist
    p = subprocess.run([sys.executable, CHECK, "--root", root, "--only", "denylist"],
                       capture_output=True, text=True, env=env)
    return p.returncode, p.stdout, p.stderr


with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as lists:
    write(d, "docs/a.md", "# A\n\nRun it with the Zorblax CLI.\n")
    write(d, "docs/b.md", "# B\n\nzorblaxian and xzorblax are other words; quux-tool is fine.\n")
    names = os.path.join(lists, "deny.txt")
    write(lists, "deny.txt", "# fake names\n\nzorblax\nquux tool\n")
    rc, out, _ = run_denylist(d, names)
    expect("denylist: case-insensitive whole-word hit fails with file:line, term not echoed",
           rc == 1 and "docs/a.md:3: [denylist]" in out and out.count("[denylist]") == 1
           and "zorblax" not in out.lower(), out)
    write(lists, "deny.txt", "frobnicator\n")
    rc, out, _ = run_denylist(d, names)
    expect("denylist: miss passes", rc == 0 and out.startswith("check-repo: OK (denylist)"), out)
    rc, out, err = run_denylist(d, None)
    expect("denylist: var unset skips", rc == 0 and "CREW_DENYLIST unset" in err, out + err)
    rc, out, _ = run_denylist(d, os.path.join(lists, "missing.txt"))
    expect("denylist: unreadable file fails closed", rc == 1 and "[denylist]" in out, out)

# Deliverables manifest (#235): every tracked path matches exactly one row.
MANIFEST_ROWS = ("# rows\n"
                 "docs/*.md\tdeliverable\tall\n"
                 "docs/specs/**\tinternal\tn/a\n"
                 "scripts/deliverables.txt\tinternal\tn/a\n")


def deliverables_tree(d, manifest, *paths):
    write(d, "scripts/deliverables.txt", manifest)
    for rel in paths:
        write(d, rel, "x\n")
    git(d, "add", "-A")
    return run(d, "--only", "deliverables")


with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        rc, out = deliverables_tree(d, MANIFEST_ROWS, "docs/a.md", "docs/specs/p/q.md")
        expect("deliverables: each tracked path matches one row (`*` stays in a segment)",
               rc == 0 and out.startswith("check-repo: OK (deliverables)"), out)
        write(d, "docs/untracked.txt", "x\n")
        rc, out = run(d, "--only", "deliverables")
        expect("deliverables: an untracked path is ignored", rc == 0, out)
        os.remove(os.path.join(d, "docs/untracked.txt"))
        rc, out = deliverables_tree(d, MANIFEST_ROWS, "docs/b.txt")
        expect("deliverables: unclassified tracked path fails",
               rc == 1 and "docs/b.txt:1: [unclassified]" in out and out.count("[unclassified]") == 1, out)
    else:
        print("skip deliverables tests (git unavailable)")

with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        rc, out = deliverables_tree(d, MANIFEST_ROWS + "docs/**\tinternal\tn/a\n", "docs/a.md")
        expect("deliverables: double match fails and names both rows",
               rc == 1 and "docs/a.md:1: [double-classified]" in out and "rows 2, 5" in out
               and out.count("[double-classified]") == 1, out)
        rc, out = deliverables_tree(d, MANIFEST_ROWS + "docs/**\tshipped\tall\n")
        expect("deliverables: bad manifest row fails",
               rc == 1 and "scripts/deliverables.txt:5: [deliverables-config]" in out, out)
        os.remove(os.path.join(d, "scripts/deliverables.txt"))
        rc, out = run(d, "--only", "deliverables")
        expect("deliverables: missing manifest fails closed",
               rc == 1 and "scripts/deliverables.txt:1: [deliverables-config]" in out, out)

with tempfile.TemporaryDirectory() as d:
    write(d, "a.md", "# A\n")
    p = subprocess.run([sys.executable, CHECK, "--root", d, "--only", "deliverables"],
                       capture_output=True, text=True)
    expect("deliverables: outside a git work tree it is skipped",
           p.returncode == 0 and "deliverables skipped" in p.stderr, p.stdout + p.stderr)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "deliverables")
expect("deliverables: the current tree passes", rc == 0, out)

# Untracked files (#1414): path checks read `git ls-files`, so a default run
# names non-ignored untracked files on stderr (a warning, exit unchanged) and
# stays quiet about ignored ones; after `git add` they are checked.
with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        deliverables_tree(d, MANIFEST_ROWS + ".gitignore\tinternal\tn/a\n", "docs/a.md")
        write(d, ".gitignore", "scratch/\n")
        git(d, "add", "-A")
        write(d, "docs/new.txt", "x\n")
        write(d, "scratch/log.txt", "x\n")
        p = subprocess.run([sys.executable, CHECK, "--root", d, "--only", "deliverables"],
                           capture_output=True, text=True)
        expect("untracked: a non-ignored untracked file is named as a warning; exit unchanged",
               p.returncode == 0 and "check-repo: warning: 1 untracked file" in p.stderr
               and "docs/new.txt" in p.stderr and "git add" in p.stderr, p.stdout + p.stderr)
        expect("untracked: an ignored file stays quiet", "scratch/" not in p.stderr, p.stderr)
        git(d, "add", "docs/new.txt")
        p = subprocess.run([sys.executable, CHECK, "--root", d, "--only", "deliverables"],
                           capture_output=True, text=True)
        expect("untracked: after git add the file is checked and the warning is gone",
               p.returncode == 1 and "docs/new.txt:1: [unclassified]" in p.stdout
               and "untracked" not in p.stderr, p.stdout + p.stderr)
    else:
        print("skip untracked tests (git unavailable)")

# Per-script docs (#325): every script documents itself in its module docstring;
# one run directly or a crew command also needs a `Usage:` line.
SCRIPT = '#!/usr/bin/env python3\n"""Do a thing.\n\nUsage: tool.py [--x]\n"""\nif __name__ == "__main__":\n    pass\n'
SCRIPT_TREE = {
    "scripts/tool.py": SCRIPT,
    "cli/mdstack": SCRIPT.replace("tool.py", "mdstack COMMAND"),
    "environments/terminal/crew.d/cmd.py": '"""`mdstack cmd` does a thing.\n\nUsage: mdstack cmd --project FILE\n"""\n',
    "environments/terminal/crew.d/_helpers.py": '"""Helpers for the crew commands."""\n',
    "scripts/test-tool.py": '"""Tests for tool.py: covers a thing."""\nif __name__ == "__main__":\n    pass\n',
    "scripts/lib_mod.py": '"""Helpers other scripts import."""\n',
    "scripts/fixtures/x/bad.py": "x = 1\n",
    "docs/tool.py": "x = 1\n",
}
for label, changes, bad in [
    ("a documented tree passes; fixtures and files outside scripts/ are ignored", {}, None),
    ("a script without a docstring fails", {"scripts/tool.py": 'if __name__ == "__main__":\n    pass\n'}, "scripts/tool.py"),
    ("a script docstring without a Usage: line fails", {"scripts/tool.py": SCRIPT.replace("Usage:", "Run:")}, "scripts/tool.py"),
    ("Usage: only in a comment fails", {"scripts/tool.py": SCRIPT.replace("Usage: tool.py [--x]\n", "").replace(
        "#!/usr/bin/env python3\n", "#!/usr/bin/env python3\n# Usage: tool.py\n")}, "scripts/tool.py"),
    ("cli/mdstack without a Usage: line fails", {"cli/mdstack": '"""mdstack CLI."""\nif __name__ == "__main__":\n    pass\n'},
     "cli/mdstack"),
    ("a crew command without a Usage: line fails",
     {"environments/terminal/crew.d/cmd.py": '"""mdstack cmd --project FILE"""\n'}, "environments/terminal/crew.d/cmd.py"),
    ("a crew.d helper without a docstring fails", {"environments/terminal/crew.d/_helpers.py": "x = 1\n"},
     "environments/terminal/crew.d/_helpers.py"),
    ("a test without a docstring fails", {"scripts/test-tool.py": "pass\n"}, "scripts/test-tool.py"),
    ("a helper module without a docstring fails", {"scripts/lib_mod.py": "x = 1\n"}, "scripts/lib_mod.py"),
    ("a file that does not parse fails, no crash", {"scripts/tool.py": '"""Do.\n\nUsage: x\n"""\ndef (:\n'}, "scripts/tool.py"),
]:
    with tempfile.TemporaryDirectory() as d:
        for rel, body in {**SCRIPT_TREE, **changes}.items():
            write(d, rel, body)
        rc, out = run(d, "--only", "script-docs")
        ok = rc == 0 if bad is None else (
            rc == 1 and "%s:1: [script-doc]" % bad in out and out.count("[script-doc]") == 1)
        expect("script-docs: " + label, ok, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "script-docs")
expect("script-docs: the current tree passes", rc == 0, out)


def load_check_repo():
    spec = importlib.util.spec_from_file_location("check_repo", CHECK)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# `--help` prints each script's docstring, its Usage: line included.
cr = load_check_repo()
REPO = os.path.dirname(SCRIPTS)
for full, rel in cr.walk(REPO):
    if not cr.SCRIPT_FILE.fullmatch(rel):
        continue
    with open(full, encoding="utf-8") as f:
        text = f.read()
    doc = ast.get_docstring(ast.parse(text))
    if cr.script_kind(rel, text) != "script":
        continue
    usage = next(l for l in doc.splitlines() if l.startswith("Usage:"))
    cmd = ([os.path.join(REPO, "cli", "mdstack"), rel.rsplit("/", 1)[1][:-3]] if "/crew.d/" in rel
           else [full])
    p = subprocess.run([sys.executable, *cmd, "--help"], capture_output=True, text=True, cwd=REPO)
    expect("--help: %s prints its Usage: line" % rel, p.returncode == 0 and usage in p.stdout, p.stdout + p.stderr)


# AC proof (#325): two branches that each add a script with its docstring and a
# test merge with no conflict, and scripts/README.md stays untouched. Control:
# the same two additions as rows of a shared table do conflict.
def git_out(d, *args):
    p = subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t", "-c", "commit.gpgsign=false",
                        *args], capture_output=True, text=True, env=GIT_ENV)
    return p.returncode, p.stdout + p.stderr


def add_script(d, name):
    write(d, "scripts/%s.py" % name, SCRIPT.replace("tool.py", name + ".py"))
    write(d, "scripts/test-%s.py" % name, '"""Tests for %s.py."""\nif __name__ == "__main__":\n    pass\n' % name)


def two_branch_merge(d, edit):
    """Commit a base, then branches a and b from it, each running edit(d, name);
    merge b into a. Returns (merge exit code, unmerged paths, base sha)."""
    git_out(d, "add", "-A")
    git_out(d, "commit", "-qm", "base")
    base = git_out(d, "rev-parse", "HEAD")[1].strip()
    for branch, name in (("a", "alpha-tool"), ("b", "alpha-tools")):  # adjacent names: the worst case for a table
        git_out(d, "checkout", "-q", "-b", branch, base)
        edit(d, name)
        git_out(d, "add", "-A")
        git_out(d, "commit", "-qm", "add " + name)
    git_out(d, "checkout", "-q", "a")
    rc, _ = git_out(d, "merge", "-q", "--no-edit", "b")
    return rc, git_out(d, "diff", "--name-only", "--diff-filter=U")[1].split(), base


with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        with open(os.path.join(SCRIPTS, "README.md"), encoding="utf-8") as f:
            write(d, "scripts/README.md", f.read())
        rc, unmerged, base = two_branch_merge(d, add_script)
        same = git_out(d, "diff", "--quiet", base, "HEAD", "--", "scripts/README.md")[0] == 0
        rc2, out = run(d, "--only", "script-docs")
        expect("merge: two branches each adding a script and its docs merge clean, scripts/README.md untouched",
               rc == 0 and not unmerged and same and rc2 == 0, "merge rc=%s unmerged=%s readme same=%s\n%s"
               % (rc, unmerged, same, out))
    else:
        print("skip merge test (git unavailable)")

with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        write(d, "scripts/README.md", "# Scripts\n\n| File | Purpose |\n|---|---|\n| `check-repo.py` | The guard |\n")

        def add_script_and_row(d, name):
            add_script(d, name)
            with open(os.path.join(d, "scripts/README.md"), "a", encoding="utf-8") as f:
                f.write("| `%s.py` | Does a thing |\n" % name)

        rc, unmerged, _ = two_branch_merge(d, add_script_and_row)
        expect("merge control: the same additions as shared-table rows conflict in scripts/README.md",
               rc != 0 and unmerged == ["scripts/README.md"], "merge rc=%s unmerged=%s" % (rc, unmerged))

# Index files (#325): the inventory table in docs/deliverables.md is generated
# from the manifest; the manifest, the required-docs config and the docs index
# are sorted, so a new entry lands at its own place instead of the shared end.
IDX_MANIFEST = ("# header\n"
                "docs/*.md\tdeliverable\tall\tProtocol: the text roles load\n"
                "docs/README.md\tinternal\tn/a\n"
                "scripts/deliverables.txt\tinternal\tn/a\tThe manifest\n")
IDX_DOC = ("# Deliverables\n\n## Inventory\n\n"
           "<!-- inventory:begin generated; do not edit -->\n<!-- inventory:end -->\n\n## Packaging\n")
IDX_ROWS = ["| `docs/*.md` | Deliverable | all | Protocol: the text roles load |",
            "| `docs/README.md` | Internal | n/a |  |",
            "| `scripts/deliverables.txt` | Internal | n/a | The manifest |"]


def index_tree(d, manifest=IDX_MANIFEST, doc=IDX_DOC, config="docs/a.md\ndocs/b.md\n"):
    write(d, "scripts/deliverables.txt", manifest)
    write(d, "docs/deliverables.md", doc)
    write(d, "cfg.txt", config)
    return ("--only", "index", "--config", os.path.join(d, "cfg.txt"))


with tempfile.TemporaryDirectory() as d:
    args = index_tree(d)
    rc, out = run(d, *args)
    expect("index: a stale inventory fails with its marker line", rc == 1
           and "docs/deliverables.md:5: [index-stale]" in out and out.count("[index-stale]") == 1, out)
    rc, out = run(d, "--fix", *args)
    with open(os.path.join(d, "docs/deliverables.md"), encoding="utf-8") as f:
        fixed = f.read().split("\n")
    table = ["", "| Path | Class | Runtime(s) | Why |", "|---|---|---|---|"] + IDX_ROWS + [""]
    expect("index: --fix writes one row per manifest row, the why column from the 4th", rc == 0
           and fixed[4] == IDX_DOC.split("\n")[4] and fixed[5:5 + len(table)] == table
           and fixed[5 + len(table)] == "<!-- inventory:end -->" and fixed[-2] == "## Packaging", "\n".join(fixed))
    rc, out = run(d, *args)
    expect("index: after --fix the check passes and a rerun changes nothing", rc == 0, out)
    write(d, "scripts/deliverables.txt", IDX_MANIFEST + "scripts/x.py\tinternal\tn/a\n")
    rc, out = run(d, *args)
    expect("index: a manifest row added without --fix is stale", rc == 1 and "[index-stale]" in out, out)
    rc, out = run(d, "--fix", *args)
    expect("index: --fix catches the table up", rc == 0 and "scripts/x.py" in open(
        os.path.join(d, "docs/deliverables.md"), encoding="utf-8").read(), out)
    with open(os.path.join(d, "docs/deliverables.md"), encoding="utf-8") as f:
        text = f.read()
    write(d, "docs/deliverables.md", text.replace("| Internal | n/a | The manifest |", "| Internal | n/a | By hand |"))
    rc, out = run(d, *args)
    expect("index: a hand-edited table row fails", rc == 1 and "[index-stale]" in out, out)
    write(d, "docs/deliverables.md", "# Deliverables\n\n## Inventory\n")
    rc, out = run(d, *args)
    expect("index: no markers fails", rc == 1 and "docs/deliverables.md:1: [index-stale]" in out, out)

for label, manifest, config, want in [
        ("an unsorted manifest", "docs/b.md\tinternal\tn/a\ndocs/a.md\tinternal\tn/a\n", "docs/a.md\n",
         "scripts/deliverables.txt:2: [index-order]"),
        ("an unsorted required-docs config", IDX_MANIFEST, "# c\ndocs/b.md\ndocs/a.md\n", "cfg.txt:3: [index-order]"),
        ("a sorted config with comments between entries", IDX_MANIFEST, "docs/a.md\n# c\ndocs/b.md\n", None)]:
    with tempfile.TemporaryDirectory() as d:
        args = index_tree(d, manifest, config=config)
        run(d, "--fix", *args)
        rc, out = run(d, *args)
        expect("index: " + label + (" fails" if want else " passes"),
               (rc == 1 and want in out and out.count("[index-order]") == 1) if want else rc == 0, out)

with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        IDX_README = ("# Docs index\n\n| Doc | Contents |\n|---|---|\n"
                      "| [../AGENTS.md](../AGENTS.md) | Agents |\n| [a.md](a.md) | A |\n| [b.md](b.md#x) | B |\n")
        DOCS_MANIFEST = ("docs/README.md\tinternal\tn/a\ndocs/a.md\tdeliverable\tall\tA doc\n"
                         "docs/b.md\tdeliverable\tall\ndocs/specs/**\tinternal\tn/a\nscripts/deliverables.txt\tinternal\tn/a\n")
        write(d, "scripts/deliverables.txt", DOCS_MANIFEST)
        for rel in ("docs/README.md", "docs/a.md", "docs/b.md", "docs/specs/p.md"):
            write(d, rel, IDX_README if rel == "docs/README.md" else "# X\n")
        git(d, "add", "-A")
        for label, readme, want in [
                ("sorted, one row per doc, every deliverable doc linked (internal docs need no row)", IDX_README, None),
                ("a second row for one doc fails", IDX_README.replace("| [b.md]", "| [a.md](a.md) | A |\n| [b.md]"),
                 "docs/README.md:7: [docs-index] second row for docs/a.md (first at line 6)"),
                ("a deliverable doc without a row fails", IDX_README.replace("| [b.md](b.md#x) | B |\n", ""),
                 "[docs-index] no row for the deliverable doc docs/b.md"),
                ("an unsorted row fails", IDX_README.replace("| [a.md](a.md) | A |\n| [b.md](b.md#x) | B |\n",
                                                             "| [b.md](b.md#x) | B |\n| [a.md](a.md) | A |\n"),
                 "docs/README.md:7: [index-order]")]:
            write(d, "docs/README.md", readme)
            rc, out = run(d, "--only", "index", "--config", os.path.join(d, "none.txt"))
            expect("docs index: " + label, (rc == 1 and want in out and out.count("[") == 1) if want else rc == 0, out)
        write(d, "scripts/deliverables.txt", DOCS_MANIFEST.replace("A doc", "A | doc"))
        rc, out = run(d, "--only", "deliverables")
        expect("deliverables: a `|` in the why column is a bad row", rc == 1
               and "scripts/deliverables.txt:2: [deliverables-config]" in out, out)
        write(d, "scripts/deliverables.txt", DOCS_MANIFEST)
        rc, out = run(d, "--only", "deliverables")
        expect("deliverables: a row may carry a why column", rc == 0, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "index")
expect("index: the current tree passes", rc == 0, out)


# AC proof (#325), on copies of the real index files: two branches that each add
# a script, a doc and an inventory row merge with no conflict, and the merged
# tree passes the index and deliverables checks. Control: the same additions
# appended at the end of the files, the old way, conflict.
INDEX_FILES = ("scripts/deliverables.txt", "scripts/required-docs.txt", "docs/deliverables.md", "docs/README.md")


def add_item(d, stem, sorted_in):
    """Add scripts/<stem>-tool.py and docs/<stem>-notes.md the way the CONTRIBUTING rule says, then --fix."""
    script, doc = "scripts/%s-tool.py" % stem, "docs/%s-notes.md" % stem
    write(d, script, '"""Do a thing."""\n')
    write(d, doc, "# Notes\n")
    edits = [("scripts/deliverables.txt", lambda l: bool(l.strip()) and not l.startswith("#"),
              ["%s\tdeliverable\tall\tNew script" % script, "%s\tdeliverable\tall\tNew doc" % doc]),
             ("scripts/required-docs.txt", lambda l: bool(l.strip()) and not l.startswith("#"), [script, doc]),
             ("docs/README.md", lambda l: l.startswith("| ["), ["| [%s-notes.md](%s-notes.md) | New doc |" % (stem, stem)])]
    for rel, is_entry, new_lines in edits:
        with open(os.path.join(d, rel), encoding="utf-8") as f:
            lines = f.read().split("\n")
        for new in new_lines:
            entries = [i for i, l in enumerate(lines) if is_entry(l)]
            at = next((i for i in entries if lines[i] > new), entries[-1] + 1) if sorted_in else entries[-1] + 1
            lines.insert(at, new)
        write(d, rel, "\n".join(lines))
    run(d, "--fix", "--only", "index", "--config", os.path.join(d, "scripts/required-docs.txt"))


def merge_two_items(d, sorted_in):
    """Seed d with the real index files, then merge branch b (zeta) into branch a (mu)."""
    for rel in INDEX_FILES:
        with open(os.path.join(os.path.dirname(SCRIPTS), rel), encoding="utf-8") as f:
            write(d, rel, f.read())
    git_out(d, "add", "-A")
    git_out(d, "commit", "-qm", "base")
    base = git_out(d, "rev-parse", "HEAD")[1].strip()
    for branch, stem in (("a", "mu"), ("b", "zeta")):
        git_out(d, "checkout", "-q", "-b", branch, base)
        add_item(d, stem, sorted_in)
        git_out(d, "add", "-A")
        git_out(d, "commit", "-qm", "add " + stem)
    git_out(d, "checkout", "-q", "a")
    rc, _ = git_out(d, "merge", "-q", "--no-edit", "b")
    return rc, git_out(d, "diff", "--name-only", "--diff-filter=U")[1].split()


with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        rc, unmerged = merge_two_items(d, True)
        rc2, out = run(d, "--only", "index", "--only", "deliverables",
                       "--config", os.path.join(d, "scripts/required-docs.txt"))
        with open(os.path.join(d, "scripts/deliverables.txt"), encoding="utf-8") as f:
            manifest = f.read()
        with open(os.path.join(d, "docs/deliverables.md"), encoding="utf-8") as f:
            inventory = f.read()
        both = all("%s-%s" % (s, k) in text for s in ("mu", "zeta") for k in ("tool.py", "notes.md")
                   for text in (manifest, inventory))
        expect("merge: two branches each adding a script, a doc and their index rows merge clean, and the merged "
               "tree passes the index and deliverables checks", rc == 0 and not unmerged and rc2 == 0 and both,
               "merge rc=%s unmerged=%s both=%s\n%s" % (rc, unmerged, both, out))
    else:
        print("skip index merge test (git unavailable)")

with tempfile.TemporaryDirectory() as d:
    if git(d, "init", "-q"):
        rc, unmerged = merge_two_items(d, False)
        want = {"scripts/deliverables.txt", "scripts/required-docs.txt", "docs/README.md", "docs/deliverables.md"}
        expect("merge control: the same additions appended at the end of the index files conflict in all four",
               rc != 0 and set(unmerged) == want, "merge rc=%s unmerged=%s" % (rc, unmerged))

# Inline evidence (#143): even an empty root directory invites committed proof;
# adapters and local captures elsewhere remain allowed.
with tempfile.TemporaryDirectory() as d:
    write(d, "templates/evidence/adapter.md", "# Adapter\n")
    write(d, ".crew/captures/view.png", "local capture")
    rc, out = run(d, "--only", "evidence")
    expect("evidence: adapters and local captures pass", rc == 0, out)
    os.makedirs(os.path.join(d, "evidence"))
    rc, out = run(d, "--only", "evidence")
    expect("evidence: an empty root directory fails", rc == 1 and "[inline-evidence]" in out, out)
    write(d, "evidence/1/proof.txt", "proof")
    rc, out = run(d, "--only", "evidence")
    expect("evidence: nested proof fails with one finding", rc == 1 and out.count("[inline-evidence]") == 1, out)
    rc, out = run(d)
    expect("evidence: enabled by default", rc == 1 and "[inline-evidence]" in out, out)

# Scenario index (#1419): one docs/campaign-scenarios/<Axx>.md per committed
# spec or driver-only scenario; the index in docs/campaign-harness.md is
# generated from them (`--fix`) and fails closed on a missing, duplicate,
# stale or dangling entry. Replaces the #1112 union-merge guard.
SC_DOC, SC_CAMP, SC_DIR = "docs/campaign-harness.md", "dev/tests/scripts/fixtures/campaign", "docs/campaign-scenarios"
SC_DRIVER = "- Driver: [`a29/run.py`](../../dev/tests/scripts/fixtures/campaign/a29/run.py)"


def scenario_file(sid, source="#1", box="shared", spec=None, notes=None):
    spec = spec or "- Spec: [`%s.json`](../../dev/tests/scripts/fixtures/campaign/%s.json)" % (sid, sid)
    return "# %s\n\n- Source: %s\n%s\n- Sandbox: %s\n\n%s\n" % (sid, source, spec, box, notes or "Notes for %s." % sid)


def scenario_tree(d):
    for sid in ("A01", "A02"):
        write(d, "%s/%s.json" % (SC_CAMP, sid), '{"id": "%s"}\n' % sid)
        write(d, "%s/%s.md" % (SC_DIR, sid), scenario_file(sid))
    write(d, SC_CAMP + "/a29/run.py", "")
    write(d, SC_DIR + "/A29.md", scenario_file("A29", box="n/a", spec=SC_DRIVER))
    write(d, SC_CAMP + "/driver-only.txt", "# driver-only scenarios\nA29\n")
    write(d, SC_DOC, "# Campaign\n\n<!-- scenarios:begin -->\n<!-- scenarios:end -->\n")
    return run(d, "--only", "scenarios", "--fix")


def sc_read(d, rel):
    with open(os.path.join(d, rel), encoding="utf-8") as f:
        return f.read()


def sc_sub(d, rel, old, new):
    text = sc_read(d, rel)
    assert old in text, (rel, old)
    write(d, rel, text.replace(old, new))


with tempfile.TemporaryDirectory() as d:
    rc, out = scenario_tree(d)
    index = sc_read(d, SC_DOC)
    expect("scenarios: --fix writes the sorted index, the driver-only A29 included",
           rc == 0 and "| [A01](campaign-scenarios/A01.md) | #1 | `A01.json` | shared |\n"
           "| [A02](campaign-scenarios/A02.md) | #1 | `A02.json` | shared |\n"
           "| [A29](campaign-scenarios/A29.md) | #1 | driver | n/a |\n\n<!-- scenarios:end -->" in index, out + index)
    rc, out = run(d, "--only", "scenarios")
    expect("scenarios: a generated index passes", rc == 0, out)

A01, A02, A29 = (SC_DIR + "/%s.md" % s for s in ("A01", "A02", "A29"))
for label, mutate, want in [
    ("missing scenario file for a committed spec",
     lambda d: write(d, SC_CAMP + "/A03.json", '{"id": "A03"}\n'), "missing: no docs/campaign-scenarios/A03.md"),
    ("stale row after a field rewrite", lambda d: sc_sub(d, A01, "Source: #1", "Source: #9"), "stale row for A01"),
    ("duplicate row", lambda d: sc_sub(d, SC_DOC, "| [A02]", "| [A02](campaign-scenarios/A02.md) | #1 | `A02.json` | shared |\n| [A02]"),
     "duplicate row for A02"),
    ("row dropped from the index", lambda d: sc_sub(d, SC_DOC, "| [A01](campaign-scenarios/A01.md) | #1 | `A01.json` | shared |\n", ""),
     "missing row for A01"),
    ("dangling spec", lambda d: os.remove(os.path.join(d, SC_CAMP, "A02.json")), "dangling: no readable committed spec"),
    ("spec id mismatch", lambda d: write(d, SC_CAMP + "/A02.json", '{"id": "A09"}\n'), "has id 'A09'"),
    ("spec naming another scenario's JSON", lambda d: sc_sub(d, A02, "A02.json", "A01.json"), "Spec must be exactly"),
    ("dangling driver", lambda d: os.remove(os.path.join(d, SC_CAMP, "a29", "run.py")), "dangling: Driver"),
    ("driver-only scenario with a committed spec",
     lambda d: write(d, SC_CAMP + "/A29.json", '{"id": "A29"}\n'), "is committed; use `- Spec:`"),
    ("file not named <Axx>.md", lambda d: write(d, SC_DIR + "/notes.md", "# Notes\n"), "not a scenario file"),
    ("heading names another ID", lambda d: sc_sub(d, A01, "# A01", "# A02"), "start with `# A01`"),
    ("Sandbox field missing", lambda d: sc_sub(d, A01, "- Sandbox: shared\n", ""), "needs `- Source:`"),
    ("Spec and Driver both set", lambda d: sc_sub(d, A01, "- Sandbox:", SC_DRIVER + "\n- Sandbox:"), "exactly one of"),
    ("second Source field", lambda d: sc_sub(d, A01, "- Source: #1\n", "- Source: #1\n- Source: #2\n"),
     "second `Source:` field"),
    ("bad sandbox for a spec", lambda d: sc_sub(d, A01, "Sandbox: shared", "Sandbox: n/a"), "fresh or shared"),
    ("bad sandbox for a driver", lambda d: sc_sub(d, A29, "Sandbox: n/a", "Sandbox: shared"), "is n/a"),
    ("a recorded driver-only scenario's file deleted", lambda d: os.remove(os.path.join(d, A29)),
     "missing: no docs/campaign-scenarios/A29.md for this driver-only scenario"),
    ("a Driver scenario not recorded", lambda d: write(d, SC_CAMP + "/driver-only.txt", ""), "exactly one listed"),
    ("a recorded driver-only ID with a Spec", lambda d: write(d, SC_CAMP + "/driver-only.txt", "A01\nA29\n"),
     "exactly one listed"),
    ("a bad driver-only record line", lambda d: write(d, SC_CAMP + "/driver-only.txt", "A29\nA29\n"),
     "one new driver-only scenario ID"),
    ("index markers missing", lambda d: write(d, SC_DOC, "# Campaign\n"), "no '<!-- scenarios:begin ...'"),
]:
    with tempfile.TemporaryDirectory() as d:
        scenario_tree(d)
        mutate(d)
        rc, out = run(d, "--only", "scenarios")
        expect("scenarios: refuses " + label, rc == 1 and want in out and "[scenario-index]" in out, out)

with tempfile.TemporaryDirectory() as d:
    scenario_tree(d)
    sc_sub(d, A01, "Source: #1", "Source: #9")
    rc, out = run(d, "--only", "scenarios", "--fix")
    rc2, out2 = run(d, "--only", "scenarios")
    expect("scenarios: --fix regenerates a stale index",
           rc == 0 and rc2 == 0 and "| [A01](campaign-scenarios/A01.md) | #9 |" in sc_read(d, SC_DOC), out + out2)

with tempfile.TemporaryDirectory() as d:
    scenario_tree(d)
    os.remove(os.path.join(d, A29))
    rc, out = run(d, "--only", "scenarios", "--fix")
    rc2, out2 = run(d, "--only", "scenarios")
    expect("scenarios: --fix refuses and keeps the row when a driver-only scenario's file is gone (review r1)",
           rc == 1 and rc2 == 1 and "| [A29](campaign-scenarios/A29.md)" in sc_read(d, SC_DOC)
           and "for this driver-only scenario" in out2, out + out2)

with tempfile.TemporaryDirectory() as d:
    write(d, SC_CAMP + "/A01.json", '{"id": "A01"}\n')
    rc, out = run(d, "--only", "scenarios")
    expect("scenarios: skipped when the harness doc is absent", rc == 0, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "scenarios")
expect("scenarios: current tree passes", rc == 0, out)
attrs = os.path.join(os.path.dirname(SCRIPTS), ".gitattributes")
expect("scenarios: the campaign page has no union merge attribute",
       not os.path.exists(attrs) or "campaign-harness.md" not in sc_read(os.path.dirname(SCRIPTS), ".gitattributes"))

# Two branches rewrite different scenarios (notes and an index field) and each
# regenerates the index: the scenario files merge cleanly, only the generated
# block conflicts, and `--fix` after the merge keeps both edits.
with tempfile.TemporaryDirectory() as d:
    sg = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                   capture_output=True, text=True)
    sg("init", "-q", "-b", "main")
    scenario_tree(d)
    sg("add", "-A")
    sg("commit", "-qm", "base")
    for branch, sid, source in [("r1", "A01", "#7"), ("r2", "A02", "#8")]:
        sg("checkout", "-qb", branch, "main")
        write(d, "%s/%s.md" % (SC_DIR, sid), scenario_file(sid, source=source, notes="Rewritten %s notes." % sid))
        run(d, "--only", "scenarios", "--fix")
        sg("commit", "-qam", branch)
    sg("checkout", "-q", "r1")
    merged = sg("merge", "-q", "--no-edit", "r2")
    unmerged = sg("diff", "--name-only", "--diff-filter=U").stdout.split()
    rc, out = run(d, "--only", "scenarios", "--fix")
    rc2, out2 = run(d, "--only", "scenarios")
    index = sc_read(d, SC_DOC)
    sg("add", "-A")
    done = sg("commit", "-qm", "merge r2")
    expect("scenarios: two rewrites conflict only in the generated index",
           merged.returncode != 0 and unmerged == [SC_DOC], "rc=%s unmerged=%s" % (merged.returncode, unmerged))
    expect("scenarios: --fix after the merge keeps both rewrites",
           rc == 0 and rc2 == 0 and done.returncode == 0 and "<<<<<<<" not in index
           and "| [A01](campaign-scenarios/A01.md) | #7 |" in index and "| [A02](campaign-scenarios/A02.md) | #8 |" in index
           and "Rewritten A01 notes." in sc_read(d, A01) and "Rewritten A02 notes." in sc_read(d, A02),
           out + out2 + index)

# Lessons index (#1929, M60 X1): the index in docs/lessons/README.md is generated
# from each lesson's front matter; one table of rows X1.1-X1.8, each failing row
# naming the file and leaving the index unchanged under --fix, beside valid controls.
LS_DOC, LS_DIR = "docs/lessons/README.md", "docs/lessons"
LS_A, LS_B, LS_M = (LS_DIR + "/" + n for n in ("2026-01-02-alpha.md", "2026-01-03-beta.md", "2026-01-01-many.md"))
LS_PROSE = "# Lessons\n\nProse before the index.\n\n<!-- lessons:begin -->\n<!-- lessons:end -->\n\nProse after it.\n"
LS_ROW = "| [2026-01-02-alpha.md](2026-01-02-alpha.md) | 2026-01-02 | Alpha lesson |"


def lesson_file(title, date, status, entries=1):
    body = "".join("### Entry %d\n\n- **Date:** %s\n- **Status:** applied. x\n\n" % (i, date) for i in range(entries))
    return "---\ntitle: %s\ndate: %s\nstatus: %s\nsource: PR #1\n---\n\n# %s\n\n%s" % (title, date, status, title, body)


def lesson_tree(d):
    write(d, LS_DOC, LS_PROSE)
    write(d, LS_A, lesson_file("Alpha lesson", "2026-01-02", "applied"))
    write(d, LS_B, lesson_file("Beta lesson", "2026-01-03", "open"))
    write(d, LS_M, lesson_file("Many lessons", "2026-01-01", "mixed", entries=2))
    return run(d, "--only", "lessons", "--fix")


with tempfile.TemporaryDirectory() as d:
    rc, out = lesson_tree(d)
    index = sc_read(d, LS_DOC)
    rc2, out2 = run(d, "--only", "lessons", "--fix")
    expect("lessons: --fix writes rows by (date, filename) between the markers, prose kept; a second run is a no-op",
           rc == 0 and rc2 == 0 and sc_read(d, LS_DOC) == index and index == LS_PROSE.replace(
               "<!-- lessons:begin -->\n", "<!-- lessons:begin -->\n\n| File | Date | Summary |\n|---|---|---|\n"
               "| [2026-01-01-many.md](2026-01-01-many.md) | 2026-01-01 | Many lessons |\n" + LS_ROW + "\n"
               "| [2026-01-03-beta.md](2026-01-03-beta.md) | 2026-01-03 | Beta lesson |\n\n"), out + out2 + index)
    rc, out = run(d, "--only", "lessons")
    expect("lessons: the generated index passes, with a multi-entry `mixed` control", rc == 0, out)

FM = "title: Alpha lesson\ndate: 2026-01-02\nstatus: applied\nsource: PR #1\n"


def front(key, new):
    """Alpha's front-matter block with its `key:` line replaced by `new` (lines; empty drops the key)."""
    return "---\n%s---\n" % "".join(new + "\n" if l.startswith(key + ":") and new else "" if l.startswith(key + ":")
                                     else l + "\n" for l in FM.splitlines())


X1_ROWS = [("X1.1 %s %s" % (key, case), LS_A, front(key, new)) for key, case, new in [
    ("title", "missing", ""), ("title", "empty", "title:"), ("title", "with a pipe", "title: Alpha | lesson"),
    ("title", "multi-line", "title: Alpha\n  lesson"), ("title", "duplicate", "title: Alpha lesson\ntitle: Again"),
    ("date", "missing", ""), ("date", "empty", "date: "), ("date", "bad form", "date: 2026-1-2"),
    ("date", "not a day", "date: 2026-02-30"), ("date", "not the filename's", "date: 2026-01-05"),
    ("date", "multi-line", "date: 2026-01-02\n  later"), ("date", "duplicate", "date: 2026-01-02\ndate: 2026-01-02"),
    ("status", "missing", ""), ("status", "empty", "status:"), ("status", "unknown", "status: shipped"),
    ("status", "multi-line", "status: applied\n  mostly"), ("status", "duplicate", "status: applied\nstatus: open"),
    ("source", "missing", ""), ("source", "empty", "source:  "), ("source", "multi-line", "source: PR #1\n  and PR #2"),
    ("source", "duplicate", "source: PR #1\nsource: PR #2"),
]] + [
    ("X1.2 no front matter", LS_A, ""),
    ("X1.2 unclosed block", LS_A, "---\n" + FM),
    ("X1.2 unknown key", LS_A, "---\n" + FM + "tags: x\n---\n"),
    ("X1.3 `mixed` on a single-entry file", LS_A, "---\n" + FM.replace("applied", "mixed") + "---\n"),
    ("X1.3 a multi-entry file without `mixed`", LS_M,
     "---\ntitle: Many lessons\ndate: 2026-01-01\nstatus: applied\nsource: PR #1\n---\n"),
]
for label, rel, front in X1_ROWS:
    with tempfile.TemporaryDirectory() as d:
        lesson_tree(d)
        before = sc_read(d, LS_DOC)
        text = sc_read(d, rel)
        write(d, rel, front + text[text.index("---\n\n#") + 4:])
        rc, out = run(d, "--only", "lessons")
        rc2, out2 = run(d, "--only", "lessons", "--fix")
        expect("lessons: %s fails with the file path; --fix leaves the index unchanged" % label,
               rc == 1 and rc2 == 1 and (rel + ":") in out and "[lesson-index]" in out and LS_B not in out
               and sc_read(d, LS_DOC) == before, out + out2)

LS_MANY = "| [2026-01-01-many.md](2026-01-01-many.md) | 2026-01-01 | Many lessons |"
for label, mutate, line, reason in [
    ("X1.4 stale row after a title change", lambda d: sc_sub(d, LS_A, "title: Alpha lesson", "title: Alpha, renamed"),
     10, "row is not generated"),
    ("X1.4 hand-edited row", lambda d: sc_sub(d, LS_DOC, "| Alpha lesson |", "| Alpha lesson, by hand |"),
     10, "row is not generated"),
    ("X1.4 duplicated row", lambda d: sc_sub(d, LS_DOC, LS_ROW, LS_ROW + "\n" + LS_ROW), 11, "duplicate row"),
    ("X1.4 rows out of order", lambda d: sc_sub(d, LS_DOC, LS_MANY + "\n" + LS_ROW, LS_ROW + "\n" + LS_MANY),
     10, "row is out of order"),
]:
    with tempfile.TemporaryDirectory() as d:
        lesson_tree(d)
        mutate(d)
        rc, out = run(d, "--only", "lessons")
        rc2, out2 = run(d, "--only", "lessons", "--fix")
        rc3, out3 = run(d, "--only", "lessons")
        expect("lessons: %s fails at the README line; --fix regenerates" % label,
               rc == 1 and ("%s:%d: [lesson-index] %s" % (LS_DOC, line, reason)) in out
               and rc2 == 0 and rc3 == 0 and sc_read(d, LS_DOC).count("2026-01-02-alpha.md](") == 1, out + out2 + out3)

with tempfile.TemporaryDirectory() as d:
    lesson_tree(d)
    before = sc_read(d, LS_DOC)
    write(d, LS_DIR + "/2026-01-02-gamma.md", lesson_file("Gamma lesson", "2026-01-02", "encoded"))
    rc, out = run(d, "--only", "lessons")
    rc2, out2 = run(d, "--only", "lessons", "--fix")
    gamma = "| [2026-01-02-gamma.md](2026-01-02-gamma.md) | 2026-01-02 | Gamma lesson |"
    expect("lessons: X1.5 a valid new file with no row passes (pending); --fix adds exactly its row",
           rc == 0 and rc2 == 0 and sc_read(d, LS_DOC) == before.replace(LS_ROW + "\n", LS_ROW + "\n" + gamma + "\n"),
           out + out2 + sc_read(d, LS_DOC))

BEGIN, END = "<!-- lessons:begin -->\n", "<!-- lessons:end -->\n"
for label, mutate in [
    ("missing begin marker", lambda t: t.replace(BEGIN, "")),
    ("missing end marker", lambda t: t.replace(END, "")),
    ("duplicated begin marker", lambda t: t.replace(BEGIN, BEGIN + BEGIN)),
    ("duplicated end marker", lambda t: t.replace(END, END + END)),
    ("reversed markers", lambda t: t.replace(BEGIN, "@@").replace(END, BEGIN).replace("@@", END)),
]:
    with tempfile.TemporaryDirectory() as d:
        lesson_tree(d)
        write(d, LS_DIR + "/2026-01-04-pending.md", lesson_file("Pending", "2026-01-04", "open"))
        write(d, LS_DOC, mutate(sc_read(d, LS_DOC)))
        before = sc_read(d, LS_DOC)
        rc, out = run(d, "--only", "lessons")
        rc2, out2 = run(d, "--only", "lessons", "--fix")
        expect("lessons: X1.6 %s fails; --fix writes nothing" % label,
               rc == 1 and rc2 == 1 and "%s:1: [lesson-index] needs one" % LS_DOC in out
               and sc_read(d, LS_DOC) == before, out + out2)

REPO = os.path.dirname(SCRIPTS)
rc, out = run(REPO, "--only", "lessons")
expect("lessons: X1.7 the migrated tree passes", rc == 0, out)
# Issue #1948: lesson PRs leave the committed index stale until a bookend --fix,
# so test idempotence on a copy of the live tree, not equality with its index.
with tempfile.TemporaryDirectory() as d:
    shutil.copytree(os.path.join(REPO, LS_DIR), os.path.join(d, LS_DIR))
    rc, out = run(d, "--only", "lessons", "--fix")
    first = sc_read(d, LS_DOC)
    rc2, out2 = run(d, "--only", "lessons", "--fix")
    rows = [l for l in first.splitlines() if l.startswith("| [")]
    names = sorted(n for n in os.listdir(os.path.join(d, LS_DIR)) if n != "README.md")
    expect("lessons: X1.7 a second --fix on the migrated tree is a no-op with exactly one row per lesson",
           rc == 0 and rc2 == 0 and sc_read(d, LS_DOC) == first and len(rows) == len(names)
           and all(sum(("| [%s](%s) |" % (n, n)) in r for r in rows) == 1 for n in names), out + out2)
with tempfile.TemporaryDirectory() as d:
    shutil.copytree(os.path.join(REPO, LS_DIR), os.path.join(d, LS_DIR))
    before = sc_read(d, LS_DOC)
    write(d, LS_DIR + "/2099-01-01-pending.md", lesson_file("Pending lesson", "2099-01-01", "open"))
    rc, out = run(d, "--only", "lessons")
    expect("lessons: X1.7 the migrated tree plus a valid lesson with no row passes unchanged",
           rc == 0 and sc_read(d, LS_DOC) == before, out)

# X1.8: two lesson PRs branched from one base each add only their file and land
# in turn by squash on the updated default branch; an index-editing control conflicts.
for adds_rows in (False, True):
    with tempfile.TemporaryDirectory() as d:
        g = lambda *a: subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *a],
                                      capture_output=True, text=True)
        g("init", "-q", "-b", "main")
        lesson_tree(d)
        g("add", "-A")
        g("commit", "-qm", "base")
        heads = []
        for branch, title, date in [("p1", "Gamma lesson", "2026-01-04"), ("p2", "Delta lesson", "2026-01-05")]:
            g("checkout", "-qb", branch, "main")
            name = "%s-%s.md" % (date, title.split()[0].lower())
            write(d, LS_DIR + "/" + name, lesson_file(title, date, "open"))
            if adds_rows:
                sc_sub(d, LS_DOC, "| Beta lesson |\n", "| Beta lesson |\n| [%s](%s) | %s | %s |\n" % (name, name, date, title))
            g("add", "-A")
            g("commit", "-qm", branch)
            heads.append(run(d, "--only", "lessons")[0])
        g("checkout", "-q", "main")
        landed = []
        for branch in ("p1", "p2"):
            merged = g("merge", "--squash", branch)
            unmerged = g("diff", "--name-only", "--diff-filter=U").stdout.split()
            g("commit", "-qm", "squash " + branch)
            landed.append((merged.returncode, unmerged, run(d, "--only", "lessons")[0]))
        if adds_rows:
            expect("lessons: X1.8 control: two PRs that each edit the index conflict on the second squash",
                   landed[0][0] == 0 and landed[1][0] != 0 and landed[1][1] == [LS_DOC], repr(landed))
            continue
        rc, out = run(d, "--only", "lessons", "--fix")
        index = sc_read(d, LS_DOC)
        expect("lessons: X1.8 two same-base lesson PRs land in turn by squash with no conflict, each revision passing",
               heads == [0, 0] and landed == [(0, [], 0), (0, [], 0)], repr((heads, landed)))
        expect("lessons: X1.8 a later bookend --fix adds both rows",
               rc == 0 and "| [2026-01-04-gamma.md](2026-01-04-gamma.md) | 2026-01-04 | Gamma lesson |\n"
               "| [2026-01-05-delta.md](2026-01-05-delta.md) | 2026-01-05 | Delta lesson |\n" in index, out + index)

with tempfile.TemporaryDirectory() as d:
    write(d, LS_A, "# no front matter\n")
    rc, out = run(d, "--only", "lessons")
    expect("lessons: skipped when the README is absent", rc == 0, out)

# Execute the CI shell with a fake python3 that runs the real denylist guard.
workflow = open(os.path.join(SCRIPTS, "..", ".github", "workflows", "ci.yml"), encoding="utf-8").read()
step = workflow.split("      - name: Repo check (", 1)[1].split("      - name:", 1)[0]
expect("CI denylist: repository secret wired", "DENYLIST_CONTENT: ${{ secrets.CREW_DENYLIST }}" in step)
shell = "\n".join(line[10:] for line in step.split("        run: |\n", 1)[1].splitlines())
for label, content, body, want in [("unset", "", "# harmless\n", 0),
                                   ("miss", "private-example", "# harmless\n", 0),
                                   ("hit", "private-example", "# PRIVATE-EXAMPLE\n", 1)]:
    with tempfile.TemporaryDirectory() as d:
        root, runner, bindir = [os.path.join(d, name) for name in ("repo", "runner", "bin")]
        for directory in (root, runner, bindir):
            os.mkdir(directory)
        write(root, "README.md", body)
        shim = os.path.join(bindir, "python3")
        import shlex
        with open(shim, "w") as f:
            f.write("#!/bin/sh\nexec %s %s --root %s --only denylist\n" %
                    tuple(shlex.quote(value) for value in (sys.executable, CHECK, root)))
        os.chmod(shim, 0o755)
        env = dict(os.environ, DENYLIST_CONTENT=content, RUNNER_TEMP=runner,
                   PATH=bindir + os.pathsep + os.environ.get("PATH", ""))
        env.pop("CREW_DENYLIST", None)
        result = subprocess.run(["bash", "-e", "-c", shell], capture_output=True, text=True, env=env)
        output = result.stdout + result.stderr
        expect("CI denylist: " + label + " exit", result.returncode == want, output)
        expect("CI denylist: " + label + " cleanup", not os.listdir(runner))
        expect("CI denylist: " + label + " no names in logs", "private-example" not in output.lower(), output)
        if want:
            expect("CI denylist: entry line only", "entry on line 1" in output, output)

# Tests per module (#1224): every test is dev/tests/<module>/test-*.py with a unique name.
LAYOUT_TREE = {"dev/tests/core/test-a.py": "", "dev/tests/scripts/fixtures/x/test-sample.py": "",
               "dev/tests/crew_testlib.py": ""}
for label, changes, bad in [
    ("tests in dev/tests/<module>/ pass; a test-*.py fixture is ignored", {}, None),
    ("a test left in scripts/ fails", {"scripts/test-b.py": ""}, "scripts/test-b.py"),
    ("a test in an unknown module fails", {"dev/tests/misc/test-b.py": ""}, "dev/tests/misc/test-b.py"),
    ("a test directly in dev/tests/ fails", {"dev/tests/test-b.py": ""}, "dev/tests/test-b.py"),
    ("a test name used by two modules fails", {"dev/tests/scripts/test-a.py": ""}, "dev/tests/scripts/test-a.py"),
]:
    with tempfile.TemporaryDirectory() as d:
        for rel, body in {**LAYOUT_TREE, **changes}.items():
            write(d, rel, body)
        rc, out = run(d, "--only", "test-layout")
        ok = rc == 0 if bad is None else (
            rc == 1 and "%s:1: [test-layout]" % bad in out and out.count("[test-layout]") == 1)
        expect("test-layout: " + label, ok, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "test-layout")
expect("test-layout: the current tree passes", rc == 0, out)

# Dependency rules D1-D9 and the runtime-word lint (docs/specs/team.md §5, #1224): a clean tree passes,
# one file breaking each rule fails with that rule, a baseline row passes it and a stale row fails.
DEPS_TREE = {
    "roles/eng/builder/SKILL.md": "Claim the item, then report done (actions/README.md, protocols/eng/stages.md).\n",
    "protocols/eng/stages.md": "A builder claims work with the `claim` action (actions/README.md).\n",
    "actions/README.md": "# Actions\n",
    "core/lib.py": '"""Shared helpers; see docs/a.md. Never names tmux."""\nX = 1  # tmux, gh pr, docs/a.md\n',
    "environments/terminal/up.py": 'CORE = "core/lib.py"\nSESSION = ["tmux", "new-window"]\n',
    "harnesses/claude-code/adapter.py": 'FLAGS = ["--permission-mode", "auto"]\nCORE = "core/lib.py"\n',
    "connectors/github/repo.py": 'GH = ["gh", "pr", "view"]\n',
    "connectors/github/manifest.toml": "# Capabilities of each operation in docs/interfaces.md.\n[pack]\n",
    "cli/mdstack": '#!/usr/bin/env python3\n"""mdstack CLI (docs/a.md): dispatches through actions/README.md."""\n'
                'ACTIONS = "actions/README.md"\n',
    "docs/a.md": "Everything: roles/x, harnesses/claude-code/, tmux, inbox, `gh pr`, --permission-mode.\n",
    "dev/tests/core/test-a.py": 'X = ["tmux", "gh", "--yolo", "docs/a.md", "harnesses/x.py"]\n',
}
for rule, rel, body in [
    ("D1", "roles/eng/builder/SKILL.md", "Launch with harnesses/claude-code/adapter.py.\n"),
    ("D2", "protocols/eng/stages.md", "Render with core/crew-render.py.\n"),
    ("D3", "environments/terminal/up.py", 'HARNESS = "harnesses/crew-harness.py"\n'),
    ("D4", "core/lib.py", 'UP = "environments/terminal/up.py"\n'),
    ("D5", "harnesses/claude-code/adapter.py", 'PANE = ["tmux", "send-keys"]\n'),
    ("D5", "connectors/github/repo.py", 'NOTE = "write it to the inbox"\n'),
    ("D6", "environments/terminal/up.py", 'subprocess.run(["gh", "pr", "view"])\n'),
    ("D7", "environments/terminal/up.py", 'ARGV = ["claude", "--dangerously-skip-permissions"]\n'),
    ("D8", "cli/mdstack", '#!/usr/bin/env python3\nUP = "environments/terminal/up.py"\n'),
    # Imports and joined paths (#1264 review): a package import, a Path join and an os.path.join.
    ("D3", "environments/terminal/up.py", "from connectors.github import transport\n"),
    ("D4", "core/lib.py", "import harnesses.claude_code\n"),
    ("D4", "core/lib.py", "target = ROOT / 'harnesses' / 'crew-harness.py'\n"),
    ("D4", "core/lib.py", 'target = os.path.join(ROOT, "connectors", "github", "manifest.toml")\n'),
    ("D8", "cli/mdstack", "#!/usr/bin/env python3\nfrom pathlib import Path\n"
                       "target = Path(__file__).resolve().parent.parent / 'environments' / 'terminal' / 'crew.d'\n"),
    ("D9", "connectors/github/manifest.toml", 'commands = "docs/backends/github.md"\n'),
    ("D9", "harnesses/claude-code/adapter.py", 'GUIDE = open("docs/a.md").read()\n'),
    ("runtime-word", "roles/eng/builder/SKILL.md", "Append `done:` to your inbox.\n"),
    ("runtime-word", "protocols/eng/stages.md", "Hand off with `mdstack send`.\n"),
    ("runtime-word", "protocols/eng/stages.md", "Hand off with `crew send`.\n"),  # the deprecated name (#1233)
]:
    for baseline, want in [("", 1), ("%s\t%s\tknown coupling (#1)\n" % (rel, rule), 0)]:
        with tempfile.TemporaryDirectory() as d:
            for path, text in {**DEPS_TREE, rel: body, "scripts/deps-baseline.txt": baseline}.items():
                write(d, path, text)
            rc, out = run(d, "--only", "deps")
            ok = (rc == 0 and "[deps" not in out) if not want else (
                rc == 1 and ("%s:" % rel) in out and ("[deps] %s:" % rule) in out and out.count("[deps]") == 1)
            expect("deps: %s in %s (%s) %s" % (rule, rel, body.strip().splitlines()[-1][:48],
                                               "passes with a baseline row" if baseline else "fails"), ok, out)

with tempfile.TemporaryDirectory() as d:
    for path, text in DEPS_TREE.items():
        write(d, path, text)
    rc, out = run(d, "--only", "deps")
    expect("deps: a clean tree passes; prose, comments (Python and TOML), docstrings, docs/ and dev/ are free",
           rc == 0, out)
    write(d, "scripts/deps-baseline.txt", "core/lib.py\tD4\tfixed since (#1)\ncore/lib.py\tD9\n")
    rc, out = run(d, "--only", "deps")
    expect("deps: a stale baseline row and a row without a reason fail",
           rc == 1 and "scripts/deps-baseline.txt:1: [deps-baseline] core/lib.py no longer breaks D4" in out
           and "scripts/deps-baseline.txt:2: [deps-baseline] bad row" in out, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "deps")
expect("deps: the current tree passes with its baseline", rc == 0, out)

# Core memory (#1230): personal data and layout fail; the current tree passes.
with tempfile.TemporaryDirectory() as d:
    write(d, "memory/owner.md", "# Owner\n\n- Lead with the ask.\n")
    rc, out = run(d, "--only", "memory")
    expect("memory: a clean owner profile passes", rc == 0, out)
    write(d, "memory/owner.md", "# Owner\n\n- Write to owner@example.com.\n")
    write(d, "memory/extra.md", "x\n")
    rc, out = run(d, "--only", "memory")
    expect("memory: personal data and a stray file fail, routed to the knowledge connector",
           rc == 1 and "memory/owner.md:3: [memory-personal] email address: keep it in the knowledge connector" in out
           and "memory/extra.md:1: [memory-layout]" in out, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "memory")
expect("memory: the current tree passes", rc == 0, out)

# Role routines (#1247): actions and events outside the contract fail; the current tree passes.
ROUTINE = ('description = "d"\nskill = "digest"\nactions = [%s]\nschedule = { every = "1d" }\ninputs = []\n'
           'outputs = ["digest"]\ndeadline = "1h"\non_miss = "skip"\ndue_on = [%s]\n')
with tempfile.TemporaryDirectory() as d:
    write(d, "actions/README.md", "| Occurrence | Event type |\n|---|---|\n| Milestone closed | `dev.eng-crew.milestone.closed` |\n")
    write(d, "roles/ops/analyst/routines/digest.toml", ROUTINE % ('"read"', '"dev.eng-crew.milestone.closed"'))
    rc, out = run(d, "--only", "routines")
    expect("routines: a routine in the contract's vocabulary passes", rc == 0, out)
    write(d, "roles/ops/analyst/routines/digest.toml", ROUTINE % ('"crew-spawn"', '"milestone-closed"'))
    rc, out = run(d, "--only", "routines")
    expect("routines: an action and an event outside the contract fail",
           rc == 1 and "roles/ops/analyst/routines/digest.toml:1: [routines] actions: 'crew-spawn' is not an action" in out
           and "[routines] due_on: 'milestone-closed' is not an event type" in out, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "routines")
expect("routines: the current tree passes", rc == 0, out)

# Campaign scenarios (#1412): an unhandled assertion, a deleted required case and no origin/main fail.
def cgit(d, *args):
    subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True)


SC = "dev/tests/scripts/fixtures/campaign/"
with tempfile.TemporaryDirectory() as d:
    cgit(d, "init", "-q", "-b", "main")
    write(d, SC + "A01.json", '{"steps": [{"name": "a", "run": "true"}, {"name": "b", "run": "true"}]}')
    cgit(d, "add", "-A")
    cgit(d, "commit", "-qm", "base")
    rc, out = run(d, "--only", "campaign")
    expect("campaign: no origin/main fails closed",
           rc == 1 and "[campaign] cannot check retained cases: cannot find the merge base of origin/main" in out, out)
    cgit(d, "update-ref", "refs/remotes/origin/main", "HEAD")
    rc, out = run(d, "--only", "campaign")
    expect("campaign: kept cases pass", rc == 0, out)
    write(d, SC + "A01.json", '{"steps": [{"name": "a", "run": "test 1 = 2 && echo x; true"}]}')
    rc, out = run(d, "--only", "campaign")
    expect("campaign: an unhandled assertion and a deleted case fail",
           rc == 1 and SC.rstrip("/") + ":1: [campaign] A01/a: unhandled assertion" in out
           and "[campaign] A01/b: required case at" in out, out)

with tempfile.TemporaryDirectory() as d:
    cgit(d, "init", "-q", "-b", "main")
    write(d, SC + "A01.json", '{"steps": [{"name": "req", "run": "exit 1", "disposition": '
                              '{"state": "expected-fail", "reason": "waits for #9"}}]}')
    cgit(d, "add", "-A")
    cgit(d, "commit", "-qm", "base")
    cgit(d, "update-ref", "refs/remotes/origin/main", "HEAD")
    cgit(d, "rm", "-q", SC + "A01.json")
    cgit(d, "commit", "-qm", "removal")
    rc, out = run(d, "--only", "campaign")
    expect("campaign: deleting the whole scenario directory still fails (#1677 review)",
           rc == 1 and not os.path.isdir(os.path.join(d, SC)) and "[campaign] A01/req: required case at" in out, out)

rc, out = run(os.path.dirname(SCRIPTS), "--only", "campaign")
expect("campaign: the current tree passes", rc == 0, out)

if failed:
    print("test-check-repo: %d FAILED" % len(failed))
    sys.exit(1)
print("test-check-repo: all passed")
