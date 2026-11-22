#!/usr/bin/env python3
"""Golden-file tests for core/crew-render.py (stdlib only).

Covers the renderer on a fixture profile and inputs in `fixtures/render/`
(expected tree, unknown-placeholder failure, missing mapping, unsupported
capability), the real tmux briefs rendered from `profiles/tmux.toml` against
`fixtures/render/tmux/`, a pack's render/ overlay, declared placeholders and render-time notes (#580),
and core memory in every role brief, inside a fenced routine prompt, left out of the size-budget render and
failing closed on a lint problem (#1230), read once per render at the remote default tip, named on stderr,
in session briefs too and refusing a failed fetch (#1537), and the per-brief size_budget headroom lines and warning band (#1056).
Run in CI.
"""
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # dev/tests/: crew_testlib
from crew_testlib import example_profile, render_template, write_pack

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
spec = importlib.util.spec_from_file_location("crew_render", os.path.join(os.path.dirname(SCRIPTS), "core", "crew-render.py"))
cr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cr)

FIX = os.path.join(TESTS, "fixtures", "render")
PROJECT = os.path.join(FIX, "crew.toml")


def tree(root):
    """{relative path: text} for every file under root."""
    out = {}
    for d, _, names in os.walk(root):
        for name in names:
            path = os.path.join(d, name)
            with open(path, encoding="utf-8") as f:
                out[os.path.relpath(path, root)] = f.read()
    return out


class Render(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.inputs = os.path.join(self.tmp, "inputs")
        self.out = os.path.join(self.tmp, "out")
        shutil.copytree(os.path.join(FIX, "inputs"), self.inputs)

    def overlay(self, rel, text):
        with open(os.path.join(self.inputs, rel), "w", encoding="utf-8") as f:
            f.write(text)

    def render(self, project=PROJECT):
        """Run the renderer on the fixture profile; return (code, stdout lines with tmp paths stripped)."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--inputs", self.inputs, "--out", self.out])
        return code, [ln.replace(self.tmp + os.sep, "") for ln in out.getvalue().splitlines()]

    def assertFails(self, expected):
        code, out = self.render()
        self.assertEqual(code, 1)
        self.assertEqual(out, expected)
        self.assertFalse(os.path.exists(self.out), "nothing is written on failure")

    def test_golden_tree(self):
        code, _ = self.render()
        self.assertEqual(code, 0)
        expected = tree(os.path.join(FIX, "expected"))
        got = tree(self.out)
        self.assertEqual(sorted(got), sorted(expected))
        for rel, text in expected.items():
            self.assertEqual(got[rel], text, rel)

    def test_budget_headroom_lines_and_warning_band(self):  # #1056
        def run(budget):
            project = os.path.join(self.tmp, "budget.toml")
            with open(PROJECT, encoding="utf-8") as f, open(project, "w", encoding="utf-8") as g:
                g.write(f.read() + ("\n[size_budget]\nbuilder = %d\n" % budget if budget else ""))
            shutil.rmtree(self.out, ignore_errors=True)
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cr.main(["--project", project, "--inputs", self.inputs, "--out", self.out])
            return code, out.getvalue(), err.getvalue().splitlines()

        code, out, err = run(None)
        self.assertEqual(code, 0)
        self.assertNotIn("budget", out, "stdout still lists only written paths")
        self.assertIn("crew-render: budget briefs/builder.md 379/16384 bytes (2%), delivered 387 bytes", err)
        self.assertIn("crew-render: budget runtime/builder-intake.md 216/16384 bytes (1%), delivered 216 bytes", err)
        self.assertEqual(len([ln for ln in err if ln.startswith("crew-render: budget ")]), 6, err)
        self.assertFalse([ln for ln in err if "WARNING" in ln], err)
        warn = "crew-render: WARNING briefs/builder.md is within 5%% of the builder size_budget (%d bytes left)"
        for budget, expected in ((399, None), (398, warn % 19), (379, warn % 0),
                                 (378, "crew-render: WARNING briefs/builder.md is 1 bytes over the builder size_budget")):
            code, _, err = run(budget)
            self.assertEqual(code, 0, "warnings never change the exit code")
            self.assertEqual([ln for ln in err if "WARNING" in ln], [expected] if expected else [], budget)

    def test_placeholders_follow_registry_identity_keys(self):
        roles = {key: dict(value, identity_key="identities.custom_" + key) for key, value in cr.ROLES.items()}
        load = cr.tomllib.load

        def registry_load(file):
            role = os.path.basename(file.name)[:-5]
            return roles[role] if os.path.dirname(file.name) == cr.crew_config.ROLES_DIR else load(file)

        spec = importlib.util.spec_from_file_location("registry_renderer", os.path.join(os.path.dirname(SCRIPTS), "core", "crew-render.py"))
        renderer = importlib.util.module_from_spec(spec)
        with patch("tomllib.load", side_effect=registry_load):
            spec.loader.exec_module(renderer)
        self.assertEqual(renderer.ROLES, roles)
        values = {metadata["identity_key"] + "." + field: role + "-" + field
                  for role, metadata in roles.items() for field in ("name", "title", "emoji")}
        values.update({metadata["identity_key"] + ".gh_user": "reviewer" if "identity_independent_of" in metadata else "author"
                       for metadata in roles.values()})
        fill = renderer.Renderer(values, self.inputs)
        for role in roles:
            self.assertEqual(fill.line("<%sBot> <%sTitle> <%sEmoji>" % ((role.title(),) * 3)),
                             "%s-name %s-title %s-emoji" % ((role,) * 3))
        self.assertEqual(fill.line("<author-login> <reviewer-login>"), "author reviewer")

    def test_team_name_placeholder_empty_when_unset(self):  # #1329
        values = cr.resolve(PROJECT, None)[0]
        self.assertNotIn("identities.team", values)
        self.assertEqual(cr.Renderer(values, self.inputs).line("[<TeamName>]"), "[]")
        self.assertEqual(cr.Renderer(dict(values, **{"identities.team": "mdp-m4"}), self.inputs).line("[<TeamName>]"),
                         "[mdp-m4]")

    def test_signature_and_status_placeholders(self):  # #431, #1291: team, legacy, emoji off and custom cases
        values = cr.resolve(PROJECT, None)[0]
        line = "<BuilderSignature> · <harness> | <report-status> | [<ReviewerEmoji>]"
        status = "✅ pass, 🔁 changes, 🚢 landed, ⛔ escalated, 🚧 blocked"
        cases = [({}, "— 🛠️ %s (%s) · <harness> | %s | [🔎]" % ("%s", "%s", status)),
                 ({"team.name": "md"}, "— 🛠️ %s (%s) · md · <harness> | %s | [🔎]" % ("%s", "%s", status)),
                 ({"identities.team": "mdp-m4"}, "— 🛠️ %s (%s) · mdp-m4 · <harness> | %s | [🔎]" % ("%s", "%s", status)),
                 ({"report.emoji": False, "team.name": "md"},
                  "— %s (%s) · md · <harness> | pass, changes, landed, escalated, blocked | []"),
                 ({"identities.builder.emoji": "B", "report.status.pass": "P", "report.status.blocked": ""},
                  "— B %s (%s) · <harness> | %s | [🔎]" % ("%s", "%s", status.replace("✅", "P").replace("🚧 ", "")))]
        for extra, want in cases:
            got = cr.Renderer(dict(values, **{"identities.builder.emoji": "🛠️", **extra}), self.inputs).line(line)
            self.assertEqual(got, want % (values["identities.builder.name"], values["identities.builder.title"]), extra)
        researcher = cr.Renderer(values, self.inputs).line("<ResearcherSignature>")
        self.assertEqual(researcher, "— 🔬 Riley (Researcher)")

    def test_precheck_enabled_disabled_and_missing_commands(self):
        with open(PROJECT, encoding="utf-8") as f:
            profile = f.read()
        project = os.path.join(self.tmp, "crew.toml")
        for settings in ('enabled = false\nlint = "do-lint"', 'enabled = true',
                         'enabled = true\nlint = "do-lint"\ntest = "do-test"\ndocs = "do-docs"\nmax_fix_attempts = 3',
                         'enabled = true\nlint = " "\ntest = ""'):
            with open(project, "w", encoding="utf-8") as f:
                f.write(profile + '\n[builder.precheck]\n' + settings + '\n')
            code, output = self.render(project)
            self.assertEqual(code, 0, output)
            got = tree(self.out)
            if 'enabled = false' in settings:
                self.assertEqual(got, tree(os.path.join(FIX, "expected")))
                continue
            brief = got["briefs/builder.md"]
            self.assertIn("## Builder pre-review check", brief)
            self.assertIn("`pass=precheck` at the final full head SHA", brief)
            for step in range(1, 8):
                self.assertIn("\n%d. " % step, brief)
            if "do-lint" in settings:
                for command in ("do-lint", "do-test", "do-docs"):
                    self.assertIn("```sh\n%s\n```" % command, brief)
                self.assertIn("at most 3 fix attempts", brief)
            else:
                for label in ("Lint / format", "Tests / build", "Docs command"):
                    self.assertIn(label + ": `n/a` (no configured command)", brief)
                self.assertIn("at most 2 fix attempts", brief)
            for name in ("coordinator", "reviewer", "synthesizer"):
                self.assertNotIn("## Builder pre-review check", got["briefs/%s.md" % name])

    def test_precheck_owners_adds_scope_step_only_when_set(self):
        with open(PROJECT, encoding="utf-8") as f:
            profile = f.read()
        project = os.path.join(self.tmp, "crew.toml")
        for owners, present in (('', False), ('owners = "tool owning-tests --path"', True)):
            with open(project, "w", encoding="utf-8") as f:
                f.write(profile + '\n[builder.precheck]\nenabled = true\ntest = "do-test"\n' + owners + '\n')
            code, output = self.render(project)
            self.assertEqual(code, 0, output)
            brief = tree(self.out)["briefs/builder.md"]
            self.assertEqual("core/crew-config.py precheck-scope" in brief, present)
            self.assertEqual("`tests=n/a` only when every path is no-owner-ok" in brief, present)
            self.assertEqual("a path absent there is `removed`, with no owners query" in brief, present)

    def test_unknown_placeholder_golden(self):
        shutil.copy(os.path.join(FIX, "unknown", "core", "builder.md"), os.path.join(self.inputs, "core", "builder.md"))
        with open(os.path.join(FIX, "unknown", "expected.txt"), encoding="utf-8") as f:
            self.assertFails(f.read().splitlines())

    def test_unsupported_capability(self):
        self.overlay("core/builder.md", "# B\n\nBoard: <op:tracker.board-status>\n")
        self.assertFails(["inputs/core/builder.md:3: unsupported capability tracker.board-status "
                                "(backend github)"])

    def test_missing_command_mapping(self):
        self.overlay("core/builder.md", "# B\n\n<op:ci.check-status>\n")
        self.assertFails(["inputs/core/builder.md:3: missing mapping: no command for ci.check-status "
                                "in backends/github.toml"])

    def test_unknown_operation(self):
        self.overlay("core/builder.md", "<op:change.teleport>\n")
        self.assertFails(["inputs/core/builder.md:1: unknown operation change.teleport"])

    def policy(self, rel, text):
        path = os.path.join(self.inputs, "policy", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def test_policy_include_renders_one_source_into_every_role(self):  # #1184
        self.overlay("core/builder.md", "# B\n<include:policy/shared/rule.md>\nEnd <BuilderBot>.\n")
        self.overlay("core/reviewer.md", "# R\n<include:policy/shared/rule.md>\n")
        for rule in ("Escalate to <CoordinatorBot>: `<op:change.open>`.\n", "Edited once by <CoordinatorBot>.\n"):
            self.policy("shared/rule.md", rule)
            shutil.rmtree(self.out, ignore_errors=True)
            code, out = self.render()
            self.assertEqual(code, 0, out)
            got = tree(self.out)
            line = cr.Renderer(cr.resolve(PROJECT, None)[0], self.inputs).line(rule)
            self.assertEqual(got["briefs/builder.md"], "# B\n" + line + "End Bo.\n")
            self.assertEqual(got["briefs/reviewer.md"], "# R\n" + line)
            self.assertIn("by Ash" if "Edited" in rule else "to Ash: `gh pr create", line)

    def test_render_template_helper_expands_shared_include(self):  # #1413
        self.overlay("core/builder.md", "# B\n<include:policy/shared/rule.md>\nEnd <BuilderBot>.\n")
        self.policy("shared/rule.md", "Escalate to <CoordinatorBot>: `<op:change.open>`.\n")
        text, problems = render_template(PROJECT, "briefs/builder.md", self.inputs)
        self.assertEqual(problems, [])
        self.assertNotIn("<include:", text)
        self.assertIn("# B\nEscalate to Ash: `gh pr create", text)
        self.assertIn("End Bo.\n", text)

    def test_policy_include_fails_closed(self):  # #1184
        self.overlay("core/builder.md", "# B\n<include:policy/shared/none.md>\n")
        code, out = self.render()
        self.assertEqual(code, 1)
        self.assertRegex(out[0], r"^inputs/core/builder\.md:2: missing policy fragment shared/none\.md ")
        self.assertFalse(os.path.exists(self.out))
        self.overlay("core/builder.md", "# B\n<include:policy/shared/outer.md>\n")
        self.policy("shared/outer.md", "Outer.\n<include:policy/shared/inner.md>\n")
        self.policy("shared/inner.md", "Inner.\n")
        self.assertFails(["inputs/policy/shared/outer.md:2: nested include: a policy fragment cannot include another"])
        self.policy("shared/outer.md", "Outer.\n<nope>\n")
        self.assertFails(["inputs/policy/shared/outer.md:2: unknown placeholder <nope>"])
        self.overlay("core/builder.md", "# B\nSee <include:policy/shared/inner.md>\n")
        self.assertFails(["inputs/core/builder.md:2: unknown placeholder <include:policy/shared/inner.md>"])

    def test_missing_role_brief(self):
        os.remove(os.path.join(self.inputs, "core", "reviewer.md"))
        code, out = self.render()
        self.assertEqual(code, 1)
        self.assertEqual(len(out), 1)
        self.assertRegex(out[0], r"^inputs/core/reviewer\.md:1: missing mapping: no brief for role reviewer")

    def test_missing_runtime_binding(self):
        shutil.rmtree(os.path.join(self.inputs, "runtimes", "grok-bot"))
        self.assertFails(["inputs/runtimes/grok-bot:1: missing mapping: no runtime binding for grok-bot"])

    def test_resolve_failure_forwarded(self):
        bad = os.path.join(self.tmp, "bad.toml")
        with open(bad, "w", encoding="utf-8") as f:
            f.write('[runtime]\nname = "nope"\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", bad, "--inputs", self.inputs, "--out", self.out])
        self.assertEqual(code, 1)
        self.assertIn("runtime.name: unknown value 'nope'", out.getvalue())
        self.assertFalse(os.path.exists(self.out))

    def test_documented_placeholders_known(self):
        """Every placeholder in the templates/README.md table is mapped or kept."""
        with open(os.path.join(os.path.dirname(SCRIPTS), "templates", "README.md"), encoding="utf-8") as f:
            text = f.read().split("## Placeholders", 1)[1].split("\n## ", 1)[0]
        names = set()
        for line in text.splitlines():
            if line.startswith("| `<"):
                cell = re.split(r"(?<!\\)\|", line)[1]
                names |= {n.replace("\\|", "|") for n in re.findall(r"`<([^`]+)>`", cell)}
        self.assertGreater(len(names), 20)
        self.assertEqual(sorted(names - set(cr.MAPPED) - cr.KEPT), [])



class TmuxBriefs(unittest.TestCase):
    """The real tmux briefs (templates/runtimes/tmux/) render from profiles/tmux.toml to the golden files (#137)."""

    def test_triggered_procedures_are_rendered_and_reachable(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cr.main(["--project", example_profile(tmp), "--out", tmp]), 0)
            got = tree(os.path.join(tmp, "runtime"))
            for role, companion in (("builder", "builder-fix"), ("researcher", "researcher-triage")):
                with self.subTest(role=role):
                    entry, procedure = got[role + ".md"], got[companion + ".md"]
                    self.assertIn("$CREW_STATE/render/runtime/" + companion + ".md", entry)
                    self.assertIn("If unreadable", entry)
                    self.assertIn("`blocked: #<n> spec-unreadable` and stop.", entry)
                    self.assertNotRegex(procedure, r"<(?:op:|include:|strategy:|flavor-)")
            builder = " ".join(got["builder.md"].split())
            for rule in ("fix, ci-red, merge-up or base-update", "including an initial express build",
                         "append `ack: <id>`", "if the ref SHA is not the head", "heartbeat",
                         "Never squash, land, approve", "never ask the owner", "Step summaries"):
                self.assertIn(rule.lower(), (builder + got["builder-fix.md"]).lower())
            self.assertNotIn("Express self-gate (`", got["builder.md"])
            self.assertIn("gh pr review <n> --comment --body-file <file>", got["builder-fix.md"])
            self.assertIn("Instead of Scope and Output".lower(), got["researcher.md"].lower())
            self.assertNotIn("pass=triage-log", got["researcher.md"])
            self.assertIn("pass=triage-log", got["researcher-triage.md"])

    def test_disabled_researcher_requires_no_companion_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            inputs = os.path.join(tmp, "inputs")
            shutil.copytree(os.path.join(os.path.dirname(SCRIPTS), "templates"), inputs)
            procedure = os.path.join(inputs, "runtimes", "tmux", "researcher-triage.md")
            with open(procedure, "a") as f:
                f.write("\n<op:tracker.unknown-triage-operation>\n")
            for cap, expected in ((0, 0), (1, 1)):
                project = os.path.join(tmp, "crew.toml")
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "tmux"\noptions = { researchers = %d }\n' % cap)
                out = os.path.join(tmp, "out-" + str(cap))
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    code = cr.main(["--project", project, "--inputs", inputs, "--out", out])
                self.assertEqual(code, expected)
                if not cap:
                    self.assertFalse(any("researcher" in rel for rel in tree(out)))
                else:
                    self.assertFalse(os.path.exists(out))

    def test_flavor_presets_and_unset_in_both_bindings(self):
        expected = {
            "thorough": "review=full; validation=always; evidence=typed; caps=[3, 3]; merge=docs; builder=crew.",
            "standard": "review=thin; validation=behaviour; evidence=typed; caps=[3, 3]; merge=docs; builder=crew.",
            "fast": "review=thin; validation=off; evidence=inline; caps=[2, 2]; merge=auto; builder=crew.",
            "solo": "review=thin; validation=behaviour; evidence=typed; caps=[3, 3]; merge=docs; builder=solo.",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for runtime in ("tmux", "grok-bot"):
                baseline = None
                for name in (None, "thorough", "standard", "fast", "solo"):
                    with self.subTest(runtime=runtime, flavor=name):
                        project = os.path.join(tmp, "crew.toml")
                        with open(project, "w") as f:
                            f.write('[runtime]\nname = "%s"\n' % runtime)
                            if name:
                                f.write('[flavor]\nname = "%s"\n' % name)
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            code = cr.main(["--project", project, "--out", os.path.join(tmp, runtime)])
                        self.assertEqual(code, 0)
                        got = tree(os.path.join(tmp, runtime, "runtime"))
                        names = ("builder", "reviewer", "synthesizer", "solo") if runtime == "tmux" else (
                            "builder-b1", "builder-b2", "reviewer-validator", "reviewer-v2-watch", "synthesizer")
                        for role in names:
                            brief = got[role + ".md"]
                            line = next(s for s in brief.splitlines() if s.startswith("Flavor:"))
                            self.assertIn((name or "standard") + "; " + expected[name or "standard"], line)
                            self.assertEqual(brief.count("Flavor:"), 1)
                        if name is None:
                            values, problems = cr.resolve(project, None)
                            self.assertEqual((problems, values["flavor.name"]), ([], "standard"))
                            baseline = got
                        if name == "standard":
                            self.assertEqual(got, baseline)
                        self.assertNotIn("## Builder pre-review check", got[names[0] + ".md"])

    def test_custom_flavor_layers_and_class_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            org, project, paths = (os.path.join(tmp, n) for n in ("org.toml", "crew.toml", "paths.txt"))
            with open(org, "w") as f:
                f.write('[flavor]\nname = "custom"\n[flavor.custom.custom]\nbase = "fast"\nreview = "light"\n'
                        'caps = [1, 2]\nbuilder = "solo"\n'
                        '[[flavor.classes]]\npaths = ["auth/**"]\nflavor = "thorough"\n'
                        'reason = "Auth needs full review; its owner grant remains docs only"\n')
            with open(project, "w") as f:
                f.write('[runtime]\nname = "tmux"\n[flavor.custom.custom]\nmerge = "per-change"\n')
            values, problems = cr.resolve(project, org)
            self.assertEqual(problems, [])
            self.assertEqual(values["flavor.review"], "light")
            self.assertEqual(values["flavor.caps"], [1, 2])
            self.assertEqual(values["flavor.merge"], "per-change")
            self.assertEqual(values["flavor.builder"], "solo")
            with open(paths, "w") as f:
                f.write("auth/old.py\ndocs/new.md\n")
            out = os.path.join(tmp, "out")
            args = ["--project", project, "--org-profile", org, "--diff-paths", paths, "--out", out]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cr.main(args), 0)
            for role in ("builder", "reviewer", "synthesizer"):
                self.assertIn("mixed; review=full; validation=always; evidence=typed; caps=[3, 3]; "
                              "merge=per-change; builder=solo.", tree(out)["runtime/" + role + ".md"])
            shutil.rmtree(out)
            for content in ("../bad.md\n", "/absolute.md\n"):
                with open(paths, "w") as f:
                    f.write(content)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cr.main(args), 1)
                self.assertFalse(os.path.exists(out))
            os.remove(paths)
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cr.main(args), 1)
            self.assertFalse(os.path.exists(out))

    def unconditional_repo_wide(self, brief):
        """Sentences that ask for a repo-wide run without the `repo` scope condition (#648)."""
        conditions = ("only when the flavor or a class rule sets it", "Run no repo-wide check",
                      "instead of rerunning it locally", "never \"fixed\" by a local full run")
        sentences = re.split(r"(?<=\.)\s+", " ".join(brief.split()))
        return [s for s in sentences
                if re.search(r"check-repo\.py|dev/tests/\*/test-\*|every test|repo-wide|whole repo|full suite", s)
                and not any(c in s for c in conditions)]

    def test_validation_scope_bounded_by_default(self):
        self.assertEqual(self.unconditional_repo_wide("Run `scripts/check-repo.py` and every test script."),
                         ["Run `scripts/check-repo.py` and every test script."])
        briefs = {"tmux": ("reviewer.md",), "grok-bot": ("reviewer-validator.md", "reviewer-v2-watch.md")}
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, names in briefs.items():
                for flavor, extra, scope in ((None, "", "bounded"), ("standard", "", "bounded"),
                                             ("thorough", "", "repo"),
                                             (None, '[builder.precheck]\ntest = "make test-changed"\n', "bounded")):
                    with self.subTest(runtime=runtime, flavor=flavor, extra=extra):
                        project, out = os.path.join(tmp, "crew.toml"), os.path.join(tmp, "out")
                        shutil.rmtree(out, ignore_errors=True)
                        with open(project, "w") as f:
                            f.write('[runtime]\nname = "%s"\n' % runtime + ('[flavor]\nname = "%s"\n' % flavor
                                                                          if flavor else "") + extra)
                        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                            self.assertEqual(cr.main(["--project", project, "--out", out]), 0)
                        got = tree(os.path.join(out, "runtime"))
                        for name in names:
                            self.assertEqual(self.unconditional_repo_wide(got[name]), [], name)
                        scoped = " ".join(got[names[-1]].split())
                        self.assertIn("render baseline %s" % ("`%s`" % scope if runtime == "tmux" else scope), scoped)
                        self.assertIn("`make test-changed`" if extra else "test command `n/a`", scoped)

    def test_every_verdict_and_gate_status_brief_prints_the_summary_card(self):  # #1947
        briefs = {"tmux": ("reviewer.md", "synthesizer.md"), "session": ("reviewer.md", "synthesizer.md"),
                  "grok-bot": ("reviewer-v2-watch.md", "synthesizer.md")}
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, names in briefs.items():
                project, out = os.path.join(tmp, "crew.toml"), os.path.join(tmp, runtime)
                with open(project, "w") as f:
                    f.write('[runtime]\nname = "%s"\n' % runtime)
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cr.main(["--project", project, "--out", out]), 0)
                got = tree(os.path.join(out, "runtime"))
                for name in names:
                    with self.subTest(runtime=runtime, brief=name):
                        text = " ".join(got[name].split())
                        self.assertIn("summary card", text)
                        self.assertIn("/core/summary-card.py", text)

    def test_selfgate_engine_fills_tmux_builder_loop(self):  # #671
        with tempfile.TemporaryDirectory() as tmp:
            for setting, mode in (("", "different"), ('[flavor]\nselfgate_engine = "same"\n', "same")):
                with self.subTest(mode=mode):
                    project, out = os.path.join(tmp, "crew.toml"), os.path.join(tmp, mode)
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "tmux"\n' + setting)
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        self.assertEqual(cr.main(["--project", project, "--out", out]), 0)
                    got = tree(os.path.join(out, "runtime"))
                    brief = " ".join((got["builder.md"] + got["builder-fix.md"]).split())
                    self.assertIn("`selfgate_engine` (profile `%s`)" % mode, brief)
                    self.assertIn("`🛠️ Builder · Selfgate · <pass|changes> @ <sha7>` COMMENT review", brief)
                    self.assertNotIn("selfgate", got["solo.md"])

    def test_unknown_flavor_preset_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            with open(project, "w") as f:
                f.write('[flavor]\nname = "unknown"\n')
            values, problems = cr.resolve(project, None)
            self.assertIsNone(values)
            self.assertTrue(problems)

    def test_solo_and_builder_share_contract_and_precheck(self):
        root = os.path.dirname(SCRIPTS)
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            with open(project, "w") as f:
                f.write('[runtime]\nname = "tmux"\n[builder.precheck]\nenabled = true\ntest = "solo-tests"\n')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cr.main(["--project", project, "--out", tmp]), 0)
            got = tree(os.path.join(tmp, "runtime"))
            contract = cr.Renderer({"paths.mdstack": "<mdstack>"}, None).line(
                "<include:docs/roles.md#pr-conventions>")
            for name in ("builder.md", "solo.md"):
                self.assertIn(contract, got[name] + (got["builder-fix.md"] if name == "builder.md" else ""))
                self.assertIn("```sh\nsolo-tests\n```", got[name])
                for rule in ("Closes #<issue#>", "## Acceptance Evidence", "create→complete→delete",
                             "CHANGELOG fragment", "box-skill", "pass=fix", "effort=<effort>"):
                    self.assertIn(rule, got[name] + (got["builder-fix.md"] if name == "builder.md" else ""))

    def test_golden_tmux_briefs(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", example_profile(tmp), "--out", os.path.join(tmp, "out")])
        self.assertEqual(code, 0, out.getvalue())
        expected = tree(os.path.join(FIX, "tmux"))
        got = tree(os.path.join(tmp, "out"))
        self.assertEqual(sorted(got), sorted(["runtime/%s.md" % r for r in cr.ROLES] +
                                            ["runtime/builder-fix.md", "runtime/researcher-triage.md",
                                             "runtime/builder-lead.md", "runtime/reviewer-lead.md", "runtime/solo.md",
                                             "runtime/synthesizer-lead.md"]))
        self.assertEqual(sorted(got), sorted(expected))
        for rel, text in expected.items():
            with self.subTest(brief=rel):
                self.assertEqual(got[rel], text)

    def test_precheck_runtime_briefs_and_org_override(self):
        root = os.path.dirname(SCRIPTS)
        with tempfile.TemporaryDirectory() as tmp:
            org = os.path.join(tmp, "org.toml")
            project = os.path.join(tmp, "crew.toml")
            with open(org, "w") as f:
                f.write('[builder.precheck]\nenabled = true\nlint = "org-lint"\ntest = "org-test"\n')
            for runtime, name in (("tmux", "builder.md"), ("grok-bot", "builder-b1.md")):
                for enabled in (True, False):
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "%s"\n[builder.precheck]\nenabled = %s\ntest = "project-test"\n'
                                % (runtime, str(enabled).lower()))
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = cr.main(["--project", project, "--org-profile", org, "--out", tmp])
                    self.assertEqual(code, 0)
                    got = tree(os.path.join(tmp, "runtime"))
                    brief = got[name]
                    self.assertEqual("## Builder pre-review check" in brief, enabled)
                    if enabled:
                        fence = "~~~" if runtime == "grok-bot" else "```"
                        self.assertIn(fence + "sh\norg-lint\n" + fence, brief)
                        self.assertIn(fence + "sh\nproject-test\n" + fence, brief)
                        self.assertNotIn("org-test", brief)
                        if runtime == "grok-bot":
                            self.assertIn("## Builder pre-review check", brief.split("```text\n", 1)[1].split("\n```", 1)[0])
                    self.assertNotIn("## Builder pre-review check", got["synthesizer.md"])

    def test_box_skills_include_reviewed_docs_and_preserve_examples(self):
        root = os.path.dirname(SCRIPTS)
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            with open(project, "w") as f:
                f.write('[paths]\nmdstack = "/opt/bundle"\n')
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = cr.main(["--project", project, "--out", tmp])
            self.assertEqual(code, 0)
            for skill, doc in (("eng-pr-pipeline", "protocol"), ("eng-crew-roles", "roles")):
                with open(os.path.join(tmp, "runtime", "skills", skill, "SKILL.md")) as f:
                    text = f.read()
                with open(os.path.join(root, "docs", doc + ".md")) as f:
                    reviewed = f.read()
                self.assertIn("name: " + skill, text)
                self.assertIn("<owner>/<repo>", text)
                self.assertIn(reviewed.splitlines()[0], text)
                self.assertIn("](/opt/bundle/docs/", text)
                normalized = cr.Renderer({"paths.mdstack": "/opt/bundle"}, None, normalize_paths=True).line(
                    "<include:docs/" + doc + ".md>")
                self.assertIn("](<path>/docs/", normalized)
                self.assertNotIn("/opt/bundle", normalized)
                # Every line survives, apart from rebased link destinations.
                strip_links = lambda body: re.sub(r"\]\([^)]+\)", "]", body)
                self.assertIn(strip_links(reviewed), strip_links(text))

    def test_box_skill_missing_source_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cr, "HERE", os.path.join(tmp, "scripts")):
                renderer = cr.Renderer({"paths.mdstack": "/bundle"}, tmp)
                with self.assertRaisesRegex(ValueError, "cannot read included doc"):
                    renderer.line("<include:docs/protocol.md>")
            inputs = os.path.join(tmp, "inputs")
            shutil.copytree(os.path.join(FIX, "inputs"), inputs)
            with open(os.path.join(inputs, "core", "builder.md"), "w") as f:
                f.write("<include:docs/unknown.md>\n")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = cr.main(["--project", PROJECT, "--inputs", inputs, "--out", os.path.join(tmp, "out")])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out")))

    def test_custom_personas_in_both_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime in ("tmux", "grok-bot"):
                with self.subTest(runtime=runtime):
                    project = os.path.join(tmp, "crew.toml")
                    with open(project, "w", encoding="utf-8") as f:
                        f.write('[runtime]\nname = "%s"\n' % runtime)
                        for role in cr.ROLES:
                            f.write('[identities.%s]\nname = "%s-custom"\ntitle = "Lead"\nemoji = "🌊"\n' % (role, role))
                    out = os.path.join(tmp, runtime)
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = cr.main(["--project", project, "--out", out])
                    self.assertEqual(code, 0)
                    got = tree(out)
                    for role in [r for r in cr.ROLES if runtime == "tmux" or r != "researcher"]:  # tmux-only (#584)
                        matches = [t for rel, t in got.items() if os.path.basename(rel).startswith(role)
                                   and "Sign every authored post" in t]
                        self.assertTrue(matches, role)
                        for text in matches:
                            self.assertIn("— 🌊 %s-custom (Lead) · <harness> · <model>" % role, text)
                            self.assertIn("including\nany fallback", text)
                            self.assertNotIn("CTO", text)

    def test_lone_pr_land_policies(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "crew.toml")
            for policy in (None, "train", "direct"):
                with self.subTest(policy=policy):
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "tmux"\n')
                        if policy is not None:
                            f.write('[runtime.options]\nlone_pr_land = "%s"\n' % policy)
                    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                        code = cr.main(["--project", project, "--out", os.path.join(tmp, "out")])
                    self.assertEqual(code, 0)
                    got = tree(os.path.join(tmp, "out"))
                    for role in ("coordinator", "synthesizer"):
                        self.assertIn('lone_pr_land = "%s"' % (policy or "train"), got["runtime/%s.md" % role])
                    synth = " ".join(got["runtime/synthesizer.md"].split())
                    for rule in ('exactly one ready PR lands immediately',
                                 'no update-branch, no one-member train',
                                 'Only the tested-with-default-branch gate is waived',
                                 'two or more ready PRs use a merge train',
                                 'Re-survey under the land lock immediately before the squash',
                                 'Tested-with-default-branch waiver: lone_pr_land=direct, exactly one ready PR',
                                 'default-branch push CI run at that exact SHA',
                                 "--status blocked --reason 'main red after #<n> <run-url>'"):
                        self.assertIn(rule, synth)
                    coordinator = " ".join(got["runtime/coordinator.md"].split())
                    self.assertIn('file a blocking `crew:ready` fix issue linking the landed PR', coordinator)

    def test_spec_scope_and_globs_fill_synthesizer_brief(self):
        """#928: merge_grant_scope and spec.paths render as JSON arrays; the golden brief covers the defaults."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        project = os.path.join(tmp, "crew.toml")
        with open(example_profile(tmp), encoding="utf-8") as f:
            text = f.read().replace('options = { permission_mode = "bypass", researchers = 2 }\n',
                                    'options = { merge_grant = "all approved per #9", merge_grant_scope = ["approved", "spec"] }\n')
        with open(project, "w", encoding="utf-8") as f:
            f.write(text + '\n[spec]\npaths = ["docs/specs/**", "rfcs/**"]\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", os.path.join(tmp, "out")])
        self.assertEqual(code, 0, out.getvalue())
        synth = tree(os.path.join(tmp, "out"))["runtime/synthesizer.md"]
        self.assertIn('Profile: scope `["approved", "spec"]`, spec `["docs/specs/**", "rfcs/**"]`,', synth)
        self.assertIn("§7 spec changes need merge-ok unless scope has `spec`", synth)

    def test_grant_provenance_with_and_without_recorded_grant(self):
        """#1746/#314: grant candidates render lookup instructions; none invents no grant; both pin authority."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(example_profile(tmp), encoding="utf-8") as f:
            base = f.read()
        cases = {"none": 'options = { permission_mode = "bypass", researchers = 2 }\n',
                 "grant": 'options = { merge_grant = "roadmap PRs per https://x/111#c1" }\n'}
        briefs = {}
        for name, options in cases.items():
            project = os.path.join(tmp, name + ".toml")
            with open(project, "w", encoding="utf-8") as f:
                f.write(base.replace('options = { permission_mode = "bypass", researchers = 2 }\n', options))
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = cr.main(["--project", project, "--out", os.path.join(tmp, name)])
            self.assertEqual(code, 0)
            briefs[name] = {k: " ".join(v.split()) for k, v in tree(os.path.join(tmp, name)).items()}
        session = os.path.join(tmp, "session.toml")
        with open(session, "w", encoding="utf-8") as f:
            f.write('[runtime]\nname = "session"\n')
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cr.main(["--project", session, "--out", os.path.join(tmp, "session")]), 0)
        session_synth = " ".join(tree(os.path.join(tmp, "session"))["runtime/synthesizer.md"].split())
        for name, got in briefs.items():
            with self.subTest(grant=name):
                for synth in (got["runtime/synthesizer-lead.md"], session_synth):
                    for rule in ("pinned to the head at each land",
                                 "its source is the decision it names",
                                 "name a candidate only; they supply no approval or permission",
                                 "a post or summary never creates a grant",
                                 "links that decision instead of restating the permission"):
                        self.assertIn(rule, synth)
                self.assertIn("links its recorded decision instead of restating the permission",
                              got["runtime/coordinator.md"])
        self.assertIn('Standing grant: none', briefs["none"]["runtime/synthesizer.md"])
        self.assertIn("With `none`, require per-PR owner merge-ok; no standing grant applies.",
                      briefs["none"]["runtime/synthesizer.md"])
        for brief in briefs["none"].values():
            self.assertNotIn("x/111#c1", brief)
        self.assertIn("Standing-grant candidate: resolve `runtime.options.merge_grant` live", briefs["grant"]["runtime/synthesizer.md"])
        self.assertIn("Standing-grant candidate: resolve `runtime.options.merge_grant` live", briefs["grant"]["runtime/coordinator.md"])

    def test_grant_reference_is_bounded_and_layered(self):
        root = os.path.dirname(SCRIPTS)
        with tempfile.TemporaryDirectory() as tmp:
            for runtime in ("tmux", "session"):
                rendered = []
                for grant in ("current permission per #9 comment 1",
                              "historical archive #8 comment 2; " * 3000 + "current per #9 comment 1"):
                    project = os.path.join(tmp, "project.toml")
                    org = os.path.join(tmp, "org.toml")
                    with open(project, "w") as f:
                        f.write('[runtime]\nname = "%s"\n[paths]\nmdstack = "/opt/framework"\n' % runtime)
                    with open(org, "w") as f:
                        f.write('[runtime.options]\nmerge_grant = "%s"\n' % grant)
                    command = [sys.executable, os.path.join(root, "core", "crew-render.py"),
                               "--project", project, "--org-profile", org, "--out", os.path.join(tmp, "out")]
                    result = subprocess.run(command, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    got = tree(os.path.join(tmp, "out"))
                    rendered.append(got)
                    resolved = subprocess.run([sys.executable, os.path.join(root, "core", "crew-config.py"),
                                               "resolve", "--project", project, "--org-profile", org],
                                              capture_output=True, text=True)
                    self.assertEqual(resolved.returncode, 0, resolved.stderr)
                    self.assertIn('runtime.options.merge_grant = "%s"  # org' % grant, resolved.stdout)
                    text = " ".join(got["runtime/synthesizer.md"].split())
                    self.assertIn('resolve --project "$CREW_PROJECT"', text)
                    self.assertIn('with `--org-profile` when configured', text)
                    self.assertIn('read named decisions on the configured tool of record', text)
                    self.assertIn('foreign/mismatched records and unreadable profiles or sources supply no standing permission', text)
                    self.assertNotIn(grant, text)
                    if runtime == "tmux":
                        self.assertIn('read `$CREW_STATE/render/runtime/synthesizer.md` at start',
                                      got["runtime/synthesizer-lead.md"])
                        self.assertIn('resolve --project "$CREW_PROJECT"', got["runtime/coordinator.md"])
                    self.assertNotIn(grant, "".join(got.values()))
                    shutil.rmtree(os.path.join(tmp, "out"))
                self.assertEqual(rendered[0], rendered[1], runtime)
                self.assertLessEqual(len(rendered[1]["runtime/synthesizer.md"].encode()), 16384)
            with open(org, "w") as f:
                f.write('[runtime.options]\nmerge_grant = "layer grant"\n')
            with open(project, "w") as f:
                f.write('[runtime]\nname = "tmux"\n[runtime.options]\nmerge_grant = "none"\n')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Standing grant: none", tree(os.path.join(tmp, "out"))["runtime/synthesizer.md"])
            shutil.rmtree(os.path.join(tmp, "out"))
            with open(project, "w") as f:
                f.write('[runtime]\nname = "tmux"\n[runtime.options]\nmerge_grant = 42\n')
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("runtime.options.merge_grant", result.stdout)
            self.assertFalse(os.path.exists(os.path.join(tmp, "out")))

    def test_release_delegation_fills_coordinator_brief(self):
        """#1435: a set release_delegation renders in the coordinator brief; the golden covers none."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        project = os.path.join(tmp, "crew.toml")
        with open(example_profile(tmp), encoding="utf-8") as f:
            text = f.read().replace('options = { permission_mode = "bypass", researchers = 2 }\n',
                                    'options = { release_delegation = "make releases https://x/985#c1" }\n')
        with open(project, "w", encoding="utf-8") as f:
            f.write(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", os.path.join(tmp, "out")])
        self.assertEqual(code, 0, out.getvalue())
        coordinator = tree(os.path.join(tmp, "out"))["runtime/coordinator.md"]
        self.assertIn('Cut go: `release_delegation = "make releases https://x/985#c1"` (docs/release.md).', coordinator)

    def test_profile_values_fill_tmux_briefs(self):
        """14.1d (#233): mdstack path, merge grant and hold semantics render from the profile; booleans as TOML."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        project = os.path.join(tmp, "crew.toml")
        with open(example_profile(tmp), encoding="utf-8") as f:
            text = f.read().replace('options = { permission_mode = "bypass", researchers = 2 }\n', 'options = { merge_grant = "#110 '
                                    'roadmap PRs", hold_label_blocks = false, mirror_deferral = "#110 roadmap PRs per #140", train_min = 4, train_window = 120 }\n')
        with open(project, "w", encoding="utf-8") as f:
            f.write(text + '\n[repo]\nowner = "acme"\nname = "widgets"\n[paths]\nmdstack = "/opt/mdstack"\n')
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", os.path.join(tmp, "out")])
        self.assertEqual(code, 0, out.getvalue())
        got = tree(os.path.join(tmp, "out"))
        synth = got["runtime/synthesizer.md"]
        self.assertIn("Standing-grant candidate: resolve `runtime.options.merge_grant` live", synth)
        self.assertIn("`hold_label_blocks = false`", synth)
        self.assertIn('`mirror_deferral = "#110 roadmap PRs per #140"`', synth)
        self.assertIn("do not change live Grok Bot behaviour", synth)
        self.assertIn("--mirror-deferred", synth)
        self.assertIn("`train_min = 4`", synth)
        self.assertIn("`train_window = 120` seconds", synth)
        self.assertIn("A single ready PR with none close merges alone immediately", synth)
        self.assertIn("`$CREW_BIN land-lock acquire", synth)
        for rel, brief in got.items():
            if rel in ("runtime/builder-fix.md", "runtime/researcher-triage.md"):
                entry = "builder" if "builder" in rel else "researcher"
                brief += got["runtime/" + entry + ".md"]
            with self.subTest(brief=rel):
                self.assertIn("/opt/mdstack/docs/protocol.md", brief)
                self.assertIn("-R acme/widgets", brief)
                self.assertNotIn("<mdstack>", brief)

    def test_mirror_option_selects_synthesizer_mirror_gate(self):
        """#877 B3: live-copy renders today's bytes; none swaps the deferral paragraph for n/a by profile."""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(example_profile(tmp), encoding="utf-8") as f:
            base = f.read()
        got = {}
        for mirror in (None, "live-copy", "none"):
            project = os.path.join(tmp, "crew-%s.toml" % mirror)
            options = 'options = { permission_mode = "bypass", researchers = 2%s }\n' % (
                ', mirror = "%s"' % mirror if mirror else "")
            with open(project, "w", encoding="utf-8") as f:
                f.write(base.replace('options = { permission_mode = "bypass", researchers = 2 }\n', options) +
                        '\n[repo]\nowner = "acme"\nname = "widgets"\n')
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cr.main(["--project", project, "--out", os.path.join(tmp, "out-%s" % mirror)])
            self.assertEqual(code, 0, out.getvalue())
            got[mirror] = tree(os.path.join(tmp, "out-%s" % mirror))
        self.assertEqual(got["live-copy"], got[None])
        self.assertIn("Mirror deferral used: none", got[None]["runtime/synthesizer.md"])
        synth = " ".join(got["none"]["runtime/synthesizer.md"].split())
        for rule in ("mirror gate is `n/a` by profile", "Record `Mirror: n/a (profile)` on direct lands",
                     "list no mirror item in gate-status", "Never wait on or ask for a mirror or deferral",
                     "ignore `crew:needs-mirror`", "every other gate still applies at head"):
            self.assertIn(rule, synth)
        for gone in ("Mirror deferral used", "do not change live Grok Bot behaviour", "need a real mirror"):
            self.assertNotIn(gone, synth)
        for role in ("reviewer", "coordinator"):
            with self.subTest(role=role):
                brief = got["none"]["runtime/%s.md" % role]
                self.assertEqual(brief, got[None]["runtime/%s.md" % role])
                self.assertNotIn("needs-mirror", brief)
                self.assertNotIn("mirror_deferral", brief)
        self.assertEqual({k: v for k, v in got["none"].items() if k != "runtime/synthesizer.md"},
                         {k: v for k, v in got[None].items() if k != "runtime/synthesizer.md"})


class PackOverlay(unittest.TestCase):
    """A pack's render/ overlay, pack-declared placeholders and render-time notes (#580)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.org = write_pack(os.path.join(self.tmp, "pack"))
        with open(os.path.join(os.path.dirname(SCRIPTS), "templates", "backends", "github.toml")) as f:
            self.github = f.read()

    def project(self, extra=""):
        path = os.path.join(self.tmp, "crew-%d.toml" % len(os.listdir(self.tmp)))
        with open(path, "w") as f:
            f.write('[runtime]\nname = "tmux"\n' + extra)
        return path

    def render(self, project, *extra):
        out_dir = os.path.join(self.tmp, "out-%d" % len(os.listdir(self.tmp)))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", out_dir, *extra])
        return code, buf.getvalue(), out_dir

    def test_spec_bookends_name_the_configured_specs_home(self):  # #1725
        url = "https://tracker.example/acme/items/12"
        default = "a milestone opens with its spec slice in\n`docs/specs/`;"
        homes = {'[docs]\n[docs.homes]\nspecs = "design/specs"\n': "`design/specs/`",
                 '[docs]\nspecs_external = "%s"\n' % url: "the external spec home `%s`" % url}
        briefs = {"tmux": "runtime/coordinator.md", "session": "runtime/coordinator.md",
                  "grok-bot": "runtime/wiring.md"}
        for runtime, brief in briefs.items():
            path = os.path.join(self.tmp, runtime + ".toml")
            with open(path, "w") as f:
                f.write('[runtime]\nname = "%s"\n' % runtime)
            code, out, base = self.render(path)
            self.assertEqual(code, 0, out)
            before = tree(base)
            self.assertIn(default, before[brief])
            for table, home in homes.items():
                with self.subTest(runtime=runtime, home=home), open(path, "w") as f:
                    f.write('[runtime]\nname = "%s"\n' % runtime + table)
                code, out, got = self.render(path)
                self.assertEqual(code, 0, out)
                after = tree(got)
                changed = {rel for rel in after if after[rel] != before[rel]}
                roles = "runtime/skills/eng-crew-roles/SKILL.md"
                self.assertEqual(changed, {brief, roles} if runtime == "grok-bot" else {brief})
                self.assertEqual(after[brief], before[brief].replace(default, default.replace("`docs/specs/`", home)))
                if runtime == "grok-bot":
                    self.assertIn("the milestone in %s (scope" % home, after[roles])
                    self.assertNotIn("the milestone in `docs/specs/`", after[roles])

    def test_overlay_policy_fragment_replaces_upstream_fragment(self):  # #1184
        code, out, upstream = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        os.makedirs(os.path.join(self.tmp, "pack", "render", "policy", "reviewer"))
        with open(os.path.join(self.tmp, "pack", "render", "policy", "reviewer", "delta-rereview.md"), "w") as f:
            f.write("Pack delta rule for <ReviewerBot>.\n")
        code, out, got = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        before, after = tree(upstream), tree(got)
        self.assertEqual({rel for rel in after if after[rel] != before[rel]}, {"runtime/reviewer.md"})
        self.assertIn("\nPack delta rule for Reviewer.\n", after["runtime/reviewer.md"])
        self.assertNotIn("Delta re-review (protocol §7)", after["runtime/reviewer.md"])

    def test_overlay_changes_only_its_file_and_mapped_commands(self):
        code, out, upstream = self.render(self.project())
        self.assertEqual(code, 0, out)
        expected = {rel: text.replace("`gh` command", "`ex` command") for rel, text in tree(upstream).items()}
        expected["runtime/solo.md"] += "\nPack rule.\n"
        self.assertNotEqual(expected, tree(upstream))
        for project, extra in ((self.project(), ["--org-profile", self.org]),
                               (self.project('[paths]\npack = "pack"\n'), [])):
            code, out, got = self.render(project, *extra)
            self.assertEqual(code, 0, out)
            self.assertEqual(tree(got), expected)

    def test_pack_declared_placeholder_is_kept_and_undeclared_fails(self):
        listed = self.github.replace(
            'list-open = "gh pr list --state open --json number,headRefName,closingIssuesReferences"',
            'list-open = "ex list --item <item-id>"')
        write_pack(os.path.join(self.tmp, "pack"), mapping=listed + '\n[placeholders]\nkept = ["item-id"]\n')
        code, out, got = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        self.assertIn("   `ex list --item <item-id>`.\n", tree(got)["runtime/builder.md"])
        for mapping, reason in ((listed, "unknown placeholder <item-id>"),
                                (listed + '\n[placeholders]\nkept = ["owner"]\n',
                                 "invalid placeholders.kept in backends/example.toml: <owner> is an install-time placeholder")):
            write_pack(os.path.join(self.tmp, "pack"), mapping=mapping)
            code, out, got = self.render(self.project(), "--org-profile", self.org)
            self.assertEqual(code, 1)
            self.assertIn("templates/policy/builder/build-pass.md:2: " + reason, out)
            self.assertFalse(os.path.exists(got))

    def async_pack(self, land):
        """The example pack with change.publish and change.land-status mapped and a [land] table (#873 B4)."""
        mapping = self.github.replace('cli-name = "gh"', 'cli-name = "ex"').replace(
            'land = "gh pr merge <n> --squash --match-head-commit <head-sha>"',
            'land = "ex land <n> --expect-head <head-sha>"\npublish = "ex publish <n>"\n'
            'land-status = "ex land-status <n> <head-sha>"')
        write_pack(os.path.join(self.tmp, "pack"), mapping=mapping)
        manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(manifest) as f:
            text = f.read().replace('land = "supported"',
                                    'land = "supported"\npublish = "supported"\nland-status = "supported"')
        with open(manifest, "w") as f:
            f.write(text + "\n[land]\n" + land)

    def test_land_delete_renders_only_where_the_backend_maps_it(self):  # #395
        code, out, got = self.render(self.project())
        self.assertEqual(code, 0, out)
        synth = tree(got)["runtime/synthesizer.md"]
        self.assertIn("run `gh pr merge <n> --squash --match-head-commit <head-sha>`, add\n"
                      "   `--delete-branch` if same-repo, not default/base, post\n", synth)
        self.assertIn("line and `Head branch: deleted|retained (<reason>)|delete failed` (exit>0,\n"
                      "   `MERGED`)", synth)
        session = os.path.join(self.tmp, "session.toml")
        with open(session, "w") as f:
            f.write('[runtime]\nname = "session"\n')
        code, out, got = self.render(session)
        self.assertEqual(code, 0, out)
        self.assertIn("bound to that head, add `--delete-branch` if\n   same-repo, not default/base, post", tree(got)["runtime/synthesizer.md"])
        self.assertIn("`Head branch: deleted|retained\n   (<reason>)|delete failed` (exit>0, `MERGED`)",
                      tree(got)["runtime/synthesizer.md"])
        write_pack(os.path.join(self.tmp, "pack"), mapping="\n".join(
            line for line in self.github.splitlines() if not line.startswith("land-delete-arg =")) + "\n")
        code, out, got = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        self.assertNotIn("--delete-branch", tree(got)["runtime/synthesizer.md"])
        self.assertNotIn("Head branch:", tree(got)["runtime/synthesizer.md"])

    def test_async_land_renders_synthesizer_and_builder_steps(self):
        code, out, sync = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        sync = tree(sync)
        self.assertIn("run `$CREW_BIN land-lock acquire", sync["runtime/synthesizer.md"])
        self.assertNotIn("land request", sync["runtime/synthesizer.md"])
        self.assertNotIn("publish", sync["runtime/builder.md"])
        self.async_pack('mode = "async"\nopens_draft = true\nserializes = true\ntests_against_tip = true\n')
        code, out, managed = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        managed = tree(managed)
        self.assertEqual({k for k in managed if managed[k] != sync[k]}, {"runtime/synthesizer.md", "runtime/builder.md"})
        synth = managed["runtime/synthesizer.md"]
        for text in ('Run `$CREW_BIN land request --project "$CREW_PROJECT" --pr <n> --head <head-sha>`',
                     "it records the intent, sends `ex land <n> --expect-head <head-sha>` only when",
                     "`ex land-status <n> <head-sha>` reads `none` at an unmoved head",
                     "post no `merge`", 'run `$CREW_BIN land resume --project "$CREW_PROJECT"`',
                     "It never requests a land again.", "(`land.serializes`, C7): take no land lock.",
                     "`Land rule: alone, backend queue`; never run\n   `gh pr update-branch <n>` or a merge train"):
            self.assertIn(text, synth)
        self.assertNotIn("land-lock acquire", synth)
        self.assertIn("run `ex publish <n>`\n   right after opening", managed["runtime/builder.md"])
        self.assertEqual(managed["runtime/builder.md"].replace(cr.Renderer({}, None).line(
            cr.LAND_PUBLISH.replace("<op:change.publish>", "ex publish <n>")), ""), sync["runtime/builder.md"])
        self.async_pack('mode = "async"\n')  # bare async: no gate alternative
        code, out, bare = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        bare = tree(bare)
        self.assertIn('First run `$CREW_BIN land-lock acquire --project "$CREW_PROJECT"`; hold the\n'
                      "   lock until the terminal status and, on landed, the merge post", bare["runtime/synthesizer.md"])
        self.assertIn("Tested with the default branch must hold at the request", bare["runtime/synthesizer.md"])
        self.assertNotIn("Backend queue", bare["runtime/synthesizer.md"])
        self.assertEqual(bare["runtime/builder.md"], sync["runtime/builder.md"])
        for synth in (managed["runtime/synthesizer.md"], bare["runtime/synthesizer.md"]):
            # (b) runs whatever lone_pr_land is, on both the request and the resume completion
            self.assertIn("(b) whatever\n   `lone_pr_land` is, check default-branch CI as step 4 does, at the printed "
                          "landed\n   revision", synth)
            self.assertIn("Complete each landed intent it prints through\n   (a) to (c)", synth)
            self.assertLess(synth.index("(b) whatever"), synth.index("(c) once CI is green"))
            step3 = synth[synth.index("\n3. "):synth.index("\n4. ")]
            self.assert_crew_commands_parse(step3)

    def test_session_async_land_polls_declared_status_within_bound(self):
        """#1351: a session profile renders the async land step: the backend's placeholder and status map through
        `mdstack land request`, bounded by land_timeout, refusing failed or unknown; sync renders stay unchanged."""
        with open(os.path.join(os.path.dirname(SCRIPTS), "profiles", "session.toml")) as f:
            session = self.project(f.read().replace('[runtime]\nname = "session"\n', ""))
        with open(session) as f:
            text = f.read().replace('name = "tmux"', 'name = "session"', 1)
        with open(session, "w") as f:
            f.write(text)
        code, out, sync = self.render(session, "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        sync = tree(sync)
        self.assertIn("3. Serial land (session C7;", sync["runtime/synthesizer.md"])
        self.assertNotIn("$CREW_BIN land", sync["runtime/synthesizer.md"])
        self.async_pack('mode = "async"\nchange_placeholder = "change"\n[land.status]\n"^MERGED (?P<revision>[0-9a-f]{40})$" '
                        '= "landed"\n"^FAILED" = "failed"\n"^PENDING$" = "queued"\n"^NONE$" = "none"\n')
        mapping = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping) as f:
            text = f.read().replace("ex land <n> --expect-head", "ex land <change> --expect-head").replace(
                "ex land-status <n>", "ex land-status <change>")
        with open(mapping, "w") as f:
            f.write(text + '\n[placeholders]\nkept = ["change"]\n')
        code, out, bare = self.render(session, "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        bare = tree(bare)
        self.assertEqual({k for k in bare if bare[k] != sync[k]}, {"runtime/synthesizer.md"})
        synth = bare["runtime/synthesizer.md"]
        step3 = synth[synth.index("\n3. "):synth.index("\n4. ")]
        flat = " ".join(step3.split())
        for rule in ('run `$CREW_BIN land request --project "$CREW_PROJECT" --pr <n> --head <head-sha>`',
                     "fills the backend's change placeholder", "sends `ex land <change> --expect-head <head-sha>`",
                     "only when `ex land-status <change> <head-sha>` reads `none` at an unmoved head",
                     "maps each status read through the declared `land.status`",
                     "polls every `land_poll_interval` seconds for at most `land_timeout` seconds",
                     "On exit 1 (failed, stale head, timeout or unknown status) post no `merge`",
                     "Hold it until the terminal status", 'release with `rmdir "$CREW_STATE/locks/merge.lock.d"`',
                     "Tested with the default branch must hold at the request",
                     'run `$CREW_BIN land resume --project "$CREW_PROJECT"`. It never requests a land again.',
                     "Complete each landed intent it prints through (a) to (c)"):
            self.assertIn(rule, flat)
        self.assertNotIn("land-lock acquire", step3)  # mdstack land-lock stays tmux-only
        self.assertNotIn("Backend queue", synth)
        self.assert_crew_commands_parse(step3)
        self.async_pack('mode = "async"\nserializes = true\ntests_against_tip = true\n')
        code, out, queue = self.render(session, "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        synth = " ".join(tree(queue)["runtime/synthesizer.md"].split())
        for rule in ("(`land.serializes`, C7): take no repo lock.", "`Land rule: alone, backend queue`",
                     "Backend queue (`land.tests_against_tip`): the two rules above do not apply."):
            self.assertIn(rule, synth)
        self.assertNotIn("mkdir -p", synth[synth.index("3. Serial land"):synth.index(" 4. ")])

    def stack_pack(self, land):
        """The example pack with change.land-stack and change.stack-status mapped and a [land] table (#1605)."""
        mapping = self.github.replace('cli-name = "gh"', 'cli-name = "ex"').replace(
            'land = "gh pr merge <n> --squash --match-head-commit <head-sha>"',
            'land = "gh pr merge <n> --squash --match-head-commit <head-sha>"\n'
            'land-stack = "ex land-stack <stack>"\nstack-status = "ex stack-status <stack>"\n'
            'land-status = "ex land-status <n> <head-sha>"')
        write_pack(os.path.join(self.tmp, "pack"), mapping=mapping)
        manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(manifest) as f:
            text = f.read().replace('land = "supported"',
                                    'land = "supported"\nland-stack = "supported"\nstack-status = "supported"\n'
                                    'land-status = "supported"')
        with open(manifest, "w") as f:
            f.write(text + "\n[land]\n" + land)

    def test_session_stack_land_renders_only_with_binding(self):
        """#1605: land.stack renders the session synthesizer's stack-land recipe; without the binding the session
        render keeps one land per run, and tmux renders (trains) never change."""
        with open(os.path.join(os.path.dirname(SCRIPTS), "profiles", "session.toml")) as f:
            session = self.project(f.read().replace('[runtime]\nname = "session"\n', ""))
        with open(session) as f:
            text = f.read().replace('name = "tmux"', 'name = "session"', 1)
        with open(session, "w") as f:
            f.write(text)
        renders = {}
        for name, land in (("bare", None), ("stack", "stack = true\n"),
                           ("tested", 'stack = true\nstack_tests_against_tip = true\nmode = "async"\nserializes = true\n')):
            if land is None:
                write_pack(os.path.join(self.tmp, "pack"))
            else:
                self.stack_pack(land)
            code, out, got = self.render(session, "--org-profile", self.org)
            self.assertEqual(code, 0, out)
            code, out, tmux = self.render(self.project(), "--org-profile", self.org)
            self.assertEqual(code, 0, out)
            renders[name] = (tree(got), tree(tmux))
        bare, stack, tested = (renders[k][0] for k in ("bare", "stack", "tested"))
        self.assertNotIn("Stack land", bare["runtime/synthesizer.md"])
        self.assertEqual({k for k in stack if stack[k] != bare[k]}, {"runtime/synthesizer.md"})
        self.assertEqual(renders["stack"][1], renders["bare"][1])  # tmux: no stack land, trains unchanged
        self.assertNotIn("land stack", renders["tested"][1]["runtime/synthesizer.md"])
        synth = stack["runtime/synthesizer.md"]
        self.assertEqual(synth.replace(synth[synth.index("\n\nStack land"):synth.index("\n\nEach `🔀 ")], ""),
                         bare["runtime/synthesizer.md"])  # the recipe is the only addition
        flat = " ".join(synth.split())
        for rule in ("Stack land (`land.stack`, protocol §7): when two or more ready PRs form one linear",
                     "for every member at that member's own live head",
                     'run `$CREW_BIN land stack --project "$CREW_PROJECT" --stack <n>:<head-sha>,...`',
                     "sends `ex land-stack <stack>` once, only when `ex stack-status <stack>` reads `none` for every member",
                     "post one `🔀 Sam · Merge` per member", "that member's printed `record:` line",
                     'mkdir "$CREW_STATE/locks/merge.lock.d"', "Tested with the default branch must hold for every member",
                     "`Land rule: stack of <k>`.", 'run `$CREW_BIN land resume --project "$CREW_PROJECT"`; it never requests.'):
            self.assertIn(rule, flat)
        self.assert_crew_commands_parse(synth[synth.index("Stack land"):])
        recipe = flat[flat.index("Stack land"):]
        refusal = recipe.index("refuse the whole stack: one held member (`crew:hold`, an open hold-until or stop), one "
                               "with red, pending or missing CI, one without its passing verdict or merge permission, "
                               "or one whose head moved means zero requests. Never run `$CREW_BIN land stack` then")
        self.assertLess(recipe.index("for every member at that member's own live head"), refusal)
        self.assertLess(refusal, recipe.index('Otherwise run `$CREW_BIN land stack --project'))  # gates before request
        flat = " ".join(tested["runtime/synthesizer.md"].split())
        recipe = flat[flat.index("Stack land"):]
        for rule in ("(`land.serializes`, C7): take no repo lock.", "`Land rule: stack of <k>, backend combined test`",
                     "(`land.stack_tests_against_tip`): the stack may land behind the default branch"):
            self.assertIn(rule, recipe)
        self.assertNotIn("mkdir", recipe)

    def test_session_per_change_stack_land_renders(self):
        """#1722: a land-stack naming <stack-top> and <stack-revisions> renders (both kept run-time placeholders), and
        per-change readback names each member's land-status in place of stack-status; the rest of the recipe holds."""
        with open(os.path.join(os.path.dirname(SCRIPTS), "profiles", "session.toml")) as f:
            session = self.project(f.read().replace('[runtime]\nname = "session"\n', ""))
        with open(session) as f:
            text = f.read().replace('name = "tmux"', 'name = "session"', 1)
        with open(session, "w") as f:
            f.write(text)
        self.stack_pack("stack = true\n")
        code, out, got = self.render(session, "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        legacy = tree(got)["runtime/synthesizer.md"]
        self.stack_pack('stack = true\nstack_status = "per-change"\n')
        mapping = os.path.join(self.tmp, "pack", "render", "backends", "example.toml")
        with open(mapping) as f:
            text = f.read().replace('"ex land-stack <stack>"', '"ex submit <stack-top> <stack-changes> <stack-revisions>"')
        with open(mapping, "w") as f:
            f.write(text)
        code, out, got = self.render(session, "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        synth = tree(got)["runtime/synthesizer.md"]
        flat = " ".join(synth.split())
        self.assertIn("sends `ex submit <stack-top> <stack-changes> <stack-revisions>` once, only when each member's "
                      "`ex land-status <n> <head-sha>` reads `none` for every member", flat)
        self.assertNotIn("stack-status", synth)
        swap = (("ex submit <stack-top> <stack-changes> <stack-revisions>", "ex land-stack <stack>"),
                ("each member's `ex land-status <n> <head-sha>`", "`ex stack-status <stack>`"))
        for new, old in swap:
            flat = flat.replace(new, old)
        self.assertEqual(flat, " ".join(legacy.split()))  # only the request and its readback differ

    def assert_crew_commands_parse(self, text):
        """Every `$CREW_BIN ...` command in text parses with the crew CLI's own argument parser (#1008 review)."""
        loader = importlib.machinery.SourceFileLoader("crew_cli", os.path.join(os.path.dirname(SCRIPTS), "cli", "mdstack"))
        crew = importlib.util.module_from_spec(importlib.util.spec_from_loader("crew_cli", loader))
        loader.exec_module(crew)
        ap = argparse.ArgumentParser(exit_on_error=False)
        sub = ap.add_subparsers(dest="cmd", required=True)
        for mod in crew.commands().values():
            mod.register(sub)
        found = re.findall(r"`\$CREW_BIN ([^`]+)`", text)
        self.assertGreaterEqual(len(found), 3, text)  # request, done, resume (+ lock pair)
        for cmd in found:
            argv = shlex.split(cmd.replace('"$CREW_PROJECT"', "/p/crew.toml").replace("<n>", "7")
                               .replace("<head-sha>", "a" * 40))
            with contextlib.redirect_stderr(io.StringIO()) as err:
                try:
                    ap.parse_args(argv)
                except (SystemExit, argparse.ArgumentError) as e:
                    self.fail("rendered `$CREW_BIN %s` does not parse: %s %s" % (cmd, e, err.getvalue()))

    def test_async_tested_land_overrides_train_decision(self):
        self.async_pack('mode = "async"\nserializes = true\ntests_against_tip = true\n')
        code, out, got = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        synth = tree(got)["runtime/synthesizer.md"]
        rule = synth.index("Backend queue (`land.tests_against_tip`): the rules below and the merge train\n"
                           "section do not apply.")
        self.assertLess(synth.index("Before step 3, look at every open crew PR:"), rule)
        self.assertLess(rule, synth.index('- With `lone_pr_land = "direct"`, two or more ready PRs use a merge train'))
        self.assertIn("Never run `gh pr update-branch <n>` or\n`mdstack train` (it refuses).", synth)

    def test_native_control_item_renders_and_mismatch_fails(self):
        """#936: a string control_item matching the pack tracker map's [ids] item renders as <control-item>."""
        write_pack(os.path.join(self.tmp, "pack"), mapping=self.github.replace("\n[ids]\n", '\n[ids]\nitem = "[A-Z][A-Z0-9]+-[0-9]+"\n'))
        project = os.path.join(self.tmp, "native.toml")
        for item, code_wanted in (('"OPS-1042"', 0), ('"ops 1042"', 1), ("12", 0)):
            with open(project, "w") as f:
                f.write('[repo]\ncontrol_item = %s\n[runtime]\nname = "grok-bot"\ninstance = "laptop"\n' % item)
            code, out, got = self.render(project, "--org-profile", self.org)
            self.assertEqual(code, code_wanted, out)
            if code:
                self.assertIn('repo.control_item: "ops 1042" does not match item pattern [A-Z][A-Z0-9]+-[0-9]+ '
                              '(tracker backend example)', out)
            else:
                self.assertIn("Control item: `%s`;" % item.strip('"'), tree(got)["runtime/wiring.md"])

    def test_classify_sensitive_always_renders_core_entry(self):
        """#962 (#880 B3): a bound extension changes no brief; <op:classify.sensitive> stays the core command."""
        project = self.project('[paths]\npack = "pack"\n')
        code, out, plain = self.render(project)
        self.assertEqual(code, 0, out)
        write_pack(os.path.join(self.tmp, "pack"), mapping=self.github.replace('cli-name = "gh"', 'cli-name = "ex"')
                   + '\n[classify]\nsensitive = "ex policy classify --stdin --json"\n')
        for rel, text in (("manifest.toml", '\n[capabilities.classify]\nsensitive = "supported"\n'),
                          ("profile.toml", '[backends.classify]\nname = "example"\n')):
            with open(os.path.join(self.tmp, "pack", rel), "a") as f:
                f.write(text)
        code, out, bound = self.render(project)
        self.assertEqual(code, 0, out)
        self.assertEqual(tree(bound), tree(plain))
        briefs = tree(bound)
        self.assertIn("`core/crew-config.py sensitive --project \"$CREW_PROJECT\"`", briefs["runtime/builder.md"])
        self.assertIn("run `core/crew-config.py sensitive` on", briefs["runtime/coordinator.md"])
        self.assertFalse(any("policy classify" in text for text in briefs.values()))
        renderer = cr.Renderer({"backends.classify.name": "example"}, os.path.join(self.tmp, "pack", "render"))
        self.assertEqual(renderer.op("classify", "sensitive"), ("core/crew-config.py sensitive", set()))

    def test_render_notes_for_registry_roles_and_leads(self):
        notes = os.path.join(self.tmp, "notes")
        os.makedirs(notes)
        project = self.project('[runtime.options.notes.render]\nbuilder = ["notes/builder.md"]\n'
                               'reviewer-lead = ["notes/lead.md", "notes/builder.md"]\n')
        code, out, _ = self.render(project)
        self.assertEqual(code, 1)
        self.assertIn("cannot read runtime.options.notes.render.builder file", out)
        for name, text in (("builder.md", "Builder rule <n>.\n"), ("lead.md", "Lead rule.\n")):
            with open(os.path.join(notes, name), "w") as f:
                f.write(text)
        code, out, got = self.render(project)
        self.assertEqual(code, 0, out)
        code, _, upstream = self.render(self.project())
        got, upstream = tree(got), tree(upstream)
        self.assertEqual(got["runtime/builder.md"],
                         upstream["runtime/builder.md"] + "\n## Render note: notes/builder.md\n\nBuilder rule <n>.\n")
        self.assertEqual(got["runtime/reviewer-lead.md"], upstream["runtime/reviewer-lead.md"] +
                         "\n## Render note: notes/lead.md\n\nLead rule.\n"
                         "\n## Render note: notes/builder.md\n\nBuilder rule <n>.\n")
        self.assertEqual({rel for rel in got if got[rel] != upstream[rel]},
                         {"runtime/builder.md", "runtime/reviewer-lead.md"})

    def git(self, *args, cwd=None):
        return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t", *args], cwd=cwd or self.tmp,
                              check=True, capture_output=True, text=True).stdout.strip()

    def memory_remote(self):
        """self.tmp as a checkout of a bare origin; returns an upstream clone that lands reviewed memory (#1537)."""
        origin, upstream = tempfile.mkdtemp(), tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, origin)
        self.addCleanup(shutil.rmtree, upstream)
        self.git("init", "-q", "--bare", "-b", "main", origin)
        self.git("init", "-q", "-b", "main")
        self.git("remote", "add", "origin", origin)
        self.git("clone", "-q", origin, upstream)
        self.git("commit", "-q", "--allow-empty", "-m", "base", cwd=upstream)
        self.git("push", "-q", "origin", "HEAD:main", cwd=upstream)
        self.git("pull", "-q", "origin", "main")
        return upstream

    def publish(self, upstream, files):
        for rel, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(upstream, rel)), exist_ok=True)
            with open(os.path.join(upstream, rel), "w") as f:
                f.write(text)
        self.git("add", "-A", cwd=upstream)
        self.git("commit", "-q", "-m", "memory", cwd=upstream)
        self.git("push", "-q", "origin", "HEAD:main", cwd=upstream)
        return self.git("rev-parse", "HEAD", cwd=upstream)

    def test_core_memory_revision_in_diagnostics_and_session(self):  # #1537 AC1/AC3
        session = os.path.join(self.tmp, "session.toml")
        with open(session, "w") as f:
            f.write('[runtime]\nname = "session"\n')
        upstream = self.memory_remote()
        sha = self.publish(upstream, {"memory/owner.md": "# Owner\n\n- First.\n"})
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(cr.main(["--project", session, "--out", os.path.join(self.tmp, "s1")]), 0)
        self.assertEqual(err.getvalue().count("crew-render: core memory from origin/main@%s (%s)\n" % (sha, self.tmp)), 1)
        briefs = tree(os.path.join(self.tmp, "s1"))
        self.assertIn("runtime/coordinator.md", briefs)
        self.assertTrue(all("- First." in t for d, t in briefs.items() if "## Core memory" in t), briefs.keys())
        self.publish(upstream, {"memory/owner.md": "# Owner\n\n- Second.\n"})  # the checkout does not move
        code, out, out_dir = self.render(session)
        self.assertEqual(code, 0, out)
        self.assertIn("- Second.", tree(out_dir)["runtime/coordinator.md"])
        self.git("remote", "set-url", "origin", os.path.join(self.tmp, "gone.git"))
        code, out, out_dir = self.render(session)
        self.assertEqual(code, 1)
        self.assertIn(os.path.join(self.tmp, "memory") + ":1: [memory-source] cannot resolve origin/main", out)
        self.assertFalse(os.path.exists(out_dir), "a failed fetch refuses rather than using stale memory")

    def test_core_memory_for_a_profile_below_the_git_root(self):  # #1537 review R1
        upstream = self.memory_remote()
        self.publish(upstream, {"sub/memory/owner.md": "# Owner\n\n- Reviewed subdirectory lesson.\n"})
        os.makedirs(os.path.join(self.tmp, "sub"))
        project = os.path.join(self.tmp, "sub", "crew.toml")
        with open(project, "w") as f:
            f.write('[runtime]\nname = "session"\n')
        code, out, out_dir = self.render(project)
        self.assertEqual(code, 0, out)
        self.assertIn("- Reviewed subdirectory lesson.", tree(out_dir)["runtime/coordinator.md"])

    def test_core_memory_in_every_role_brief(self):  # #1230
        tmux, grok = self.project('[runtime.options.notes.render]\nbuilder = ["note.md"]\n'), \
            os.path.join(self.tmp, "grok.toml")
        with open(grok, "w") as f:
            f.write('[runtime]\nname = "grok-bot"\n')
        with open(os.path.join(self.tmp, "note.md"), "w") as f:
            f.write("Note.\n")
        (_, _, before), (_, _, grok_before) = self.render(tmux), self.render(grok)
        before, grok_before = tree(before), tree(grok_before)
        files = {"memory/owner.md": "# Owner\n\n- Lead with the ask.\n", "memory/roles/builder.md": "# B\n\n- Build.\n",
                 "memory/roles/coordinator.md": "# C\n\n- Route.\n"}
        upstream = self.memory_remote()
        self.publish(upstream, files)
        os.makedirs(os.path.join(self.tmp, "memory", "roles"))
        with open(os.path.join(self.tmp, "memory", "owner.md"), "w") as f:
            f.write("# Owner\n\n- Local, unmerged edit.\n")
        snapshot, calls = cr.crew_memory.snapshot, []
        with patch.object(cr.crew_memory, "snapshot", lambda *a: calls.append(a) or snapshot(*a)):
            code, out, got = self.render(tmux)
        self.assertEqual(code, 0, out)
        self.assertEqual(len(calls), 1, "one revision per render, shared by every role output (#1537)")
        self.assertNotIn("Local, unmerged edit", "".join(tree(got).values()))
        got = tree(got)

        def section(role):
            rel = "memory/roles/%s.md" % role
            return ("\n## Core memory\n\nThe owner profile and this role's core memory, curated in git under "
                    "`memory/`. Change them only through a reviewed memory PR.\n\n### memory/owner.md\n\n"
                    + files["memory/owner.md"] + ("\n### %s\n\n%s" % (rel, files[rel]) if rel in files else ""))
        note = "\n## Render note: note.md\n\nNote.\n"
        self.assertEqual(got["runtime/builder.md"], before["runtime/builder.md"][:-len(note)] + section("builder") + note)
        self.assertEqual(got["runtime/builder-lead.md"], before["runtime/builder-lead.md"] + section("builder"))
        self.assertEqual(got["runtime/coordinator.md"], before["runtime/coordinator.md"] + section("coordinator"))
        self.assertEqual(got["runtime/reviewer.md"], before["runtime/reviewer.md"] + section("reviewer"))
        self.assertEqual({rel for rel in got if got[rel] != before[rel]},
                         set(got) - {"runtime/solo.md", "runtime/builder-fix.md", "runtime/researcher-triage.md"})
        budget = os.path.join(self.tmp, "budget")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(cr.main(["--project", tmux, "--out", budget], normalize_paths=True), 0)
        self.assertFalse(any("## Core memory" in text for text in tree(budget).values()), "the size budget skips memory")
        code, out, grok_got = self.render(grok)
        self.assertEqual(code, 0, out)
        grok_got = tree(grok_got)
        head, fence = grok_before["runtime/builder-b1.md"].rsplit("\n```", 1)
        self.assertEqual(grok_got["runtime/builder-b1.md"], head + section("builder") + "\n```" + fence)
        self.assertEqual({rel for rel in grok_got if grok_got[rel] != grok_before[rel]},
                         {"runtime/builder-b1.md", "runtime/coordinator-after-merge.md", "runtime/reviewer-validator.md",
                          "runtime/synthesizer.md", "runtime/researcher.md"})
        self.publish(upstream, {"memory/roles/builder.md": files["memory/roles/builder.md"] + "- Mail ben@example.org.\n"})
        code, out, out_dir = self.render(tmux)
        self.assertEqual(code, 1)
        self.assertEqual(out.count("[memory-personal]"), 1, out)
        self.assertIn(os.path.join(self.tmp, "memory/roles/builder.md") + ":4: [memory-personal] email address", out)
        self.assertFalse(os.path.exists(out_dir))

    def test_rebase_strategy_wording(self):
        """#952 (#874 B2): a rebase pack picks the strategy lines; a declared merge renders like no [strategy]."""
        manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(manifest) as f:
            base = f.read()
        renders = {}
        for name, table in (("none", ""), ("merge", '\n[strategy]\nupdate_from_base = "merge"\n'),
                            ("rebase", '\n[strategy]\nupdate_from_base = "rebase"\nretains_prior_heads = true\n')):
            with open(manifest, "w") as f:
                f.write(base + table)
            for runtime in ("tmux", "grok-bot"):
                path = os.path.join(self.tmp, "crew-%s-%s.toml" % (name, runtime))
                with open(path, "w") as f:
                    f.write('[runtime]\nname = "%s"\n[builder.precheck]\nenabled = true\n' % runtime)
                code, out, got = self.render(path, "--org-profile", self.org)
                self.assertEqual(code, 0, out)
                renders[name, runtime] = tree(got)
        changed = {"tmux": {"runtime/builder.md", "runtime/builder-fix.md", "runtime/solo.md", "runtime/synthesizer.md"},
                   "grok-bot": {"runtime/builder-b1.md", "runtime/builder-b2.md", "runtime/synthesizer.md"}}
        for runtime in ("tmux", "grok-bot"):
            merge, rebase = renders["none", runtime], renders["rebase", runtime]
            self.assertEqual(renders["merge", runtime], merge)
            self.assertEqual({rel for rel in merge if merge[rel] != rebase[rel]}, changed[runtime])
            self.assertFalse([rel for rel in merge if "<strategy:" in merge[rel] + rebase[rel]])
        merge, tmux, grok = renders["none", "tmux"], renders["rebase", "tmux"], renders["rebase", "grok-bot"]
        step = "1. Fresh base: fetch and rebase the unpublished branch; %s for an existing PR.\n"
        for rel in ("runtime/builder.md", "runtime/solo.md"):
            self.assertIn(step % "use merge-up", merge[rel])
            self.assertIn(step % "rebase onto `main` and upload", tmux[rel])
        self.assertIn(step % "rebase onto `main` and upload", grok["runtime/builder-b1.md"])
        self.assertIn("no rebase or force-push.", merge["runtime/builder-fix.md"])
        self.assertNotIn("no rebase or force-push.", tmux["runtime/builder-fix.md"])
        self.assertIn("rebase onto the default branch, resolve the conflict, upload the result as a new head",
                      tmux["runtime/builder-fix.md"])
        self.assertIn("Use a merge\ncommit for updates", merge["runtime/solo.md"])
        self.assertNotIn("Use a merge\ncommit for updates", tmux["runtime/solo.md"])
        self.assertIn("rebase onto it and upload a new head (`gh pr update-branch", tmux["runtime/solo.md"])
        self.assertIn("rebase onto the default branch and upload (no trains)", tmux["runtime/synthesizer.md"])
        self.assertIn("`bisect` refuse, so every train rule below is void.", tmux["runtime/synthesizer.md"])
        self.assertIn("rebase onto\nmain, resolve, upload a new head", grok["runtime/builder-b2.md"])
        self.assertIn("never train, and run\nchange.update-from-base", grok["runtime/synthesizer.md"])

    def test_unused_researcher_skips_its_brief_and_operations(self):
        """#926: researchers = 0 renders no researcher brief; every other file is unchanged."""
        code, out, upstream = self.render(self.project())
        self.assertEqual(code, 0, out)
        code, out, got = self.render(self.project('[runtime.options]\nresearchers = 0\n'))
        self.assertEqual(code, 0, out)
        upstream, got = tree(upstream), tree(got)
        self.assertIn("runtime/researcher.md", upstream)
        self.assertEqual(got, {rel: text for rel, text in upstream.items()
                               if rel not in ("runtime/researcher.md", "runtime/researcher-triage.md")})

    def test_researcher_records_by_comment_without_write_item(self):
        """#926: write-item unsupported renders the researcher record via tracker.comment, with no overlay copy."""
        manifest = os.path.join(self.tmp, "pack", "manifest.toml")
        with open(manifest) as f:
            text = f.read()
        self.assertIn('write-item = "supported"', text)
        code, out, supported = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        with open(manifest, "w") as f:
            f.write(text.replace('write-item = "supported"', 'write-item = "unsupported"'))
        code, out, got = self.render(self.project(), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        supported, got = tree(supported), tree(got)
        self.assertIn("Post one finding on the source issue (`gh issue comment <n> --body-file <file>`)",
                      supported["runtime/researcher.md"])
        self.assertIn("Post one finding on the source issue (`gh issue comment <n> -R <owner>/<repo> --body-file "
                      "<file>`)", got["runtime/researcher.md"])
        self.assertEqual({rel for rel in got if got[rel] != supported[rel]}, {"runtime/researcher.md"})
        code, out, idle = self.render(self.project('[runtime.options]\nresearchers = 0\n'), "--org-profile", self.org)
        self.assertEqual(code, 0, out)
        self.assertNotIn("runtime/researcher.md", tree(idle))

    def test_op_fallback_fails_when_no_choice_is_supported(self):
        """#926: <op:a.b|c.d> takes the first supported operation; with none it fails on the first."""
        renderer = cr.Renderer({"backends.markers.name": "github", "backends.tracker.name": "github",
                                "backends.markers.capabilities.write-item": "unsupported", "repo.owner": "acme",
                                "repo.name": "widgets"},
                               os.path.join(os.path.dirname(SCRIPTS), "templates"))
        self.assertEqual(renderer.line("<op:markers.write-item|tracker.comment>"),
                         "gh issue comment <n> -R acme/widgets --body-file <file>")
        renderer.values["backends.tracker.capabilities.comment"] = "unsupported"
        with self.assertRaisesRegex(ValueError, r"^unsupported capability markers\.write-item \(backend github\)$"):
            renderer.line("<op:markers.write-item|tracker.comment>")


class RoleRuntime(unittest.TestCase):
    """#1055: runtime.options.role_runtime renders one role from another runtime's templates."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        with open(os.path.join(os.path.dirname(SCRIPTS), "profiles", "tmux.toml")) as f:
            self.base = f.read()
        self.options = 'options = { permission_mode = "bypass", researchers = 2'
        self.assertIn(self.options + " }", self.base)

    def render(self, role_runtime=None):
        name = "crew-%d.toml" % len(os.listdir(self.tmp))
        project, out_dir = os.path.join(self.tmp, name), os.path.join(self.tmp, "out-" + name)
        with open(project, "w") as f:
            f.write(self.base if role_runtime is None else
                    self.base.replace(self.options, self.options + ", role_runtime = %s" % role_runtime))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", out_dir], normalize_paths=True)
        return code, buf.getvalue().replace(self.tmp + os.sep, ""), tree(out_dir) if code == 0 else None

    def test_session_coordinator_beside_tmux_workers(self):
        _, _, upstream = self.render()
        code, out, got = self.render('{ coordinator = "session" }')
        self.assertEqual(code, 0, out)
        self.assertEqual(sorted(got), sorted(upstream))
        self.assertEqual({rel for rel in got if got[rel] != upstream[rel]}, {"runtime/coordinator.md"})
        self.assertTrue(got["runtime/coordinator.md"].startswith("# Coordinator brief: <owner>/<repo> (session)\n"))
        self.assertIn("Concurrency caps: builder runs `5`, reviewer passes", got["runtime/coordinator.md"])
        for worker in ("builder", "reviewer", "synthesizer", "researcher"):
            self.assertTrue(got["runtime/%s.md" % worker].startswith("# "), worker)
            self.assertNotIn("(session)", got["runtime/%s.md" % worker].splitlines()[0], worker)

    def test_session_synthesizer_keeps_its_own_land_step(self):
        """#1351 merge-up: <land-step> follows the template's runtime, so a swapped-in session synthesizer keeps its
        mkdir-lock land on a tmux profile and never gets the tmux land-lock step."""
        code, out, got = self.render('{ synthesizer = "session" }')
        self.assertEqual(code, 0, out)
        synth = got["runtime/synthesizer.md"]
        self.assertIn("3. Serial land (session C7;", synth)
        self.assertNotIn("land-lock acquire", synth)

    def test_empty_override_renders_byte_identically(self):
        _, _, upstream = self.render()
        code, out, got = self.render("{}")
        self.assertEqual(code, 0, out)
        self.assertEqual(got, upstream)

    def test_missing_template_fails_closed(self):
        code, out, _ = self.render('{ builder = "grok-bot" }')
        self.assertEqual(code, 1)
        self.assertRegex(out, r"templates/runtimes/grok-bot/builder\.md:1: missing mapping: no grok-bot template "
                              r"for role builder\n")
        code, out, _ = self.render('{ researcher = "session" }')  # #1404: the session brief is sweep-only
        self.assertEqual(code, 1)
        self.assertIn("role_runtime.researcher: the session researcher brief runs only the triage sweep", out)
        code, out, _ = self.render('{ coordinator = "tmux" }')
        self.assertEqual(code, 1)
        self.assertIn("role_runtime.coordinator: unknown value 'tmux'", out)


class SessionRuntime(unittest.TestCase):
    """#914: runtime.name = "session" renders the coordinator and every worker brief."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        with open(os.path.join(os.path.dirname(SCRIPTS), "profiles", "session.toml")) as f:
            self.base = f.read()

    def render(self, repo="", normalize=False, *extra):
        project = os.path.join(self.tmp, "crew-%d.toml" % len(os.listdir(self.tmp)))
        with open(project, "w") as f:
            f.write(self.base.replace("[runtime]\n", repo + "[runtime]\n" + ('instance = "laptop"\n' if repo else "")))
        out_dir = os.path.join(self.tmp, "out-%d" % len(os.listdir(self.tmp)))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
            code = cr.main(["--project", project, "--out", out_dir, *extra], normalize_paths=normalize)
        self.assertEqual(code, 0, buf.getvalue())
        return tree(out_dir)

    def test_full_brief_set_within_budget(self):
        self.base = self.base.replace("reviewers = 1 }", "reviewers = 1, researchers = 1 }")  # #1724: opt-in sweep
        got = self.render(normalize=True)
        self.assertEqual(sorted(got), ["runtime/%s.md" % r for r in ("builder", "coordinator", "researcher", "reviewer",
                                                                     "synthesizer")])
        for rel, text in got.items():
            with self.subTest(brief=rel):
                self.assertLessEqual(len(text.encode("utf-8")), 16384)
                self.assertNotIn("<control-item:", text)
                self.assertNotIn("(tmux)", text)
                if rel != "runtime/coordinator.md":
                    self.assertIn('"This run", the block `mdstack brief` appends below; without it, or without its '
                                  "Item, Pass or Base, do not start.", " ".join(text.split()))
        coordinator = " ".join(got["runtime/coordinator.md"].split())
        for rule in ("builder runs `2`, reviewer passes `1`, synthesizer runs 1;", "Session backend `native`",
                     "While the owner is present, admit at most `2` builder runs and `1` reviewer passes;",  # #1053
                     'Append its "## This run" block verbatim to the worker prompt',
                     "Exit 2 (a missing Item, Pass or Base) means do not dispatch."):
            self.assertIn(rule, coordinator)

    def test_release_delegation_renders_in_coordinator(self):  # #1542: #1435 parity with the tmux coordinator
        self.assertIn('Cut go: `release_delegation = "none"` (docs/release.md).', self.render()["runtime/coordinator.md"])
        self.base = self.base.replace("reviewers = 1 }", 'reviewers = 1, release_delegation = "make releases https://x/985#c1" }')
        coordinator = self.render()["runtime/coordinator.md"]
        self.assertIn('Cut go: `release_delegation = "make releases https://x/985#c1"` (docs/release.md).', coordinator)

    def test_present_caps_render(self):  # #1053
        self.base = self.base.replace("builders = 2, reviewers = 1", "builders = 4, reviewers = 3, present_builders = 1")
        coordinator = " ".join(self.render()["runtime/coordinator.md"].split())
        self.assertIn("builder runs `4`, reviewer passes `3`", coordinator)
        self.assertIn("admit at most `1` builder runs and `3` reviewer passes; an active recorded non-quiet away "
                      "entry uses the full caps.", coordinator)

    def test_researchers_positive_cap_adds_only_the_sweep_brief(self):  # #1057; #1404; #1724: opt-in sweep
        unset = self.render()
        self.assertEqual(sorted(unset), ["runtime/builder.md", "runtime/coordinator.md", "runtime/reviewer.md",
                                         "runtime/synthesizer.md"])
        base = self.base
        for cap in ("1", "2"):
            self.base = base.replace("reviewers = 1 }", "reviewers = 1, researchers = %s }" % cap)
            swept = self.render()
            sweep = " ".join(swept.pop("runtime/researcher.md").split())
            for rule in ("This binding runs only the triage sweep", "## Triage sweep", "pass=triage-log",
                         "$CREW_BIN poll --triage-only"):
                self.assertIn(rule, sweep)
            self.assertEqual(swept, unset, cap)
        self.base = base.replace("reviewers = 1 }", "reviewers = 1, researchers = 0 }")
        self.assertIn("researchers = 0", self.base)
        self.assertEqual(self.render(), unset)

    def test_render_note_for_unrendered_role_fails(self):  # #1054
        for name in ("note.md", "lead.md"):
            with open(os.path.join(self.tmp, name), "w") as f:
                f.write("Note.\n")

        def render(notes):
            project = os.path.join(self.tmp, "crew-%d.toml" % len(os.listdir(self.tmp)))
            with open(project, "w") as f:
                f.write(self.base.replace("reviewers = 1 }", "reviewers = 1, researchers = 1, notes = { render = { %s } } }"
                                          % notes))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                code = cr.main(["--project", project, "--out", os.path.join(self.tmp, "out-%d" % len(os.listdir(self.tmp)))])
            return code, buf.getvalue(), project

        code, out, project = render('builder = ["note.md"], builder-lead = ["lead.md"], researcher = ["note.md"]')
        self.assertEqual(code, 1, out)
        self.assertEqual(out.splitlines(), [
            "%s:1: runtime.options.notes.render.%s: runtime session renders no %s brief (note dropped)" % (project, r, r)
            for r in ("builder-lead",)])
        code, out, _ = render('builder = ["note.md"], builder-lead = []')
        self.assertEqual(code, 0, out)
        self.assertTrue(tree(out.splitlines()[0].rsplit("/runtime/", 1)[0])["runtime/builder.md"]
                        .endswith("\n## Render note: note.md\n\nNote.\n"))

    def test_control_item_selects_ownership_text(self):
        none = self.render()
        coordinator = none["runtime/coordinator.md"]
        self.assertIn("This profile sets no `repo.control_item`, so there is no ownership record", coordinator)
        for inert in ("## Guard", "claimed", "## Quota", "## Outgoing", "## Incoming", "ownership --project",
                      "runtime id"):
            self.assertNotIn(inert, coordinator)
        for role in ("builder", "reviewer", "synthesizer"):
            self.assertNotIn("Ownership:", none["runtime/%s.md" % role])
        with open(os.path.join(os.path.dirname(SCRIPTS), "templates", "backends", "github.toml")) as f:
            org = write_pack(os.path.join(self.tmp, "pack"), mapping=f.read().replace("\n[ids]\n", '\n[ids]\nitem = "[A-Z]+-[0-9]+"\n'))
        for item, shown, extra in (("985", "985", ()), ('"OPS-1042"', "OPS-1042", ("--org-profile", org))):
            with self.subTest(control_item=item):  # a tracker-native item (#937) counts as a control item
                got = self.render('[repo]\ncontrol_item = %s\n\n' % item, False, *extra)
                coordinator = got["runtime/coordinator.md"]
                self.assertNotIn("sets no `repo.control_item`", coordinator)
                for kept in ("This session's runtime id is `session@laptop`.", "## Guard", "## Quota",
                             "## Outgoing: `/crew handoff to RUNTIME-ID", "## Incoming", "(`%s`), post `claimed`" % shown):
                    self.assertIn(kept, coordinator)
                for role in ("builder", "reviewer", "synthesizer"):
                    brief = got["runtime/%s.md" % role]
                    self.assertIn("Ownership: at each wake and before dispatch, run", brief)
                    self.assertEqual(brief.replace(brief[brief.index("Ownership:"):brief.index("Flavor:")], ""),
                                     none["runtime/%s.md" % role])


    def test_hosted_backend_renders_control_plane_dispatch(self):  # #1052
        for repo in ("", "[repo]\ncontrol_item = 985\n\n"):
            with self.subTest(control_item=bool(repo)):
                local = self.render(repo)
                self.base = self.base.replace('session_backend = "native"', 'session_backend = "hosted"')
                hosted = self.render(repo)
                self.base = self.base.replace('session_backend = "hosted"', 'session_backend = "native"')
                self.assertEqual(sorted(hosted), sorted(local))
                for rel, text in hosted.items():
                    self.assertNotIn("<session-backend:", text)
                    self.assertIsNone(re.search(r"subagent|\bPID\b|native|task handle", text, re.I), rel)
                    self.assertIn("hosted session", " ".join(text.split()), rel)
                coordinator = " ".join(hosted["runtime/coordinator.md"].split())
                for rule in ("Session backend `hosted`: create each worker as a hosted session through the control "
                             "plane and record the session id it returns as the worker's handle; check liveness by "
                             "reading that session's state from the control plane.",
                             "a completed session state alone is not a pass result."):
                    self.assertIn(rule, coordinator)
                self.assertEqual("let each hosted session finish its round" in coordinator, bool(repo))
                for rel, text in local.items():
                    self.assertNotIn("<session-backend:", text)
                    self.assertNotIn("hosted session", " ".join(text.split()), rel)

    def test_assigned_checkout_isolation_replaces_the_worktree_sentence(self):  # #1959
        default = self.render()
        base = self.base
        self.base = base.replace('session_backend = "native"', 'session_backend = "native", isolation = "worktree"')
        self.assertEqual(self.render(), default)
        for backend, sentence in (("native", "CLI run whose PID and OS start time you record. Each worker and probe runs "
                                             "in its pre-provisioned dedicated checkout and creates no worktree; none "
                                             "shares this checkout."),
                                  ("hosted", "control plane. Each worker and probe runs in its pre-provisioned dedicated "
                                             "checkout and creates no worktree; none shares this checkout.")):
            with self.subTest(backend=backend):
                self.base = base.replace('session_backend = "native"',
                                         'session_backend = "%s", isolation = "assigned-checkout"' % backend)
                got = self.render()
                self.base = base.replace('session_backend = "native"', 'session_backend = "%s"' % backend)
                worktree = self.render()
                coordinator = " ".join(got["runtime/coordinator.md"].split())
                self.assertIn(sentence, coordinator)
                self.assertNotIn("<isolation:", got["runtime/coordinator.md"])
                self.assertNotIn("Give each worker and probe its own worktree", coordinator)
                self.assertNotIn("<n>-<sha7>-<role>-<pass>/", coordinator)
                self.assertIn("Give each worker and probe its own worktree", " ".join(worktree["runtime/coordinator.md"].split()))
                self.assertEqual({k: v for k, v in got.items() if k != "runtime/coordinator.md"},
                                 {k: v for k, v in worktree.items() if k != "runtime/coordinator.md"})
        self.base = base

    def test_land_step_holds_a_working_lock(self):
        synth = self.render()["runtime/synthesizer.md"]
        step = synth[synth.index("3. Serial land"):synth.index("\n4. ")]
        self.assertNotIn("land-lock acquire", step)  # mdstack land-lock refuses session profiles (PR #1040 review)
        flat = " ".join(step.split())
        for rule in ("append `blocked: #<n> land lock held` to `$CREW_STATUS` and stop",
                     "repeat the step 2 check at the live head", "If the gate fails or the head moved, release and stop."):
            self.assertIn(rule, flat)
        acquire, release = re.findall(r"`(mkdir -p [^`]+|rmdir [^`]+)`", step)
        self.assertLess(flat.index("repeat the step 2 check"), flat.index(release))
        env = dict(os.environ, CREW_STATE=os.path.join(self.tmp, "state"))
        sh = lambda cmd: subprocess.run(["sh", "-c", cmd], env=env, capture_output=True).returncode
        self.assertEqual(sh(acquire), 0)
        self.assertNotEqual(sh(acquire), 0)  # a second synthesizer is refused while the lock is held
        self.assertEqual(sh(release), 0)
        self.assertEqual(sh(acquire), 0)

    def test_synthesizer_lands_alone_without_tmux_only_commands(self):
        """#1041: `mdstack train`, `land` and `land-lock` refuse a session profile, so the brief runs none of them."""
        base = self.base
        for opts in ("", 'lone_pr_land = "direct", '):
            with self.subTest(opts=opts):
                self.base = base.replace("builders = 2", opts + "builders = 2")
                synth = self.render()["runtime/synthesizer.md"]
                flat = " ".join(synth.split())
                self.assertEqual(re.findall(r"\$CREW_BIN (?:train|land|land-lock)\b", synth), [])
                self.assertEqual([m for m in re.findall(r"mdstack (?:train|land|land-lock)\b[^.]*", flat)
                                  if "refuses" not in m and "never run it" not in m], [])
                self.assertNotIn("Merge train (mdstack train)", synth)
                for rule in ("session lands have no merge train", "Land each ready PR alone through step 3, one per run",
                             "`Land rule: alone, direct`",
                             "If express resolves (`core/crew-config.py class-flavor --express`)"):
                    self.assertIn(rule, flat)

    def test_synthesizer_renders_sections_the_merge_gate_refers_to(self):
        """#1539: the shared merge gate points "below" to gate-status and verdict portability."""
        synth = self.render()["runtime/synthesizer.md"]
        flat = " ".join(synth.split())
        for ref in ("report gate-status below", "carried only under the portability check below"):
            self.assertIn(ref, flat)
        for section in ("Verdict portability: apply protocol §7's full content",
                        "Gate-status reporting (diagnostic only; changes no gate or exemption):",
                        "pass=gate-status pr=<n> sha=<head-sha>"):
            self.assertIn(section, flat)
            self.assertLess(flat.index("report gate-status below"), flat.index(section))
        self.assertIn("otherwise edit that review body in place with gh api --method PUT", flat)


class SecretRetrieval(unittest.TestCase):
    """#397: every coordinator brief carries the secret-retrieval rule; no rendered brief prints a secret."""

    RULE = "Secret retrieval: never suggest a command that prints a secret"
    PRINTS = re.compile(r"printenv \w+\b(?! \|)|echo \$\w*(?:KEY|TOKEN|SECRET|PASS)\b(?! \|)|cat \S*\.env\b(?! \|)"
                        r"|(?<!\$\()gh auth token\b")

    def renders(self, tmp):
        for runtime in ("tmux", "session", "grok-bot"):
            project = os.path.join(tmp, "%s.toml" % runtime)
            with open(project, "w") as f:
                f.write('[runtime]\nname = "%s"\n' % runtime)
            out = os.path.join(tmp, runtime)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cr.main(["--project", project, "--out", out]), 0)
            yield runtime, tree(os.path.join(out, "runtime"))

    def test_rule_in_coordinators_and_no_secret_print(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, got in self.renders(tmp):
                coordinators = sorted(rel for rel in got if rel.startswith("coordinator") and rel != "coordinator-wiring.md")
                self.assertTrue(coordinators, runtime)
                for rel, text in got.items():
                    flat = " ".join(text.split())
                    with self.subTest(runtime=runtime, brief=rel):
                        if rel in coordinators:
                            self.assertTrue(self.RULE in flat, "no secret-retrieval rule in %s/%s" % (runtime, rel))
                        start = flat.find(self.RULE)
                        if start >= 0:
                            flat = flat[:start] + flat[flat.index("length or last 4.", start):]
                        self.assertEqual(self.PRINTS.findall(flat), [])

    def test_lint_catches_a_secret_print(self):
        for bad in ("run `printenv TODO_API_KEY`", "`echo $API_KEY`", "`cat .env`", "`gh auth token`"):
            self.assertTrue(self.PRINTS.search(bad), bad)
        for ok in ("`printenv API_KEY | pbcopy`", 'GH_TOKEN="$(gh auth token --user x)"', "`cat .env | pbcopy`"):
            self.assertFalse(self.PRINTS.search(ok), ok)



class OwnerConfigAuthorization(unittest.TestCase):
    """#372: every coordinator brief carries the owner-config authorization rule (instruction presence only)."""

    CLAUSES = (
        "Owner config (profile, team file, config): edit only within a recorded owner authorization's scope,",
        "or a documented repair's; report the key and link the record, no new ask.",
        "Else keep the config, report the unusable path and reason, and route it to the §6 owner-decision path.",
        "Owner-only settings stay restricted.",
    )
    POINTER = ("Owner config: edit only under a recorded authorization, per `", "/docs/roles.md`, Owner config edits.")

    def test_rule_in_every_coordinator_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            for runtime, got in SecretRetrieval().renders(tmp):
                coordinators = sorted(rel for rel in got if rel.startswith("coordinator") and rel != "coordinator-wiring.md")
                self.assertTrue(coordinators, runtime)
                for rel in coordinators:
                    flat = " ".join(got[rel].split())
                    if runtime == "tmux":  # size budget: a pointer to the roles.md section, like the usage line
                        for part in self.POINTER:
                            self.assertIn(part, flat)
                        continue
                    for clause in self.CLAUSES:
                        with self.subTest(runtime=runtime, brief=rel, clause=clause[:30]):
                            self.assertIn(clause, flat)


if __name__ == "__main__":
    unittest.main()
