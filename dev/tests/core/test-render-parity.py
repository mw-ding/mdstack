#!/usr/bin/env python3
"""Render parity for the Grok Bot templates and tmux reviewer brief (stdlib only).

Renders the real input tree (templates/) from profiles/default.toml, alone and
with the agentconnect example values, and diffs every runtime file against the
pre-conversion template text (fixtures/parity/pre/) filled in by plain string
replacement. Whitespace is normalized (trailing spaces, trailing blank lines).
Any diff fails. Placeholder table and backend mapping checks ride along.

The tmux reviewer uses a literal-command oracle in `fixtures/parity/tmux-reviewer.md.txt`.
Fixtures in `fixtures/parity/`. A seeded one-word drift fails; every placeholder
has a profile-key row and every operation a command in
`templates/backends/github.toml`. Run in CI.
"""
import contextlib
import difflib
import argparse
import importlib.util
import io
import json
import os
import re
import shlex
import shutil
import sys
import tempfile
import unittest

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
ROOT = os.path.dirname(SCRIPTS)
sys.path.insert(0, TESTS)  # crew_testlib
from crew_testlib import example_profile  # noqa: E402
spec = importlib.util.spec_from_file_location("crew_render", os.path.join(os.path.dirname(SCRIPTS), "core", "crew-render.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)
spec = importlib.util.spec_from_file_location("brief", os.path.join(os.path.dirname(SCRIPTS), "environments", "terminal", "crew.d", "brief.py"))
brief = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brief)

INPUTS = os.path.join(ROOT, "templates")
PRE = os.path.join(TESTS, "core", "fixtures", "parity", "pre")
DEFAULT_PROFILE = os.path.join(ROOT, "profiles", "default.toml")
EXAMPLE_PROFILE = os.path.join(TESTS, "core", "fixtures", "parity", "crew.toml")
# Placeholder -> value, written out by hand so the oracle does not reuse the renderer's map.
# Placeholders not listed render as written (the default profile's placeholder-valued keys).
DEFAULT_VALUES = {
    "flavor-name": "standard", "flavor-review": "thin", "flavor-validation": "behaviour",
    "flavor-evidence": "typed", "flavor-caps": "[3, 3]", "flavor-merge": "docs", "flavor-builder": "crew",
    "flavor-validation-scope": "bounded", "precheck-test": "`n/a`", "precheck-lint": "`n/a`",
    "max-active-milestones": "1",
    "control-item": "none", "runtime-id": "grok-bot@unconfigured",
    "default-branch": "main", "timezone": "UTC", "fallback-engine": "claude-code",
    "CoordinatorBot": "Ash", "BuilderBot": "Builder", "ReviewerBot": "Reviewer",
    "SynthesizerBot": "Synthesizer", "user-logins": "<user-login>",
    "CoordinatorTitle": "CTO", "CoordinatorEmoji": "🔥",
    "BuilderTitle": "Builder", "BuilderEmoji": "🛠️",
    "ReviewerTitle": "Reviewer-validator", "ReviewerEmoji": "🔎",
    "SynthesizerTitle": "Synthesizer", "SynthesizerEmoji": "🔀",
    "ResearcherBot": "Riley", "ResearcherTitle": "Researcher", "ResearcherEmoji": "🔬",
    "CoordinatorSignature": "— 🔥 Ash (CTO)", "BuilderSignature": "— 🛠️ Builder (Builder)",
    "ReviewerSignature": "— 🔎 Reviewer (Reviewer-validator)", "SynthesizerSignature": "— 🔀 Synthesizer (Synthesizer)",
    "ResearcherSignature": "— 🔬 Riley (Researcher)",
    "report-status": "✅ pass, 🔁 changes, 🚢 landed, ⛔ escalated, 🚧 blocked",
    "report-merge-status": "🚢 landed or 🚧 blocked",
}
EXAMPLE_VALUES = dict(DEFAULT_VALUES, **{
    "owner": "mw-ding", "repo": "agentconnect", "author-login": "mw-ding", "reviewer-login": "md-mt",
    "user-logins": 'mw-ding", "md-mt', "CoordinatorBot": "Ash", "BuilderBot": "Ben", "ReviewerBot": "Vera",
    "SynthesizerBot": "Sam", "BuilderSignature": "— 🛠️ Ben (Builder)",
    "ReviewerSignature": "— 🔎 Vera (Reviewer-validator)", "SynthesizerSignature": "— 🔀 Sam (Synthesizer)",
})
TOKEN = re.compile(r"<([^<>\s!/=-][^<>\n]*)>")
TITLE_EMOJI = re.compile(r"(?:🔥|🛠️|🔎|🔀|🔬) (?=\S+ · [A-Z])")  # a role post title's emoji, dropped by report.emoji = false


def normalize(text):
    return "\n".join(line.rstrip() for line in text.splitlines()).rstrip("\n").splitlines()


def expected(values):
    """{runtime/<name>: pre-conversion text with values filled in}."""
    out = {}
    for name in sorted(os.listdir(PRE)):
        with open(os.path.join(PRE, name), encoding="utf-8") as f:
            text = f.read()
        for key, value in values.items():
            text = text.replace("<%s>" % key, value)
        out[os.path.join("runtime", name[:-len(".txt")])] = text
    return out


def render(project, inputs, out):
    """Run the renderer; return (code, stdout)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
        code = cr.main(["--project", project, "--inputs", inputs, "--out", out])
    return code, buf.getvalue()


def parity_diff(project, values, inputs=INPUTS):
    """Unified diff (empty on parity) between the rendered runtime files and the filled pre-conversion text."""
    tmp = tempfile.mkdtemp()
    try:
        code, stdout = render(project, inputs, os.path.join(tmp, "out"))
        if code:
            return "render failed:\n" + stdout
        got = {}
        for d, dirs, names in os.walk(os.path.join(tmp, "out")):
            if os.path.relpath(d, os.path.join(tmp, "out")) == "runtime":
                dirs[:] = [name for name in dirs if name != "skills"]
            for name in names:
                path = os.path.join(d, name)
                with open(path, encoding="utf-8") as f:
                    got[os.path.relpath(path, os.path.join(tmp, "out"))] = f.read()
    finally:
        shutil.rmtree(tmp)
    want, diff = expected(values), []
    for rel in sorted(set(got) | set(want)):
        diff += difflib.unified_diff(normalize(want.get(rel, "")), normalize(got.get(rel, "")),
                                     "pre/" + rel, "rendered/" + rel, lineterm="")
    return "\n".join(diff)


class Parity(unittest.TestCase):
    def test_grok_express_falls_back_to_the_crew_lane(self):
        """An express-labelled imported item runs the crew lane on Grok Bot (#777): every flavor-resolving routine
        says so, and the coordinator re-records the normal flavor and removes crew:express before dispatch."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            with open(project, "w") as f:
                f.write('[runtime]\nname = "grok-bot"\n[triage]\nenabled = true\n')
            code, output = render(project, INPUTS, os.path.join(tmp, "out"))
            self.assertEqual(code, 0, output)
            texts = {}
            for name in ("builder-b1.md", "reviewer-validator.md", "reviewer-v2-watch.md", "synthesizer.md",
                         "wiring.md"):
                with open(os.path.join(tmp, "out", "runtime", name)) as f:
                    texts[name] = " ".join(f.read().split())
            for name, text in texts.items():
                with self.subTest(role=name):
                    self.assertNotIn("pass=selfgate", text)
                    if name != "wiring.md":
                        for rule in ("Treat a crew:express label or express item record as the crew lane",
                                     "never the express rule", "independent review and validation; approval lands",
                                     "to Ash to re-record the normal flavor"):
                            self.assertIn(rule, text)
                    if name not in ("wiring.md", "builder-b1.md"):  # #958
                        self.assertIn("scripts/crew-precheck.py (--item <issue#> when the PR closes exactly one issue)",
                                      text)
            for rule in ("Express stays an option on Grok Bot, not enabled",
                         "post a signed pass=flavor record naming the item's normal flavor",
                         "then remove `crew:express`", "`triage.enabled = true` installs no Grok timer",
                         "The researcher is never the triage host"):
                self.assertIn(rule, texts["wiring.md"])

    def test_grok_researcher_parent_handoff(self):
        """Grok Riley handoff (#780): one signed request, a fresh read-only worker with its actual engine, signature
        and mdstack brief run block, one signed finding, and a parent that verifies the URL before relaying the TL;DR.
        No listener, research gate or tmux command."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            with open(project, "w") as f:
                f.write('[runtime]\nname = "grok-bot"\n')
            code, output = render(project, INPUTS, os.path.join(tmp, "out"))
            self.assertEqual(code, 0, output)
            texts = {}
            for name in ("researcher.md", "wiring.md"):
                with open(os.path.join(tmp, "out", "runtime", name)) as f:
                    texts[name] = " ".join(f.read().split())
        brief, wiring = texts["researcher.md"], texts["wiring.md"]
        for rule in ("You are Riley, a fresh worker for one research request",
                     '"## This run" block from mdstack brief with Item, Pass and Base filled',
                     "Read-only on code: never push, build, review, validate or land", "You hold no gate.",
                     "newest signed Ash request comment on the source issue", "Post exactly one finding",
                     "🔬 Riley · Research · #<n>",
                     "<!-- crew:v1 role=researcher pass=research issue=<n> engine=<engine> model=<model> effort=<effort> -->",
                     "— 🔬 Riley (Researcher) · <harness> · <model>", "from the session that actually ran",
                     "never copy the planned engine", 'return "done: #<n> research <url>" to the parent turn',
                     "no routine, no listener and no research gate, and needs no tmux command"):
            with self.subTest(brief=rule):
                self.assertIn(rule, brief)
        for rule in ("### 2e. Researcher handoff", "Post one signed `Ash` request comment on the source issue",
                     "Start one fresh read-only worker from [researcher.md](researcher.md)",
                     'mdstack brief --item "issue #<n>" --pass research', '--engine "<engine> <model> <effort>"',
                     "naming the engine it will actually run", "one signed `🔬 Riley · Research · #<n>` finding",
                     "Verify the URL", "Then relay its TL;DR to the owner",
                     "No listener, routine, research gate or tmux command is involved"):
            with self.subTest(wiring=rule):
                self.assertIn(rule, wiring)
        for text in (brief, wiring):
            for tmux_only in ("mdstack spawn researcher", "$CREW_STATUS", "tmux new-window"):
                self.assertNotIn(tmux_only, text)
    def test_grok_cross_runtime_limits_documented(self):
        """The Grok binding declares its supported defaults, the tmux-only features and the #140 deferral
        provenance (#779), with no retroactive owner approval; the runbook points at it before wiring."""
        with open(os.path.join(ROOT, "docs", "runtimes", "grok-bot.md")) as f:
            binding = f.read()
        section = binding.split("## Cross-runtime limits", 1)[1].split("\n## ", 1)[0]
        text = " ".join(section.split())
        for rule in ("`docs`, the default", "CI-first: V2 wakes on `ci-passed`",
                     "Manual and immediate", "Red train: nothing lands, and the members merge one at a time",
                     "Option kept, not enabled", "### tmux-only", "`lone_pr_land = \"direct\"`",
                     "Forge-less remote test runner", "Crew scheduler and role leads",
                     "Reaping idle or terminal windows", "Triage timer and sweep",
                     "the tested-with-default-branch gate is never waived",
                     "It adds no owner approval after the fact"):
            self.assertIn(rule, text)
        rows = {m.group(1): m.group(2) for m in re.finditer(r"^\| \[#(\d+)\]\([^)]*\) \|(.*)$", section, re.M)}
        for pr in ("418", "425"):
            self.assertIn("Gap: no deferral record", rows[pr])
        for pr in ("402", "428", "433", "436"):
            self.assertIn("N/A: no Grok template, protocol or roles change", rows[pr])
        with open(os.path.join(ROOT, "docs", "runbooks", "grok-onboarding.md")) as f:
            self.assertIn("runtimes/grok-bot.md#cross-runtime-limits", f.read())

    def test_flavor_gate_contract_in_rendered_roles(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, names in (
                ("tmux", ("builder.md", "reviewer.md", "synthesizer.md")),
                ("grok-bot", ("builder-b1.md", "builder-b2.md", "reviewer-v2-watch.md", "synthesizer.md")),
                ("session", ("builder.md", "reviewer.md", "synthesizer.md")),  # #914
            ):
                project = os.path.join(tmp, "crew.toml")
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "%s"\n[flavor]\nname = "fast"\n' % runtime)
                out = os.path.join(tmp, runtime)
                code, output = render(project, INPUTS, out)
                self.assertEqual(code, 0, output)
                for name in names:
                    with self.subTest(runtime=runtime, role=name):
                        with open(os.path.join(out, "runtime", name)) as f:
                            text = " ".join(f.read().split())
                        for rule in ("newest signed item pass=flavor record",
                                     "including both rename paths",
                                     "knob-wise strictest item/path rigor",
                                     "missing record means thorough",
                                     "Unreadable resolution blocks",
                                     "never waives CI, holds or F1–F7"):
                            self.assertIn(rule, text)
                        if "reviewer" in name:
                            for rule in ("pass=validate verdict=pass marker plus validation=skipped",
                                         "a failed validation never becomes a skip",
                                         "mixed rigor lists knobs and omits it"):
                                self.assertIn(rule, text)
                        if "synthesizer" in name:
                            for rule in ("Until follow-up B, existing recorded owner grants retain their scope regardless of merge mode.",
                                         "eligible under the live knobs",
                                         "An older verdict must still satisfy any tightening",
                                         "recorded, time-boxed owner grant"):
                                self.assertIn(rule, text)

    def test_landing_authority_contract_in_all_runtime_briefs(self):
        with open(os.path.join(TESTS, "core", "fixtures", "parity", "landing-authority.json")) as f:
            rules = json.load(f)
        with open(os.path.join(TESTS, "core", "fixtures", "parity", "landing-authority-reference.json")) as f:
            reference = json.load(f)
        with open(os.path.join(ROOT, "docs", "protocol.md")) as f:
            protocol = " ".join(f.read().split("### Land rules and merge trains", 1)[1].split())
        for rule in reference["protocol"]:
            self.assertIn(rule, protocol)
        with tempfile.TemporaryDirectory() as tmp:
            for runtime in ("tmux", "grok-bot", "session"):
                project = os.path.join(tmp, "crew.toml")
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "%s"\n' % runtime)
                out = os.path.join(tmp, "out", runtime)
                code, output = render(project, INPUTS, out)
                self.assertEqual(code, 0, output)
                for name in os.listdir(os.path.join(out, "runtime")):
                    if not name.startswith(("coordinator", "synthesizer")):
                        continue
                    with open(os.path.join(out, "runtime", name)) as f:
                        raw = f.read()
                    self.assertLessEqual(len(raw.encode("utf-8")), 16384, (runtime, name))
                    text = " ".join(raw.split())
                    brief_rules = rules if runtime == "grok-bot" else reference["brief"]
                    for rule in brief_rules:
                        self.assertIn(rule, text, (runtime, name))
                    if runtime == "grok-bot" and name == "coordinator-steering-dispatcher.md":
                        self.assertIn("resume-landing: record stop-id on that same landing-control issue, "
                                      "then wake the synthesizer", text)

    def test_policy_fragment_edit_reaches_every_including_render(self):  # #1184
        """Each templates/policy fragment is included by a runtime template; a one-line edit to it changes
        exactly the renders of the templates that include it, in every runtime."""
        include = re.compile(r"^<include:(policy/[^>]+)>$", re.M)
        users = {}
        for runtime in ("tmux", "session", "grok-bot"):
            for name in sorted(os.listdir(os.path.join(INPUTS, "runtimes", runtime))):
                if name.endswith(".md"):
                    with open(os.path.join(INPUTS, "runtimes", runtime, name), encoding="utf-8") as f:
                        for frag in include.findall(f.read()):
                            users.setdefault(frag, set()).add((runtime, name))
        fragments = {os.path.relpath(os.path.join(d, n), INPUTS) for d, _, names in os.walk(os.path.join(INPUTS, "policy"))
                     for n in names if n != "SKILL.md" and (n != "README.md" or d != os.path.join(INPUTS, "policy"))}
        self.assertEqual(sorted(fragments), sorted(users))
        self.assertTrue(all(len(u) > 1 for u in users.values()), users)
        with tempfile.TemporaryDirectory() as tmp:
            inputs = os.path.join(tmp, "templates")
            shutil.copytree(INPUTS, inputs)
            for frag in sorted(users):
                with open(os.path.join(inputs, frag), "a", encoding="utf-8") as f:
                    f.write("Sentinel %s.\n" % frag)
            for runtime in ("tmux", "session", "grok-bot"):
                project = os.path.join(tmp, runtime + ".toml")
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "%s"\n' % runtime
                            + ("options = { researchers = 1 }\n" if runtime == "session" else ""))  # #1724: opt-in sweep
                code, output = render(project, inputs, os.path.join(tmp, "out", runtime))
                self.assertEqual(code, 0, output)
                for name in os.listdir(os.path.join(inputs, "runtimes", runtime)):
                    if not name.endswith(".md"):
                        continue
                    with open(os.path.join(tmp, "out", runtime, "runtime", name), encoding="utf-8") as f:
                        text = f.read()
                    for frag, where in users.items():
                        self.assertEqual(text.count("Sentinel %s." % frag), int((runtime, name) in where),
                                         (runtime, name, frag))

    def test_role_skills_use_agent_skills_format(self):  # #1221, docs/specs/team.md REQ-04
        """Each role directory under templates/policy has an entry SKILL.md; every SKILL.md has name and
        description front matter, name equal to its directory; every link resolves and every role fragment
        is linked from that role's skills."""
        policy = os.path.join(INPUTS, "policy")
        roles = sorted(n for n in os.listdir(policy) if os.path.isdir(os.path.join(policy, n)) and n != "shared")
        self.assertEqual(roles, ["builder", "coordinator", "researcher", "reviewer", "synthesizer"])
        for role in roles:
            skills = [os.path.join(d, "SKILL.md") for d, _, names in os.walk(os.path.join(policy, role))
                      if "SKILL.md" in names]
            self.assertIn(os.path.join(policy, role, "SKILL.md"), skills)
            linked = set()
            for path in skills:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                match = re.match(r"---\nname: ([a-z0-9-]+)\ndescription: ([^\n]+)\n---\n", text)
                self.assertTrue(match, path)
                self.assertEqual(match.group(1), os.path.basename(os.path.dirname(path)), path)
                self.assertNotIn(": ", match.group(2), path)  # a YAML plain scalar
                for link in re.findall(r"\]\(([^)#]+)", text):
                    target = os.path.normpath(os.path.join(os.path.dirname(path), link))
                    self.assertTrue(os.path.exists(target), (path, link))
                    linked.add(target)
            fragments = {os.path.join(policy, role, n) for n in os.listdir(os.path.join(policy, role))
                         if n.endswith(".md") and n != "SKILL.md"}
            self.assertEqual(sorted(fragments - linked), [], role)

    def test_tmux_merge_up_recheck_contract(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        code, stdout = render(example_profile(tmp), INPUTS, tmp)
        self.assertEqual(code, 0, stdout)
        with open(os.path.join(TESTS, "core", "fixtures", "parity", "merge-up-recheck.json")) as f:
            contract = json.load(f)
        for name, rules in contract.items():
            with open(os.path.join(tmp, "runtime", name + ".md")) as f:
                text = " ".join(f.read().split())
            for rule in rules:
                self.assertIn(rule, text, name)

    def test_grok_dispatch_appends_crew_brief(self):  # #778
        """B1, B2 and V2 build every build, fix, review and validate worker turn's run block with mdstack brief."""
        parser = argparse.ArgumentParser()
        brief.register(parser.add_subparsers())
        labels = ["Item", "Pass", "Round", "Worktree", "Base", "Engine", "Claim"]
        with tempfile.TemporaryDirectory() as tmp:
            code, output = render(DEFAULT_PROFILE, INPUTS, tmp)
            self.assertEqual(code, 0, output)
            for name, passes in (("builder-b1.md", ["build"]), ("builder-b2.md", ["fix"]),
                                 ("reviewer-v2-watch.md", ["review", "validate"])):
                with open(os.path.join(tmp, "runtime", name)) as f:
                    text = " ".join(f.read().split())
                self.assertIn('Append its "## This run" block verbatim to the worker prompt; '
                              "never hand-write run parameters.", text, name)
                command = re.search(r"cli/mdstack brief (.*?--worktree \S+)", text).group(1)
                for pass_ in passes:
                    with self.subTest(role=name, pass_=pass_):
                        filled = re.sub(r"<[^<>]+>", "x", command.replace("<pass>", pass_)).rstrip(",")
                        args = parser.parse_args(["brief"] + shlex.split(filled))
                        block = brief.run_block([(label, getattr(args, flag)) for flag, label in brief.FIELDS])
                        self.assertEqual([line[2:].split(":")[0] for line in block.splitlines()[3:]], labels)
                        self.assertIn("- Pass: %s\n" % pass_, block)
                if "reviewer" in name:
                    self.assertIn("Review and validation each run in a fresh, independent session: neither "
                                  "reuses the builder's conversation or the other pass's session, and the "
                                  "validation prompt never carries the review output.", text)

    def test_coordinator_milestone_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, brief in (("tmux", "coordinator.md"), ("grok-bot", "wiring.md"), ("session", "coordinator.md")):
                for settings, limit in (("", 1), ("max_active_milestones = 2", 2)):
                    with self.subTest(runtime=runtime, limit=limit):
                        project = os.path.join(tmp, "crew.toml")
                        with open(project, "w") as f:
                            f.write('[runtime]\nname = "%s"\n[runtime.options]\n%s\n' % (runtime, settings))
                        out = os.path.join(tmp, "out")
                        code, output = render(project, INPUTS, out)
                        self.assertEqual(code, 0, output)
                        with open(os.path.join(out, "runtime", brief)) as f:
                            text = " ".join(f.read().split())
                        self.assertIn('max_active_milestones = %d' % limit, text)
                        self.assertIn('Dispatch new builds from at most %d open milestones, in milestone order' % limit, text)
                        for rule in ("The earliest active milestone keeps priority",
                                     "A later milestone only fills builder capacity the earlier one cannot use",
                                     "remaining items are blocked by dependencies or already in flight",
                                     "In-flight PRs in any milestone still finish"):
                            self.assertIn(rule, text)

    def test_coordinator_plan_gate(self):  # #444, #396
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, brief in (("tmux", "coordinator.md"), ("grok-bot", "wiring.md"), ("session", "coordinator.md")):
                with self.subTest(runtime=runtime):
                    project = os.path.join(tmp, "crew.toml")
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "%s"\n' % runtime)
                    out = os.path.join(tmp, "out-" + runtime)
                    code, output = render(project, INPUTS, out)
                    self.assertEqual(code, 0, output)
                    with open(os.path.join(out, "runtime", brief)) as f:
                        text = " ".join(f.read().split())
                    for rule in ("Plan gate (protocol §6): new `crew:ready` or builds only for items in an "
                                 "owner-approved milestone or project with a signed `cmd=plan-ok` record;",
                                 '"start building" means propose a plan and wait.',
                                 "Exempt: fix, CI and follow-ups on approved work; owner-requested trivial docs.",
                                 "Platform items need the §6 preflight."):
                        self.assertIn(rule, text)
        with open(os.path.join(ROOT, "docs", "protocol.md"), encoding="utf-8") as f:
            protocol = f.read()
        gate = protocol[protocol.index("**Plan gate (#444, #396).**"):protocol.index("**Metrics gate.**")]
        self.assertIn("`<CoordinatorEmoji> <CoordinatorBot> · Steer · plan approved: <plan>`", gate)
        self.assertIn("`<!-- crew:v1 role=coordinator pass=steer cmd=plan-ok plan=<milestone-or-project-id> "
                      "cmd-id=<source-id> sha=<default-branch-head> round=n/a verdict=n/a -->`", gate)
        flat = " ".join(gate.split())
        for rule in ("is a request to propose a plan, never approval", "adding an item needs a new record",
                     "An unreadable record means no approval", "items come only from settled decisions",
                     "An unknown or incompatible fact blocks readiness"):
            self.assertIn(rule, flat)
        with open(os.path.join(ROOT, "templates", "spec.md"), encoding="utf-8") as f:
            spec = f.read()
        self.assertIn("## Target environment (verified on <YYYY-MM-DD>)", spec)
        self.assertIn("## Owner prerequisites", spec)

    def test_coordinator_spec_bookends(self):  # #259
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, brief in (("tmux", "coordinator.md"), ("grok-bot", "wiring.md"), ("session", "coordinator.md")):
                with self.subTest(runtime=runtime):
                    project = os.path.join(tmp, "crew.toml")
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "%s"\n' % runtime)
                    out = os.path.join(tmp, "out-" + runtime)
                    code, output = render(project, INPUTS, out)
                    self.assertEqual(code, 0, output)
                    with open(os.path.join(out, "runtime", brief)) as f:
                        text = " ".join(f.read().split())
                    for rule in ("Spec bookends (roles.md): a milestone opens with its spec slice",
                                 "its other items wait for that to merge.",
                                 "It closes with a status-sync slice:",
                                 "every landed or superseded item closed.",
                                 "The milestone closes after that merges."):
                        self.assertIn(rule, text)
        with open(os.path.join(ROOT, "docs", "roles.md"), encoding="utf-8") as f:
            roles = " ".join(f.read().split())
        for rule in ("**Spec bookends (#259).** Every milestone opens with a spec slice",
                     "The milestone closes only after that slice merges.",
                     "This adds no merge permission"):
            self.assertIn(rule, roles)

    def test_tmux_lone_land_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(TESTS, "core", "fixtures", "parity", "lone-land.json")) as f:
                contract = json.load(f)
            for policy in ("train", "direct"):
                project = os.path.join(tmp, "crew.toml")
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "tmux"\n[runtime.options]\nlone_pr_land = "%s"\n' % policy)
                out = os.path.join(tmp, "out")
                code, output = render(project, INPUTS, out)
                self.assertEqual(code, 0, output)
                for name, rules in contract.items():
                    with open(os.path.join(out, "runtime", name + ".md")) as f:
                        text = " ".join(f.read().split())
                    self.assertIn('lone_pr_land = "%s"' % policy, text)
                    for rule in rules:
                        self.assertIn(rule, text, name)

    def assertParity(self, diff):
        if diff:
            self.fail("rendered text differs from the pre-conversion text:\n" + diff)

    def test_default_profile_parity(self):
        self.assertParity(parity_diff(DEFAULT_PROFILE, DEFAULT_VALUES))

    def test_example_values_parity(self):
        self.assertParity(parity_diff(EXAMPLE_PROFILE, EXAMPLE_VALUES))

    def test_tmux_reviewer_parity(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output = render(example_profile(tmp), INPUTS, tmp)
            self.assertEqual(code, 0, output)
            with open(os.path.join(TESTS, "core", "fixtures", "parity", "tmux-reviewer.md.txt")) as f:
                expected_text = f.read().replace("<ReviewerBot>", "Vera").replace("<hold-label-blocks>", "true")
                for key, value in DEFAULT_VALUES.items():
                    if key.startswith(("flavor-", "precheck-")):
                        expected_text = expected_text.replace("<" + key + ">", value)
            with open(os.path.join(tmp, "runtime", "reviewer.md")) as f:
                self.assertEqual(normalize(f.read()), normalize(expected_text))

    def test_role_briefs_keep_markers_and_carry_the_report_headline(self):  # #431 AC1-3, #1291
        """Every builder, reviewer, synthesizer, coordinator and researcher brief carries the report-skeleton headline
        rule with the profile's statuses, and emoji off, a team and custom statuses change no crew:v1 marker line and
        no line outside signatures/status."""
        marker = re.compile(r"<!-- crew:v1 [^\n]*-->")
        roles = ("builder", "reviewer", "synthesizer", "coordinator", "researcher")
        with tempfile.TemporaryDirectory() as tmp:
            for runtime in ("tmux", "grok-bot", "session"):
                briefs = {}
                for mode, extra in (("plain", ""), ("custom", '\n[identities]\nteam = "md"\n\n[report]\nemoji = false\n'
                                                              'status = { pass = "P" }\n'),
                                    ("status", '\n[report]\nstatus = { pass = "P", landed = "L", blocked = "B" }\n')):
                    project = os.path.join(tmp, "%s-%s.toml" % (runtime, mode))
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "%s"\n%s' % (runtime, extra))
                    out = os.path.join(tmp, "out", runtime, mode)
                    code, output = render(project, INPUTS, out)
                    self.assertEqual(code, 0, output)
                    for name in os.listdir(os.path.join(out, "runtime")):
                        if name.startswith(roles) and "-lead" not in name and name.endswith(".md"):
                            with open(os.path.join(out, "runtime", name), encoding="utf-8") as f:
                                briefs.setdefault(name, {})[mode] = f.read()
                self.assertTrue(briefs, runtime)
                briefs = {name: text for name, text in briefs.items() if "Sign every" in text["plain"]}
                self.assertTrue(briefs, runtime)
                for name, text in briefs.items():
                    with self.subTest(runtime=runtime, brief=name):
                        self.assertIn("roles.md skeleton", text["plain"])
                        full = "✅ pass, 🔁 changes, 🚢 landed, ⛔ escalated, 🚧 blocked" in text["plain"]
                        self.assertTrue(full or "🚢 landed or 🚧 blocked" in text["plain"])  # merge statuses only
                        self.assertIn("P pass, 🔁 changes, L landed, ⛔ escalated, B blocked" if full
                                      else "L landed or B blocked", text["status"])
                        self.assertIn("pass, changes, landed, escalated, blocked" if full
                                      else "landed or blocked", text["custom"])
                        self.assertEqual(marker.findall(text["custom"]), marker.findall(text["plain"]))
                        self.assertEqual(marker.findall(text["status"]), marker.findall(text["plain"]))
                        for plain, custom in zip(text["plain"].splitlines(), text["custom"].splitlines()):
                            if plain != custom and TITLE_EMOJI.sub("", plain) != custom:  # emoji-off titles (#1946)
                                self.assertRegex(plain, r"^`?— \S+ \S+ \([^)]*\) · <harness>|✅ pass|🚢 landed or", (plain, custom))
                                self.assertRegex(custom, r"^`?— \S+ \([^)]*\) · md · <harness>|(^| )pass, changes|[ (]landed or", (plain, custom))

    def test_seeded_one_word_drift_fails(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        inputs = os.path.join(tmp, "templates")
        shutil.copytree(INPUTS, inputs)
        path = os.path.join(inputs, "runtimes", "grok-bot", "synthesizer.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Guard first", text)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text.replace("Guard first", "Guard last", 1))
        diff = parity_diff(EXAMPLE_PROFILE, EXAMPLE_VALUES, inputs)
        self.assertIn("-Guard first", diff)
        self.assertIn("+Guard last", diff)

    def test_inputs_default_to_templates(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", DEFAULT_PROFILE, "--out", tmp])
        self.assertEqual(code, 0, buf.getvalue())
        self.assertEqual(sorted(os.listdir(os.path.join(tmp, "runtime"))),
                         sorted([n[:-len(".txt")] for n in os.listdir(PRE)] + ["skills"]))

    def test_every_operation_maps_from_backend_file(self):
        values, problems = cr.resolve(DEFAULT_PROFILE, None)
        self.assertEqual(problems, [])
        renderer = cr.Renderer(values, INPUTS)
        mapping = renderer.table(os.path.join(INPUTS, "backends", "github.toml"))
        conditional = cr.crew_config.CONDITIONAL_OPERATIONS
        runtime_run = dict(cr.crew_config.STATUS_OPERATIONS, ids=["status-destination"])  # not <op:> tokens (#1313)
        self.assertEqual({c: sorted(t) for c, t in mapping.items() if c in runtime_run},
                         {c: sorted(ops) for c, ops in runtime_run.items()})
        self.assertEqual({c: sorted(set(t) - set(conditional.get(c, []))) for c, t in mapping.items()
                          if c not in runtime_run},
                         {c: sorted(ops) for c, ops in cr.crew_config.OPERATIONS.items()})
        for concern, ops in cr.crew_config.OPERATIONS.items():
            for op in ops:
                self.assertTrue(renderer.line("<op:%s.%s>" % (concern, op)).strip(), op)

    def test_verdict_state_tag_commands_render_on_one_line(self):  # #823
        with tempfile.TemporaryDirectory() as tmp:
            code, output = render(example_profile(tmp), INPUTS, tmp)
            self.assertEqual(code, 0, output)
            with open(os.path.join(tmp, "runtime", "reviewer.md")) as f:
                text = f.read()
        for tag, others in (("approved", ("in-review", "changes")), ("changes", ("in-review", "approved"))):
            line = next(ln for ln in text.splitlines() if "--add-label crew:%s " % tag in ln)
            for other in others:
                self.assertIn("--remove-label crew:%s" % other, line)

    def test_placeholder_table_maps_every_placeholder(self):
        """Every token in the input tree has a templates/README.md row; its profile key matches the renderer."""
        with open(os.path.join(INPUTS, "README.md"), encoding="utf-8") as f:
            text = f.read().split("## Placeholders", 1)[1].split("\n## ", 1)[0]
        rows = {}
        for line in text.splitlines():
            if line.startswith("| `<"):
                cells = re.split(r"(?<!\\)\|", line)
                for name in re.findall(r"`<([^`]+)>`", cells[1]):
                    rows[name.replace("\\|", "|")] = cells[3]
        used = set()
        for d, _, names in [w for sub in ("core", "runtimes", "backends", "policy") for w in os.walk(os.path.join(INPUTS, sub))]:
            for name in names:
                path = os.path.join(d, name)
                if path == os.path.join(INPUTS, "policy", "README.md"):  # prose about fragments, never rendered
                    continue
                if name.endswith(".toml"):  # only the command values render, not the comments
                    text = "\n".join(v for t in cr.Renderer(None, None).table(path).values() for v in t.values())
                else:
                    with open(path, encoding="utf-8") as f:
                        text = f.read()
                for token in TOKEN.findall(text):
                    if token.startswith("include:policy/"):  # a whole-line fragment include (#1184)
                        self.assertTrue(os.path.isfile(os.path.join(INPUTS, token[len("include:"):])), token)
                    elif token.startswith("include:"):
                        self.assertIn(token, ("include:docs/protocol.md", "include:docs/roles.md",
                                              "include:docs/roles.md#pr-conventions"))
                    elif token.startswith("strategy:"):  # a line prefix, not a placeholder (#952)
                        self.assertIn(token, ("strategy:merge", "strategy:rebase"))
                    elif token.startswith("control-item:"):  # a block marker line, not a placeholder (#914)
                        self.assertIn(token, ("control-item:set", "control-item:none", "control-item:end"))
                    elif token.startswith("session-backend:"):  # a block marker line, not a placeholder (#1052)
                        self.assertIn(token, ("session-backend:hosted", "session-backend:local", "session-backend:end"))
                    elif token.startswith("isolation:"):  # a block marker line, not a placeholder (#1959)
                        self.assertIn(token, ("isolation:worktree", "isolation:assigned-checkout", "isolation:end"))
                    elif token.startswith("title:"):  # a role post title head (#1946)
                        self.assertRegex(token, r"^title:(coordinator|builder|reviewer|synthesizer|researcher)/[a-z-]+$")
                    elif not token.startswith("op:"):
                        used.add(token)
        self.assertEqual(sorted(used - set(rows)), [])
        for name, cell in rows.items():
            if name in cr.MAPPED:
                for key in cr.MAPPED[name]:
                    self.assertIn("`%s`" % key, cell, name)
            else:
                self.assertIn(name, cr.KEPT)
                self.assertIn("none (run-time)", cell, name)


if __name__ == "__main__":
    unittest.main()
