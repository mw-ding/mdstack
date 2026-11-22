#!/usr/bin/env python3
"""Offline tests for core/crew-config.py validate (stdlib only).

Covers the validator (valid profile, missing key, unknown concern and backend,
token-shaped value, wrong type) and the resolver (layer precedence, merge rule,
dropped invariant key, cross-key checks, pack manifest folding with unsupported
and undeclared operations, `resolve_profile` returning what the CLI prints); the
default profile and GitHub pack manifest validate, cover every concern with no
`unsupported` capability, and match the roles.md routing; and the host
inventory and placement keys (#204: overlay names only, secret patterns,
unknown capability, one primary, placement hosts and rule needs, tmux only,
merge across layers); and `precheck-scope` path ownership (#881). Run in CI.
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

TESTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # dev/tests/
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(TESTS)), "scripts")
spec = importlib.util.spec_from_file_location("crew_config", os.path.join(os.path.dirname(SCRIPTS), "core", "crew-config.py"))
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)

CONCERNS = ["change", "review", "tracker", "state-tags", "markers", "ci", "events", "owner-channel", "release"]

VALID = """\
[repo]
owner = "acme"
name = "widgets"

[runtime]
name = "tmux"
options = { builders = 3 }

%s

[identities]
owners = ["acme-owner"]
coordinator = { gh_user = "acme-bot" }
builder = { gh_user = "acme-bot" }
reviewer = { gh_user = "acme-reviewer" }
synthesizer = { gh_user = "acme-bot" }

[engines]
coordinator = "codex"
trivial = { order = ["claude-code/sonnet"] }
default = { order = ["codex/gpt-6.1-sol", "claude-code/sonnet"], effort = "medium" }
deep = { order = ["codex/gpt-6.1-sol"] }

[paths]
state_dir = "/srv/crew-state"
worktree_root = "/srv/wt"
""" % "\n".join('[backends.%s]\nname = "github"' % c for c in CONCERNS)


def validate(text, install=False):
    """Write text to a temp crew.toml, run `validate`, return (code, stdout lines)."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "crew.toml")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cc.main(["validate", path] + (["--install"] if install else []))
        lines = [ln.replace(path, "crew.toml") for ln in out.getvalue().splitlines()]
        return code, lines



class IdleBuilderProfile(unittest.TestCase):
    def test_idle_builder_ttl_is_nonnegative_integer(self):
        for ttl in (0, 30, 1800):
            self.assertEqual(validate(VALID.replace("builders = 3", "idle_builder_ttl = %d" % ttl))[0], 0)
        for ttl in ("-1", '"30"', "true"):
            self.assertEqual(validate(VALID.replace("builders = 3", "idle_builder_ttl = " + ttl))[0], 1)


class SlackProfile(unittest.TestCase):
    def test_notify_binding_env_and_closed_scope(self):
        text = VALID.replace('[backends.owner-channel]\nname = "github"',
                             '[backends.owner-channel]\nname = "slack"').replace(
                                 'options = { builders = 3 }',
                                 'options = { slack_webhook_env = "CREW_SLACK_WEBHOOK_URL", slack_digest_interval = 60 }')
        self.assertEqual(validate(text)[0], 0)
        for bad in (text.replace('slack_digest_interval = 60', 'slack_digest_interval = 0'),
                    text.replace('CREW_SLACK_WEBHOOK_URL', 'https://example.test/webhook'),
                    text.replace('slack_webhook_env = "CREW_SLACK_WEBHOOK_URL", ', ''),
                    text.replace('[backends.change]\nname = "github"', '[backends.change]\nname = "slack"'),
                    text.replace('name = "tmux"', 'name = "grok-bot"')):
            self.assertEqual(validate(bad)[0], 1)


class FlavorTest(unittest.TestCase):
    def test_solo_preset_keeps_standard_rigor_and_changes_builder_only(self):
        solo = dict(cc.FLAVOR_PRESETS["solo"])
        self.assertEqual(solo.pop("builder"), "solo")
        standard = dict(cc.FLAVOR_PRESETS["standard"])
        standard.pop("builder")
        self.assertEqual(solo, standard)

    def test_presets_and_custom(self):
        for name in set(cc.FLAVOR_PRESETS) - {"express"}:
            code, lines = validate(VALID + '\n[flavor]\nname = "%s"\n' % name)
            self.assertEqual(code, 0, lines)
        text = VALID + '''
[flavor]
name = "docs-site"
goal = "speed"
[flavor.custom.docs-site]
base = "fast"
review = "light"
merge = "docs"
caps = [1, 2]
parallelism = { builders = 2, reviewers = 1 }
engines = { default = { order = ["codex/gpt-6.1-sol"], effort = "medium" } }
'''
        self.assertEqual(validate(text)[0], 0)

    def test_floor_items(self):
        cases = [("ci = \"off\"", 1), ("ci_waiver = true", 1),
                 ('review = "' + 'ghp_' + 'a' * 36 + '"', 2),
                 ("landing_role = \"builder\"", 3), ("audit = false", 4),
                 ("review = \"off\"", 4), ("hold = false", 5),
                 ("gate_changes = \"auto\"", 6), ("sensitive_merge = \"auto\"", 7),
                 ("caps = [3, 0]", 1)]
        for setting, floor in cases:
            with self.subTest(setting=setting):
                text = VALID + '\n[flavor.custom.test]\nbase = "fast"\n' + setting + '\n'
                code, lines = validate(text)
                self.assertEqual(code, 1, lines)
                self.assertTrue(any("floor F%d:" % floor in line for line in lines), lines)
        for section in ("flavor", "flavor.custom.test", "flavor.classes"):
            prefix = '\n[[%s]]\n' % section if section.endswith('classes') else '\n[%s]\n' % section
            self.assertEqual(validate(VALID + prefix + 'ci = "off"\n')[0], 1)

    def test_express_is_item_only_and_selfgate_engine_knob(self):
        express = cc.FLAVOR_PRESETS["express"]
        self.assertEqual((express["review"], express["validation"], express["merge"], express["selfgate_engine"]),
                         ("off", "off", "auto", "different"))
        for setting, key in [('name = "express"', 'flavor.name'),
                             ('custom = { x = { base = "express" } }', 'flavor.custom.x.base'),
                             ('classes = [{ paths = ["docs/**"], flavor = "express", reason = "r" }]', 'flavor.classes[0].flavor'),
                             ('selfgate_engine = "other"', 'flavor.selfgate_engine'),
                             ('custom = { x = { base = "fast", selfgate_engine = "same" } }', 'flavor.custom.x.selfgate_engine')]:
            with self.subTest(setting=setting):
                code, lines = validate(VALID + '\n[flavor]\n' + setting + '\n')
                self.assertEqual(code, 1, lines)
                self.assertTrue(any(key in line for line in lines), lines)
        for value in cc.SELFGATE_ENGINES:
            self.assertEqual(validate(VALID + '\n[flavor]\nselfgate_engine = "%s"\n' % value)[0], 0)
        code, lines = validate(VALID + '\n[flavor.custom.x]\nbase = "standard"\nreview = "off"\n')
        self.assertEqual(code, 1, lines)
        self.assertTrue(any("floor F4:" in line for line in lines), lines)

    def test_closed_schema_names_bounds_and_engines(self):
        cases = [('name = "unknown"', 'flavor.name'), ('goal = "unknown"', 'flavor.goal'),
                 ('typo = true', 'flavor.typo'), ('custom = []', 'flavor.custom'),
                 ('classes = [1]', 'flavor.classes[0]')]
        cases += [('custom = { test = { base = "fast", %s } }' % setting, key)
                  for setting, key in [('review = "unknown"', '.review'), ('caps = [0, 3]', '.caps'),
                                       ('caps = [3, 4]', '.caps'), ('caps = [true, 2]', '.caps'),
                                       ('caps = [2]', '.caps'), ('parallelism = { builders = 4 }', '.parallelism.builders'),
                                       ('parallelism = { reviewers = 0 }', '.parallelism.reviewers'),
                                       ('engines = { deep = { effort = "low" } }', '.engines.deep.effort'),
                                       ('engines = { default = { order = ["unknown/auto"] } }', '.engines.default.order'),
                                       ('engines = { default = { order = [] } }', '.engines.default.order')]]
        cases += [('custom = { fast = { base = "standard" } }', 'shadows a preset'),
                  ('custom = { solo = { base = "standard" } }', 'shadows a preset'),
                  ('custom = { a = { base = "b" }, b = { base = "fast" } }', '.base')]
        for setting, key in cases:
            with self.subTest(setting=setting):
                code, lines = validate(VALID + '\n[flavor]\n' + setting + '\n')
                self.assertEqual(code, 1, lines)
                self.assertTrue(any(key in line for line in lines), lines)

    def test_class_lowering_reason(self):
        for name, reason, status in [('fast', '', 1), ('fast', 'reason = " "', 1),
                                     ('fast', 'reason = "docs only"', 0), ('thorough', '', 0)]:
            text = VALID + '\n[flavor]\nname = "standard"\n[[flavor.classes]]\npaths = ["docs/**"]\nflavor = "%s"\n%s\n' % (name, reason)
            self.assertEqual(validate(text)[0], status)
        for paths in ('[]', '["../docs/**"]', '["/docs/**"]', '[" "]'):
            text = VALID + '\n[[flavor.classes]]\npaths = %s\nflavor = "thorough"\n' % paths
            self.assertEqual(validate(text)[0], 1)
        text = VALID + '\n[flavor.custom.less]\nbase = "thorough"\ncaps = [2, 3]\n[[flavor.classes]]\npaths = ["docs/**"]\nflavor = "less"\n'
        self.assertEqual(validate(text)[0], 1)

    def test_layer_merging_classes_replacement_and_gap(self):
        with tempfile.TemporaryDirectory() as d:
            project, org = os.path.join(d, "crew.toml"), os.path.join(d, "org.toml")
            with open(project, "w") as f:
                f.write(VALID)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cc.main(["resolve", "--project", project]), 0)
            self.assertIn('flavor.name = "standard"  # core (unset: flagged)', out.getvalue())
            for name in ("thorough", "standard"):
                with open(project, "w") as f:
                    f.write(VALID + '\n[flavor]\nname = "%s"\n' % name)
                profile, prov, problems, _ = cc.resolve_profile(project)
                self.assertEqual((problems, profile["flavor"]["name"], prov["flavor.name"]), ([], name, "project"))
            with open(org, "w") as f:
                f.write('[flavor]\nname = "site"\nclasses = [{ paths = ["old/**"], flavor = "thorough" }]\n[flavor.custom.site]\nbase = "fast"\nmerge = "docs"\n')
            with open(project, "w") as f:
                f.write(VALID + '\n[flavor]\nclasses = []\n[flavor.custom.site]\nreview = "full"\n')
            profile, prov, problems, _ = cc.resolve_profile(project, org)
            self.assertEqual(problems, [])
            self.assertEqual(profile['flavor']['custom']['site'], {'base': 'fast', 'merge': 'docs', 'review': 'full'})
            self.assertEqual(profile['flavor']['classes'], [])
            self.assertEqual(prov['flavor.custom.site.review'], 'project')
            self.assertEqual(prov['flavor.custom.site.base'], 'org')


class ClassFlavorTest(unittest.TestCase):
    def profile(self):
        return {"flavor": {"name": "standard", "classes": [
            {"paths": ["docs/**", "*.md"], "flavor": "fast", "reason": "docs only"},
            {"paths": ["docs/private/*"], "flavor": "thorough"},
            {"paths": ["src/?.py"], "flavor": "fast", "reason": "spikes"}]}}

    def test_dialect_overlap_and_unmatched_paths(self):
        profile = self.profile()
        cases = [("README.md", [0], "thin"), ("docs/nested/a.md", [0], "thin"),
                 ("docs/private/a.md", [0, 1], "full"), ("docs/private/nested/a.md", [0], "thin"),
                 ("src/a.py", [2], "thin"), ("src/ab.py", [], "thin"),
                 ("nested/README.md", [], "thin")]
        for path, indexes, review in cases:
            with self.subTest(path=path):
                result = cc.class_flavor(profile, [path])
                self.assertEqual(result["matches"], {path: indexes})
                self.assertEqual(result["rigor"]["review"], review)
                expected = "off" if indexes == [0] or indexes == [2] else "always" if 1 in indexes else "behaviour"
                self.assertEqual(result["rigor"]["validation"], expected)

    def test_mixed_paths_and_order_independence(self):
        profile = self.profile()
        result = cc.class_flavor(profile, ["docs/a.md", "src/main.py"])
        self.assertEqual(result["rigor"]["validation"], "behaviour")
        self.assertEqual(result["rigor"]["caps"], [3, 3])
        self.assertEqual(result, cc.class_flavor(profile, ["src/main.py", "docs/a.md", "docs/a.md"]))
        profile["flavor"]["classes"].reverse()
        self.assertEqual(result["rigor"], cc.class_flavor(profile, ["src/main.py", "docs/a.md"])["rigor"])

    def test_custom_knob_wise_combination_without_resources(self):
        profile = {"flavor": {"name": "standard", "custom": {
            "a": {"base": "fast", "review": "full", "caps": [1, 3], "parallelism": {"builders": 1}},
            "b": {"base": "standard", "diversity": "required", "caps": [3, 1]}}, "classes": [
                {"paths": ["docs/**"], "flavor": "a", "reason": "docs"},
                {"paths": ["docs/**"], "flavor": "b", "reason": "docs"}]}}
        rigor = cc.class_flavor(profile, ["docs/a.md"])["rigor"]
        self.assertEqual(rigor, {"review": "full", "validation": "behaviour", "diversity": "required",
                                 "evidence": "typed", "merge": "docs", "precheck": "on",
                                 "lighter_lane": "docs", "validation_scope": "bounded", "caps": [3, 3]})

    def test_defaults_empty_paths_and_invalid_paths(self):
        self.assertEqual(cc.class_flavor({}, ["unknown.py"])["rigor"]["review"], "thin")
        self.assertEqual(cc.class_flavor(self.profile(), [])["rigor"]["validation"], "behaviour")
        for path in ("/docs/a.md", "../docs/a.md", "docs/../a.md", "./README.md", "docs//a.md", " "):
            with self.subTest(path=path), self.assertRaises(ValueError):
                cc.class_flavor(self.profile(), [path])

    def test_express_resolution(self):
        profile = self.profile()
        result = cc.class_flavor(profile, ["src/main.py", "docs/a.md"], express=True)
        self.assertEqual((result["lane"], result["tightening"]), ("express", []))
        self.assertEqual(result["rigor"], {"review": "off", "validation": "off", "diversity": "waivable",
                                           "evidence": "typed", "merge": "auto", "precheck": "on",
                                           "lighter_lane": "docs", "validation_scope": "bounded", "caps": [3, 3],
                                           "selfgate_engine": "different"})
        profile["flavor"]["selfgate_engine"] = "same"
        self.assertEqual(cc.class_flavor(profile, [], express=True)["rigor"]["selfgate_engine"], "same")
        tight = cc.class_flavor(profile, ["src/main.py", "docs/private/a.md"], express=True)
        self.assertEqual((tight["lane"], tight["tightening"]), ("crew", [1]))
        self.assertEqual(tight["rigor"], cc.class_flavor(profile, ["src/main.py", "docs/private/a.md"])["rigor"])
        self.assertEqual(cc.class_flavor(profile, ["src/main.py"])["lane"], "crew")
        caps = {"flavor": {"name": "standard", "custom": {"more": {"base": "fast", "caps": [3, 3]}},
                           "classes": [{"paths": ["a/**"], "flavor": "more", "reason": "r"}]}}
        self.assertEqual(cc.class_flavor(caps, ["a/b.py"], express=True)["lane"], "express")
        caps["flavor"]["name"] = "fast"
        caps["flavor"]["custom"]["more"]["review"] = "full"
        self.assertEqual(cc.class_flavor(caps, ["a/b.py"], express=True)["lane"], "crew")

    def test_cli_layers_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            project, org = os.path.join(d, "crew.toml"), os.path.join(d, "org.toml")
            with open(org, "w") as f:
                f.write('[flavor]\nname = "standard"\nclasses = [{ paths = ["docs/**"], flavor = "thorough" }]\n')
            with open(project, "w") as f:
                f.write(VALID + '\n[flavor]\nclasses = [{ paths = ["docs/**"], flavor = "fast", reason = "docs" }]\n')
            def run(paths):
                out, err = io.StringIO(), io.StringIO()
                with patch("sys.stdin", io.StringIO(paths)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = cc.main(["class-flavor", "--project", project, "--org-profile", org])
                return code, out.getvalue(), err.getvalue()
            code, out, err = run("docs/a.md\n")
            self.assertEqual(code, 0, err)
            self.assertEqual(json.loads(out)["rigor"]["validation"], "off")
            self.assertEqual(json.loads(out)["project"], "standard")
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.stdin", io.StringIO("docs/a.md\n")), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cc.main(["class-flavor", "--project", project, "--org-profile", org, "--express"])
            self.assertEqual((code, json.loads(out.getvalue())["lane"]), (0, "express"), err.getvalue())
            self.assertEqual(run("../docs/a.md\n")[0:2], (1, ""))
            with open(project, "a") as f:
                f.write('name = "unknown"\n')
            code, out, err = run("docs/a.md\n")
            self.assertEqual((code, out), (1, ""))
            self.assertIn("flavor.name", err)


class ValidateTest(unittest.TestCase):
    def test_runtime_notes_schema(self):
        for notes in ('{}', '{ builder = [], reviewer = ["review.md"], synthesizer = ["/srv/land.md"] }',
                      '{ render = { coordinator = ["c.md"], builder-lead = ["lead.md"], reviewer-lead = [] } }'):
            code, lines = validate(VALID.replace('options = { builders = 3 }', 'options = { notes = %s }' % notes))
            self.assertEqual(code, 0, lines)
        for notes, expected in [('[]', 'notes: expected table, got list'),
                                ('{ unknown = [] }', 'notes.unknown: unknown key'),
                                ('{ builder = "a.md" }', 'notes.builder: expected list, got string'),
                                ('{ builder = [1] }', 'notes.builder[0]: expected a nonempty file path'),
                                ('{ builder = [" "] }', 'notes.builder[0]: expected a nonempty file path'),
                                ('{ builder-lead = [] }', 'notes.builder-lead: unknown key'),
                                ('{ render = [] }', 'notes.render: expected table, got list'),
                                ('{ render = { solo = [] } }', 'notes.render.solo: unknown key'),
                                ('{ render = { reviewer-lead = [""] } }',
                                 'notes.render.reviewer-lead[0]: expected a nonempty file path')]:
            self.assertFails(VALID.replace('options = { builders = 3 }', 'options = { notes = %s }' % notes),
                             'crew.toml:runtime.options.' + expected)

    def test_session_runtime_selector_and_options(self):  # #914
        session = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { %s }')
        for options in ("", 'session_backend = "cli", builders = 2, reviewers = 1, max_active_milestones = 2',
                        'session_backend = "hosted"',  # #1052
                        'merge_grant = "none", lone_pr_land = "direct", train_min = 3, mirror = "none", notes = {}',
                        'researchers = 0',  # #1057: the documented no-researcher statement survives a tmux migration
                        'researchers = 1',  # #1404: the session triage sweep worker
                        # #1548: mdstack up's coordinator launch; coordinator = none needs no roles value
                        'session = "ash-solo", permission_mode = "safe", launch = { coordinator = "none", resume = "abc-1" }'):
            code, lines = validate(session % options)
            self.assertEqual(code, 0, lines)
        for options, expected in [
                ('session_backend = "tmux"', "session_backend: unknown value 'tmux' (expected one of: native, cli, hosted)"),
                ('researchers = -1', "researchers: must be >= 0, got -1"),
                ('researchers = "0"', "researchers: expected integer, got string"),
                ('tmux_server = "default"', "tmux_server: unknown key"),
                ('permission_mode = "yolo"', "permission_mode: unknown value 'yolo' (expected one of: bypass, auto, safe)"),
                ('launch = { coordinator = "screen" }', "launch.coordinator: unknown value 'screen' (expected one of: tmux, none)"),
                ('max_active_milestones = 0', "max_active_milestones: must be >= 1, got 0")]:
            self.assertFails(session % options, "crew.toml:runtime.options." + expected)

    def test_session_release_delegation_resolves_and_needs_a_link(self):  # #1542: #1435 parity
        session = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { %s }')
        code, lines = resolve(session % "")
        self.assertEqual(code, 0, lines)
        self.assertIn('runtime.options.release_delegation = "none"  # core', lines)
        code, lines = resolve(session % 'release_delegation = "make releases https://github.com/o/r/issues/985#c1"')
        self.assertEqual(code, 0, lines)
        self.assertIn('runtime.options.release_delegation = "make releases https://github.com/o/r/issues/985#c1"  # project',
                      lines)
        self.assertFails(session % 'release_delegation = "releases ok"', "crew.toml:runtime.options.release_delegation: "
                         "expected the owner's recorded words with a https:// link to the record")

    def test_session_present_caps_bounded_by_full_caps(self):  # #1053
        session = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { %s }')
        for options in ("present_builders = 5, present_reviewers = 2", "builders = 3, present_builders = 1",
                        "builders = 3, reviewers = 3, present_builders = 3, present_reviewers = 3"):
            code, lines = validate(session % options)
            self.assertEqual(code, 0, (options, lines))
        for options, expected in [
                ("builders = 2, present_builders = 3", "present_builders: must be <= builders (2), got 3"),
                ("present_builders = 6", "present_builders: must be <= builders (5), got 6"),
                ("present_reviewers = 3", "present_reviewers: must be <= reviewers (2), got 3"),
                ("present_reviewers = 0", "present_reviewers: must be >= 1, got 0"),
                ('present_builders = "2"', "present_builders: expected integer, got string")]:
            self.assertFails(session % options, "crew.toml:runtime.options." + expected)
        # tmux keeps its admission-time clamp: an over-cap present limit still validates.
        code, lines = validate(VALID.replace("builders = 3", "builders = 3, present_builders = 9, present_reviewers = 9"))
        self.assertEqual(code, 0, lines)
        self.assertFails(VALID.replace("builders = 3", 'session_backend = "native"'),
                         "crew.toml:runtime.options.session_backend: unknown value 'native' (expected one of: tmux, herdr)")
        for server in ("default", "dedicated"):  # #1327
            code, lines = validate(VALID.replace("builders = 3", 'tmux_server = "%s"' % server))
            self.assertEqual(code, 0, lines)
        self.assertFails(VALID.replace("builders = 3", 'tmux_server = "own"'),
                         "crew.toml:runtime.options.tmux_server: unknown value 'own' (expected one of: default, dedicated)")
        self.assertFails(VALID.replace('name = "tmux"', 'name = "hosted"'),
                         "crew.toml:runtime.name: unknown value 'hosted' (expected one of: grok-bot, tmux, session)")

    def test_role_runtime_schema(self):  # #1055
        code, lines = resolve(VALID)
        self.assertFalse([ln for ln in lines if "role_runtime" in ln], lines)
        for value in ('{}', '{ coordinator = "session" }', '{ coordinator = "session", builder = "grok-bot" }'):
            code, lines = validate(VALID.replace('options = { builders = 3 }', 'options = { role_runtime = %s }' % value))
            self.assertEqual(code, 0, lines)
        for value, expected in [('"session"', 'role_runtime: expected table, got string'),
                                ('{ solo = "session" }', 'role_runtime.solo: unknown key'),
                                ('{ coordinator = 1 }', 'role_runtime.coordinator: expected string, got integer'),
                                ('{ coordinator = "tmux" }',
                                 "role_runtime.coordinator: unknown value 'tmux' (expected one of: grok-bot, session)")]:
            self.assertFails(VALID.replace('options = { builders = 3 }', 'options = { role_runtime = %s }' % value),
                             'crew.toml:runtime.options.' + expected)

    def test_launch_topology_schema(self):
        """#606: absent launch adds no resolved key; each key and its values validate."""
        code, lines = resolve(VALID)
        self.assertEqual(code, 0, lines)
        self.assertFalse([ln for ln in lines if "launch" in ln], lines)
        for launch in ('{}', '{ coordinator = "tmux", roles = "hosted", resume = "ask", reconcile = "backend" }',
                       '{ coordinator = "none", roles = "none", resume = "0f9c-ab_1.2:x" }', '{ roles = "tmux" }'):
            code, lines = validate(VALID.replace('options = { builders = 3 }', 'options = { launch = %s }' % launch))
            self.assertEqual(code, 0, lines)
        for launch, expected in [('"hosted"', 'launch: expected table, got string'),
                                 ('{ roles = "remote" }', "launch.roles: unknown value 'remote' (expected one of: tmux, hosted, none)"),
                                 ('{ coordinator = "none" }', 'launch.roles: roles = tmux needs coordinator = tmux (role windows join its session)'),
                                 ('{ resume = "$(id)" }', 'launch.resume: expected fresh, ask or a session id ([A-Za-z0-9._:-])'),
                                 ('{ reconcile = "github" }', "launch.reconcile: unknown value 'github' (expected one of: backend)")]:
            self.assertFails(VALID.replace('options = { builders = 3 }', 'options = { launch = %s }' % launch),
                             'crew.toml:runtime.options.' + expected)

    def assertFails(self, text, expected):
        code, lines = validate(text)
        self.assertEqual(code, 1, lines)
        self.assertIn(expected, lines)

    def test_valid_profile(self):
        code, lines = validate(VALID)
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines, ["crew-config: OK (crew.toml)"])

    def test_pi_coordinator_and_provider_qualified_tier(self):
        text = VALID.replace('coordinator = "codex"', 'coordinator = "pi"').replace(
            '"codex/gpt-6.1-sol"', '"pi/anthropic/claude-sonnet-4-5"')
        code, lines = validate(text)
        self.assertEqual(code, 0, lines)

    def test_role_keys_follow_registry(self):
        roles = {key: dict(value) for key, value in cc.ROLE_REGISTRY.items()}
        roles["builder"]["identity_key"] = "identities.worker"
        roles["coordinator"]["engine_source"] = "lead"
        with patch.object(cc, "ROLE_REGISTRY", roles):
            renamed = VALID.replace("builder = { gh_user", "worker = { gh_user").replace('coordinator = "codex"', 'lead = "codex"')
            self.assertEqual(validate(renamed)[0], 0)
            self.assertFails(VALID, "crew.toml:identities.builder: unknown key")
            self.assertFails(VALID, "crew.toml:identities.worker: missing required key")
            self.assertFails(VALID, "crew.toml:engines.coordinator: unknown key")
            self.assertEqual(validate(renamed.replace('lead = "codex"', 'lead = "muse"'))[0], 0)
            self.assertFails(renamed.replace('lead = "codex"', 'lead = "opencode"'),
                             "crew.toml:engines.lead: unknown value 'opencode' (expected one of: claude-code, codex, pi, cursor, muse)")

    def test_size_budget_schema(self):
        self.assertEqual(validate(VALID + "\n[size_budget]\nbuilder = 8192\n")[0], 0)
        for value, reason in (("0", "must be >= 1"), ("-1", "must be >= 1"),
                              ("true", "expected integer, got boolean"), ('"8192"', "expected integer, got string")):
            self.assertFails(VALID + "\n[size_budget]\nbuilder = " + value + "\n",
                             "crew.toml:size_budget.builder: " + reason)
        self.assertFails(VALID + "\n[size_budget]\nunknown = 1\n", "crew.toml:size_budget.unknown: unknown key")

    def test_precheck_valid_and_optional(self):
        for settings in ('', 'enabled = true', 'enabled = false',
                         'enabled = true\nlint = "lint"\ntest = "test"\ndocs = "docs"\nmax_fix_attempts = 3'):
            code, lines = validate(VALID + '\n[builder.precheck]\n' + settings + '\n')
            self.assertEqual(code, 0, lines)

    def test_precheck_unknown_keys_types_and_attempts(self):
        for settings, expected in [('unknown = true', 'unknown: unknown key'),
                                   ('enabled = "yes"', 'enabled: expected boolean'),
                                   ('lint = []', 'lint: expected string'),
                                   ('test = false', 'test: expected string'),
                                   ('docs = 1', 'docs: expected string'),
                                   ('max_fix_attempts = true', 'max_fix_attempts: expected integer'),
                                   ('max_fix_attempts = 0', 'max_fix_attempts: must be >= 1'),
                                   ('max_fix_attempts = -1', 'max_fix_attempts: must be >= 1')]:
            code, lines = validate(VALID + '\n[builder.precheck]\n' + settings + '\n')
            self.assertEqual(code, 1, lines)
            self.assertTrue(any('builder.precheck.' + expected in line for line in lines), lines)
        self.assertFails(VALID + '\n[builder]\nunknown = true\n', 'crew.toml:builder.unknown: unknown key')

    def test_persona_fields(self):
        for role in ("coordinator", "builder", "reviewer", "synthesizer"):
            original = '%s = { gh_user = "%s" }' % (role, "acme-reviewer" if role == "reviewer" else "acme-bot")
            for field in ("title", "emoji"):
                with self.subTest(role=role, field=field):
                    self.assertEqual(validate(VALID.replace(original, original[:-2] + ', %s = "custom" }' % field))[0], 0)
                    self.assertFails(VALID.replace(original, original[:-2] + ', %s = 42 }' % field),
                                     "crew.toml:identities.%s.%s: expected string, got integer" % (role, field))
        self.assertFails(VALID.replace('coordinator = { gh_user = "acme-bot" }',
                                      'coordinator = { gh_user = "acme-bot", harness = "codex" }'),
                         "crew.toml:identities.coordinator.harness: unknown key")

    def test_persona_layers_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            project, org = os.path.join(d, "project.toml"), os.path.join(d, "org.toml")
            with open(project, "w") as f:
                f.write(VALID.replace('coordinator = { gh_user = "acme-bot" }',
                                     'coordinator = { gh_user = "acme-bot", name = "River", emoji = "🌊" }'))
            with open(org, "w") as f:
                f.write('[identities.coordinator]\ntitle = "Lead"\nemoji = "🌲"\n')
            profile, provenance, problems, _ = cc.resolve_profile(project, org)
            self.assertEqual(problems, [])
            self.assertEqual(profile["identities"]["coordinator"],
                             {"gh_user": "acme-bot", "name": "River", "title": "Lead", "emoji": "🌊"})
            self.assertEqual(provenance["identities.coordinator.title"], "org")
            self.assertEqual(provenance["identities.coordinator.emoji"], "project")
            profile, _, problems, _ = cc.resolve_profile(project)
            self.assertEqual(problems, [])
            self.assertEqual(profile["identities"]["coordinator"]["title"], "CTO")
            self.assertEqual(profile["identities"]["reviewer"]["emoji"], "🔎")

    def test_train_local_and_mirror_deferral_options(self):
        opts = 'options = { train_local_checks = true, mirror_deferral = "#110 roadmap PRs per #140" }'
        code, lines = validate(VALID.replace('options = { builders = 3 }', opts))
        self.assertEqual(code, 0, lines)
        for option, value, expected in [("train_local_checks", '"yes"', "boolean"),
                                        ("mirror_deferral", "true", "string")]:
            code, lines = validate(VALID.replace('options = { builders = 3 }',
                                                 'options = { %s = %s }' % (option, value)))
            self.assertEqual(code, 1, lines)
            self.assertTrue(any(option in line and expected in line for line in lines), lines)

    def test_doc_example_is_valid(self):
        with open(os.path.join(SCRIPTS, "..", "docs", "profile.md"), encoding="utf-8") as f:
            m = re.search(r"```toml\n(.*?)```", f.read(), re.S)
        code, lines = validate(m.group(1))
        self.assertEqual(code, 0, lines)

    def test_sandbox_env_option(self):
        self.assertEqual(validate(VALID.replace('builders = 3', 'sandbox_env = "CREW_TEST_SANDBOX=1"'))[0], 0)
        self.assertFails(VALID.replace('builders = 3', 'sandbox_env = 1'),
                         "crew.toml:runtime.options.sandbox_env: expected string, got integer")

    def test_missing_required_key(self):
        self.assertFails(VALID.replace('owner = "acme"\n', ""),
                         "crew.toml:repo.owner: missing required key")
        self.assertFails(VALID.replace('[backends.ci]\nname = "github"\n', ""),
                         "crew.toml:backends.ci: missing required key")

    def test_unknown_concern(self):
        self.assertFails(VALID + '\n[backends.chat]\nname = "github"\n',
                         "crew.toml:backends.chat: unknown key")

    def test_unknown_backend(self):
        self.assertFails(VALID.replace('[backends.change]\nname = "github"', '[backends.change]\nname = "gitlab"'),
                         "crew.toml:backends.change.name: unknown value 'gitlab' (expected one of: github)")

    def test_token_shaped_value(self):
        token = "ghp_" + "A" * 36  # built at runtime so the repo never holds a token
        code, lines = validate(VALID.replace('builder = { gh_user = "acme-bot" }',
                                             'builder = { gh_user = "%s" }' % token))
        self.assertEqual(code, 1)
        self.assertTrue(any(ln.startswith("crew.toml:identities.builder.gh_user: token-shaped value")
                            for ln in lines), lines)
        bearer = VALID.replace('worktree_root = "/srv/wt"', 'worktree_root = "Authorization: " "Bearer abc123"'.replace('" "', ''))
        self.assertFails(bearer, "crew.toml:paths.worktree_root: token-shaped value "
                         "(bearer auth header with a literal value); refer to credentials by mechanism")

    def test_placeholder_is_not_a_token(self):
        code, lines = validate(VALID.replace('"/srv/wt"', '"Authorization: Bearer <token>"'))
        self.assertEqual(code, 0, lines)

    def test_wrong_type(self):
        self.assertFails(VALID.replace("builders = 3", 'builders = "3"'),
                         "crew.toml:runtime.options.builders: expected integer, got string")
        self.assertFails(VALID.replace('owners = ["acme-owner"]', 'owners = "acme-owner"'),
                         "crew.toml:identities.owners: expected list of strings, got string")
        self.assertFails(VALID.replace("builders = 3", "builders = true"),
                         "crew.toml:runtime.options.builders: expected integer, got boolean")

    def test_unknown_key_and_option(self):
        self.assertFails(VALID + '\n[extra]\nx = 1\n', "crew.toml:extra: unknown key")
        self.assertFails(VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "grok-bot"\noptions = { builders = 3 }'),
                         "crew.toml:runtime.options.builders: unknown key")

    def test_max_active_milestones_validation(self):
        for runtime in ("tmux", "grok-bot"):
            profile = VALID.replace('name = "tmux"', 'name = "%s"' % runtime)
            for options in ("", "max_active_milestones = 2"):
                code, lines = validate(profile.replace("builders = 3", options))
                self.assertEqual(code, 0, lines)
            for value, reason in (("0", "must be >= 1, got 0"),
                                  ("true", "expected integer, got boolean"),
                                  ('"2"', "expected integer, got string")):
                self.assertFails(profile.replace("builders = 3", "max_active_milestones = " + value),
                                 "crew.toml:runtime.options.max_active_milestones: " + reason)

    def test_admission_and_train_option_validation(self):
        self.assertEqual(validate(VALID.replace("builders = 3", "train_min = 3, train_window = 120, max_suites = 2"))[0], 0)
        for key, minimum in (("train_min", 2), ("train_window", 1), ("max_suites", 1)):
            for value, reason in (("true", "expected integer, got boolean"),
                                  ('"2"', "expected integer, got string"),
                                  (str(minimum - 1), "must be >= %d, got %d" % (minimum, minimum - 1)),
                                  ("-1", "must be >= %d, got -1" % minimum)):
                self.assertFails(VALID.replace("builders = 3", "%s = %s" % (key, value)),
                                 "crew.toml:runtime.options.%s: %s" % (key, reason))
        for value in ("12", "12.5"):
            self.assertEqual(validate(VALID.replace("builders = 3", "max_load = " + value))[0], 0)
        for value, reason in (("true", "expected number, got boolean"), ('"12"', "expected number, got string"),
                              ("0", "must be > 0, got 0"), ("-1.5", "must be > 0, got -1.5")):
            self.assertFails(VALID.replace("builders = 3", "max_load = " + value),
                             "crew.toml:runtime.options.max_load: " + reason)

    def test_schedule_target_option_validation(self):  # #623
        ok = "load_high = 8, load_low = 2.5, error_high = 1, schedule_interval = 60, schedule_ramp = 1, stuck_after = 1"
        self.assertEqual(validate(VALID.replace("builders = 3", ok))[0], 0)
        for value in ("warn", "critical"):  # #1282
            self.assertEqual(validate(VALID.replace("builders = 3", 'memory_high = "%s"' % value))[0], 0)
        self.assertFails(VALID.replace("builders = 3", 'memory_high = "normal"'),
                         "crew.toml:runtime.options.memory_high: unknown value 'normal' (expected one of: warn, critical)")
        for key in ("error_high", "schedule_interval", "schedule_ramp", "stuck_after"):
            for value, reason in (("true", "expected integer, got boolean"), ("1.5", "expected integer, got float"),
                                  ("0", "must be >= 1, got 0")):
                self.assertFails(VALID.replace("builders = 3", "%s = %s" % (key, value)),
                                 "crew.toml:runtime.options.%s: %s" % (key, reason))
        for key in ("load_high", "load_low"):
            for value, reason in (('"5"', "expected number, got string"), ("0", "must be > 0, got 0")):
                self.assertFails(VALID.replace("builders = 3", "%s = %s" % (key, value)),
                                 "crew.toml:runtime.options.%s: %s" % (key, reason))
        for pair, reason in (("load_high = 5, load_low = 5", "must be < load_high (5), got 5"),
                             ("load_low = 7", "must be < load_high (6.0), got 7"),
                             ("load_high = 3.5", "must be < load_high (3.5), got 4.0")):
            self.assertFails(VALID.replace("builders = 3", pair), "crew.toml:runtime.options.load_low: " + reason)

    def test_engines(self):
        cursor = VALID.replace('coordinator = "codex"', 'coordinator = "cursor"').replace('claude-code/sonnet', 'cursor/composer-1')
        self.assertEqual(validate(cursor)[0], 0)
        self.assertFails(VALID.replace('trivial = { order = ["claude-code/sonnet"] }', 'trivial = { order = ["unknown/auto"] }'),
                         "crew.toml:engines.trivial.order[0]: unknown engine 'unknown' "
                         "(expected <engine>/<model>, engine one of: claude-code, codex, muse, opencode, pi, cursor)")
        self.assertFails(VALID.replace('effort = "medium"', 'effort = "max"'),
                         "crew.toml:engines.default.effort: unknown value 'max' (expected one of: low, medium, high)")

    def test_engine_role_overrides(self):  # #597
        roles = '\n[engines.roles]\nsynthesizer = { order = ["codex/gpt-6.1-sol"] }\n'
        self.assertEqual(validate(VALID + roles)[0], 0)
        for old, new, expected in (
                ("synthesizer", "coordinator", "crew.toml:engines.roles.coordinator: unknown key"),
                ('"codex/gpt-6.1-sol"', '"bogus/auto"', "crew.toml:engines.roles.synthesizer.order[0]: unknown engine 'bogus'"),
                ('order = ["codex/gpt-6.1-sol"]', 'effort = "low"', "crew.toml:engines.roles.synthesizer.effort: unknown key"),
                ('{ order = ["codex/gpt-6.1-sol"] }', '"codex"', "crew.toml:engines.roles.synthesizer: expected table")):
            code, lines = validate(VALID + roles.replace(old, new))
            self.assertEqual(code, 1, lines)
            self.assertTrue(any(line.startswith(expected) for line in lines), lines)

    def test_tool_probes(self):
        tools = '\n[tools.example]\nrunning = ["session", "version"]\ninstalled = ["example", "--version"]\npin = "2.10.0"\n'
        self.assertEqual(validate(VALID + tools)[0], 0)
        for old, new, key, reason in (
                ('running = ["session", "version"]', 'running = "session"', "running", "expected list of strings, got string"),
                ('running = ["session", "version"]', 'running = []', "running", "expected list of strings, got list"),
                ('running = ["session", "version"]', 'running = [""]', "running", "command arguments must not be empty"),
                ('installed = ["example", "--version"]', '', "installed", "missing required key"),
                ('pin = "2.10.0"', 'pin = "latest"', "pin", "expected X.Y.Z or vX.Y.Z minimum version")):
            self.assertFails(VALID + tools.replace(old, new), "crew.toml:tools.example.%s: %s" % (key, reason))

    def test_capabilities(self):
        ok = VALID.replace('[backends.review]\nname = "github"',
                           '[backends.review]\nname = "github"\ncapabilities = { post-verdict = "emulated (COMMENT review)" }')
        self.assertEqual(validate(ok)[0], 0)
        self.assertFails(ok.replace("emulated (COMMENT review)", "emulated"),
                         "crew.toml:backends.review.capabilities.post-verdict: expected supported, "
                         "unsupported or emulated (<how>)")
        self.assertFails(ok.replace("post-verdict", "merge"),
                         "crew.toml:backends.review.capabilities.merge: unknown key")

    def test_invalid_toml(self):
        code, lines = validate("[repo\n")
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith("crew.toml:(toml): invalid TOML"), lines)

    def test_missing_file(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            code = cc.main(["validate", "/nonexistent/crew.toml"])
        self.assertEqual(code, 1)
        self.assertIn("/nonexistent/crew.toml:(file): cannot read", out.getvalue())


ROOT = os.path.join(SCRIPTS, "..")
DEFAULT_PROFILE = os.path.join(ROOT, "profiles", "default.toml")
CAPABILITY_OK = re.compile(r"supported|emulated \(.*\S.*\)")


def load_toml(path):
    with open(path, "rb") as f:
        return cc.tomllib.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class DefaultProfileTest(unittest.TestCase):
    """Default GitHub profile and pack manifest (13.12, #124)."""

    def test_default_profile_and_manifest_validate(self):
        for path in [DEFAULT_PROFILE, os.path.join(ROOT, "connectors", "github", "manifest.toml")]:
            code, lines = validate(read(path))
            self.assertEqual(code, 0, (path, lines))

    def test_default_profile_covers_every_concern_none_unsupported(self):
        backends = load_toml(DEFAULT_PROFILE)["backends"]
        self.assertEqual(sorted(backends), sorted(CONCERNS))
        for concern, table in backends.items():
            manifest = load_toml(os.path.join(ROOT, "connectors", table["name"], "manifest.toml"))
            effective = dict(manifest["capabilities"].get(concern, {}), **table.get("capabilities", {}))
            for op in cc.OPERATIONS[concern]:
                value = effective.get(op, "unsupported")
                self.assertTrue(CAPABILITY_OK.fullmatch(value), "%s.%s: %s" % (concern, op, value))

    def test_default_profile_sets_renderer_keys(self):
        p = load_toml(DEFAULT_PROFILE)
        for role in ["coordinator", "builder", "reviewer", "synthesizer"]:
            self.assertTrue(p["identities"][role].get("name"), role)
        self.assertTrue(p["paths"].get("toolchain_bin"))
        self.assertTrue(p["engines"].get("fallback_engine"))
        self.assertTrue(p["runtime"].get("timezone"))
        self.assertEqual(p["runtime"]["name"], "grok-bot")
        self.assertNotEqual(p["identities"]["reviewer"]["gh_user"], p["identities"]["builder"]["gh_user"])

    def test_engine_routing_matches_roles_md(self):
        """Each tier's order is roles.md Current routing, private-repo case: no Muse,
        no Cursor; Codex `-p <profile>` fallbacks are not <engine>/<model> entries."""
        roles = read(os.path.join(ROOT, "docs", "roles.md"))
        section = roles.split("### Current routing", 1)[1].split("\n### ", 1)[0]
        token = re.compile(r"Muse Code|Claude Code `([^`]+)`|Codex `([^`-][^`]*)`|OpenCode \+ DeepSeek `([^`]+)`")
        engines = load_toml(DEFAULT_PROFILE)["engines"]
        for tier, label in [("trivial", "trivial"), ("default", "default"), ("deep", "deep / risky")]:
            row = re.search(r"^\| %s \|(.*)$" % re.escape(label), section, re.M).group(1)
            expected = []
            for m in token.finditer(row):
                if m.group(1):
                    expected.append("claude-code/" + m.group(1))
                elif m.group(2):
                    expected.append("codex/" + m.group(2))
                elif m.group(3):
                    expected.append("opencode/" + m.group(3))
            self.assertEqual(engines[tier]["order"], expected, tier)
            self.assertEqual(engines[tier]["effort"], cc.TIER_EFFORT[tier])
            self.assertIn(cc.TIER_EFFORT[tier], row.split("|")[1])
            self.assertFalse(any(e.startswith(("muse/", "cursor/")) for e in engines[tier]["order"]))
        self.assertEqual(engines["coordinator"], "claude-code")
        self.assertIn(engines["fallback_engine"], ["claude-code", "codex"])

    def test_paths_checkout_validated(self):  # #1178
        ok = VALID.replace('worktree_root = "/srv/wt"', 'worktree_root = "/srv/wt"\ncheckout = "../mdstack"')
        self.assertEqual(validate(ok)[0], 0, validate(ok)[1])
        self.assertFails(ok.replace('checkout = "../mdstack"', "checkout = 1"),
                         "crew.toml:paths.checkout: expected string, got integer")

    def test_paths_root_resolves_relative_children_only(self):  # #1178
        paths = {"root": "~/stack", "state_dir": ".crew/state", "worktree_root": "/abs/wt", "live_dir": "<live-dir>",
                 "checkout": "../mdstack", "toolchain_bin": "bin", "pack": "pack"}
        prov = {}
        with patch.dict(os.environ, {"CREW_ROOT": ""}):
            cc.resolve_root(paths, prov)
        root = os.path.expanduser("~/stack")
        self.assertEqual(paths, {"root": root, "state_dir": os.path.join(root, ".crew/state"), "worktree_root": "/abs/wt",
                                 "live_dir": "<live-dir>", "checkout": os.path.join(os.path.dirname(root), "mdstack"),
                                 "toolchain_bin": "bin", "pack": "pack"})
        self.assertEqual(prov, {})
        moved = {"root": "/old", "state_dir": "s"}
        with patch.dict(os.environ, {"CREW_ROOT": "/new"}):
            cc.resolve_root(moved, prov)
        self.assertEqual((moved, prov), ({"root": "/new", "state_dir": "/new/s"}, {"paths.root": "env CREW_ROOT"}))
        unset = {"state_dir": "s"}
        with patch.dict(os.environ, {"CREW_ROOT": "/new"}):
            cc.resolve_root(unset, prov)
        self.assertEqual(unset, {"state_dir": "s"})

    def test_renderer_keys_validated(self):
        ok = (VALID.replace('builder = { gh_user = "acme-bot" }', 'builder = { gh_user = "acme-bot", name = "Bob" }')
              .replace('options = { builders = 3 }', 'options = { builders = 3 }\ntimezone = "UTC"')
              .replace('coordinator = "codex"', 'coordinator = "codex"\nfallback_engine = "claude-code"')
              .replace('worktree_root = "/srv/wt"', 'worktree_root = "/srv/wt"\ntoolchain_bin = "/opt/node/bin"'))
        self.assertEqual(validate(ok)[0], 0, validate(ok)[1])
        self.assertFails(ok.replace('name = "Bob"', "name = 1"),
                         "crew.toml:identities.builder.name: expected string, got integer")
        self.assertFails(ok.replace('timezone = "UTC"', "timezone = 0"),
                         "crew.toml:runtime.timezone: expected string, got integer")
        self.assertFails(ok.replace('toolchain_bin = "/opt/node/bin"', "toolchain_bin = []"),
                         "crew.toml:paths.toolchain_bin: expected string, got list")
        self.assertFails(ok.replace('fallback_engine = "claude-code"', 'fallback_engine = "unknown"'),
                         "crew.toml:engines.fallback_engine: unknown value 'unknown' "
                         "(expected one of: claude-code, codex, muse, opencode, pi, cursor)")

    assertFails = ValidateTest.assertFails

    def test_manifest_validation(self):
        manifest = read(os.path.join(ROOT, "connectors", "github", "manifest.toml"))
        self.assertFails(manifest.replace('name = "github"', 'name = "gitlab"', 1),
                         "crew.toml:pack.mdstack_version: required for an external backend")
        self.assertFails(re.sub(r"\nland = .*", "", manifest),
                         "crew.toml:capabilities.change.land: missing required key")
        self.assertFails(manifest.replace('close = "supported"', 'close = "maybe"'),
                         "crew.toml:capabilities.change.close: expected supported, unsupported or emulated (<how>)")
        self.assertFails(manifest + '\n[capabilities.chat]\nask = "supported"\n',
                         "crew.toml:capabilities.chat: unknown key")


def resolve(project, default=None, org=None, org_path=None):
    """Write layer files to a temp dir, run `resolve`, return (code, stdout lines) with the dir stripped."""
    with tempfile.TemporaryDirectory() as d:
        paths = {}
        for name, text in (("default", default), ("org", org), ("crew", project)):
            paths[name] = os.path.join(d, name + ".toml")
            if text is not None:
                with open(paths[name], "w", encoding="utf-8") as f:
                    f.write(text)
        argv = ["resolve", "--project", paths["crew"]]
        if org is not None or org_path:
            argv += ["--org-profile", org_path or paths["org"]]
        saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, paths["default"]
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cc.main(argv)
        finally:
            cc.DEFAULT_PROFILE = saved
        return code, [ln.replace(d + os.sep, "") for ln in out.getvalue().splitlines()]


class ResearcherProfile(unittest.TestCase):
    """#584: the optional researcher identity and the `researchers` cap."""

    def test_researcher_identity_is_optional_and_checked(self):
        self.assertEqual(validate(VALID)[0], 0)
        ok = VALID.replace('synthesizer = { gh_user = "acme-bot" }',
                           'synthesizer = { gh_user = "acme-bot" }\nresearcher = { gh_user = "acme-bot", name = "Riley" }')
        self.assertEqual(validate(ok)[0], 0)
        code, lines = validate(ok.replace('researcher = { gh_user = "acme-bot", name = "Riley" }',
                                          'researcher = { name = "Riley" }'))
        self.assertEqual(code, 1)
        self.assertTrue(any("identities.researcher.gh_user" in ln for ln in lines), lines)
        code, lines = validate(ok.replace('name = "Riley" }', 'name = "Riley", role = "x" }'))
        self.assertEqual(code, 1)
        self.assertTrue(any("identities.researcher.role" in ln for ln in lines), lines)

    def test_team_name_is_optional_and_checked(self):  # #1329
        for value in ('""', '"mdp-m4"', '"%s"' % ("a" * 63)):
            self.assertEqual(validate(VALID.replace('owners = ["acme-owner"]', 'owners = ["acme-owner"]\nteam = ' + value))[0], 0)
        for value in ('"MDP"', '"mdp m4"', '"%s"' % ("a" * 64), "4"):
            code, lines = validate(VALID.replace('owners = ["acme-owner"]', 'owners = ["acme-owner"]\nteam = ' + value))
            self.assertEqual(code, 1, value)
            self.assertTrue(any("identities.team" in ln for ln in lines), lines)

    def test_report_table_is_optional_and_checked(self):  # #431: emoji off switch and the fixed status set
        for table in ("", "[report]\nemoji = false\n", '[report]\nstatus = { pass = "OK", blocked = "" }\n'):
            self.assertEqual(validate(VALID + "\n" + table)[0], 0, table)
        for table, key in (('[report]\nemoji = "no"\n', "report.emoji"), ("[report]\ncolour = 1\n", "report.colour"),
                           ('[report]\nstatus = { done = "x" }\n', "report.status.done"),
                           ("[report]\nstatus = { pass = 1 }\n", "report.status.pass")):
            code, lines = validate(VALID + "\n" + table)
            self.assertEqual(code, 1, table)
            self.assertTrue(any(key in ln for ln in lines), lines)

    def test_researchers_cap_defaults_to_two_and_must_be_nonnegative(self):  # 2 since #748; 0 runs none (#926)
        for value in ("-1", "true", '"2"', "1.5"):
            text = VALID.replace("builders = 3", "builders = 3, researchers = " + value)
            self.assertEqual(validate(text)[0], 1, value)
        for value in ("0", "2"):
            self.assertEqual(validate(VALID.replace("builders = 3", "builders = 3, researchers = " + value))[0], 0)
        code, lines = resolve(VALID.replace("builders = 3", "builders = 3, researchers = 0"), default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("runtime.options.researchers = 0  # project", lines)
        code, lines = resolve(VALID.replace("builders = 3", "builders = 3, researchers = 0") +
                              "\n[triage]\nenabled = true\n", default=VALID)
        self.assertEqual(code, 1)
        self.assertTrue(any("runtime.options.researchers: 0 runs no researcher, but triage.enabled = true" in ln
                            for ln in lines), lines)
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("runtime.options.researchers = 2  # core", lines)

    def test_triage_table_defaults_and_checks(self):  # #748
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        for line in ("triage.enabled = false  # core", "triage.interval_hours = 6  # core",
                     'triage.mode = "shadow"  # core', 'triage.repos = ["acme/widgets"]  # core'):
            self.assertIn(line, lines)
        ok = VALID + '\n[triage]\nenabled = true\ninterval_hours = 2\nrepos = ["acme/widgets", "acme/tools"]\n' \
            'rules = "triage-rules.toml"\nmode = "apply"\n'
        self.assertEqual(validate(ok)[0], 0)
        code, lines = resolve(ok, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('triage.repos = ["acme/widgets", "acme/tools"]  # project', lines)
        for bad, key in [("interval_hours = 0", "triage.interval_hours"), ('mode = "auto"', "triage.mode"),
                         ('repos = ["widgets"]', "triage.repos[0]"), ("repos = []", "triage.repos"),
                         ('rules = " "', "triage.rules"), ('enabled = "yes"', "triage.enabled"),
                         ("cadence = 6", "triage.cadence"), ("trackers = []", "triage.trackers"),
                         ('trackers = ["OPS board"]', "triage.trackers[0]")]:
            code, lines = validate(VALID + "\n[triage]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(key + ":" in ln for ln in lines), (bad, lines))

    def test_triage_trackers_name_a_non_github_tracker(self):  # #1404
        code, lines = validate(VALID + '\n[triage]\ntrackers = ["OPS"]\n')
        self.assertEqual(code, 1)
        self.assertTrue(any("triage.trackers: needs a non-GitHub tracker backend" in ln for ln in lines), lines)
        native = VALID.replace('[backends.tracker]\nname = "github"', '[backends.tracker]\nname = "example"')
        self.assertNotEqual(native, VALID)
        code, lines = validate(native + '\n[triage]\ntrackers = ["OPS", "ops:intake"]\n')
        self.assertFalse([ln for ln in lines if "triage." in ln], lines)

    def test_reflection_table_defaults_off_and_checks(self):  # #1521
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("reflection.enabled = false  # core", lines)
        code, lines = resolve(VALID + "\n[reflection]\nenabled = true\n", default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("reflection.enabled = true  # project", lines)
        self.assertIn("triage.enabled = false  # core", lines)  # independent of [triage]
        for bad, key in [('enabled = "yes"', "reflection.enabled"), ("interval_days = 7", "reflection.interval_days")]:
            code, lines = validate(VALID + "\n[reflection]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(key + ":" in ln for ln in lines), (bad, lines))

    def test_ci_required_checks_resolve_and_check(self):  # #1536
        code, lines = resolve(VALID + '\n[ci]\nrequired_checks = ["markdownlint", "links", "repo-guard"]\n', default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('ci.required_checks = ["markdownlint", "links", "repo-guard"]  # project', lines)
        code, lines = validate(VALID + "\n[ci]\n")
        self.assertEqual(code, 0, lines)
        for bad, key in [("required_checks = []", "ci.required_checks:"), ('required_checks = "links"', "ci.required_checks:"),
                         ('required_checks = ["links", " "]', "ci.required_checks[1]:"),
                         ('required_checks = ["links", "links"]', "ci.required_checks[1]:"), ("optional = true", "ci.optional:")]:
            code, lines = validate(VALID + "\n[ci]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(key in ln for ln in lines), (bad, lines))

    def test_docs_table_defaults_and_checks(self):  # #1024
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertFalse(any(ln.startswith("docs.") for ln in lines), lines)
        code, lines = resolve(VALID + "\n[docs]\n", default=VALID)
        self.assertEqual(code, 0, lines)
        for line in ("docs.enabled = false  # core", "docs.interval_days = 7  # core", "docs.stale_days = 90  # core",
                     "docs.size_budget = 500  # core", 'docs.repos = ["acme/widgets"]  # core'):
            self.assertIn(line, lines)
        ok = VALID + '\n[docs]\nenabled = true\ninterval_days = 7\nrepos = ["acme/widgets", "acme/widgets-pack"]\n' \
            'stale_days = 90\nsize_budget = 500\n\n[docs.homes]\nrunbook = "docs/operations.md"\n' \
            'decisions = "README.md#decisions"\nspecs = "design/specs/"\n'
        self.assertEqual(validate(ok)[0], 0)
        code, lines = resolve(ok, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("docs.enabled = true  # project", lines)
        self.assertIn('docs.homes.decisions = "README.md#decisions"  # project', lines)
        for bad, key in [('enabled = "yes"', "docs.enabled"), ('interval_days = "7"', "docs.interval_days"),
                         ("stale_days = 1.5", "docs.stale_days"), ("size_budget = true", "docs.size_budget"),
                         ('repos = "acme/widgets"', "docs.repos"), ('homes = "README.md"', "docs.homes"),
                         ("interval_days = 0", "docs.interval_days"), ("stale_days = 0", "docs.stale_days"),
                         ("size_budget = -1", "docs.size_budget"), ("repos = []", "docs.repos"),
                         ('repos = ["widgets"]', "docs.repos[0]"), ("cadence = 7", "docs.cadence"),
                         ('homes = { changelog = "CHANGELOG.md" }', "docs.homes.changelog"),
                         ("homes = { runbook = 7 }", "docs.homes.runbook")] + \
                [('homes = { runbook = "%s" }' % home, "docs.homes.runbook")
                 for home in ("", "/etc/runbook.md", "../runbook.md", "README.md#", "#ops")] + \
                [('homes = { specs = "README.md#specs" }', "docs.homes.specs")]:
            code, lines = validate(VALID + "\n[docs]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(ln.startswith("crew.toml:%s: " % key) for ln in lines), (bad, lines))

    def test_docs_specs_external_reference(self):  # #1725
        url = "https://tracker.example/acme/items/12"
        code, lines = resolve(VALID + '\n[docs]\nspecs_external = "%s"\n' % url, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('docs.specs_external = "%s"  # project' % url, lines)
        for bad, reason in [('specs_external = "design/specs"', "expected an absolute URL"),
                            ('specs_external = "gh issue view 12"', "expected an absolute URL"),
                            ('specs_external = "https://x.example/a b"', "expected an absolute URL"),
                            ('specs_external = ""', "expected an absolute URL"),
                            ('specs_external = "%s"\nhomes = { specs = "design/specs" }' % url,
                             "conflicts with docs.homes.specs")]:
            code, lines = validate(VALID + "\n[docs]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(ln.startswith("crew.toml:docs.specs_external: " + reason) for ln in lines), (bad, lines))
        code, lines = validate(VALID + '\n[docs]\nspecs_external = "%s"\nhomes = { runbook = "ops.md" }\n' % url)
        self.assertEqual(code, 0, lines)

    def test_install_table_sources_and_refusals(self):  # #943
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertFalse(any(ln.startswith("install.") for ln in lines), lines)
        sums, commit = "a" * 64, "b" * 40
        for ok in ('source = "github"', 'source = "mirror"\nlocation = "/srv/rel"\nsha256sums_digest = "%s"' % sums,
                   'source = "url"\nlocation = "https://rel.example/mdstack"',
                   'source = "url"\nlocation = "http://127.0.0.1:8080/rel"',
                   'source = "git"\nlocation = "/srv/mdstack.git"\ngit_commit = "%s"' % commit,
                   'source = "git"\nlocation = "/srv/mdstack.git"\ngit_commit = "%s"' % ("c" * 64)):
            self.assertEqual(validate(VALID + "\n[install]\n" + ok + "\n"), OK, ok)
        code, lines = resolve(VALID + '\n[install]\nsource = "mirror"\nlocation = "/srv/rel"\n', default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('install.source = "mirror"  # project', lines)
        for bad, key in [('source = "s3"', "install.source"), ("source = 1", "install.source"),
                         ('location = "/srv/rel"', "install.location"), ('source = "mirror"', "install.location"),
                         ('source = "mirror"\nlocation = " "', "install.location"),
                         ('source = "url"\nlocation = "http://rel.example"', "install.location"),
                         ('source = "url"\nlocation = "file:///srv/rel"', "install.location"),
                         ('source = "mirror"\nlocation = "/r"\nsha256sums_digest = "abc"', "install.sha256sums_digest"),
                         ('source = "mirror"\nlocation = "/r"\nsha256sums_digest = "%s"' % ("A" * 64),
                          "install.sha256sums_digest"),
                         ('sha256sums_digest = "%s"' % sums, "install.sha256sums_digest"),
                         ('source = "git"\nlocation = "/g"\nsha256sums_digest = "%s"\ngit_commit = "%s"' % (sums, commit),
                          "install.sha256sums_digest"),
                         ('source = "git"\nlocation = "/g"', "install.git_commit"),
                         ('source = "git"\nlocation = "/g"\ngit_commit = "abc123"', "install.git_commit"),
                         ('source = "mirror"\nlocation = "/r"\ngit_commit = "%s"' % commit, "install.git_commit"),
                         ('source = "mirror"\nlocation = "/r"\nmirror = true', "install.mirror")]:
            code, lines = validate(VALID + "\n[install]\n" + bad + "\n")
            self.assertEqual(code, 1, bad)
            self.assertTrue(any(key + ":" in ln for ln in lines), (bad, lines))
        self.assertEqual(validate(VALID + "\ninstall = 5\n")[0], 1)

    def test_researcher_identity_resolves_to_the_author_login(self):  # #584 part 2: a registry role
        code, lines = resolve(VALID, default=VALID)
        self.assertEqual(code, 0, lines)
        for line in ('identities.researcher.gh_user = "acme-bot"  # core', 'identities.researcher.name = "Riley"  # core',
                     "size_budget.researcher = 16384  # core"):
            self.assertIn(line, lines)
        own = VALID.replace('synthesizer = { gh_user = "acme-bot" }',
                            'synthesizer = { gh_user = "acme-bot" }\nresearcher = { gh_user = "acme-research" }')
        self.assertIn('identities.researcher.gh_user = "acme-research"  # project', resolve(own, default=VALID)[1])


class ResolveTest(unittest.TestCase):
    def test_present_caps_validation_and_resolved_defaults(self):
        for key in ("present_builders", "present_reviewers"):
            for value in ("0", "-1", "true", '"2"', "1.5"):
                text = VALID.replace('options = { builders = 3 }',
                                     'options = { builders = 3, %s = %s }' % (key, value))
                self.assertEqual(validate(text)[0], 1, (key, value))
                self.assertEqual(resolve(text, default=VALID)[0], 1, (key, value))
        for options, expected in (('builders = 3, reviewers = 4', (3, 4)),
                                  ('builders = 3, reviewers = 4, present_builders = 1, present_reviewers = 2', (1, 2))):
            text = VALID.replace('options = { builders = 3 }', 'options = { %s }' % options)
            code, lines = resolve(text, default=VALID)
            self.assertEqual(code, 0, lines)
            for key, value in zip(("present_builders", "present_reviewers"), expected):
                self.assertIn('runtime.options.%s = %s  # %s' %
                              (key, value, "core" if "present_" not in options else "project"), lines)

    def test_size_budget_defaults_and_layer_overrides(self):
        self.assertResolves(['size_budget.builder = 16384  # core',
                             'size_budget.reviewer = 16384  # core'], VALID)
        self.assertResolves(['size_budget.builder = 8192  # project',
                             'size_budget.reviewer = 4096  # org',
                             'size_budget.coordinator = 16384  # core'],
                            VALID + "\n[size_budget]\nbuilder = 8192\n",
                            org="[size_budget]\nbuilder = 12288\nreviewer = 4096\n")

    def assertResolves(self, expected, *args, **kwargs):
        code, lines = resolve(*args, **kwargs)
        self.assertEqual(code, 0, lines)
        for line in expected:
            self.assertIn(line, lines)
        return lines

    def assertFails(self, expected, *args, **kwargs):
        code, lines = resolve(*args, **kwargs)
        self.assertEqual(code, 1, lines)
        self.assertIn(expected, lines)

    def test_session_runtime_core_defaults(self):  # #914
        lines = self.assertResolves(['runtime.name = "session"  # project',
                                     'runtime.options.session_backend = "native"  # core',
                                     'runtime.options.builders = 5  # core',
                                     'runtime.options.reviewers = 2  # core',
                                     'runtime.options.max_active_milestones = 1  # core',
                                     'runtime.options.merge_grant = "none"  # core',
                                     'runtime.options.researchers = 0  # core'],  # #1724: the sweep is opt-in
                                    VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"'))
        for line in ('runtime.options.present_builders = 5  # core', 'runtime.options.present_reviewers = 2  # core'):
            self.assertIn(line, lines)  # #1053: owner-present limits default to the full caps

    def test_session_triage_needs_an_explicit_positive_researcher_cap(self):  # #1724
        session = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { %s }')
        triage = "\n[triage]\nenabled = true\n"
        for options, layer in (("", "core"), ("researchers = 0", "crew.toml")):  # unset resolves to the core 0
            code, lines = resolve(session % options + triage, default=VALID)
            self.assertEqual(code, 1, lines)
            self.assertTrue(any(ln.endswith("runtime.options.researchers: 0 runs no researcher, but triage.enabled = true "
                                            "needs one for its sweep; set researchers >= 1 (the session default is 0, "
                                            "#1724)") and ln.startswith(layer) for ln in lines), lines)
        code, lines = resolve(session % "researchers = 1" + triage, default=VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn("runtime.options.researchers = 1  # project", lines)
        code, lines = resolve(VALID + triage, default=VALID)  # tmux keeps its default of 2
        self.assertEqual(code, 0, lines)
        self.assertIn("runtime.options.researchers = 2  # core", lines)

    def test_session_present_cap_bound_spans_layers(self):  # #1053
        project = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { builders = 3 }')
        org = '[runtime.options]\npresent_builders = %d\n'
        lines = self.assertResolves(['runtime.options.present_builders = 2  # org'], project, default=VALID, org=org % 2)
        self.assertIn('runtime.options.present_reviewers = 2  # core', lines)
        self.assertFails("org.toml:runtime.options.present_builders: must be <= builders (3), got 4",
                         project, default=VALID, org=org % 4)

    def test_core_defaults_under_project(self):
        self.assertResolves(['repo.default_branch = "main"  # core',
                             'repo.owner = "acme"  # project',
                             'runtime.options.builders = 3  # project',
                             'runtime.options.reviewers = 2  # core',
                             'engines.trivial.effort = "low"  # core',
                             'engines.default.effort = "medium"  # project'], VALID)

    def test_each_layer_overrides_the_one_before(self):
        default = VALID.replace('name = "widgets"', 'name = "widgets"\ndefault_branch = "trunk"')
        org = '[engines]\ndefault = { order = ["claude-code/opus"] }\ndeep = { effort = "medium" }\n'
        project = '[repo]\nowner = "other"\n[engines]\ndeep = { effort = "low" }\n'
        self.assertResolves(['repo.default_branch = "trunk"  # default',
                             'repo.name = "widgets"  # default',
                             'engines.default.order = ["claude-code/opus"]  # org',
                             'engines.default.effort = "medium"  # default',
                             'engines.deep.effort = "low"  # project',
                             'repo.owner = "other"  # project'], project, default=default, org=org)

    def test_table_merge_and_scalar_array_replace(self):
        project = '[identities]\nowners = ["a", "b"]\n[engines]\ndefault = { order = ["claude-code/opus"] }\n'
        lines = self.assertResolves(['identities.owners = ["a", "b"]  # project',
                                     'identities.builder.gh_user = "acme-bot"  # default',
                                     'engines.default.order = ["claude-code/opus"]  # project'],
                                    project, default=VALID)
        self.assertNotIn('engines.default.order = ["codex/gpt-6.1-sol", "claude-code/sonnet"]  # default', lines)

    def test_engine_role_override_resolves(self):  # #597
        project = '[engines.roles]\nsynthesizer = { order = ["codex/gpt-6.1-sol"] }\n'
        self.assertResolves(['engines.roles.synthesizer.order = ["codex/gpt-6.1-sol"]  # project'], project, default=VALID)
        self.assertFails("crew.toml:engines.roles.lead: unknown key", project.replace("synthesizer", "lead"), default=VALID)

    def test_missing_org_layer(self):
        self.assertResolves(['repo.owner = "acme"  # project'], VALID)
        self.assertResolves(['repo.owner = "acme"  # default'], "", default=VALID)
        code, lines = resolve(VALID, org_path="/nonexistent/org.toml")
        self.assertEqual(code, 1)
        self.assertTrue(lines[0].startswith("/nonexistent/org.toml:(file): cannot read"), lines)

    def test_drop_invariant_key_is_an_error(self):
        self.assertFails("crew.toml:identities.reviewer.gh_user: cannot remove invariant-protecting key (set by default)",
                         'identities = "none"\n', default=VALID)
        default = VALID.replace('[backends.review]\nname = "github"',
                                '[backends.review]\nname = "github"\ncapabilities = { post-verdict = "supported" }')
        self.assertFails("org.toml:backends.review.capabilities.post-verdict: cannot remove invariant-protecting key "
                         "(set by default)", "", default=default, org='[backends.review]\ncapabilities = "none"\n')

    def test_resolved_profile_is_validated(self):
        self.assertFails("(resolved):repo.owner: missing required key", VALID.replace('owner = "acme"\n', ""))
        self.assertFails("crew.toml:extra: unknown key", '[extra]\nx = 1\n', default=VALID)

    def test_unsupported_invariant_rule(self):
        one = VALID.replace('[backends.review]\nname = "github"',
                            '[backends.review]\nname = "github"\ncapabilities = { request-rereview = "unsupported" }')
        self.assertResolves([], one)
        self.assertFails("crew.toml:backends.review.capabilities.post-verdict: unsupported leaves I2 with no other "
                         "operation keeping it; profile unsupported (docs/interfaces.md)",
                         one.replace('{ request-rereview', '{ post-verdict = "unsupported", request-rereview'))

    def test_single_identity_requires_emulated_verdict(self):
        single = VALID.replace('reviewer = { gh_user = "acme-reviewer" }', 'reviewer = { gh_user = "acme-bot" }')
        self.assertFails(os.path.join(cc.CONNECTORS_DIR, "github", "manifest.toml") +
                         ":backends.review.capabilities.post-verdict: reviewer gh_user equals builder "
                         "gh_user; a single-identity profile must declare emulated (<how>) (#111)", single)
        self.assertResolves([], single.replace('[backends.review]\nname = "github"',
                                               '[backends.review]\nname = "github"\n'
                                               'capabilities = { post-verdict = "emulated (COMMENT review)" }'))

    def test_release_table_and_gate_operations(self):
        """#585: the optional [release] table and the release concern."""
        release = '\n[release]\nchangelog = "docs/HISTORY.md"\nrelease_id = "commit"\n'
        self.assertResolves(['release.release_id = "commit"  # project'], VALID + release)
        no_release = VALID.replace('[backends.release]\nname = "github"', "")
        self.assertResolves([], no_release)
        self.assertFails("(resolved):backends.release.capabilities.approve-check: undeclared (counts as unsupported) "
                         "with a [release] table leaves the release gate unkept; profile unsupported for release "
                         "(docs/interfaces.md)", no_release + release)
        self.assertFails("crew.toml:backends.release.capabilities.record-release: unsupported with a [release] table "
                         "leaves the release gate unkept; profile unsupported for release (docs/interfaces.md)",
                         VALID.replace('[backends.release]\nname = "github"', '[backends.release]\nname = "github"\n'
                                       'capabilities = { record-release = "unsupported" }') + release)
        for bad in ('release_id = "hash"', 'versioning = "calver"', 'tag_prefix = "v"', 'changelog = 1'):
            self.assertEqual(validate(VALID + "\n[release]\n" + bad + "\n")[0], 1, bad)

    def test_merge_grant_and_hold_options(self):
        """14.1d (#233): tmux synthesizer options default to per-PR merge-ok and a blocking crew:hold."""
        self.assertResolves(['runtime.options.merge_grant = "none"  # core',
                             'runtime.options.hold_label_blocks = true  # core'], VALID)
        self.assertResolves(['runtime.options.merge_grant = "#110 roadmap PRs per #111"  # project',
                             'runtime.options.hold_label_blocks = false  # project',
                             'paths.mdstack = "/srv/mdstack"  # project'],
                            VALID.replace("builders = 3", 'builders = 3, merge_grant = "#110 roadmap PRs per #111", '
                                          "hold_label_blocks = false")
                            + 'mdstack = "/srv/mdstack"\n')
        self.assertFails("crew.toml:runtime.options.hold_label_blocks: expected boolean, got string",
                         VALID.replace("builders = 3", 'builders = 3, hold_label_blocks = "no"'))

    def test_lone_pr_land_option(self):
        self.assertResolves(['runtime.options.lone_pr_land = "train"  # core'], VALID)
        for policy in ("train", "direct"):
            self.assertResolves(['runtime.options.lone_pr_land = "%s"  # project' % policy],
                                VALID.replace("builders = 3", 'lone_pr_land = "%s"' % policy),
                                org='[runtime.options]\nlone_pr_land = "direct"\n')
        self.assertFails("crew.toml:runtime.options.lone_pr_land: unknown value 'skip' (expected one of: train, direct)",
                         VALID.replace("builders = 3", 'lone_pr_land = "skip"'))
        self.assertFails("crew.toml:runtime.options.lone_pr_land: expected string, got boolean",
                         VALID.replace("builders = 3", "lone_pr_land = true"))

    def test_mirror_option(self):
        """runtime.options.mirror (#877 B1): live-copy by default, none is an opt-in that conflicts with a deferral."""
        self.assertResolves(['runtime.options.mirror = "live-copy"  # core'], VALID)
        for value in ("live-copy", "none"):
            self.assertResolves(['runtime.options.mirror = "%s"  # project' % value],
                                VALID.replace("builders = 3", 'mirror = "%s"' % value))
        self.assertResolves(['runtime.options.mirror = "none"  # org'], VALID, org='[runtime.options]\nmirror = "none"\n')
        self.assertFails("crew.toml:runtime.options.mirror: unknown value 'x' (expected one of: live-copy, none)",
                         VALID.replace("builders = 3", 'mirror = "x"'))
        self.assertFails("crew.toml:runtime.options.mirror: expected string, got boolean",
                         VALID.replace("builders = 3", "mirror = false"))
        grok = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "grok-bot"\noptions = { mirror = "none" }')
        self.assertFails("crew.toml:runtime.options.mirror: unknown key", grok)
        conflict = 'crew.toml:runtime.options.mirror: "none" conflicts with mirror_deferral "#110 per #140"; ' \
            "an install with no live copy has nothing to defer"
        both = VALID.replace("builders = 3", 'mirror = "none", mirror_deferral = "#110 per #140"')
        self.assertFails(conflict, both)
        self.assertEqual(validate(both), (1, [conflict]))
        self.assertFails('org.toml:runtime.options.mirror: "none" conflicts with mirror_deferral "#110 per #140"; '
                         "an install with no live copy has nothing to defer",
                         VALID.replace("builders = 3", 'mirror_deferral = "#110 per #140"'),
                         org='[runtime.options]\nmirror = "none"\n')
        self.assertResolves(['runtime.options.mirror = "none"  # project', 'runtime.options.mirror_deferral = "none"  # project'],
                            VALID.replace("builders = 3", 'mirror = "none", mirror_deferral = "none"'))

    def test_suite_cap_resolves_explicit_override(self):
        self.assertResolves(["runtime.options.max_suites = 3  # project"],
                            VALID.replace("builders = 3", "max_suites = 3"),
                            org="[runtime.options]\nmax_suites = 2\n")
        code, lines = resolve(VALID)
        self.assertEqual(code, 0, lines)
        self.assertFalse(any(line.startswith("runtime.options.max_suites =") for line in lines))

    def test_max_active_milestones_resolve(self):
        for runtime in ("tmux", "grok-bot"):
            profile = VALID.replace('name = "tmux"', 'name = "%s"' % runtime)
            self.assertResolves(['runtime.options.max_active_milestones = 1  # core'],
                                profile.replace("builders = 3", ""))
            self.assertResolves(['runtime.options.max_active_milestones = 2  # project'],
                                profile.replace("builders = 3", "max_active_milestones = 2"),
                                org='[runtime.options]\nmax_active_milestones = 3\n')
            self.assertFails("crew.toml:runtime.options.max_active_milestones: must be >= 1, got 0",
                             profile.replace("builders = 3", "max_active_milestones = 0"))

    def test_train_options_resolve(self):
        self.assertResolves(['runtime.options.train_min = 2  # core',
                             'runtime.options.train_window = 600  # core'], VALID)
        self.assertResolves(['runtime.options.train_min = 4  # project',
                             'runtime.options.train_window = 120  # org'],
                            VALID.replace("builders = 3", "train_min = 4"),
                            org='[runtime.options]\ntrain_min = 3\ntrain_window = 120\n')
        self.assertFails("crew.toml:runtime.options.train_min: must be >= 2, got 1",
                         VALID.replace("builders = 3", "train_min = 1"))
        self.assertFails("crew.toml:runtime.options.train_window: must be >= 1, got 0",
                         VALID.replace("builders = 3", "train_window = 0"))

    def test_permission_mode_option(self):
        """#293: tmux role windows launch unattended by default (bypass); auto and safe are opt-in."""
        self.assertResolves(['runtime.options.permission_mode = "bypass"  # core'], VALID)
        for mode in ["bypass", "auto", "safe"]:
            self.assertResolves(['runtime.options.permission_mode = "%s"  # project' % mode],
                                VALID.replace("builders = 3", 'builders = 3, permission_mode = "%s"' % mode))
        self.assertFails("crew.toml:runtime.options.permission_mode: unknown value 'yolo' (expected one of: bypass, "
                         "auto, safe)", VALID.replace("builders = 3", 'builders = 3, permission_mode = "yolo"'))
        self.assertFails("crew.toml:runtime.options.permission_mode: expected string, got boolean",
                         VALID.replace("builders = 3", "builders = 3, permission_mode = true"))

    def test_integer_option_range(self):
        self.assertFails("crew.toml:runtime.options.builders: must be >= 1, got 0",
                         VALID.replace("builders = 3", "builders = 0"))

    def test_doc_example_resolves(self):
        with open(os.path.join(SCRIPTS, "..", "docs", "profile.md"), encoding="utf-8") as f:
            m = re.search(r"```toml\n(.*?)```", f.read(), re.S)
        self.assertResolves(['runtime.options.builders = 5  # project'], m.group(1))

    def test_resolve_profile_is_what_the_cli_prints(self):
        """#165: resolve_profile returns the merged profile and per-leaf provenance; `resolve` prints exactly that."""
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            with open(project, "w", encoding="utf-8") as f:
                f.write(VALID)
            saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
            try:
                merged, provenance, problems, layers = cc.resolve_profile(project)
                failed = cc.resolve_profile(os.path.join(d, "missing.toml"))
            finally:
                cc.DEFAULT_PROFILE = saved
        self.assertEqual((problems, layers), ([], ["core", "project"]))
        self.assertEqual(merged["runtime"]["options"]["builders"], 3)
        self.assertEqual([provenance[k] for k in ("repo.owner", "repo.default_branch", "backends.change.capabilities.land")],
                         ["project", "core", "pack:github"])
        self.assertEqual(resolve(VALID), (0, ["%s = %s  # %s" % (k, json.dumps(v, ensure_ascii=False), provenance[k])
                                              for k, v in cc.leaves(merged)]))
        self.assertEqual(failed[:2], (None, None))
        self.assertEqual([p.replace(d + os.sep, "") for p in failed[2]],
                         ["missing.toml:(file): cannot read (No such file or directory)"])




# --- team files (#634): one [team] table plus small [repos.<name>] sections. ---
TEAM = """\
[team]
pack = "github"
personas = { builder = "Ben", reviewer = "Vera" }
accounts = { all = "acme-bot", reviewer = "acme-reviewer" }
runtime = { name = "tmux", options = { builders = 3 } }
identities = { owners = ["acme-owner"] }
engines = { coordinator = "codex", trivial = { order = ["claude-code/sonnet"] }, default = { order = ["codex/gpt-6.1-sol", "claude-code/sonnet"], effort = "medium" }, deep = { order = ["codex/gpt-6.1-sol"] } }
paths = { state_dir = "/srv/crew-state", worktree_root = "/srv/wt" }

[repos.widgets]
repo = "acme/widgets"

[repos.gadgets]
repo = "acme/gadgets"
default_branch = "trunk"
merge_grant = "docs PRs"
train_window = 120
sensitive = ["billing/**"]
precheck = { enabled = true, lint = "make lint" }
"""


class TeamFileTest(unittest.TestCase):
    def resolve(self, text, ref=""):
        """Resolve teams/ext.toml (plus #ref) with no default layer; return (merged, provenance, problems)."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ext.toml")
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
            try:
                merged, prov, problems, layers = cc.resolve_profile(path + ref)
            finally:
                cc.DEFAULT_PROFILE = saved
        return merged, prov, [p.replace(d + os.sep, "") for p in problems], layers

    def test_repo_sections_layer_over_the_team(self):
        merged, prov, problems, layers = self.resolve(TEAM, "#gadgets")
        self.assertEqual((problems, layers), ([], ["core", "team", "repo"]))
        self.assertEqual((merged["repo"], prov["repo.name"]), ({"owner": "acme", "name": "gadgets", "default_branch": "trunk"}, "repo"))
        opts = merged["runtime"]["options"]
        self.assertEqual((opts["merge_grant"], opts["train_window"], opts["builders"]), ("docs PRs", 120, 3))
        self.assertEqual((merged["sensitive"]["paths"], merged["builder"]["precheck"]["lint"]), (["billing/**"], "make lint"))
        self.assertEqual([merged["identities"][r]["gh_user"] for r in ("builder", "reviewer")], ["acme-bot", "acme-reviewer"])
        self.assertEqual((merged["identities"]["builder"]["name"], prov["identities.builder.name"]), ("Ben", "team"))
        self.assertEqual((merged["paths"]["state_dir"], opts["session"]), ("/srv/crew-state/ext", "crew-team-ext"))
        self.assertEqual(merged["backends"]["change"]["name"], "github")
        merged, prov, problems, _ = self.resolve(TEAM, "#widgets")
        self.assertEqual((problems, merged["repo"]["name"], merged["runtime"]["options"]["merge_grant"]), ([], "widgets", "none"))

    def test_repo_selection(self):
        self.assertEqual(self.resolve(TEAM)[2], ["ext.toml:repos: lists 2 repos; select one as ext.toml#<repo>"])
        self.assertEqual(self.resolve(TEAM, "#nope")[2], ["ext.toml:repos: names no repo 'nope' (repos: widgets, gadgets)"])
        one = TEAM[:TEAM.index("[repos.gadgets]")]
        self.assertEqual(self.resolve(one)[0]["repo"]["name"], "widgets")
        self.assertEqual(self.resolve(VALID, "#widgets")[2],
                         ["ext.toml:(file): not a team file; ext.toml#widgets needs [team] and [repos.<name>]"])

    def test_repo_sections_take_only_allowlisted_keys(self):
        bad = TEAM.replace('repo = "acme/widgets"', 'repo = "acme/widgets"\nbuilders = 9\nidentities = {}')
        problems = self.resolve(bad, "#widgets")[2]
        allowed = "repo, default_branch, precheck, sensitive, spec, checkout, control_item, labels, milestones, doc_home, " \
            "flavor, merge_grant, merge_grant_scope, mirror_deferral, mirror, lone_pr_land, train_min, train_window, " \
            "train_local_checks"
        self.assertEqual(problems, ["ext.toml:repos.widgets.builders: not allowed in a repo section (team-only; allowed: %s)" % allowed,
                                    "ext.toml:repos.widgets.identities: not allowed in a repo section (team-only; allowed: %s)" % allowed])
        problems = self.resolve(TEAM.replace("[team]\n", '[team]\nmerge_grant = "x"\n').replace(
            'repo = "acme/widgets"', 'repo = "widgets"'), "#widgets")[2]
        self.assertEqual(problems, ["ext.toml:team.merge_grant: unknown team key (per-repo; set it in [repos.<name>])",
                                    "ext.toml:repos.widgets.repo: expected <owner>/<name>"])
        self.assertIn("ext.toml[repos.gadgets]:runtime.options.train_window: expected integer, got string",
                      self.resolve(TEAM.replace("train_window = 120", 'train_window = "2m"'), "#gadgets")[2])

    def test_closed_project_keys_resolve_with_provenance(self):  # #1856: team §9.8's five keys, from the repo section
        text = TEAM.replace('runtime = { name = "tmux",', 'runtime = { name = "tmux", instance = "eng",').replace(
            'train_window = 120', 'train_window = 120\ncontrol_item = 5\nlabels = { "crew:ready" = "ready" }\n'
            'milestones = [3, 1]\ndoc_home = "handbook"\nflavor = { name = "thorough" }')
        merged, prov, problems, _ = self.resolve(text, "#gadgets")
        self.assertEqual(problems, [])
        self.assertEqual({k: merged["repo"][k] for k in ("control_item", "labels", "milestones", "doc_home")},
                         {"control_item": 5, "labels": {"crew:ready": "ready"}, "milestones": [3, 1], "doc_home": "handbook"})
        self.assertEqual({prov[k] for k in ("repo.control_item", "repo.labels.crew:ready", "repo.milestones",
                                            "repo.doc_home", "flavor.name")}, {"repo"})
        self.assertEqual(merged["flavor"]["name"], "thorough")
        widgets = self.resolve(text, "#widgets")[0]  # omitted keys keep today's resolution: nothing added
        self.assertEqual((widgets["repo"], widgets["flavor"]), ({"owner": "acme", "name": "widgets", "default_branch": "main"},
                                                                {"name": "standard"}))

    def test_closed_project_keys_refuse_unknown_and_invalid_values(self):
        def problems(lines):
            return self.resolve(TEAM.replace('train_window = 120', 'train_window = 120\n' + lines), "#gadgets")[2]
        self.assertEqual(problems('flavor = { name = "thorough", engines = {} }'),
                         ["ext.toml:repos.gadgets.flavor.engines: unknown key"])
        self.assertIn("ext.toml[repos.gadgets]:repo.labels.crew:hold: label 'ready\\n' is also crew:ready's label; each "
                      "state tag needs its own", problems('labels = { "crew:ready" = " ready", "crew:hold" = "ready\\n" }'))
        self.assertEqual(problems('milestones = [1.0]'), ["ext.toml[repos.gadgets]:repo.milestones[0]: expected a milestone "
                                                          "number >= 1"])  # an integral float is not a milestone number
        self.assertEqual(problems('labels = { "crew:done" = "done", "crew:hold" = "crew:ready", "crew:spec" = " " }'), [
            "ext.toml[repos.gadgets]:repo.labels.crew:done: unknown state tag (expected one of: %s)" % ", ".join(cc.STATE_TAGS),
            "ext.toml[repos.gadgets]:repo.labels.crew:hold: label 'crew:ready' is also crew:ready's label; each state tag "
            "needs its own",
            "ext.toml[repos.gadgets]:repo.labels.crew:spec: expected a nonempty tracker label"])
        self.assertEqual(problems('milestones = [2, 2, "v1", 0]'), [
            "ext.toml[repos.gadgets]:repo.milestones[1]: duplicate milestone 2",
            "ext.toml[repos.gadgets]:repo.milestones[2]: expected a milestone number >= 1",
            "ext.toml[repos.gadgets]:repo.milestones[3]: expected a milestone number >= 1"])
        self.assertEqual(problems("milestones = []"), ["ext.toml[repos.gadgets]:repo.milestones: expected a nonempty list "
                                                       "(omit it for the tracker's own milestone order)"])
        for home in ("../outside", "/abs", "docs/../../x", ""):
            self.assertEqual(problems('doc_home = "%s"' % home), [
                "ext.toml[repos.gadgets]:repo.doc_home: expected a nonempty project-relative directory without .. "
                "(no escape from the checkout)"], home)
        self.assertEqual(problems('control_item = 0'), ["ext.toml[repos.gadgets]:repo.control_item: must be >= 1",
                                                        "(resolved):runtime.instance: control_item needs an instance label "
                                                        "([a-z0-9-], 1-63 characters)"])

    def test_project_flavor_tightens_never_relaxes(self):  # team §9.1: strictest of team and project; relaxing refuses
        team = TEAM.replace("[team]\n", '[team]\nflavor = { name = "standard" }\n')
        merged, prov, problems, _ = self.resolve(team.replace('train_window = 120', 'train_window = 120\n'
                                                              'flavor = { name = "thorough" }'), "#gadgets")
        self.assertEqual((problems, merged["flavor"]["name"], prov["flavor.name"]), ([], "thorough", "repo"))
        self.assertEqual(self.resolve(team.replace('train_window = 120', 'train_window = 120\nflavor = { name = "fast" }'),
                                      "#gadgets")[2], [
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes validation from behaviour (flavor standard, set by team) "
            "to off; a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes evidence from typed (flavor standard, set by team) to "
            "inline; a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes merge from docs (flavor standard, set by team) to auto; "
            "a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes precheck from on (flavor standard, set by team) to off; "
            "a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes lighter_lane from docs (flavor standard, set by team) to "
            "docs+tests; a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes caps[0] from 3 (flavor standard, set by team) to 2; "
            "a project may only tighten",
            "ext.toml[repos.gadgets]:flavor.name: fast relaxes caps[1] from 3 (flavor standard, set by team) to 2; "
            "a project may only tighten"])
        thorough = TEAM.replace("[team]\n", '[team]\nflavor = { name = "thorough" }\n')  # unset repo: the team's
        self.assertEqual(self.resolve(thorough, "#gadgets")[0]["flavor"]["name"], "thorough")
        self.assertIn("ext.toml[repos.gadgets]:flavor.name: standard relaxes review from full (flavor thorough, set by "
                      "team) to thin; a project may only tighten",
                      self.resolve(thorough.replace('train_window = 120', 'train_window = 120\nflavor = { name = "standard" }'),
                                   "#gadgets")[2])
        self.assertIn("ext.toml[repos.gadgets]:flavor.name: express is an item flavor only (record plus crew:express); "
                      "never a project, class or base",
                      self.resolve(team.replace('train_window = 120', 'train_window = 120\nflavor = { name = "express" }'),
                                   "#gadgets")[2])

    def test_project_flavor_floor_is_every_lower_layer(self):  # a weaker team never hides a stricter org floor
        with tempfile.TemporaryDirectory() as d:
            org, team = os.path.join(d, "org.toml"), os.path.join(d, "eng.toml")
            with open(org, "w") as f:
                f.write('[flavor]\nname = "thorough"\n')
            with open(team, "w") as f:
                f.write(TEAM.replace("[team]\n", '[team]\nflavor = { name = "standard" }\n').replace(
                    'train_window = 120', 'train_window = 120\nflavor = { name = "%s" }'))
            text = open(team).read()
            for project, expected in (("standard", ["%s[repos.gadgets]:flavor.name: standard relaxes review from full "
                                                    "(flavor thorough, set by org) to thin; a project may only tighten"
                                                    % team, "%s[repos.gadgets]:flavor.name: standard relaxes "
                                                    "validation from always (flavor thorough, set by org) to behaviour; "
                                                    "a project may only tighten" % team,
                                                    "%s[repos.gadgets]:flavor.name: standard relaxes "
                                                    "validation_scope from repo (flavor thorough, set by org) to bounded; "
                                                    "a project may only tighten" % team]),
                                      ("thorough", [])):  # the control: matching the strictest floor resolves
                with open(team, "w") as f:
                    f.write(text % project)
                problems = cc.resolve_profile(team + "#gadgets", org)[2]
                self.assertEqual([p for p in problems if "flavor.name" in p], expected, project)

    def test_duplicate_repo_and_team_wide_grant_refuse_for_every_selector(self):
        twice = TEAM + '\n[repos.copy]\nrepo = "ACME/Widgets"\n'
        for ref in ("#widgets", "#gadgets", "#copy"):
            self.assertIn("ext.toml:repos.copy.repo: ACME/Widgets is repos.widgets's repo too; a team holds each repo once",
                          self.resolve(twice, ref)[2])
        self.assertIn("ext.toml:repos.copy.repo: acme/widgets\n is repos.widgets's repo too; a team holds each repo once",
                      self.resolve(TEAM + '\n[repos.copy]\nrepo = "acme/widgets\\n"\n', "#widgets")[2])  # equivalence
        wide = TEAM.replace("options = { builders = 3 }", 'options = { builders = 3, merge_grant = "all PRs" }')
        self.assertIn("ext.toml:team.runtime.options.merge_grant: a landing grant is per repo; set it in [repos.<name>] "
                      "so its scope never spans the team", self.resolve(wide, "#widgets")[2])
        self.assertEqual(self.resolve(TEAM, "#gadgets")[2], [])  # the control: a per-repo grant still resolves

    def test_doc_home_symlink_escape_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            checkout = os.path.join(d, "widgets")
            os.makedirs(os.path.join(checkout, "handbook"))
            os.symlink(d, os.path.join(checkout, "out"))
            text = TEAM.replace('repo = "acme/widgets"', 'repo = "acme/widgets"\ncheckout = "%s"\ndoc_home = "%%s"' % checkout)
            self.assertEqual(self.resolve(text % "handbook", "#widgets")[2], [])
            self.assertEqual(self.resolve(text % "out/elsewhere", "#widgets")[2], [
                "ext.toml[repos.widgets]:repo.doc_home: out/elsewhere resolves outside the checkout %s"
                % os.path.realpath(checkout)])

    def test_repo_section_sets_mirror(self):
        merged, prov, problems, _ = self.resolve(TEAM.replace('train_window = 120', 'train_window = 120\nmirror = "none"'),
                                                 "#gadgets")
        self.assertEqual(problems, [])
        self.assertEqual((merged["runtime"]["options"]["mirror"], prov["runtime.options.mirror"]), ("none", "repo"))
        self.assertEqual(self.resolve(TEAM, "#widgets")[0]["runtime"]["options"]["mirror"], "live-copy")

    def test_repo_section_sets_its_checkout(self):  # #1287: each repo names its clone; the team file sits in none
        merged, prov, problems, _ = self.resolve(TEAM.replace('repo = "acme/widgets"',
                                                              'repo = "acme/widgets"\ncheckout = "/src/widgets"'), "#widgets")
        self.assertEqual(problems, [])
        self.assertEqual((merged["paths"]["checkout"], prov["paths.checkout"]), ("/src/widgets", "repo"))
        self.assertEqual(merged["paths"]["worktree_root"], "/srv/wt")
        self.assertNotIn("checkout", self.resolve(TEAM, "#gadgets")[0]["paths"])
        rooted = TEAM.replace('paths = { state_dir', 'paths = { root = "/home/crew", state_dir').replace(
            'repo = "acme/widgets"', 'repo = "acme/widgets"\ncheckout = "src/<repo>"')
        self.assertEqual(self.resolve(rooted, "#widgets")[0]["paths"]["checkout"], "/home/crew/src/widgets")

    def test_explicit_team_name_keeps_identity_across_file_names(self):  # #1348
        named = TEAM.replace("[team]\n", '[team]\nname = "md"\n')
        with tempfile.TemporaryDirectory() as d:
            saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
            try:
                os.makedirs(os.path.join(d, "teams"))
                target = os.path.join(d, "teams", "md.toml")
                with open(target, "w", encoding="utf-8") as f:
                    f.write(named)
                os.symlink(target, os.path.join(d, "link.toml"))
                os.symlink(target, os.path.join(d, "config.toml"))
                seen = set()
                for ref in ("teams/md.toml", "config.toml", "link.toml"):
                    merged, _, problems, _ = cc.resolve_profile(os.path.join(d, ref) + "#gadgets")
                    self.assertEqual(problems, [], ref)
                    seen.add((merged["paths"]["state_dir"], merged["runtime"]["options"]["session"]))
                self.assertEqual(seen, {("/srv/crew-state/md", "crew-team-md")})
            finally:
                cc.DEFAULT_PROFILE = saved
        merged, prov, problems, _ = self.resolve(TEAM, "#gadgets")  # a nameless file keeps its file-name identity
        self.assertEqual((problems, merged["paths"]["state_dir"]), ([], "/srv/crew-state/ext"))
        for bad in ('"MD"', '""', "7", '"%s"' % ("a" * 64)):
            self.assertEqual(self.resolve(TEAM.replace("[team]\n", "[team]\nname = %s\n" % bad), "#gadgets")[2],
                             ["ext.toml:team.name: expected [a-z0-9-] (1-63 characters)"], bad)

    def test_team_name_reaches_meta_for_signatures(self):  # #1291: team.name, else the file name; legacy has none
        for text, want in ((TEAM, "ext"), (TEAM.replace("[team]\n", '[team]\nname = "md"\n'), "md")):
            with tempfile.TemporaryDirectory() as d:
                path = os.path.join(d, "ext.toml")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
                try:
                    meta = {}
                    self.assertEqual(cc.resolve_profile(path + "#gadgets", meta=meta)[2], [])
                    self.assertEqual(meta["team.name"], (want, "team"))
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(VALID)
                    meta = {}
                    self.assertEqual(cc.resolve_profile(path, meta=meta)[2], [])
                    self.assertNotIn("team.name", meta)
                finally:
                    cc.DEFAULT_PROFILE = saved

    def test_explicit_team_name_lifts_the_file_name_rule(self):  # #1348: My Team.toml with team.name resolves
        with tempfile.TemporaryDirectory() as d:
            saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
            try:
                path = os.path.join(d, "My Team.toml")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(TEAM)
                problems = cc.resolve_profile(path + "#gadgets")[2]
                self.assertTrue(any("team file name must be <team>.toml" in p for p in problems), problems)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(TEAM.replace("[team]\n", '[team]\nname = "my-team"\n'))
                merged, _, problems, _ = cc.resolve_profile(path + "#gadgets")
                self.assertEqual((problems, merged["paths"]["state_dir"]), ([], "/srv/crew-state/my-team"))
            finally:
                cc.DEFAULT_PROFILE = saved

    def test_legacy_profile_is_a_one_repo_team(self):
        """VALID as a one-repo team file resolves to the same values; only the team state root and session differ."""
        team = TEAM[:TEAM.index("[repos.widgets]")].replace(
            'personas = { builder = "Ben", reviewer = "Vera" }\n', "") + '[repos.widgets]\nrepo = "acme/widgets"\n'
        with tempfile.TemporaryDirectory() as d:
            legacy = os.path.join(d, "crew.toml")
            with open(legacy, "w", encoding="utf-8") as f:
                f.write(VALID)
            saved, cc.DEFAULT_PROFILE = cc.DEFAULT_PROFILE, os.path.join(d, "absent.toml")
            try:
                old = cc.resolve_profile(legacy)[0]
            finally:
                cc.DEFAULT_PROFILE = saved
        new = self.resolve(team)[0]
        self.assertEqual(new["paths"].pop("state_dir"), "/srv/crew-state/ext")
        self.assertEqual(new["runtime"]["options"].pop("session"), "crew-team-ext")
        del old["paths"]["state_dir"]
        self.assertEqual(new, old)

# --- pack manifest folding (13.15, #127) ---
GITHUB_MANIFEST = read(os.path.join(ROOT, "connectors", "github", "manifest.toml"))


def resolve_with_packs(project, manifest):
    """Run `resolve` with cc.CONNECTORS_DIR pointed at a temp dir holding github/manifest.toml (None: no manifest)."""
    with tempfile.TemporaryDirectory() as packs:
        if manifest is not None:
            os.makedirs(os.path.join(packs, "github"))
            with open(os.path.join(packs, "github", "manifest.toml"), "w", encoding="utf-8") as f:
                f.write(manifest)
        saved, cc.CONNECTORS_DIR = cc.CONNECTORS_DIR, packs
        try:
            code, lines = resolve(project)
        finally:
            cc.CONNECTORS_DIR = saved
        return code, [ln.replace(packs + os.sep, "connectors/") for ln in lines]



class ProjectContextTest(unittest.TestCase):
    """Canonical project identity and the closed work envelope (team §9.3, D1; #1856)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.tmp)
        self.team = self.write("teams/eng.toml", TEAM.replace("[team]\n", '[team]\nname = "eng"\n'))
        self.solo = self.write("solo/one.toml", TEAM.replace("[team]\n", '[team]\nname = "eng"\n').split("[repos.gadgets]")[0])
        self.single = self.write("single/config.toml", VALID.replace('name = "widgets"', 'name = "Widgets"'))

    def write(self, rel, text):
        path = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return path

    def test_aliases_symlinks_and_omitted_selector_give_one_identity(self):
        os.symlink(self.solo, os.path.join(self.tmp, "alias.toml"))
        refs = [self.solo, self.solo + "#widgets", os.path.join(self.tmp, "alias.toml"),
                os.path.join(self.tmp, "solo", "..", "solo", "one.toml#widgets")]
        self.assertEqual({cc.project_identity(ref) for ref in refs}, {("eng", "acme/widgets")})
        self.assertEqual({cc.context(ref, "eng", "acme", "widgets")["project"] for ref in refs},
                         {os.path.realpath(self.solo) + "#widgets"})
        self.assertEqual(cc.project_identity(self.single), ("repo:acme/widgets", "acme/widgets"))  # derived singleton
        self.assertEqual(cc.project_identity(self.team + "#gadgets"), ("eng", "acme/gadgets"))
        for ref, reason in ((self.team, "lists 2 repos; select one"), (self.team + "#nope", "names no repo 'nope'")):
            with self.assertRaises(ValueError) as e:
                cc.project_identity(ref)
            self.assertIn(reason, str(e.exception))

    def test_envelope_refusals_and_controls(self):
        a = cc.context(self.team + "#widgets", "eng", "acme", "widgets")
        b = cc.context(self.team + "#gadgets", "eng", "acme", "gadgets")
        head = "1a" * 20
        env = cc.envelope(a, item=42, change=7, head=head, pass_="review", round_=1)
        self.assertEqual(sorted(env), sorted(cc.ENVELOPE))
        self.assertIsNone(cc.envelope_problem(env, a))  # the control: A's envelope acts in A
        self.assertIsNone(cc.envelope_problem(cc.envelope(a), a))  # a new build: change and head explicitly absent
        alias = dict(env, project=self.team.replace("teams/", "teams/../teams/") + "#widgets")
        self.assertIsNone(cc.envelope_problem(alias, a))  # another locator for the same identity
        self.assertEqual(cc.envelope_problem(env, b), "work envelope names acme/widgets in team eng, not acme/gadgets in team eng")
        self.assertEqual(cc.envelope_problem(dict(env, repo="acme/gadgets", team="eng"), b),
                         "work envelope project %s is acme/widgets in team eng, not acme/gadgets" % a["project"])
        self.assertIn("work envelope project /nowhere.toml does not resolve (",
                      cc.envelope_problem(dict(env, project="/nowhere.toml"), a))
        self.assertIn("does not resolve", cc.envelope_problem(dict(env, project=self.team + "#nope"), a))
        closed = "work envelope missing or not the closed key set (%s)" % ", ".join(cc.ENVELOPE)
        for bad in (None, {}, dict(env, extra=1), {k: v for k, v in env.items() if k != "round"}):
            self.assertEqual(cc.envelope_problem(bad, a), closed)
        for key, value in (("head", "abc"), ("head", head.upper()), ("round", 0), ("pass", "Review"), ("change", "7 x"),
                           ("team", "")):
            self.assertEqual(cc.envelope_problem(dict(env, **{key: value}), a), "work envelope has an invalid " + key)
        self.assertEqual(cc.envelope_problem(dict(env, change=None), a), "work envelope has an invalid head")


class ManifestFoldTest(unittest.TestCase):
    def test_external_backend_by_manifest_path(self):
        manifest = GITHUB_MANIFEST.replace('name = "github"', 'name = "example"')
        manifest = manifest.replace('[pack]\n', '[pack]\nmdstack_version = "v1.0.0"\n')
        with tempfile.TemporaryDirectory() as d:
            pack, project = os.path.join(d, "manifest.toml"), os.path.join(d, "crew.toml")
            with open(pack, "w") as f:
                f.write(manifest)
            with open(project, "w") as f:
                f.write(VALID.replace('[backends.review]\nname = "github"',
                                     '[backends.review]\nname = "example"\n'
                                     'capabilities = { post-verdict = "emulated (COMMENT review)" }'))
            profile, provenance, problems, _ = cc.resolve_profile(project, pack_manifest=pack)
            self.assertEqual(problems, [])
            self.assertEqual(profile["backends"]["review"]["name"], "example")
            self.assertEqual(provenance["backends.review.capabilities.list-verdicts"], "external-pack")
            self.assertEqual(provenance["backends.review.capabilities.post-verdict"], "project")
            self.assertEqual(provenance["backends.change.capabilities.land"], "pack:github")
            for command in (["validate", project, "--pack-manifest", pack],
                            ["resolve", "--project", project, "--pack-manifest", pack]):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cc.main(command), 0)
            with open(project, "a") as f:
                f.write('toolchain_bin = "/opt/bin"\nlive_dir = "/srv/live"\nmdstack = "/srv/mdstack"\n')
            for command in (["validate", project], ["resolve", "--project", project]):
                command += ["--install", "--pack-manifest", pack]
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cc.main(command), 0)
            with open(project) as f:
                concrete = f.read()
            with open(project, "w") as f:
                f.write(concrete.replace('owner = "acme"', 'owner = "<owner>"'))
            for command in (["validate", project], ["resolve", "--project", project]):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(cc.main(command + ["--install", "--pack-manifest", pack]), 1)
                self.assertIn("repo.owner: unfilled install-time placeholder <owner>", out.getvalue())
            with open(project, "w") as f:
                f.write(concrete)
            self.assertTrue(cc.resolve_profile(project)[2])
            org = os.path.join(d, "profile.toml")
            with open(org, "w") as f:
                f.write('[repo]\nname = "org-default"\n')
            self.assertEqual(cc.resolve_profile(project, org)[2], [])
            with open(project, "a") as f:
                f.write('pack = "."\n')
            profile, provenance, problems, layers = cc.resolve_profile(project)
            self.assertEqual(problems, [])
            self.assertEqual(layers, ["core", "default", "org", "project"])
            self.assertEqual(profile["repo"]["name"], "widgets")
            self.assertEqual(provenance["backends.review.capabilities.list-verdicts"], "external-pack")
            for bad in (manifest.replace('mdstack_version = "v1.0.0"\n', ''),
                        manifest.replace('list-verdicts = "supported"', 'list-verdicts = "invalid"'),
                        '[pack\n'):
                with open(pack, "w") as f:
                    f.write(bad)
                self.assertTrue(cc.resolve_profile(project, pack_manifest=pack)[2])
            os.unlink(pack)
            self.assertTrue(cc.resolve_profile(project, pack_manifest=pack)[2])

    def test_external_manifest_name_and_pin(self):
        manifest = GITHUB_MANIFEST.replace('name = "github"', 'name = "example"')
        self.assertEqual(validate(manifest)[0], 1)
        pinned = manifest.replace('[pack]\n', '[pack]\nmdstack_version = "v1.0.0"\n')
        self.assertEqual(validate(pinned)[0], 0)
        self.assertEqual(validate(pinned.replace('name = "example"', 'name = "../example"'))[0], 1)

    def test_manifest_capabilities_fold_under_profile(self):
        project = VALID.replace('[backends.review]\nname = "github"', '[backends.review]\nname = "github"\n'
                                'capabilities = { post-verdict = "emulated (COMMENT review)" }')
        code, lines = resolve(project)
        self.assertEqual(code, 0, lines)
        self.assertIn('backends.change.capabilities.land = "supported"  # pack:github', lines)
        self.assertIn('backends.review.capabilities.post-verdict = "emulated (COMMENT review)"  # project', lines)
        self.assertIn('backends.review.capabilities.list-verdicts = "supported"  # pack:github', lines)

    def test_manifest_unsupported_counts(self):
        bad = re.sub(r'(post-verdict|request-rereview) = "supported"', r'\1 = "unsupported"', GITHUB_MANIFEST)
        code, lines = resolve_with_packs(VALID, bad)
        self.assertEqual(code, 1, lines)
        self.assertIn("connectors/github/manifest.toml:backends.review.capabilities.post-verdict: unsupported leaves I2 "
                      "with no other operation keeping it; profile unsupported (docs/interfaces.md)", lines)
        rescued = VALID.replace('[backends.review]\nname = "github"', '[backends.review]\nname = "github"\n'
                                'capabilities = { post-verdict = "supported" }')
        self.assertEqual(resolve_with_packs(rescued, bad)[0], 0)

    def test_manifest_undeclared_counts(self):
        missing = re.sub(r"\n(post-verdict|request-rereview) = .*", "", GITHUB_MANIFEST)
        code, lines = resolve_with_packs(VALID, missing)
        self.assertEqual(code, 1, lines)
        self.assertIn("(resolved):backends.review.capabilities.post-verdict: undeclared (counts as unsupported) "
                      "leaves I2 with no other operation keeping it; profile unsupported (docs/interfaces.md)", lines)
        code, lines = resolve_with_packs(VALID, None)
        self.assertEqual(code, 1, lines)
        self.assertTrue(any("undeclared (counts as unsupported) leaves I1 " in ln for ln in lines), lines)

    def test_broken_manifest_fails(self):
        code, lines = resolve_with_packs(VALID, "[pack\n")
        self.assertEqual(code, 1, lines)
        self.assertTrue(lines[0].startswith("connectors/github/manifest.toml:(toml): invalid TOML"), lines)

    def test_manifest_version_pin_validates(self):
        pinned = GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nmdstack_version = "0123456789abcdef0123456789abcdef01234567"\n')
        self.assertEqual(validate(pinned), (0, ["crew-config: OK (crew.toml)"]))
        self.assertIn("crew.toml:pack.mdstack_version: expected string, got integer",
                      validate(pinned.replace('"0123456789abcdef0123456789abcdef01234567"', "1"))[1])

    def test_pack_version_semver(self):
        pinned = GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nmdstack_version = "v4.0.0"\n')
        for good in ("0.5.0", "1.2.3-rc.1+build.7"):
            self.assertEqual(validate(pinned.replace('[pack]\n', '[pack]\nversion = "%s"\n' % good)),
                             (0, ["crew-config: OK (crew.toml)"]), good)
        for bad in ("v0.5.0", "0.5", "01.0.0", "0.5.0-"):
            self.assertIn("crew.toml:pack.version: expected a SemVer version (MAJOR.MINOR.PATCH, no leading v)",
                          validate(pinned.replace('[pack]\n', '[pack]\nversion = "%s"\n' % bad))[1], bad)
        self.assertEqual(validate(pinned)[0], 0)

    def test_pack_version_resolve_metadata(self):
        manifest = GITHUB_MANIFEST.replace('name = "github"', 'name = "example"')
        manifest = manifest.replace('[pack]\n', '[pack]\nmdstack_version = "v4.0.0"\n')
        project_text = VALID.replace('[backends.review]\nname = "github"', '[backends.review]\nname = "example"')
        with tempfile.TemporaryDirectory() as d:
            pack, project = os.path.join(d, "manifest.toml"), os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(project_text)

            def run(text):
                with open(pack, "w") as f:
                    f.write(text)
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = cc.main(["resolve", "--project", project, "--pack-manifest", pack])
                return code, out.getvalue().splitlines()

            code, legacy = run(manifest)
            self.assertEqual(code, 0, legacy)
            self.assertFalse(any(ln.startswith("pack.") for ln in legacy), legacy)
            code, lines = run(manifest.replace('[pack]\n', '[pack]\nversion = "0.5.0"\n'))
            self.assertEqual(code, 0, lines)
            self.assertEqual(lines, legacy + ['pack.version = "0.5.0"  # pack:example'])
            meta = {}
            profile = cc.resolve_profile(project, pack_manifest=pack, meta=meta)[0]
            self.assertNotIn("pack", profile)
            self.assertEqual(meta, {"pack.version": ("0.5.0", "pack:example")})


class AsyncLandTest(unittest.TestCase):
    """#929 (#873 B1): the optional [land] table, conditional change operations and the land timing options."""
    EXTERNAL = GITHUB_MANIFEST.replace('name = "github"', 'name = "example"').replace(
        '[pack]\n', '[pack]\nmdstack_version = "v5.0.0"\n')
    ASYNC = EXTERNAL.replace('land = "supported"\n', 'land = "supported"\nland-status = "supported"\n') + \
        '\n[land]\nmode = "async"\nserializes = true\n'

    def run_resolve(self, manifest, project_text):
        with tempfile.TemporaryDirectory() as d:
            pack, project = os.path.join(d, "manifest.toml"), os.path.join(d, "crew.toml")
            with open(pack, "w") as f:
                f.write(manifest)
            with open(project, "w") as f:
                f.write(project_text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cc.main(["resolve", "--project", project, "--pack-manifest", pack])
            meta = {}
            cc.resolve_profile(project, pack_manifest=pack, meta=meta)
            return code, [ln.replace(d + os.sep, "") for ln in out.getvalue().splitlines()], meta

    def test_manifest_land_table(self):
        ok = (0, ["crew-config: OK (crew.toml)"])
        self.assertEqual(validate(GITHUB_MANIFEST), ok)  # no [land]: sync, unchanged manifest valid
        self.assertEqual(validate(GITHUB_MANIFEST + '\n[land]\nmode = "sync"\n'), ok)
        self.assertEqual(validate(self.ASYNC), ok)
        draft = self.ASYNC.replace('land = "supported"\n', 'land = "supported"\npublish = "supported"\n', 1)
        self.assertEqual(validate(draft + 'opens_draft = true\ntests_against_tip = true\n'), ok)
        native = self.ASYNC.replace('land-status = "supported"\n', 'land-status = "supported"\nread-landed = "supported"\n')
        self.assertEqual(validate(native + 'change_placeholder = "change"\nhead_guard = false\n[land.status]\n'
                                  'NOT_STARTED = "none"\nSUCCESS = "landed"\n'), ok)  # #1042
        self.assertEqual(validate(self.ASYNC + '[land.status]\n"MERGED (?P<revision>[0-9a-f]{40})" = "landed"\n'), ok)
        for text, expected in (
                (self.EXTERNAL + '\n[land]\nmode = "async"\n',
                 "crew.toml:land.mode: async needs change.land-status supported or emulated"),
                (self.ASYNC.replace('land-status = "supported"', 'land-status = "unsupported"'),
                 "crew.toml:land.mode: async needs change.land-status supported or emulated"),
                (self.ASYNC + 'opens_draft = true\n', "crew.toml:land.opens_draft: needs change.publish supported or emulated"),
                (GITHUB_MANIFEST + '\n[land]\nserializes = true\n', 'crew.toml:land.serializes: only valid with mode = "async"'),
                (GITHUB_MANIFEST + '\n[land]\nmode = "queued"\n',
                 "crew.toml:land.mode: unknown value 'queued' (expected one of: sync, async)"),
                (GITHUB_MANIFEST + '\n[land]\nretries = 2\n', "crew.toml:land.retries: unknown key"),
                (GITHUB_MANIFEST + '\n[land]\nserializes = "yes"\n', "crew.toml:land.serializes: expected boolean, got string"),
                (GITHUB_MANIFEST.replace('land = "supported"\n', 'land = "supported"\npublish = "maybe"\n'),
                 "crew.toml:capabilities.change.publish: expected supported, unsupported or emulated (<how>)"),
                (GITHUB_MANIFEST + '\n[land]\nhead_guard = false\n', 'crew.toml:land.head_guard: only valid with mode = "async"'),
                (GITHUB_MANIFEST + '\n[land]\nchange_placeholder = "change"\n',
                 'crew.toml:land.change_placeholder: only valid with mode = "async"'),
                (self.ASYNC + 'change_placeholder = "<change>"\n',
                 "crew.toml:land.change_placeholder: expected a placeholder name ([a-z][a-z0-9-]*, no angle brackets)"),
                (self.ASYNC + '[land.status]\nDONE = "merged"\n',
                 "crew.toml:land.status.DONE: unknown value 'merged' (expected one of: none, queued, landing, landed, failed)"),
                (self.ASYNC + '[land.status]\n"(" = "none"\n', "crew.toml:land.status: pattern '(' is not a regular expression "
                 "(missing ), unterminated subpattern at position 0)"),
                (self.ASYNC + '[land.status]\nSUCCESS = "landed"\n', "crew.toml:land.status: a landed pattern without a "
                 "(?P<revision>...) group needs change.read-landed supported or emulated")):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_stack_land_validator_cli_exit_codes(self):
        """#1605 review: the shipped `core/crew-config.py validate` process exits 0 on an accepted stack-land manifest
        and nonzero, naming the key, on each rejected one."""
        stack = GITHUB_MANIFEST.replace('land = "supported"\n', 'land = "supported"\nland-stack = "supported"\n'
                                        'stack-status = "supported"\n', 1)
        cases = ((stack + '\n[land]\nstack = true\nstack_tests_against_tip = true\n', 0, "crew-config: OK"),
                 (GITHUB_MANIFEST + '\n[land]\nstack = true\n', 1, "land.stack: needs change.land-stack"),
                 (stack.replace('stack-status = "supported"', 'stack-status = "unsupported"') + '\n[land]\nstack = true\n',
                  1, "land.stack: needs change.stack-status"),
                 (stack + '\n[land]\nstack_tests_against_tip = true\n', 1,
                  "land.stack_tests_against_tip: only valid with stack = true"))
        with tempfile.TemporaryDirectory() as d:
            for text, code, expected in cases:
                path = os.path.join(d, "manifest.toml")
                with open(path, "w") as f:
                    f.write(text)
                r = subprocess.run([sys.executable, os.path.join(ROOT, "core", "crew-config.py"), "validate", path],
                                   capture_output=True, text=True)
                self.assertEqual(r.returncode, code, r.stdout + r.stderr)
                self.assertIn(expected, r.stdout)

    def test_manifest_stack_land(self):
        """#1605: land.stack admits the atomic stack-land operation and its readback; the validator checks both."""
        ok = (0, ["crew-config: OK (crew.toml)"])
        stack = GITHUB_MANIFEST.replace('land = "supported"\n', 'land = "supported"\nland-stack = "supported"\n'
                                        'stack-status = "supported"\n', 1)
        self.assertEqual(validate(stack), ok)  # declared operations alone change nothing
        self.assertEqual(validate(stack + '\n[land]\nstack = true\n'), ok)  # sync individual lands plus a stack land
        self.assertEqual(validate(stack + '\n[land]\nstack = true\nstack_tests_against_tip = true\n'), ok)
        for text, expected in (
                (GITHUB_MANIFEST + '\n[land]\nstack = true\n',
                 "crew.toml:land.stack: needs change.land-stack supported or emulated"),
                (stack.replace('stack-status = "supported"', 'stack-status = "unsupported"') + '\n[land]\nstack = true\n',
                 "crew.toml:land.stack: needs change.stack-status supported or emulated"),
                (stack + '\n[land]\nstack_tests_against_tip = true\n',
                 "crew.toml:land.stack_tests_against_tip: only valid with stack = true"),
                (stack + '\n[land]\nstack = "yes"\n', "crew.toml:land.stack: expected boolean, got string")):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_manifest_per_change_stack_land(self):
        """#1722: per-change stack readback needs land-status, not stack-status; a sync stack binding may declare its
        change placeholder, and status only for per-change readback; per-change refuses the combined-tip claim."""
        ok = (0, ["crew-config: OK (crew.toml)"])
        caps = GITHUB_MANIFEST.replace('land = "supported"\n', 'land = "supported"\nland-stack = "supported"\n'
                                       'land-status = "supported"\nread-revision-id = "supported"\n', 1)
        per = caps + '\n[land]\nstack = true\nstack_status = "per-change"\nchange_placeholder = "rev"\n'
        self.assertEqual(validate(per), ok)
        self.assertEqual(validate(per + '[land.status]\n"MERGED (?P<revision>[0-9a-f]{40})" = "landed"\n'), ok)
        legacy = caps.replace('land-status = "supported"', 'stack-status = "supported"')
        self.assertEqual(validate(legacy + '\n[land]\nstack = true\nchange_placeholder = "rev"\n'), ok)
        for text, expected in (
                (per.replace('land-status = "supported"', 'land-status = "unsupported"'),
                 "crew.toml:land.stack: needs change.land-status supported or emulated"),
                (caps + '\n[land]\nstack = true\n', "crew.toml:land.stack: needs change.stack-status supported or emulated"),
                (per + 'stack_tests_against_tip = true\n', "crew.toml:land.stack_tests_against_tip: per-change readback "
                 "names no combined-stack check; expected false"),
                (caps + '\n[land]\nstack_status = "per-change"\n', "crew.toml:land.stack_status: only valid with stack = true"),
                (per.replace('"per-change"', '"each"'),
                 "crew.toml:land.stack_status: unknown value 'each' (expected one of: stack, per-change)"),
                (legacy + '\n[land]\nstack = true\n[land.status]\nNEW = "none"\n',
                 'crew.toml:land.status: only valid with mode = "async"'),
                (GITHUB_MANIFEST + '\n[land]\nchange_placeholder = "rev"\n',
                 'crew.toml:land.change_placeholder: only valid with mode = "async"')):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_manifest_stack_separator(self):
        """#1956: land.stack_separator is " " or ",", and only with stack = true."""
        ok = (0, ["crew-config: OK (crew.toml)"])
        caps = GITHUB_MANIFEST.replace('land = "supported"\n', 'land = "supported"\nland-stack = "supported"\n'
                                       'stack-status = "supported"\n', 1)
        for sep in ('" "', '","'):
            self.assertEqual(validate(caps + '\n[land]\nstack = true\nstack_separator = %s\n' % sep), ok)
        for text, expected in (
                (caps + '\n[land]\nstack = true\nstack_separator = ";"\n',
                 "crew.toml:land.stack_separator: unknown value ';' (expected one of:  , ,)"),
                (caps + '\n[land]\nstack_separator = ","\n',
                 "crew.toml:land.stack_separator: only valid with stack = true")):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_profile_may_declare_conditional_operations(self):
        text = VALID.replace('[backends.change]\nname = "github"',
                             '[backends.change]\nname = "github"\ncapabilities = { publish = "unsupported", '
                             'land-status = "emulated (poll the queue page)" }')
        self.assertEqual(validate(text), (0, ["crew-config: OK (crew.toml)"]))

    def test_resolve_async_metadata_and_refusals(self):
        bound = VALID.replace('[backends.change]\nname = "github"', '[backends.change]\nname = "example"')
        code, legacy, meta = self.run_resolve(self.EXTERNAL, bound)
        self.assertEqual((code, meta), (0, {}), legacy)
        self.assertFalse(any(ln.startswith("land.") for ln in legacy), legacy)
        code, lines, meta = self.run_resolve(self.ASYNC, bound)
        self.assertEqual(code, 0, lines)
        self.assertIn('backends.change.capabilities.land-status = "supported"  # external-pack', lines)
        self.assertEqual(lines[-2:], ['land.mode = "async"  # external-pack', 'land.serializes = true  # external-pack'])
        self.assertEqual(meta, {"land.mode": ("async", "external-pack"), "land.serializes": (True, "external-pack")})
        overridden = bound.replace('name = "example"', 'name = "example"\ncapabilities = { land-status = "unsupported" }', 1)
        grok = bound.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "grok-bot"')
        for text, expected in ((overridden, "manifest.toml:land.mode: async needs change.land-status supported or emulated"),
                               (grok, "manifest.toml:land.mode: runtime grok-bot has no async land binding; expected sync")):
            code, lines, _ = self.run_resolve(self.ASYNC, text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_session_runtime_accepts_async_land(self):
        """#1351: the session runtime has an async land binding, so resolve accepts the full [land] table there."""
        bound = VALID.replace('[backends.change]\nname = "github"', '[backends.change]\nname = "example"').replace(
            'name = "tmux"\noptions = { builders = 3 }', 'name = "session"\noptions = { builders = 2, reviewers = 1 }')
        manifest = self.ASYNC + 'change_placeholder = "change"\n[land.status]\n"^MERGED (?P<revision>[0-9a-f]{40})$" = ' \
            '"landed"\n"^FAILED" = "failed"\n'
        code, lines, meta = self.run_resolve(manifest, bound)
        self.assertEqual(code, 0, lines)
        self.assertEqual(meta["land.mode"], ("async", "external-pack"))
        self.assertEqual(meta["land.change_placeholder"], ("change", "external-pack"))
        self.assertEqual(meta["land.status"][0], {"^MERGED (?P<revision>[0-9a-f]{40})$": "landed", "^FAILED": "failed"})
        for key in ('land.mode = "async"', 'land.change_placeholder = "change"', "land.status = "):
            self.assertTrue(any(ln.startswith(key) for ln in lines), (key, lines))

    def test_land_timing_options(self):
        code, lines = resolve(VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('runtime.options.land_poll_interval = 60  # core', lines)
        self.assertIn('runtime.options.land_timeout = 3600  # core', lines)
        ok = "land_poll_interval = 30, land_timeout = 30"
        self.assertEqual(validate(VALID.replace("builders = 3", ok))[0], 0)
        for opts, expected in (("land_poll_interval = 0", "runtime.options.land_poll_interval: must be >= 1, got 0"),
                               ("land_timeout = -5", "runtime.options.land_timeout: must be >= 1, got -5"),
                               ('land_timeout = "1h"', "runtime.options.land_timeout: expected integer, got string"),
                               ("land_timeout = 59", "runtime.options.land_timeout: must be >= land_poll_interval (60), got 59"),
                               ("land_poll_interval = 120, land_timeout = 90",
                                "runtime.options.land_timeout: must be >= land_poll_interval (120), got 90")):
            code, lines = validate(VALID.replace("builders = 3", opts))
            self.assertEqual(code, 1, lines)
            self.assertIn("crew.toml:" + expected, lines)


class ClassifyConcernTest(unittest.TestCase):
    """#961 (#880 B1): the optional classify concern, its backend-map command and the resolve refusals."""
    EXTERNAL = AsyncLandTest.EXTERNAL + '\n[capabilities.classify]\nsensitive = "supported"\n'
    BOUND = VALID.replace('[identities]', '[backends.classify]\nname = "example"\n\n[identities]') + 'pack = "pack"\n'
    COMMAND = 'policy classify --stdin --json'

    def run_resolve(self, project_text, manifest=None, backend_map=None):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pack", "render", "backends"))
            for path, text in (("crew.toml", project_text), ("pack/manifest.toml", manifest or self.EXTERNAL),
                               ("pack/render/backends/example.toml", backend_map)):
                if text is not None:
                    with open(os.path.join(d, path), "w") as f:
                        f.write(text)
            project, out = os.path.join(d, "crew.toml"), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cc.main(["resolve", "--project", project])
            meta = {}
            cc.resolve_profile(project, meta=meta)
            return code, [ln.replace(d + os.sep, "") for ln in out.getvalue().splitlines()], meta

    def test_not_an_op_token_concern(self):
        self.assertNotIn("classify", cc.OPERATIONS)  # bootstrap, a team's pack and the renderer's op set skip it
        self.assertEqual(cc.CONCERNS["classify"], ["sensitive"])

    def test_manifest_and_profile_schema(self):
        ok = (0, ["crew-config: OK (crew.toml)"])
        self.assertEqual(validate(GITHUB_MANIFEST), ok)  # no [capabilities.classify]: built-in only
        self.assertEqual(validate(self.EXTERNAL), ok)
        self.assertEqual(validate(VALID.replace('[identities]', '[backends.classify]\nname = "github"\n'
                                                'capabilities = { sensitive = "unsupported" }\n\n[identities]')), ok)
        for text, expected in (
                (self.EXTERNAL.replace('sensitive = "supported"', 'sensitive = "emulated (run both)"'),
                 "crew.toml:capabilities.classify.sensitive: expected supported or unsupported "
                 "(an extension runs or does not)"),
                (self.EXTERNAL.replace('sensitive = "supported"', 'content = "supported"'),
                 "crew.toml:capabilities.classify.content: unknown key"),
                (self.EXTERNAL.replace('sensitive = "supported"\n', ''),
                 "crew.toml:capabilities.classify.sensitive: missing required key"),
                (VALID.replace('[identities]', '[backends.classify]\nname = "github"\n'
                               'capabilities = { sensitive = "emulated (x)" }\n\n[identities]'),
                 "crew.toml:backends.classify.capabilities.sensitive: expected supported or unsupported "
                 "(an extension runs or does not)"),
                (VALID.replace('[identities]', '[backends.classify]\nname = "nobody"\n\n[identities]'),
                 "crew.toml:backends.classify.name: unknown value 'nobody' (expected one of: github)")):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_undeclared_is_built_in_only(self):
        code, lines = resolve(VALID)
        self.assertEqual(code, 0, lines)
        self.assertFalse(any("classify" in ln for ln in lines), lines)
        code, lines, meta = self.run_resolve(self.BOUND.replace('[backends.classify]\nname = "example"\n', ''))
        self.assertEqual((code, meta), (0, {}), lines)

    def test_resolve_prints_bound_command(self):
        code, lines, meta = self.run_resolve(self.BOUND, backend_map='[classify]\nsensitive = "%s"\n' % self.COMMAND)
        self.assertEqual(code, 0, lines)
        self.assertIn('backends.classify.capabilities.sensitive = "supported"  # external-pack', lines)
        self.assertEqual(lines[-1], 'classify.sensitive = "%s"  # pack:example' % self.COMMAND)
        self.assertEqual(meta, {"classify.sensitive": (self.COMMAND, "pack:example")})

    def test_input_redirection_is_not_a_placeholder(self):
        command = "policy classify --json < paths.txt"
        code, lines, meta = self.run_resolve(self.BOUND, backend_map='[classify]\nsensitive = "%s"\n' % command)
        self.assertEqual((code, meta), (0, {"classify.sensitive": (command, "pack:example")}), lines)

    def test_resolve_refusals(self):
        good = '[classify]\nsensitive = "%s"\n' % self.COMMAND
        for project, backend_map, expected in (
                (VALID.replace('[identities]', '[backends.classify]\nname = "github"\n\n[identities]'), None,
                 "crew.toml:backends.classify.name: binds github, whose classify.sensitive is undeclared"),
                (self.BOUND.replace('name = "example"\n', 'name = "example"\n'
                                    'capabilities = { sensitive = "unsupported" }\n', 1), good,
                 "crew.toml:backends.classify.name: binds example, whose classify.sensitive is unsupported"),
                (self.BOUND, None, "templates/backends/example.toml:classify.sensitive: "
                 "no command for the example sensitivity extension"),  # no overlay: the bundled map
                (self.BOUND, '[change]\nopen = "x"\n', "pack/render/backends/example.toml:classify.sensitive: "
                 "no command for the example sensitivity extension"),
                (self.BOUND, '[classify]\nsensitive = "<cli> policy classify"\n',
                 "pack/render/backends/example.toml:classify.sensitive: unfilled placeholder <cli>"),
                (self.BOUND, '[classify]\nsensitive = "<op:change.cli-name> policy classify"\n',
                 "pack/render/backends/example.toml:classify.sensitive: unfilled placeholder <op:change.cli-name>")):
            code, lines, meta = self.run_resolve(project, backend_map=backend_map)
            self.assertEqual((code, meta), (1, {}), lines)
            self.assertTrue(any(expected in ln for ln in lines), lines)


class SensitiveExtensionTest(unittest.TestCase):
    """#962 (#880 B2): `sensitive` unions a bound extension's matches with the built-in rules, fail-closed."""
    OK = '{"label": null, "matches": {}}'

    def run_sensitive(self, paths, reply=OK, code=0, project=ClassifyConcernTest.BOUND, extra="", diff=False):
        """(exit, parsed stdout or None, stdin the extension saw or None) for one `sensitive` run."""
        with tempfile.TemporaryDirectory() as d:
            seen, out_file = os.path.join(d, "seen.txt"), os.path.join(d, "reply.json")
            command = "cat > '%s'; cat '%s'; exit %d" % (seen, out_file, code)
            os.makedirs(os.path.join(d, "pack", "render", "backends"))
            for path, text in (("crew.toml", project + extra), ("pack/manifest.toml", ClassifyConcernTest.EXTERNAL),
                               ("pack/render/backends/example.toml", "[classify]\nsensitive = %s\n" % json.dumps(command)),
                               ("reply.json", reply)):
                with open(os.path.join(d, path), "w") as f:
                    f.write(text)
            out = io.StringIO()
            stdin = io.TextIOWrapper(io.BytesIO(paths.encode())) if diff else io.StringIO(paths)
            with patch("sys.stdin", stdin), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                status = cc.main(["sensitive", "--project", os.path.join(d, "crew.toml")] + ["--diff"] * diff)
            if os.path.exists(seen):
                with open(seen) as f:
                    stdin = f.read()
            else:
                stdin = None
            return status, json.loads(out.getvalue()) if out.getvalue() else None, stdin

    def test_no_extension_output_unchanged(self):
        unbound = ClassifyConcernTest.BOUND.replace('[backends.classify]\nname = "example"\n', '')
        for paths, expected in (("auth/login.py\n", {"label": "crew:sensitive", "matches": {"auth/login.py": ["auth/**"]}}),
                                ("README.md\n", {"label": None, "matches": {}})):
            self.assertEqual(self.run_sensitive(paths, project=unbound), (0, expected, None))

    def test_extension_negative_cannot_clear_built_in(self):
        code, result, stdin = self.run_sensitive("auth/login.py\nREADME.md\n")
        self.assertEqual((code, stdin), (0, "auth/login.py\nREADME.md\n"))  # the same stdin bytes
        self.assertEqual(result, {"label": "crew:sensitive", "matches": {"auth/login.py": ["auth/**"]}, "errors": []})
        self.assertEqual(self.run_sensitive("README.md\n")[1], {"label": None, "matches": {}, "errors": []})

    def test_extension_only_positive_and_union(self):
        reply = '{"label": "crew:sensitive", "matches": {"README.md": ["owners"], "auth/login.py": ["iam"]}, "x": 1}'
        code, result, _ = self.run_sensitive("auth/login.py\nREADME.md\n", reply)
        self.assertEqual((code, result), (0, {"label": "crew:sensitive", "errors": [], "matches": {
            "README.md": ["example:owners"], "auth/login.py": ["auth/**", "example:iam"]}}))
        self.assertEqual(list(result["matches"]), ["README.md", "auth/login.py"])

    def test_shared_content_records(self):
        reply = json.dumps({"label": "crew:sensitive", "matches": {}, "content": [
            {"rule": "b", "path": "z.md", "side": "new", "line": 3},
            {"rule": "a", "path": "a.md", "side": "old", "line": 12}]})
        code, result, _ = self.run_sensitive("a.md\nz.md\n", reply)
        self.assertEqual((code, result), (0, {"label": "crew:sensitive", "matches": {}, "errors": [], "content": [
            {"rule": "example:a", "path": "a.md", "side": "old", "line": 12},
            {"rule": "example:b", "path": "z.md", "side": "new", "line": 3}]}))
        self.assertNotIn("content", self.run_sensitive("a.md\n", '{"label": null, "matches": {}, "content": []}')[1])

    def test_failed_or_malformed_extension_reads_sensitive(self):
        record = '{"rule": "r", "path": "a.md", "side": "%s", "line": %s}'
        for reply, code, cause in (
                (self.OK, 2, "exit 2"),
                ("not json", 0, "stdout is not one JSON object"),
                ("", 0, "stdout is not one JSON object"),
                ('[{"label": null}]', 0, "stdout is not one JSON object"),
                ('{"matches": {}}', 0, "label is not null or crew:sensitive"),
                ('{"label": "sensitive", "matches": {}}', 0, "label is not null or crew:sensitive"),
                ('{"label": null}', 0, "matches is not an object of path to rule-name lists"),
                ('{"label": null, "matches": {"a.md": "owners"}}', 0, "matches is not an object of path to rule-name lists"),
                ('{"label": null, "matches": {"a.md": []}}', 0, "matches is not an object of path to rule-name lists"),
                ('{"label": null, "matches": {}, "content": {}}', 0, "malformed content record"),
                ('{"label": null, "matches": {}, "content": [%s]}' % (record % ("both", 1)), 0, "malformed content record"),
                ('{"label": null, "matches": {}, "content": [%s]}' % (record % ("new", 0)), 0, "malformed content record"),
                ('{"label": null, "matches": {}, "content": [%s]}' % (record % ("new", "true")), 0, "malformed content record"),
                ('{"label": "crew:sensitive", "matches": {}}', 0, "label crew:sensitive with no match to record")):
            with self.subTest(reply=reply, code=code):
                status, result, _ = self.run_sensitive("README.md\n", reply, code)
                self.assertEqual((status, result), (0, {"label": "crew:sensitive", "matches": {},
                                                        "errors": ["example: " + cause]}))

    def test_failure_keeps_built_in_matches_and_drops_extension_ones(self):
        reply = '{"label": "crew:sensitive", "matches": {"README.md": ["owners"]}}'
        code, result, _ = self.run_sensitive("auth/login.py\nREADME.md\n", reply, 1)
        self.assertEqual(result, {"label": "crew:sensitive", "matches": {"auth/login.py": ["auth/**"]},
                                  "errors": ["example: exit 1"]})

    def test_timeout_reads_sensitive(self):
        with patch.object(cc, "EXTENSION_TIMEOUT", 1):
            self.assertEqual(cc.run_extension("example", "exec sleep 5", b""), ({}, [], "example: timed out after 1s"))

    def test_diff_input_unions_content_records(self):
        rule = '\n[[sensitive.content]]\nname = "m"\npattern = "merge gate"\nreason = "r"\n'
        diff = git_diff({"docs/a.md": "one\n"}, {"docs/a.md": "one\nthe merge gate\n"})
        reply = json.dumps({"label": "crew:sensitive", "matches": {}, "content": [
            {"rule": "x", "path": "docs/a.md", "side": "new", "line": 1}]})
        code, result, stdin = self.run_sensitive(diff, reply, extra=rule, diff=True)
        self.assertEqual((code, stdin), (0, diff))  # the extension reads the same diff bytes
        self.assertEqual(result, {"label": "crew:sensitive", "matches": {}, "errors": [], "content": [
            {"rule": "example:x", "path": "docs/a.md", "side": "new", "line": 1},
            {"rule": "m", "path": "docs/a.md", "side": "new", "line": 2}]})
        self.assertEqual(self.run_sensitive("not a diff\n", extra=rule, diff=True), (3, None, None))

    def test_invalid_config_and_content_rules_run_no_extension(self):
        for extra, status in (('\n[sensitive]\npaths = [1]\n', 1),
                              ('\n[[sensitive.content]]\nname = "m"\npattern = "merge"\nreason = "r"\n', 3)):
            self.assertEqual(self.run_sensitive("README.md\n", extra=extra), (status, None, None))


class UpdateStrategyTest(unittest.TestCase):
    """#951 (#874 B1): the optional [strategy] table; rebase only with retained prior heads, merge by default."""
    EXTERNAL = AsyncLandTest.EXTERNAL
    REBASE = EXTERNAL + '\n[strategy]\nupdate_from_base = "rebase"\nretains_prior_heads = true\n'
    run_resolve = AsyncLandTest.run_resolve

    def test_manifest_strategy_table(self):
        ok = (0, ["crew-config: OK (crew.toml)"])
        self.assertEqual(validate(GITHUB_MANIFEST), ok)  # no [strategy]: merge, unchanged manifest valid
        self.assertEqual(validate(GITHUB_MANIFEST + '\n[strategy]\nupdate_from_base = "merge"\n'), ok)
        self.assertEqual(validate(GITHUB_MANIFEST + '\n[strategy]\nretains_prior_heads = false\n'), ok)
        self.assertEqual(validate(self.REBASE), ok)
        for text, expected in (
                (self.EXTERNAL + '\n[strategy]\nupdate_from_base = "rebase"\n',
                 "crew.toml:strategy.update_from_base: rebase needs retains_prior_heads = true"),
                (self.REBASE.replace("retains_prior_heads = true", "retains_prior_heads = false"),
                 "crew.toml:strategy.update_from_base: rebase needs retains_prior_heads = true"),
                (GITHUB_MANIFEST + '\n[strategy]\nretains_prior_heads = true\n',
                 'crew.toml:strategy.retains_prior_heads: only valid with update_from_base = "rebase"'),
                (GITHUB_MANIFEST + '\n[strategy]\nupdate_from_base = "squash"\n',
                 "crew.toml:strategy.update_from_base: unknown value 'squash' (expected one of: merge, rebase)"),
                (GITHUB_MANIFEST + '\n[strategy]\nforce_push = true\n', "crew.toml:strategy.force_push: unknown key"),
                (self.REBASE.replace("retains_prior_heads = true", 'retains_prior_heads = "yes"'),
                 "crew.toml:strategy.retains_prior_heads: expected boolean, got string")):
            code, lines = validate(text)
            self.assertEqual(code, 1, lines)
            self.assertIn(expected, lines)

    def test_resolve_strategy_metadata_and_refusals(self):
        bound = VALID.replace('[backends.change]\nname = "github"', '[backends.change]\nname = "example"')
        code, legacy, meta = self.run_resolve(self.EXTERNAL, bound)
        self.assertEqual((code, meta), (0, {}), legacy)  # undeclared: merge, resolve output unchanged
        self.assertFalse(any(ln.startswith("strategy.") for ln in legacy), legacy)
        code, lines, meta = self.run_resolve(self.REBASE, bound)
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-2:], ['strategy.update_from_base = "rebase"  # external-pack',
                                      'strategy.retains_prior_heads = true  # external-pack'])
        self.assertEqual(meta, {"strategy.update_from_base": ("rebase", "external-pack"),
                                "strategy.retains_prior_heads": (True, "external-pack")})
        code, lines, _ = self.run_resolve(self.EXTERNAL + '\n[strategy]\nupdate_from_base = "rebase"\n', bound)
        self.assertEqual(code, 1, lines)
        self.assertIn("manifest.toml:strategy.update_from_base: rebase needs retains_prior_heads = true", lines)

    def test_resolve_refuses_builtin_pack_rebase_without_retained_heads(self):
        code, lines = resolve_with_packs(VALID, GITHUB_MANIFEST + '\n[strategy]\nupdate_from_base = "rebase"\n')
        self.assertEqual(code, 1, lines)
        self.assertTrue(any(ln.endswith("strategy.update_from_base: rebase needs retains_prior_heads = true")
                            for ln in lines), lines)


class ReleasePairingTest(unittest.TestCase):
    """#910: with an external pack, [release] and a pack-bound [backends.release] bind together (real defaults)."""
    TABLE = '[release]\nchangelog = "CHANGELOG.md"\n'
    ROW = '[backends.release]\nname = "example"\n'

    def resolve(self, org, manifest=None, project=None):
        manifest = manifest or GITHUB_MANIFEST.replace('name = "github"', 'name = "example"').replace(
            '[pack]\n', '[pack]\nmdstack_version = "v1.0.0"\n')
        with tempfile.TemporaryDirectory() as d:
            for name, text in (("crew.toml", project or VALID.replace('[backends.release]\nname = "github"', "")),
                               ("profile.toml", org), ("manifest.toml", manifest)):
                with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                    f.write(text)
            problems = cc.resolve_profile(os.path.join(d, "crew.toml"), os.path.join(d, "profile.toml"))[2]
        return [p.replace(d + os.sep, "") for p in problems]

    def test_table_without_pack_row_fails_naming_backends_release(self):
        self.assertEqual(self.resolve(self.TABLE), [
            'profile.toml:backends.release: [release] table here, but [backends.release] is the bundled default '
            '(%s, name = "github") while pack example declares release capabilities (manifest.toml); add '
            '[backends.release] name = "example" to profile.toml (docs/interfaces.md)' % cc.DEFAULT_PROFILE])

    def test_pack_row_without_table_fails_naming_release(self):
        self.assertEqual(self.resolve(self.ROW), [
            "profile.toml:release: [backends.release] binds pack example here, but no layer sets a [release] "
            "table; add [release] to profile.toml (docs/interfaces.md)"])
        self.assertEqual(self.resolve("", project=VALID.replace('[backends.release]\nname = "github"', self.ROW)), [
            "crew.toml:release: [backends.release] binds pack example here, but no layer sets a [release] "
            "table; add [release] to crew.toml or the pack's profile.toml (docs/interfaces.md)"])

    def test_both_or_neither_resolve(self):
        self.assertEqual(self.resolve(self.TABLE + self.ROW), [])
        self.assertEqual(self.resolve(""), [])

    def test_unrelated_pack_and_legacy_github_unchanged(self):
        no_release = re.sub(r"\n\[capabilities\.release\][^[]*", "\n", GITHUB_MANIFEST).replace(
            'name = "github"', 'name = "example"').replace('[pack]\n', '[pack]\nmdstack_version = "v1.0.0"\n')
        self.assertEqual(self.resolve(self.TABLE, manifest=no_release), [])
        self.assertEqual(self.resolve(self.TABLE, project=VALID), [])
        self.assertEqual(self.resolve(self.TABLE + '[backends.release]\nname = "github"\n'), [])
        self.assertTrue(self.resolve(self.TABLE + self.ROW + 'capabilities = { approve-check = "unsupported" }\n'))
        github = GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nmdstack_version = "v1.0.0"\n')
        self.assertEqual(self.resolve("", manifest=github), [])  # an external pack named github: default row only


# --- host inventory and project affinity (20.2, #204) ---
HOSTS = """
[hosts.host-a]
primary = true
capabilities = { os = "macos", arch = "arm64", engines = ["claude-code", "codex"] }
max_runs = 2

[hosts.host-b]
capabilities = { os = "linux", arch = "x86_64", devices = ["ios-simulator"], engines = ["codex"] }
max_runs = 4
roles = ["reviewer"]
root = "/srv/crew"

[placement]
hosts = ["host-a", "host-b"]

[[placement.rules]]
role = "reviewer"
pass = "validate"
paths = ["ios/**"]
needs = { devices = ["ios-simulator"] }
"""
OK = (0, ["crew-config: OK (crew.toml)"])


class HostInventoryTest(unittest.TestCase):
    assertFails = ValidateTest.assertFails

    def test_inventory_validates_and_is_optional(self):
        self.assertEqual(validate(VALID + HOSTS), OK)
        self.assertEqual(validate(VALID), OK)

    def test_doc_example_validates(self):
        doc = read(os.path.join(ROOT, "docs", "profile.md")).split("### `[hosts.<name>]` and `[placement]`", 1)[1]
        self.assertEqual(validate(VALID + re.search(r"```toml\n(.*?)```", doc, re.S).group(1)), OK)

    def test_secret_pattern_rejected(self):
        token = "ghp_" + "B" * 36  # built at runtime so the repo never holds a token
        code, lines = validate(VALID + HOSTS.replace('root = "/srv/crew"', 'root = "/srv/%s"' % token))
        self.assertEqual(code, 1)
        self.assertIn("crew.toml:hosts.host-b.root: token-shaped value (GitHub token (ghp_/gho_/ghu_/ghs_/ghr_)); "
                      "refer to credentials by mechanism", lines)
        self.assertFails(VALID + HOSTS.replace('root = "/srv/crew"', 'toolchain_bin = "ssh://ops:" "hunter2@host-b/bin"'
                                               .replace('" "', "")),
                         "crew.toml:hosts.host-b.toolchain_bin: token-shaped value (URL with embedded credentials); "
                         "refer to credentials by mechanism")

    def test_host_named_by_overlay_name_only(self):
        for bad in ["10.0.0.7", "fd7a::7", "ops@host-b", "host-b:22", "Host_B"]:
            text = HOSTS.replace("[hosts.host-b]", '[hosts."%s"]' % bad).replace('"host-b"', '"%s"' % bad)
            self.assertFails(VALID + text, "crew.toml:hosts.%s: expected an overlay network name ([a-z0-9-], "
                             "1-63 characters); no IP literal, user@ or :port" % bad)

    def test_host_address_is_a_dns_name(self):
        """#1034: a dotted DNS `address` beside the short label validates; an IP, user@, :port or bare label does not."""
        for good in ["host-b.region.example.com", "host-b.tailnet.ts.net"]:
            self.assertEqual(validate(VALID + HOSTS.replace('root = "/srv/crew"', 'address = "%s"' % good)), OK)
        for bad in ["10.0.0.7", "fd7a::7", "ops@host-b.example.com", "host-b.example.com:22", "Host-B.example.com",
                    "host-b", "host-b.example.com."]:
            self.assertFails(VALID + HOSTS.replace('root = "/srv/crew"', 'address = "%s"' % bad),
                             "crew.toml:hosts.host-b.address: expected a dotted DNS name ([a-z0-9-] labels); "
                             "no IP literal, user@ or :port")

    def test_unknown_capability(self):
        self.assertFails(VALID + HOSTS.replace('arch = "arm64",', 'arch = "arm64", gpu = "a100",'),
                         "crew.toml:hosts.host-a.capabilities.gpu: unknown key")
        self.assertFails(VALID + HOSTS.replace('devices = ["ios-simulator"], engines', 'devices = ["usb-camera"], engines'),
                         "crew.toml:hosts.host-b.capabilities.devices[0]: unknown value 'usb-camera' (expected one of: "
                         "ios-simulator, ios-device, android-emulator, android-device)")
        self.assertFails(VALID + HOSTS.replace('os = "linux"', 'os = "windows"'),
                         "crew.toml:hosts.host-b.capabilities.os: unknown value 'windows' (expected one of: linux, macos)")
        self.assertFails(VALID + HOSTS.replace('engines = ["codex"]', 'engines = ["unknown"]'),
                         "crew.toml:hosts.host-b.capabilities.engines[0]: unknown value 'unknown' "
                         "(expected one of: claude-code, codex, muse, opencode, pi, cursor)")
        self.assertFails(VALID + HOSTS.replace('needs = { devices', 'needs = { gpu = "a100", devices'),
                         "crew.toml:placement.rules[0].needs.gpu: unknown key")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", 'max_runs = 4\nip = "10.0.0.7"'),
                         "crew.toml:hosts.host-b.ip: unknown key")

    def test_connect(self):
        connect = 'max_runs = 4\nconnect = { alias = "b", transport = "mosh", proxy = "p %h %p", options = ["-v"] }'
        self.assertEqual(validate(VALID + HOSTS.replace("max_runs = 4", connect)), OK)
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", connect.replace('"mosh"', '"telnet"')),
                         "crew.toml:hosts.host-b.connect.transport: unknown value 'telnet' (expected one of: ssh, mosh, et)")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", connect.replace('"mosh"', '"et"')),
                         "crew.toml:hosts.host-b.connect.proxy: et takes its ProxyCommand from your SSH config; set "
                         "proxy only for ssh or mosh")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", connect.replace('"b"', '"B.x"')),
                         "crew.toml:hosts.host-b.connect.alias: expected [a-z0-9-], 1-63 characters")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", connect.replace('"b"', '"host-a"')),
                         "crew.toml:hosts: connect alias 'host-a' names more than one host")
        self.assertEqual(validate(VALID + HOSTS.replace("max_runs = 4", connect.replace('"b"', '"host-b"'))), OK)
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", 'max_runs = 4\nconnect = { port = 22 }'),
                         "crew.toml:hosts.host-b.connect.port: unknown key")

    def test_required_keys_and_types(self):
        self.assertFails(VALID + HOSTS.replace("max_runs = 4\n", ""), "crew.toml:hosts.host-b.max_runs: missing required key")
        self.assertFails(VALID + HOSTS.replace('os = "linux", ', ""), "crew.toml:hosts.host-b.capabilities.os: missing required key")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", "max_runs = 0"), "crew.toml:hosts.host-b.max_runs: must be >= 1, got 0")
        self.assertFails(VALID + HOSTS.replace("primary = true", 'primary = "yes"'),
                         "crew.toml:hosts.host-a.primary: expected boolean, got string")

    def test_exactly_one_primary(self):
        self.assertFails(VALID + HOSTS.replace("primary = true\n", ""),
                         "crew.toml:hosts: expected exactly one host with primary = true, got 0")
        self.assertFails(VALID + HOSTS.replace("max_runs = 4", "max_runs = 4\nprimary = true"),
                         "crew.toml:hosts: expected exactly one host with primary = true, got 2")

    def test_placement(self):
        self.assertFails(VALID + '[placement]\nhosts = ["host-a"]\n', "crew.toml:placement: needs a [hosts] table")
        self.assertFails(VALID + HOSTS.replace('hosts = ["host-a", "host-b"]', 'hosts = ["host-a", "host-c"]'),
                         "crew.toml:placement.hosts[1]: names no host in [hosts]: 'host-c'")
        self.assertFails(VALID + HOSTS.replace('roles = ["reviewer"]', 'roles = ["coordinator"]'),
                         "crew.toml:hosts.host-b.roles[0]: unknown value 'coordinator' (expected one of: builder, reviewer)")
        self.assertFails(VALID + HOSTS.replace('hosts = ["host-a", "host-b"]', 'hosts = ["host-b"]'),
                         "crew.toml:placement.hosts: no host here takes role builder (default: the primary host)")
        no_placement = HOSTS.split("[placement]")[0]
        self.assertEqual(validate(VALID + no_placement), OK)
        self.assertFails(VALID + no_placement.replace("max_runs = 2", 'max_runs = 2\nroles = ["builder"]'),
                         "crew.toml:placement.hosts: no host here takes role reviewer (default: the primary host)")

    def test_rule_needs_and_pass(self):
        self.assertFails(VALID + HOSTS.replace('needs = { devices = ["ios-simulator"] }', 'needs = { devices = ["android-emulator"] }'),
                         "crew.toml:placement.rules[0].needs: no host taking role reviewer meets these needs")
        self.assertFails(VALID + HOSTS.replace('role = "reviewer"\npass = "validate"', 'role = "builder"'),
                         "crew.toml:placement.rules[0].needs: no host taking role builder meets these needs")
        self.assertEqual(validate(VALID + HOSTS.replace('needs = { devices', 'needs = { os = "linux", arch = "x86_64", devices')), OK)
        self.assertFails(VALID + HOSTS.replace('pass = "validate"', 'pass = "land"'),
                         "crew.toml:placement.rules[0].pass: unknown value 'land' (expected one of: review, validate)")
        self.assertFails(VALID + HOSTS.replace('paths = ["ios/**"]\n', "").replace('needs = { devices = ["ios-simulator"] }\n', ""),
                         "crew.toml:placement.rules[0].needs: missing required key")

    def test_forge_less_host(self):
        runner = '[hosts.host-c]\nforge = false\ncapabilities = { os = "linux", arch = "x86_64" }\nmax_runs = 3\n'
        self.assertEqual(validate(VALID + HOSTS + runner), OK)
        self.assertEqual(validate(VALID + HOSTS + runner.replace("max_runs = 3", "max_runs = 3\nroles = []")), OK)
        self.assertFails(VALID + HOSTS + runner.replace("forge = false", 'forge = "no"'),
                         "crew.toml:hosts.host-c.forge: expected boolean, got string")
        self.assertFails(VALID + HOSTS + runner.replace("forge = false", ""),
                         "crew.toml:hosts.host-c.capabilities.engines: missing required key")
        self.assertFails(VALID + HOSTS + runner.replace("max_runs = 3", "max_runs = 3\nprimary = true"),
                         "crew.toml:hosts.host-c.forge: a forge-less host cannot be the primary")

    def test_host_checkout_command(self):
        """#1035: checkout = "command" on any host, forge-less or not; #1723: the primary too."""
        runner = '[hosts.host-c]\nforge = false\ncapabilities = { os = "linux", arch = "x86_64" }\nmax_runs = 3\n'
        self.assertEqual(validate(VALID + HOSTS + runner + 'checkout = "command"\n'), OK)
        self.assertEqual(validate(VALID + HOSTS + runner + 'checkout = "mirror"\n'), OK)
        self.assertFails(VALID + HOSTS + runner + 'checkout = "sl clone"\n',
                         "crew.toml:hosts.host-c.checkout: unknown value 'sl clone' (expected one of: mirror, command)")
        self.assertEqual(validate(VALID + HOSTS.replace("primary = true", 'primary = true\ncheckout = "command"', 1)), OK)
        self.assertFails(VALID + HOSTS + runner.replace("max_runs = 3", 'max_runs = 3\nroles = ["reviewer"]'),
                         "crew.toml:hosts.host-c.roles: a forge-less host takes runner jobs only; expected no roles")
        self.assertFails(VALID + HOSTS.replace('hosts = ["host-a", "host-b"]', 'hosts = ["host-a", "host-c"]') + runner,
                         "crew.toml:placement.hosts[1]: names a forge-less host: 'host-c'")
        self.assertFails(VALID + HOSTS.replace('devices = ["ios-simulator"], engines', 'engines')
                         + runner.replace('os = "linux"', 'os = "linux", devices = ["ios-simulator"]'),
                         "crew.toml:placement.rules[0].needs: no host taking role reviewer meets these needs")

    def test_hosts_need_tmux_or_session(self):
        grok = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "grok-bot"')
        self.assertFails(grok + HOSTS, "crew.toml:hosts: a host inventory needs runtime tmux or session, got 'grok-bot'")
        session = VALID.replace('name = "tmux"\noptions = { builders = 3 }', 'name = "session"')
        self.assertFails(session + HOSTS, "crew.toml:placement: placement needs runtime tmux, got 'session'")
        code, lines = validate(session + HOSTS.split("[placement]")[0])
        self.assertEqual(code, 0, lines)

    def test_resolve_merges_hosts_across_layers(self):
        org = HOSTS.split("[placement]")[0]
        project = '[hosts.host-c]\ncapabilities = { os = "linux", arch = "arm64", engines = ["codex"] }\nmax_runs = 1\n' \
                  '[placement]\nhosts = ["host-c", "host-a"]\n'
        lines = ResolveTest.assertResolves(self, ['hosts.host-a.max_runs = 2  # org', 'hosts.host-c.max_runs = 1  # project',
                                                  'placement.hosts = ["host-c", "host-a"]  # project'],
                                           project, default=VALID, org=org)
        self.assertNotIn("placement.rules", "\n".join(lines))


class SensitiveTest(unittest.TestCase):
    def test_defaults_match_root_and_nested_security_paths(self):
        paths = [".github/workflows/release.yml"] + [prefix + directory + "/change.py"
                 for prefix in ["", "src/"]
                 for directory in ["auth", "secrets", "permissions", "access-control", "migrations", "deletions"]]
        self.assertEqual(set(cc.sensitive_matches({}, paths)), set(paths))
        self.assertEqual(cc.sensitive_matches({}, ["docs/auth.md", "src/authentication/change.py",
                                                   ".github/ISSUE_TEMPLATE/bug.md", "README.md"]), {})

    def test_profile_additions_cannot_remove_defaults_and_globs_respect_segments(self):
        profile = {"sensitive": {"paths": ["infra/iam/*", "scripts/drop-?.py", "docs/protocol.md"]}}
        paths = ["infra/iam/policy.json", "infra/iam/nested/policy.json", "scripts/drop-a.py",
                 "scripts/drop-all.py", "docs/protocol.md", "auth/login.py"]
        matches = cc.sensitive_matches(profile, paths)
        self.assertEqual(set(matches), {"infra/iam/policy.json", "scripts/drop-a.py", "docs/protocol.md", "auth/login.py"})
        self.assertIn("auth/login.py", cc.sensitive_matches({"sensitive": {"paths": []}}, paths))

    def test_validation_and_layer_replacement(self):
        self.assertEqual(validate(VALID + '\n[sensitive]\npaths = []\n')[0], 0)
        for paths in ['"auth/**"', '[1]', '[""]', '["/auth/**"]', '["src/../auth/**"]']:
            self.assertEqual(validate(VALID + '\n[sensitive]\npaths = ' + paths + '\n')[0], 1)
        code, lines = resolve('[sensitive]\npaths = ["project/**"]\n', default=VALID,
                              org='[sensitive]\npaths = ["org/**"]\n')
        self.assertEqual(code, 0, lines)
        self.assertIn('sensitive.paths = ["project/**"]  # project', lines)

    def test_cli_reports_matches_and_rejects_bad_config(self):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            for config, paths, status, label in [(VALID, "auth/login.py\n", 0, "crew:sensitive"),
                                                 (VALID, "README.md\n", 0, None),
                                                 (VALID + '\n[sensitive]\npaths = [1]\n', "README.md\n", 1, None)]:
                with open(project, "w") as f:
                    f.write(config)
                out = io.StringIO()
                with patch("sys.stdin", io.StringIO(paths)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = cc.main(["sensitive", "--project", project])
                self.assertEqual(code, status)
                if not status:
                    self.assertEqual(json.loads(out.getvalue())["label"], label)
                else:
                    self.assertEqual(out.getvalue(), "")


class SensitiveContentTest(unittest.TestCase):
    """#879 B1: [[sensitive.content]] schema and layering; path-only results are unchanged without rules."""
    RULE = '\n[[sensitive.content]]\nname = "%s"\npattern = \'%s\'\nreason = "merge rule text"\n'

    def test_valid_rules_and_schema_errors(self):
        good = VALID + self.RULE % ("merge-rules", r"(?i)\bmerge[- ]gate\b") + 'paths = ["docs/**"]\n' \
            + self.RULE % ("land-rules", "land")
        self.assertEqual(validate(good)[0], 0, validate(good)[1])
        for extra, reason in [(self.RULE % ("a", "x") + self.RULE % ("a", "y"), "duplicate content rule name"),
                              (self.RULE % (" ", "x"), "content[0].name: expected a nonempty string"),
                              (self.RULE % ("a", "(unclosed"), "content[0].pattern: invalid regex"),
                              (self.RULE % ("a", "x") + 'paths = ["/docs/**"]\n', "content[0].paths[0]"),
                              (self.RULE % ("a", "x") + 'paths = ["docs/../x"]\n', "content[0].paths[0]"),
                              (self.RULE % ("a", "x") + 'paths = []\n', "content[0].paths: expected list of strings"),
                              (self.RULE % ("a", "x") + 'scope = "docs"\n', "content[0].scope: unknown key"),
                              ('\n[[sensitive.content]]\nname = "a"\n', "content[0].pattern: missing required key"),
                              ('\n[sensitive]\ncontent = "x"\n', "sensitive.content: expected list")]:
            code, out = validate(VALID + extra)
            self.assertEqual(code, 1, extra)
            self.assertIn(reason, "\n".join(out))

    def test_layers_replace_the_whole_array(self):
        code, lines = resolve(self.RULE % ("project-rule", "x"), default=VALID,
                              org=self.RULE % ("org-a", "a") + self.RULE % ("org-b", "b"))
        self.assertEqual(code, 0, lines)
        content = [line for line in lines if line.startswith("sensitive.content = ")]
        self.assertEqual(len(content), 1, lines)
        self.assertIn('"project-rule"', content[0])
        self.assertTrue(content[0].endswith("# project"))
        self.assertNotIn("org-a", content[0])

    def run_cli(self, config, paths):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(config)
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.stdin", io.StringIO(paths)), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cc.main(["sensitive", "--project", project])
        return code, out.getvalue(), err.getvalue()

    def test_path_list_with_content_rules_is_incomplete_not_clean(self):
        code, out, err = self.run_cli(VALID + self.RULE % ("merge-rules", "merge"), "README.md\n")
        self.assertEqual((code, out), (3, ""))
        self.assertIn("content rules need a unified diff", err)

    def test_path_only_result_unchanged_without_content_rules(self):
        for paths, expected in [("auth/login.py\n", {"label": "crew:sensitive", "matches": {"auth/login.py": ["auth/**"]}}),
                                ("README.md\n", {"label": None, "matches": {}})]:
            code, out, _ = self.run_cli(VALID, paths)
            self.assertEqual((code, json.loads(out)), (0, expected))



def git_diff(before, after):
    """`git diff --no-color --no-renames` between two {path: text} trees, as the builder makes it."""
    with tempfile.TemporaryDirectory() as d:
        def git(*args):
            return subprocess.run(["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                  check=True, capture_output=True, text=True).stdout
        git("init", "-q")
        for tree in (before, after):
            git("rm", "-rq", "--ignore-unmatch", ".")
            for path, text in tree.items():
                os.makedirs(os.path.dirname(os.path.join(d, path)) or d, exist_ok=True)
                with open(os.path.join(d, path), "w") as f:
                    f.write(text)
            git("add", "-A")
            git("commit", "-qm", "x", "--allow-empty")
        return git("diff", "--no-color", "--no-renames", "HEAD~1", "HEAD")


class SensitiveDiffTest(unittest.TestCase):
    """#879 B2: `sensitive --diff` content matching on added and removed lines (docs/profile.md Content rules)."""
    RULE = SensitiveContentTest.RULE
    MERGE = VALID + RULE % ("merge-rules", r"(?i)\bmerge[- ]gate\b") + 'paths = ["docs/**", "notes/**"]\n'
    BASE = {"docs/a.md": "one\ntwo\nthe merge gate holds\nfour\n", "src/x.py": "merge gate\n"}

    def run_cli(self, config, diff, org=None):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(config)
            argv = ["sensitive", "--project", project, "--diff"]
            if org:
                with open(os.path.join(d, "org.toml"), "w") as f:
                    f.write(org)
                argv += ["--org-profile", os.path.join(d, "org.toml")]
            out, err = io.StringIO(), io.StringIO()
            stdin = io.TextIOWrapper(io.BytesIO(diff.encode()))
            with patch("sys.stdin", stdin), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cc.main(argv)
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_added_line_matches_on_the_new_side(self):
        diff = git_diff(self.BASE, dict(self.BASE, **{"docs/b.md": "x\nNo merge-gate bypass\n"}))
        code, out, _ = self.run_cli(self.MERGE, diff)
        self.assertEqual((code, out), (0, {"label": "crew:sensitive", "matches": {},
                                           "content": [{"rule": "merge-rules", "path": "docs/b.md", "side": "new", "line": 2}]}))

    def test_removed_line_matches_on_the_old_side(self):
        diff = git_diff(self.BASE, dict(self.BASE, **{"docs/a.md": "one\ntwo\nfour\n"}))
        code, out, _ = self.run_cli(self.MERGE, diff)
        self.assertEqual(out["content"], [{"rule": "merge-rules", "path": "docs/a.md", "side": "old", "line": 3}])
        self.assertEqual((code, out["label"]), (0, "crew:sensitive"))

    def test_moved_file_matches_both_paths_and_runs_path_rules_on_each(self):
        after = {"notes/a.md": self.BASE["docs/a.md"], "auth/x.py": self.BASE["src/x.py"]}
        code, out, _ = self.run_cli(self.MERGE, git_diff(self.BASE, after))
        self.assertEqual(code, 0)
        self.assertEqual(out["matches"], {"auth/x.py": ["auth/**"]})
        self.assertEqual(out["content"], [{"rule": "merge-rules", "path": "docs/a.md", "side": "old", "line": 3},
                                          {"rule": "merge-rules", "path": "notes/a.md", "side": "new", "line": 3}])

    def test_outside_scope_context_and_headers_never_match(self):
        before = {"docs/merge gate.md": "merge gate\nkeep\n", "src/x.py": "a\n"}
        after = {"docs/merge gate.md": "merge gate\nkept\n", "src/x.py": "merge gate\n"}
        code, out, _ = self.run_cli(self.MERGE, git_diff(before, after))
        self.assertEqual((code, out), (0, {"label": None, "matches": {}, "content": []}))

    def test_changed_lines_that_look_like_headers_stay_content(self):
        diff = ("diff --git a/docs/a.md b/docs/a.md\nindex 1..2 100644\n--- a/docs/a.md\n+++ b/docs/a.md\n"
                "@@ -1,2 +1,2 @@\n--- a/merge gate\n+++ b/merge gate\n context\n")
        code, out, _ = self.run_cli(self.MERGE, diff)
        self.assertEqual((code, out["content"]), (0, [{"rule": "merge-rules", "path": "docs/a.md", "side": "new", "line": 1},
                                                       {"rule": "merge-rules", "path": "docs/a.md", "side": "old", "line": 1}]))

    def test_rule_replacement_by_a_later_layer(self):
        diff = git_diff(self.BASE, dict(self.BASE, **{"docs/a.md": "land rule\n"}))
        org = VALID + self.RULE % ("org-land", "land rule")
        code, out, _ = self.run_cli(self.RULE % ("project-merge", "merge gate"), diff, org=org)
        self.assertEqual([(r["rule"], r["side"]) for r in out["content"]], [("project-merge", "old")])
        code, out, _ = self.run_cli("", diff, org=org)
        self.assertEqual([(r["rule"], r["side"]) for r in out["content"]], [("org-land", "new")])

    def test_missing_or_incomplete_diff_exits_3_never_clean(self):
        good = git_diff(self.BASE, dict(self.BASE, **{"docs/a.md": "x\n"}))
        renamed = good.replace("index ", "similarity index 90%\nrename from docs/a.md\nrename to docs/b.md\nindex ", 1)
        overlong = good.replace("+x\n", "+x\n+merge gate\n")
        for diff in ["", "\n", "docs/a.md\n", good[:-4], renamed, overlong, good.replace(" @@", " @", 1),
                     good.replace("a/docs/a.md b/docs/a.md", '"a/docs/\\303.md" "b/docs/\\303.md"', 1)]:
            code, out, err = self.run_cli(self.MERGE, diff)
            self.assertEqual((code, out), (3, None), diff)
            self.assertIn("incomplete diff input", err)

    def test_diff_cut_inside_a_file_header_exits_3(self):
        modified = git_diff(self.BASE, dict(self.BASE, **{"docs/a.md": "one\n"}))
        added = git_diff(self.BASE, dict(self.BASE, **{"docs/b.md": "x\nmerge gate\n"}))
        deleted = git_diff(self.BASE, {"src/x.py": "merge gate\n"})
        self.assertIn("new file mode", added)
        self.assertIn("deleted file mode", deleted)
        cuts = []
        for diff in (modified, added, deleted):
            lines = diff.splitlines(keepends=True)
            hunk = next(i for i, line in enumerate(lines) if line.startswith("@@"))
            cuts += ["".join(lines[:cut]) for cut in range(1, hunk + 2)]  # every header prefix, then a bare hunk header
        cuts += ["diff --git a/run.sh b/run.sh\nold mode 100644\n",
                 "".join(modified.splitlines(keepends=True)[:3]) + git_diff(self.BASE, dict(self.BASE, **{"x.md": "y\n"}))]
        for cut in cuts:
            code, out, err = self.run_cli(self.MERGE, cut)
            self.assertEqual((code, out), (3, None), cut)
            self.assertRegex(err, "is incomplete|ends inside a hunk")

    def test_hunkless_file_blocks_that_are_complete_still_classify(self):
        before = dict(self.BASE, **{"auth/gone.txt": "", "img.bin": "\0a"})
        after = dict(self.BASE, **{"auth/new.txt": "", "img.bin": "\0b"})
        mode = "diff --git a/auth/run.sh b/auth/run.sh\nold mode 100644\nnew mode 100755\n"
        mode += ("diff --git a/auth/full.txt b/auth/full.txt\ndeleted file mode 100644\n"
                 "index e69de29bb2d1d6434b8b29ae775ad8c2e48c5391..0000000000000000000000000000000000000000\n")
        code, out, _ = self.run_cli(self.MERGE, git_diff(before, after) + mode)
        self.assertEqual((code, out["content"]), (0, []))
        self.assertEqual(sorted(out["matches"]), ["auth/full.txt", "auth/gone.txt", "auth/new.txt", "auth/run.sh"])

    def test_path_only_result_unchanged_without_content_rules(self):
        diff = git_diff(self.BASE, dict(self.BASE, **{"auth/login.py": "merge gate\n"}))
        code, out, _ = self.run_cli(VALID, diff)
        self.assertEqual((code, out), (0, {"label": "crew:sensitive", "matches": {"auth/login.py": ["auth/**"]}}))
        code, out, _ = self.run_cli(VALID, git_diff(self.BASE, dict(self.BASE, **{"README.md": "x\n"})))
        self.assertEqual((code, out), (0, {"label": None, "matches": {}}))

class SensitiveCallSiteTest(unittest.TestCase):
    """#879 B3: conditional change.read-diff, triage --paths-only and the GitHub read-diff binding."""
    MERGE = SensitiveDiffTest.MERGE

    def test_read_diff_required_only_with_content_rules(self):
        without = GITHUB_MANIFEST.replace('read-diff = "supported"\n', "")
        self.assertNotEqual(without, GITHUB_MANIFEST)
        code, lines = resolve_with_packs(self.MERGE, without)
        self.assertEqual(code, 1)
        self.assertIn("backends.change.capabilities.read-diff: undeclared (counts as unsupported) with "
                      "[[sensitive.content]] rules", "\n".join(lines))
        code, lines = resolve_with_packs(self.MERGE, without.replace('[capabilities.change]\n',
                                                                     '[capabilities.change]\nread-diff = "unsupported"\n'))
        self.assertIn("read-diff: unsupported with", "\n".join(lines))
        for project, manifest in [(VALID, without), (self.MERGE, GITHUB_MANIFEST)]:
            code, lines = resolve_with_packs(project, manifest)
            self.assertEqual(code, 0, lines)

    def run_cli(self, config, paths, *flags):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(config)
            out, err = io.StringIO(), io.StringIO()
            with patch("sys.stdin", io.StringIO(paths)), contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(err):
                code = cc.main(["sensitive", "--project", project, *flags])
        return code, out.getvalue(), err.getvalue()

    def test_paths_only_runs_path_rules_with_content_rules_configured(self):
        for paths, expected in [("docs/a.md\nauth/login.py\n", {"label": "crew:sensitive",
                                                                "matches": {"auth/login.py": ["auth/**"]}}),
                                ("docs/a.md\n", {"label": None, "matches": {}})]:
            for config in (self.MERGE, VALID):
                code, out, _ = self.run_cli(config, paths, "--paths-only")
                self.assertEqual((code, json.loads(out)), (0, expected))
        self.assertEqual(self.run_cli(self.MERGE, "docs/a.md\n")[0], 3)

    def test_paths_only_and_diff_are_exclusive(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_cli(VALID, "", "--paths-only", "--diff")
        self.assertEqual(raised.exception.code, 2)

    def test_github_read_diff_command_feeds_sensitive_diff(self):
        """The bundled map's read-diff, run in a plain clone, gives a no-rename diff at head that classifies."""
        command = load_toml(os.path.join(ROOT, "templates", "backends", "github.toml"))["change"]["read-diff"]
        with tempfile.TemporaryDirectory() as d:
            def git(*args, cwd=d):
                return subprocess.run(["git", "-C", cwd, "-c", "user.name=t", "-c", "user.email=t@t", *args],
                                      check=True, capture_output=True, text=True).stdout.strip()
            work, origin, clone = (os.path.join(d, n) for n in ("work", "origin.git", "clone"))
            git("init", "-q", "-b", "main", work)
            os.makedirs(os.path.join(work, "docs"))
            with open(os.path.join(work, "docs", "a.md"), "w") as f:
                f.write("one\nthe merge gate holds\n")
            git("add", "-A", cwd=work)
            git("commit", "-qm", "base", cwd=work)
            git("clone", "-q", "--bare", work, origin)
            git("clone", "-q", origin, clone)
            os.makedirs(os.path.join(work, "notes"))
            git("mv", "docs/a.md", "notes/a.md", cwd=work)
            git("commit", "-qm", "move", cwd=work)
            head = git("rev-parse", "HEAD", cwd=work)
            git("push", "-q", origin, "HEAD:refs/pull/7/head", cwd=work)
            command = command.replace("<default-branch>", "main").replace("<n>", "7").replace("<head-sha>", head)
            diff = subprocess.run(["sh", "-c", command], cwd=clone, check=True, capture_output=True, text=True).stdout
        self.assertNotIn("rename from", diff)
        code, out, _ = SensitiveDiffTest.run_cli(self, self.MERGE, diff)
        self.assertEqual((code, out["content"]), (0, [
            {"rule": "merge-rules", "path": "docs/a.md", "side": "old", "line": 2},
            {"rule": "merge-rules", "path": "notes/a.md", "side": "new", "line": 2}]))


class SpecTest(unittest.TestCase):
    """#398 B1: spec globs and the opt-in merge_grant_scope (docs/protocol.md §7 spec change)."""
    def test_default_globs_match_path_only_and_both_rename_sides(self):
        self.assertEqual(cc.spec_matches({}, ["docs/specs/a.md", "docs/specs/x/b.md", "docs/spec.md", "README.md"]),
                         {"docs/specs/a.md": ["docs/specs/**"], "docs/specs/x/b.md": ["docs/specs/**"]})
        self.assertEqual(set(cc.spec_matches({}, ["docs/specs/old.md", "docs/archive/old.md"])), {"docs/specs/old.md"})

    def test_profile_globs_replace_defaults_and_empty_leaves_label_only(self):
        profile = {"spec": {"paths": ["rfcs/**"]}}
        self.assertEqual(set(cc.spec_matches(profile, ["rfcs/1.md", "docs/specs/a.md"])), {"rfcs/1.md"})
        self.assertEqual(cc.spec_matches({"spec": {"paths": []}}, ["docs/specs/a.md"]), {})

    def test_spec_paths_validation_and_layer_replacement(self):
        self.assertEqual(validate(VALID + '\n[spec]\npaths = []\n')[0], 0)
        for paths in ['"docs/**"', '[1]', '[""]', '["/docs/**"]', '["docs/../x/**"]']:
            self.assertEqual(validate(VALID + '\n[spec]\npaths = ' + paths + '\n')[0], 1, paths)
        self.assertEqual(validate(VALID + '\n[spec]\nglobs = ["x/**"]\n')[1][0], "crew.toml:spec.globs: unknown key")
        code, lines = resolve('[spec]\npaths = ["project/**"]\n', default=VALID, org='[spec]\npaths = ["org/**"]\n')
        self.assertEqual(code, 0, lines)
        self.assertIn('spec.paths = ["project/**"]  # project', lines)

    def test_merge_grant_scope_absent_by_default_and_validated(self):
        self.assertFalse(any(ln.startswith("runtime.options.merge_grant_scope") for ln in resolve(VALID)[1]))
        granted = VALID.replace("builders = 3", 'builders = 3, merge_grant = "spec PRs per #110"')
        for scope in ('["approved"]', '["approved", "spec"]'):
            code, lines = resolve(granted.replace("builders = 3", "builders = 3, merge_grant_scope = " + scope))
            self.assertIn("runtime.options.merge_grant_scope = %s  # project" % scope, lines)
        for scope, problem in [('["approved", "sensitive"]', "runtime.options.merge_grant_scope[1]: unknown value "
                                "'sensitive' (expected one of: approved, spec)"),
                               ("[]", "runtime.options.merge_grant_scope: expected list of strings, got list"),
                               ('"spec"', "runtime.options.merge_grant_scope: expected list of strings, got string")]:
            code, lines = validate(granted.replace("builders = 3", "builders = 3, merge_grant_scope = " + scope))
            self.assertEqual(code, 1, lines)
            self.assertIn("crew.toml:" + problem, lines)

    def test_spec_scope_refused_without_a_standing_grant(self):
        code, lines = validate(VALID.replace("builders = 3", 'builders = 3, merge_grant_scope = ["approved", "spec"]'))
        self.assertEqual(code, 1, lines)
        self.assertIn("crew.toml:runtime.options.merge_grant_scope: spec needs a standing merge_grant; merge_grant is none",
                      lines)
        self.assertEqual(validate(VALID.replace("builders = 3", 'builders = 3, merge_grant_scope = ["approved"]'))[0], 0)

    def test_release_delegation_defaults_none_and_needs_a_link(self):
        """#1435: absent keeps a per-cut owner merge-ok; a set delegation carries the owner's words and link."""
        code, lines = resolve(VALID)
        self.assertEqual(code, 0, lines)
        self.assertIn('runtime.options.release_delegation = "none"  # core', lines)
        words = 'builders = 3, release_delegation = "all approvals incl. releases https://github.com/o/r/issues/985#c1"'
        code, lines = resolve(VALID.replace("builders = 3", words))
        self.assertIn('runtime.options.release_delegation = "all approvals incl. releases '
                      'https://github.com/o/r/issues/985#c1"  # project', lines)
        code, lines = validate(VALID.replace("builders = 3", 'builders = 3, release_delegation = "releases ok"'))
        self.assertEqual(code, 1, lines)
        self.assertIn("crew.toml:runtime.options.release_delegation: expected the owner's recorded words with a "
                      "https:// link to the record", lines)

    def test_team_repo_sections_set_spec_paths_and_scope(self):
        text = TEAM.replace('merge_grant = "docs PRs"', 'merge_grant = "docs PRs"\nmerge_grant_scope = ["approved", "spec"]\n'
                            'spec = ["rfcs/**"]')
        merged, prov, problems, _ = TeamFileTest.resolve(None, text, "#gadgets")
        self.assertEqual(problems, [])
        self.assertEqual((merged["spec"]["paths"], prov["spec.paths"]), (["rfcs/**"], "repo"))
        self.assertEqual(merged["runtime"]["options"]["merge_grant_scope"], ["approved", "spec"])
        problems = TeamFileTest.resolve(None, text.replace('merge_grant = "docs PRs"\n', ""), "#gadgets")[2]
        self.assertEqual(problems, ["ext.toml[repos.gadgets]:runtime.options.merge_grant_scope: spec needs a standing "
                                    "merge_grant; merge_grant is none"])


class PrecheckScopeTest(unittest.TestCase):
    """#881: per-path test ownership; spaced paths, unowned code, query failure, docs only and a mixed change.
    #1345: paths absent at head (deletions, rename sources) are removed, never unowned."""
    OWNERS = """case "$1" in
  "src/my app.py") echo //src:app_test; echo //src:lib_test ;;
  src/lib.py) echo //src:lib_test ;;
  boom/*) echo "query backend down" >&2; exit 2 ;;
esac
"""

    def scope(self, paths, extra='no_owner_ok = ["**/BUILD", "*.md", "**/*.md", "docs/**"]', removed=()):
        """Run precheck-scope from a fake worktree at head holding every stdin path except `removed`."""
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "owners.sh"), "w") as f:
                f.write(self.OWNERS)
            project = os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(VALID + '\n[builder.precheck]\nowners = "sh %s/owners.sh"\n%s\n' % (d, extra))
            head = os.path.join(d, "head")
            for path in set(paths.splitlines()) - set(removed):
                os.makedirs(os.path.dirname(os.path.join(head, path)), exist_ok=True)
                open(os.path.join(head, path), "w").close()
            os.makedirs(head, exist_ok=True)
            out, err, cwd = io.StringIO(), io.StringIO(), os.getcwd()
            try:
                os.chdir(head)
                with patch("sys.stdin", io.StringIO(paths)), contextlib.redirect_stdout(out), \
                        contextlib.redirect_stderr(err):
                    code = cc.main(["precheck-scope", "--project", project])
            finally:
                os.chdir(cwd)
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def test_directory_rename_runs_destinations_and_lists_sources_removed(self):
        code, result, _ = self.scope("old/lib.py\nold/my app.py\nsrc/lib.py\nsrc/my app.py\n",
                                     removed=("old/lib.py", "old/my app.py"))
        self.assertEqual((code, result["tests"], result["targets"]), (0, "run", ["//src:app_test", "//src:lib_test"]))
        self.assertEqual((result["removed"], result["unowned"]), (["old/lib.py", "old/my app.py"], []))
        self.assertEqual([e["class"] for e in result["paths"]], ["removed", "removed", "owned", "owned"])

    def test_deletion_only_is_na_and_never_queried(self):
        code, result, _ = self.scope("src/orphan.py\nboom/x.py\n", removed=("src/orphan.py", "boom/x.py"))
        self.assertEqual((code, result["tests"], result["targets"]), (0, "n/a", []))
        self.assertEqual((result["removed"], result["unowned"]), (["boom/x.py", "src/orphan.py"], []))

    def test_new_unowned_file_still_fails_beside_a_removed_path(self):
        code, result, _ = self.scope("src/gone.py\nsrc/orphan.py\n", removed=("src/gone.py",))
        self.assertEqual((code, result["tests"], result["unowned"], result["removed"]),
                         (3, "fail", ["src/orphan.py"], ["src/gone.py"]))

    def test_spaced_path_keeps_one_argument(self):
        code, result, _ = self.scope("src/my app.py\n")
        self.assertEqual((code, result["tests"], result["targets"]), (0, "run", ["//src:app_test", "//src:lib_test"]))
        self.assertEqual(result["paths"][0]["class"], "owned")

    def test_unowned_code_fails(self):
        code, result, _ = self.scope("src/orphan.py\nREADME.md\n")
        self.assertEqual((code, result["tests"], result["unowned"]), (3, "fail", ["src/orphan.py"]))

    def test_query_failure_stops(self):
        code, result, err = self.scope("README.md\nboom/x.py\n")
        self.assertEqual((code, result), (4, None))
        self.assertIn("query backend down", err)

    def test_docs_only_is_na(self):
        code, result, _ = self.scope("docs/guide one.md\nsrc/BUILD\n")
        self.assertEqual((code, result["tests"], result["targets"]), (0, "n/a", []))
        self.assertEqual(result["no_owner_ok"], ["docs/guide one.md", "src/BUILD"])

    def test_mixed_change_runs_owned_and_lists_na_paths(self):
        code, result, _ = self.scope("src/lib.py\nsrc/my app.py\ndocs/a.md\n")
        self.assertEqual((code, result["tests"], result["targets"]), (0, "run", ["//src:app_test", "//src:lib_test"]))
        self.assertEqual(result["no_owner_ok"], ["docs/a.md"])
        self.assertEqual([e["class"] for e in result["paths"]], ["no-owner-ok", "owned", "owned"])

    def test_without_no_owner_ok_every_unowned_path_fails(self):
        code, result, _ = self.scope("docs/a.md\n", extra="")
        self.assertEqual((code, result["unowned"]), (3, ["docs/a.md"]))

    def test_missing_owners_and_validation(self):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            with open(project, "w") as f:
                f.write(VALID)
            with patch("sys.stdin", io.StringIO("a.py\n")), contextlib.redirect_stderr(io.StringIO()) as err:
                self.assertEqual(cc.main(["precheck-scope", "--project", project]), 1)
            self.assertIn("builder.precheck.owners is not set", err.getvalue())
        self.assertEqual(validate(VALID + '\n[builder.precheck]\nowners = "q"\nno_owner_ok = ["docs/**"]\n')[0], 0)
        for settings, expected in [('owners = " "', 'owners: expected a nonempty shell command'),
                                   ('owners = []', 'owners: expected string'),
                                   ('no_owner_ok = "docs/**"', 'no_owner_ok: expected list of strings'),
                                   ('no_owner_ok = ["/abs"]', 'no_owner_ok[0]: expected a nonempty repo-relative glob'),
                                   ('no_owner_ok = ["a/../b"]', 'no_owner_ok[0]: expected a nonempty repo-relative glob')]:
            code, lines = validate(VALID + '\n[builder.precheck]\n' + settings + '\n')
            self.assertEqual(code, 1, lines)
            self.assertTrue(any('builder.precheck.' + expected in line for line in lines), lines)


class RecordedPackTest(unittest.TestCase):
    def test_pack_path_schema(self):
        self.assertEqual(validate(VALID + '\npack = "org"\n')[0], 0)
        self.assertEqual(validate(VALID + '\npack = 1\n')[0], 1)
        self.assertEqual(validate(VALID + '\npack = " "\n')[0], 1)

    def test_recorded_pack_resolution_and_explicit_override(self):
        with tempfile.TemporaryDirectory() as d:
            project = os.path.join(d, "crew.toml")
            pack = os.path.join(d, "org")
            os.mkdir(pack)
            org = os.path.join(pack, "profile.toml")
            with open(org, "w") as f:
                f.write('[identities.coordinator]\ntitle = "Org lead"\n[runtime.options]\nbuilders = 4\n')
            for directory in ("org", pack):
                with open(project, "w") as f:
                    f.write(VALID + '\npack = "%s"\n' % directory)
                profile, prov, problems, layers = cc.resolve_profile(project)
                self.assertEqual(problems, [])
                self.assertEqual(layers, ["core", "default", "org", "project"])
                self.assertEqual(profile["identities"]["coordinator"]["title"], "Org lead")
                self.assertEqual(prov["identities.coordinator.title"], "org")
                self.assertEqual(profile["runtime"]["options"]["builders"], 3)
            other = os.path.join(d, "override.toml")
            with open(other, "w") as f:
                f.write('[identities.coordinator]\ntitle = "Explicit lead"\n')
            self.assertEqual(cc.resolve_profile(project, other)[0]["identities"]["coordinator"]["title"],
                             "Explicit lead")
            with open(org, "w") as f:
                f.write('[invalid\n')
            self.assertTrue(cc.resolve_profile(project)[2])
            os.unlink(org)
            self.assertEqual(cc.resolve_profile(project)[2], [])
            os.rmdir(pack)
            self.assertTrue(any("paths.pack: pack directory missing" in p for p in cc.resolve_profile(project)[2]))

    def test_recorded_pack_without_profile_selects_its_manifest(self):
        manifest = GITHUB_MANIFEST.replace('name = "github"', 'name = "example"')
        manifest = manifest.replace('[pack]\n', '[pack]\nmdstack_version = "v4.0.0"\nversion = "0.5.0"\n')
        with tempfile.TemporaryDirectory() as d:
            project, pack = os.path.join(d, "crew.toml"), os.path.join(d, "pack")
            os.mkdir(pack)
            with open(os.path.join(pack, "manifest.toml"), "w") as f:
                f.write(manifest)
            with open(project, "w") as f:
                f.write(VALID.replace('[backends.review]\nname = "github"', '[backends.review]\nname = "example"') +
                        '\npack = "pack"\n')
            meta = {}
            profile, prov, problems, layers = cc.resolve_profile(project, meta=meta)
            self.assertEqual(problems, [])
            self.assertEqual(layers, ["core", "default", "project"])
            self.assertEqual(meta, {"pack.version": ("0.5.0", "pack:example")})
            self.assertEqual(prov["backends.review.capabilities.list-verdicts"], "external-pack")
            with open(os.path.join(pack, "manifest.toml"), "w") as f:
                f.write(manifest.replace('version = "0.5.0"', 'version = "v0.5.0"'))
            self.assertTrue(any("pack.version: expected a SemVer version" in p
                                for p in cc.resolve_profile(project)[2]))


class ControlItemIdsTest(unittest.TestCase):
    """#936: backend map [ids] loaded by resolve; control_item as an integer or a string matching ids.item."""
    PATTERN = "[A-Z][A-Z0-9]+-[0-9]+"
    NATIVE = VALID.replace('[backends.tracker]\nname = "github"', '[backends.tracker]\nname = "example"')

    def pack(self, d, ids='[ids]\nitem = "%s"\n' % PATTERN):
        pack = os.path.join(d, "pack")
        os.makedirs(os.path.join(pack, "render", "backends"), exist_ok=True)
        with open(os.path.join(pack, "manifest.toml"), "w") as f:
            f.write(GITHUB_MANIFEST.replace('name = "github"', 'name = "example"')
                    .replace('[pack]\n', '[pack]\nmdstack_version = "v4.0.0"\n'))
        with open(os.path.join(pack, "render", "backends", "example.toml"), "w") as f:
            f.write('[markers]\nread-item = "ex item comments <control-item> --json"\n' + ids)
        return os.path.join(pack, "manifest.toml")

    def run_cli(self, d, item, *command, text=None):
        project = os.path.join(d, "crew.toml")
        with open(project, "w") as f:
            f.write((text or self.NATIVE).replace("[repo]\n", "[repo]\ncontrol_item = %s\n" % item)
                    .replace("[runtime]\n", '[runtime]\ninstance = "laptop"\n'))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cc.main([c.replace("<project>", project) for c in command])
        return code, out.getvalue().replace(project, "crew.toml")

    def test_github_integer_unchanged_and_string_needs_a_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_cli(d, "12", "validate", "<project>", text=VALID), (0, "crew-config: OK (crew.toml)\n"))
            code, out = self.run_cli(d, "12", "resolve", "--project", "<project>", text=VALID)
            self.assertEqual(code, 0, out)
            self.assertIn('repo.control_item = 12  # project\n', out)
            self.assertIn('ids.item = "[1-9][0-9]*"  # core\nids.change = "[1-9][0-9]*"  # core\n', out)
            for command in (["validate", "<project>"], ["resolve", "--project", "<project>"]):
                code, out = self.run_cli(d, '"OPS-1042"', *command, text=VALID)
                self.assertEqual(code, 1)
                self.assertIn("crew.toml:repo.control_item: a string id needs the tracker backend's [ids] item pattern",
                              out)
            for bad, reason in (("0", "must be >= 1"), ("true", "expected integer or string, got boolean"),
                                ("1.5", "expected integer or string, got float"),
                                ('""', "a string id needs the tracker backend's [ids] item pattern")):
                code, out = self.run_cli(d, bad, "validate", "<project>", text=VALID)
                self.assertEqual(code, 1, bad)
                self.assertIn("crew.toml:repo.control_item: " + reason, out)

    def test_native_string_id_matches_the_tracker_pattern(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = self.pack(d)
            for command in (["validate", "<project>", "--pack-manifest", manifest],
                            ["resolve", "--project", "<project>", "--pack-manifest", manifest]):
                code, out = self.run_cli(d, '"OPS-1042"', *command)
                self.assertEqual(code, 0, out)
                for bad in ('"ops 1042"', '""', '"OPS-1042 "', "false"):
                    code, out = self.run_cli(d, bad, *command)
                    self.assertEqual(code, 1, bad)
                code, out = self.run_cli(d, '"ops 1042"', *command)
                self.assertIn('repo.control_item: "ops 1042" does not match item pattern %s (tracker backend example)'
                              % self.PATTERN, out)
                self.assertEqual(self.run_cli(d, "7", *command)[0], 0)
            code, out = self.run_cli(d, '"OPS-1042"', "resolve", "--project", "<project>", "--pack-manifest", manifest)
            self.assertIn('repo.control_item = "OPS-1042"  # project\n', out)
            self.assertIn('ids.item = "%s"  # backend-map:example\nids.change = "[1-9][0-9]*"  # core\n'
                          % self.PATTERN, out)
            self.assertEqual(self.run_cli(d, '"OPS-1042"', "resolve", "--project", "<project>",
                                          text=self.NATIVE + '\npack = "pack"\n')[0], 0)
            os.rename(os.path.join(d, "pack", "render", "backends", "example.toml"),
                      os.path.join(d, "pack", "render", "backends", "github.toml"))  # a pack overlay of the GitHub map
            self.assertEqual(self.run_cli(d, '"OPS-1042"', "validate", "<project>", text=VALID + '\npack = "pack"\n'),
                             (0, "crew-config: OK (crew.toml)\n"))

    def test_external_backend_without_a_map_keeps_default_ids(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = self.pack(d)
            os.unlink(os.path.join(d, "pack", "render", "backends", "example.toml"))
            code, out = self.run_cli(d, "7", "resolve", "--project", "<project>", "--pack-manifest", manifest)
            self.assertEqual(code, 0, out)
            self.assertIn('ids.item = "[1-9][0-9]*"  # core\n', out)
            code, out = self.run_cli(d, '"OPS-1042"', "resolve", "--project", "<project>", "--pack-manifest", manifest)
            self.assertEqual(code, 1)
            self.assertIn("repo.control_item: a string id needs the tracker backend's [ids] item pattern", out)

    def test_unsafe_or_invalid_patterns_and_profile_ids_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            for ids, reason in (('[ids]\nitem = "[A-Z"\n', "ids.item: pattern does not compile"),
                                ('[ids]\nitem = "[A-Z]*"\n', "ids.item: pattern matches ''"),
                                ('[ids]\nitem = "[A-Z ]+"\n', "ids.item: pattern matches ' '"),
                                ('[ids]\nitem = "[A-Z<]+"\n', "ids.item: pattern matches '<'"),
                                ('[ids]\nitem = 1\n', "ids.item: expected string, got integer"),
                                ('[ids]\nticket = "[0-9]+"\n', "ids.ticket: unknown key")):
                manifest = self.pack(d, ids)
                code, out = self.run_cli(d, "7", "resolve", "--project", "<project>", "--pack-manifest", manifest)
                self.assertEqual(code, 1, ids)
                self.assertIn("backend-map:example:" + reason, out)
            code, out = self.run_cli(d, "7", "validate", "<project>", text=VALID + '\n[ids]\nitem = "[0-9]+"\n')
            self.assertEqual(code, 1)
            self.assertIn("crew.toml:ids: unknown key", out)


    def test_marker_key_from_the_change_map(self):
        """#1031: the change map's [ids] marker_key validates and resolves; other values are refused."""
        with tempfile.TemporaryDirectory() as d:
            text = VALID + '\npack = "pack"\n'
            os.makedirs(os.path.join(d, "pack", "render", "backends"))
            overlay = os.path.join(d, "pack", "render", "backends", "github.toml")
            for value in ("item", "change"):
                with open(overlay, "w") as f:
                    f.write('[ids]\nmarker_key = "%s"\n' % value)
                self.assertEqual(self.run_cli(d, "7", "validate", "<project>", text=text),
                                 (0, "crew-config: OK (crew.toml)\n"))
                code, out = self.run_cli(d, "7", "resolve", "--project", "<project>", text=text)
                self.assertEqual(code, 0, out)
                self.assertIn('ids.change = "[1-9][0-9]*"  # core\nids.marker_key = "%s"  # backend-map:github\n'
                              % value, out)
            for bad, reason in (('"issue"', "unknown value 'issue' (expected one of: change, item)"),
                                ("1", "expected string, got integer")):
                with open(overlay, "w") as f:
                    f.write("[ids]\nmarker_key = %s\n" % bad)
                for command in (["validate", "<project>"], ["resolve", "--project", "<project>"]):
                    code, out = self.run_cli(d, "7", *command, text=text)
                    self.assertEqual(code, 1, bad)
                    self.assertIn("backend-map:github:ids.marker_key: " + reason, out)
            os.unlink(overlay)
            code, out = self.run_cli(d, "7", "resolve", "--project", "<project>", text=text)
            self.assertEqual(code, 0, out)
            self.assertNotIn("marker_key", out)

    def test_marker_key_on_a_tracker_only_map_is_not_carried(self):
        with tempfile.TemporaryDirectory() as d:
            manifest = self.pack(d, '[ids]\nitem = "%s"\nmarker_key = "item"\n' % self.PATTERN)
            code, out = self.run_cli(d, "7", "resolve", "--project", "<project>", "--pack-manifest", manifest)
            self.assertEqual(code, 0, out)
            self.assertIn('ids.item = "%s"  # backend-map:example\n' % self.PATTERN, out)
            self.assertNotIn("marker_key", out)

class InstallValidationTest(unittest.TestCase):
    def test_install_placeholders_rejected_with_key_paths(self):
        for original, leftover, key in [('"acme"', '"<owner>"', "repo.owner"),
                                        ('"acme-owner"', '"<user-login>"', "identities.owners[0]"),
                                        ('"/srv/crew-state"', '"/srv/<state-dir>"', "paths.state_dir")]:
            text = VALID.replace(original, leftover)
            self.assertEqual(validate(text)[0], 0)
            code, lines = validate(text, install=True)
            self.assertEqual(code, 1)
            self.assertTrue(any(key + ": unfilled install-time placeholder" in line for line in lines), lines)

    def test_runtime_placeholders_and_concrete_values_stay_allowed(self):
        text = VALID.replace('builders = 3', 'builders = 3, notes = { builder = ["<n>-<head-sha>.md"] }')
        self.assertEqual(validate(text, install=True)[0], 0)
        self.assertEqual(validate(VALID, install=True)[0], 0)

    def test_install_resolve_scans_effective_profile(self):
        with tempfile.TemporaryDirectory() as d:
            project, org = os.path.join(d, "crew.toml"), os.path.join(d, "org.toml")
            with open(project, "w") as f:
                f.write(VALID)
            with open(org, "w") as f:
                f.write('[paths]\ntoolchain_bin = "/opt/bin"\nlive_dir = "/srv/live"\nmdstack = "/srv/mdstack"\n')
            for extra, expected in (([], 0), (["--install"], 1),
                                    (["--install", "--org-profile", org], 0)):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                    code = cc.main(["resolve", "--project", project] + extra)
                self.assertEqual(code, expected, out.getvalue())
                if expected:
                    self.assertIn("paths.toolchain_bin: unfilled install-time placeholder <toolchain-bin>",
                                  out.getvalue())


class HarnessRegistryTest(unittest.TestCase):
    """#964 (#883 B1): the optional pack.harness registry and its static checks."""
    REGISTRY = """\
[[pointer]]
harness = "claude-code"
target = ".claude/skills/org-review-tool/SKILL.md"
source = "harness/review-tool.md"
mode = "copy"

[[pointer]]
harness = "claude-code"
target = ".claude/agents/org-venue.md"
source = "harness/venue.md"
mode = "pointer"

[[pointer]]
harness = "codex"
launch_note = "harness/codex-venue.md"
"""

    def run_validate(self, registry, manifest=None, setup=None):
        """Lay out a pack with the registry, run `validate` on its manifest and `resolve` with it; return lines."""
        with tempfile.TemporaryDirectory() as d:
            pack = os.path.join(d, "pack")
            os.makedirs(os.path.join(pack, "harness"))
            for name in ("review-tool.md", "venue.md", "codex-venue.md"):
                with open(os.path.join(pack, "harness", name), "w") as f:
                    f.write("# %s\n" % name)
            with open(os.path.join(pack, "harness.toml"), "w") as f:
                f.write(registry)
            path = os.path.join(pack, "manifest.toml")
            with open(path, "w") as f:
                f.write(manifest or GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nharness = "harness.toml"\n'))
            if setup:
                setup(d, pack)
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cc.main(["validate", path])
            problems = []
            cc.load_pack(path, lambda key, reason: problems.append("%s: %s" % (key, reason)))
            lines = [ln.replace(path, "manifest.toml") for ln in out.getvalue().splitlines()]
            self.assertEqual(code == 0, not problems, (lines, problems))
            return code, lines

    def assertRejects(self, expected, registry, **kwargs):
        code, lines = self.run_validate(registry, **kwargs)
        self.assertEqual(code, 1, lines)
        self.assertIn("manifest.toml:" + expected, lines)

    def test_valid_registry_and_none(self):
        self.assertEqual(self.run_validate(self.REGISTRY), (0, ["crew-config: OK (manifest.toml)"]))
        self.assertEqual(self.run_validate("", manifest=GITHUB_MANIFEST), (0, ["crew-config: OK (manifest.toml)"]))
        self.assertEqual(self.run_validate(self.REGISTRY.replace('mode = "copy"\n', ""))[0], 0)

    def test_registry_file(self):
        missing = GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nharness = "nope.toml"\n')
        self.assertRejects("pack.harness: not a regular file in the pack: 'nope.toml'", "", manifest=missing)
        outside = GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nharness = "../harness.toml"\n')
        self.assertRejects("pack.harness: escapes the pack directory: '../harness.toml'", "", manifest=outside)
        self.assertRejects("pack.harness.pointer: missing required key", "")
        self.assertRejects("pack.harness.extra: unknown key", "extra = 1\n" + self.REGISTRY)
        code, lines = self.run_validate("[[pointer]\n")
        self.assertTrue(any(ln.startswith("manifest.toml:pack.harness: invalid TOML in harness.toml") for ln in lines))
        self.assertRejects("pack.harness: expected string, got integer", "",
                           manifest=GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nharness = 1\n'))

    def test_shapes_and_keys(self):
        self.assertRejects("pack.harness.pointer[2].target: unknown key",
                           self.REGISTRY + 'target = "x.md"\n')
        self.assertRejects("pack.harness.pointer[0].harness: missing required key",
                           '[[pointer]]\nlaunch_note = "harness/codex-venue.md"\n')
        self.assertRejects("pack.harness.pointer[0].source: missing required key",
                           '[[pointer]]\nharness = "codex"\ntarget = "AGENTS.local.md"\n')
        self.assertRejects("pack.harness.pointer[0].mode: unknown value 'exec' (expected one of: copy, pointer)",
                           self.REGISTRY.replace('mode = "copy"', 'mode = "exec"'))
        self.assertRejects("pack.harness.pointer[2].harness: a launch note is for codex only, got 'claude-code'",
                           self.REGISTRY.replace('harness = "codex"', 'harness = "claude-code"'))

    def test_unimplemented_and_unknown_adapter(self):
        self.assertRejects("pack.harness.pointer[0].harness: adapter pi has no install pointer bootstrap implements "
                           "(expected one of: claude-code, codex)",
                           self.REGISTRY.replace('harness = "claude-code"', 'harness = "pi"', 1))
        self.assertRejects("pack.harness.pointer[0].harness: unknown value 'vim' (expected one of: claude-code, codex)",
                           self.REGISTRY.replace('harness = "claude-code"', 'harness = "vim"', 1))

    def test_targets(self):
        def target(value):
            return self.REGISTRY.replace('".claude/skills/org-review-tool/SKILL.md"', '"%s"' % value)
        for bad in ("/etc/crew.md", "~/.claude/skills/x.md"):
            self.assertRejects("pack.harness.pointer[0].target: expected a project-relative path, got %r" % bad,
                               target(bad))
        for bad in ("../outside.md", ".claude/../x.md", "./x.md", ".git/hooks/pre-commit", "a//b.md", "dir/"):
            self.assertRejects("pack.harness.pointer[0].target: expected a normalized path with no empty, ., .. or "
                               ".git component, got %r" % bad, target(bad))
        self.assertRejects("pack.harness.pointer[1].target: duplicate target "
                           "'.claude/skills/org-review-tool/SKILL.md'",
                           self.REGISTRY.replace('".claude/agents/org-venue.md"',
                                                 '".claude/skills/org-review-tool/SKILL.md"'))
        for builtin in cc.HARNESS_BUILTINS:
            self.assertRejects("pack.harness.pointer[0].target: collides with a built-in bootstrap target: %r" % builtin,
                               target(builtin))

    def test_home_root(self):
        """#1032: root = "home" targets the agent home; still relative, and only project targets meet the built-ins."""
        home = '[[pointer]]\nharness = "claude-code"\nroot = "home"\ntarget = "%s"\nsource = "harness/venue.md"\n'
        builtin = sorted(cc.HARNESS_BUILTINS)[0]
        self.assertEqual(self.run_validate(self.REGISTRY + home % builtin)[0], 0)
        self.assertEqual(self.run_validate(self.REGISTRY + home % ".claude/skills/org-review-tool/SKILL.md")[0], 0)
        for bad in ("/etc/crew.md", "~/.claude/CLAUDE.md"):
            self.assertRejects("pack.harness.pointer[3].target: expected a home-relative path, got %r" % bad,
                               self.REGISTRY + home % bad)
        self.assertRejects("pack.harness.pointer[3].target: expected a normalized path with no empty, ., .. or "
                           ".git component, got '../x.md'", self.REGISTRY + home % "../x.md")
        self.assertRejects("pack.harness.pointer[4].target: duplicate target 'rules.md'",
                           self.REGISTRY + home % "rules.md" + home % "rules.md")
        self.assertRejects("pack.harness.pointer[3].root: unknown value 'etc' (expected one of: project, home)",
                           self.REGISTRY + (home % "x.md").replace('"home"', '"etc"'))
        self.assertRejects("pack.harness.pointer[2].root: unknown key", self.REGISTRY + 'root = "home"\n')

    def test_source_containment(self):
        self.assertRejects("pack.harness.pointer[0].source: escapes the pack directory: '../secret.md'",
                           self.REGISTRY.replace('"harness/review-tool.md"', '"../secret.md"'))
        self.assertRejects("pack.harness.pointer[0].source: escapes the pack directory: '/etc/hosts'",
                           self.REGISTRY.replace('"harness/review-tool.md"', '"/etc/hosts"'))

        def link_out(d, pack):
            with open(os.path.join(d, "secret.md"), "w") as f:
                f.write("x\n")
            os.symlink(os.path.join(d, "secret.md"), os.path.join(pack, "harness", "link.md"))
        self.assertRejects("pack.harness.pointer[2].launch_note: escapes the pack directory: 'harness/link.md'",
                           self.REGISTRY.replace('"harness/codex-venue.md"', '"harness/link.md"'), setup=link_out)

        def link_in(d, pack):
            os.symlink("venue.md", os.path.join(pack, "harness", "alias.md"))
        self.assertEqual(self.run_validate(self.REGISTRY.replace('"harness/venue.md"', '"harness/alias.md"'),
                                           setup=link_in)[0], 0)
        self.assertRejects("pack.harness.pointer[0].source: not a regular file in the pack: 'harness'",
                           self.REGISTRY.replace('"harness/review-tool.md"', '"harness"'))

        def binary(d, pack):
            with open(os.path.join(pack, "harness", "review-tool.md"), "wb") as f:
                f.write(b"\xff\xfe")
        self.assertRejects("pack.harness.pointer[0].source: cannot read as UTF-8: 'harness/review-tool.md'",
                           self.REGISTRY, setup=binary)

    def test_without_directory_fails_closed(self):
        problems = []
        cc.validate_manifest(cc.tomllib.loads(GITHUB_MANIFEST.replace('[pack]\n', '[pack]\nharness = "h.toml"\n')),
                             lambda key, reason: problems.append("%s: %s" % (key, reason)))
        self.assertEqual(problems, ["pack.harness: cannot check the registry without the manifest's directory"])


class KnowledgeManifestTest(unittest.TestCase):
    """#1229: a connector manifest may declare the knowledge concern alone; core concerns stay all-or-nothing."""
    KNOWLEDGE = '[capabilities.knowledge]\nread = "supported"\npropose-edit = "supported"\n'

    def problems(self, text):
        out = []
        cc.validate_manifest(cc.tomllib.loads(text), lambda key, reason: out.append("%s: %s" % (key, reason)),
                             external_pin=False)
        return out

    def test_knowledge_only_and_beside_core(self):
        self.assertEqual(self.problems('[pack]\nname = "notes"\ncommands = "x"\n' + self.KNOWLEDGE), [])
        self.assertEqual(self.problems(GITHUB_MANIFEST + self.KNOWLEDGE), [])
        self.assertEqual(self.problems(read(os.path.join(ROOT, "connectors", "notion", "manifest.toml"))), [])

    def test_partial_declarations_fail(self):
        self.assertIn("capabilities.knowledge.propose-edit: missing required key",
                      self.problems('[pack]\nname = "n"\ncommands = "x"\n[capabilities.knowledge]\nread = "supported"\n'))
        mixed = self.problems('[pack]\nname = "n"\ncommands = "x"\n' + self.KNOWLEDGE +
                              '[capabilities.ci]\ncheck-status = "supported"\nfailing-jobs = "supported"\n')
        self.assertIn("capabilities.change: missing required key", mixed)


class SharedStatusConfigTest(unittest.TestCase):
    """#1313 (docs/specs/shared-status.md §2, §7; S.2 config rows, S.6): the optional [status] table, the team-level
    rule, the optional status concern and its resolve refusals. Each refusal row names its valid control."""
    DEST = "https://github.com/acme/status/issues/5"
    TABLE = ('[status]\nenabled = true\ndestination = "%s"\ninstance_id = "alpha"\n'
             'decision_log = "https://github.com/acme/widgets/issues/985"\n' % DEST)
    EXTERNAL = AsyncLandTest.EXTERNAL
    BOUND = VALID.replace('[identities]', '[backends.status]\nname = "example"\n\n[identities]') + 'pack = "pack"\n'
    MAP = ('[status]\nread-records = "example-status read"\npublish-record = "example-status publish"\n\n'
           '[ids]\nstatus-destination = "https://example\\\\.test/boards/[0-9]+"\n')

    def run_pack(self, project_text, manifest=None, backend_map=None):
        """resolve with a pack dir (manifest and render/backends/example.toml); (code, lines, meta)."""
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "pack", "render", "backends"))
            for path, text in (("crew.toml", project_text), ("pack/manifest.toml", manifest or self.EXTERNAL),
                               ("pack/render/backends/example.toml", backend_map)):
                if text is not None:
                    with open(os.path.join(d, path), "w") as f:
                        f.write(text)
            project, out = os.path.join(d, "crew.toml"), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                code = cc.main(["resolve", "--project", project])
            meta = {}
            cc.resolve_profile(project, meta=meta)
            return code, [ln.replace(d + os.sep, "") for ln in out.getvalue().splitlines()], meta

    def test_status_table_rows(self):
        ok = (0, ["crew-config: OK (crew.toml)"])
        self.assertEqual(validate(VALID), ok)  # control: no [status] table at all
        self.assertEqual(validate(VALID + self.TABLE), ok)  # control: the full enabled table
        self.assertEqual(validate(VALID + "[status]\n"), ok)  # control: an empty table is off
        off = self.TABLE.replace("enabled = true", "enabled = false")
        rows = [  # (edit of the enabled table, expected problem)
            ("enabled = true", 'enabled = "yes"', "status.enabled: expected boolean, got string"),
            ("enabled = true", "enabled = true\nverbose = true", "status.verbose: unknown key"),
            ("enabled = true", "enabled = true\npublish_interval = \"300\"", "status.publish_interval: expected integer, got string"),
            ("enabled = true", "enabled = true\npublish_interval = true", "status.publish_interval: expected integer, got boolean"),
            ("enabled = true", "enabled = true\npublish_interval = 300.0", "status.publish_interval: expected integer, got float"),
            ("enabled = true", "enabled = true\npublish_interval = 59", "status.publish_interval: must be 60-3600 seconds, got 59"),
            ("enabled = true", "enabled = true\npublish_interval = 3601", "status.publish_interval: must be 60-3600 seconds, got 3601"),
            ("enabled = true", "enabled = true\nstale_after = 599", "status.stale_after: must be 2 x publish_interval (600) to 86400 seconds, got 599"),
            ("enabled = true", "enabled = true\nstale_after = 86401", "status.stale_after: must be 2 x publish_interval (600) to 86400 seconds, got 86401"),
            ("enabled = true", "enabled = true\npublish_interval = 600\nstale_after = 900", "status.stale_after: must be 2 x publish_interval (1200) to 86400 seconds, got 900"),
            ('"alpha"', '"Alpha"', 'status.instance_id: expected [a-z0-9][a-z0-9-]{0,62}, got "Alpha"'),
            ('"alpha"', '"-alpha"', 'status.instance_id: expected [a-z0-9][a-z0-9-]{0,62}, got "-alpha"'),
            ('"alpha"', '"%s"' % ("a" * 64), 'status.instance_id: expected [a-z0-9][a-z0-9-]{0,62}, got "%s"' % ("a" * 64)),
            ('"alpha"', "7", "status.instance_id: expected string, got integer"),
            ("widgets/issues/985", "widgets/pull/985", 'status.decision_log: expected an issue URL https://github.com/<owner>/<repo>/issues/<n>, got "https://github.com/acme/widgets/pull/985"'),
            ("widgets/issues/985", "widgets/issues/985?x=1", 'status.decision_log: expected an issue URL https://github.com/<owner>/<repo>/issues/<n>, got "https://github.com/acme/widgets/issues/985?x=1"'),
            ("status/issues/5", "status/pull/5", 'status.destination: "https://github.com/acme/status/pull/5" does not match the status-destination pattern'),
            ("https://github.com/acme/status", "https://<user>:<password>@github.com/acme/status", 'status.destination: "https://<user>:<password>@github.com/acme/status/issues/5" does not match'),
            ("status/issues/5", "status/issues/5/", 'status.destination: "https://github.com/acme/status/issues/5/" does not match'),
        ]
        for old, new, want in rows:
            with self.subTest(new=new):
                code, lines = validate(VALID + self.TABLE.replace(old, new, 1))
                self.assertEqual(code, 1, lines)
                self.assertTrue(any(ln.startswith("crew.toml:" + want) for ln in lines), (want, lines))
        for key in ("destination", "instance_id", "decision_log"):  # enabled needs all three; off needs none
            line = next(ln for ln in self.TABLE.splitlines() if ln.startswith(key))
            code, lines = validate(VALID + self.TABLE.replace(line + "\n", ""))
            self.assertEqual(code, 1, lines)
            self.assertIn("crew.toml:status.%s: missing; enabled = true needs destination, instance_id and "
                          "decision_log" % key, lines)
            self.assertEqual(validate(VALID + off.replace(line + "\n", "")), ok)

    def test_resolve_prints_status_only_when_a_layer_sets_it(self):
        code, plain = resolve(VALID)
        self.assertEqual(code, 0, plain)
        self.assertFalse([ln for ln in plain if ln.startswith(("status.", "backends.status", "ids.status"))], plain)
        code, lines = resolve(VALID + self.TABLE)
        self.assertEqual(code, 0, lines)
        added = [ln for ln in lines if ln not in plain]
        self.assertEqual(sorted(added), sorted([
            'status.enabled = true  # project', 'status.destination = "%s"  # project' % self.DEST,
            'status.instance_id = "alpha"  # project',
            'status.decision_log = "https://github.com/acme/widgets/issues/985"  # project',
            'status.publish_interval = 300  # core', 'status.stale_after = 900  # core',
            'backends.status.name = "github"  # default',
            'backends.status.capabilities.read-records = "supported"  # pack:github',
            'backends.status.capabilities.publish-record = "supported"  # pack:github',
            'ids.status-destination = "https://github\\\\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+/issues/[1-9][0-9]*"  '
            '# backend-map:github',
            'status.read-records = "\\"${MDSTACK_PYTHON:-python3}\\" \\"$MDSTACK_ROOT/connectors/github/status.py\\" '
            'read-records"  # pack:github',
            'status.publish-record = "\\"${MDSTACK_PYTHON:-python3}\\" \\"$MDSTACK_ROOT/connectors/github/status.py\\" '
            'publish-record"  # pack:github']))
        self.assertEqual([ln for ln in plain if ln not in lines], [])
        meta = {}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "crew.toml")
            with open(path, "w") as f:
                f.write(VALID + self.TABLE)
            cc.resolve_profile(path, meta=meta)
        self.assertIn("connectors/github/status.py", meta["status.read-records"][0])
        self.assertEqual(meta["status.publish-record"][1], "pack:github")

    def test_status_pack_declared_undeclared_emulated(self):
        undeclared = self.EXTERNAL.split("\n[capabilities.status]")[0] + "\n"
        emulated = self.EXTERNAL.replace('publish-record = "supported"', 'publish-record = "emulated (one comment)"')
        code, lines, meta = self.run_pack(self.BOUND + self.TABLE.replace(self.DEST, "https://example.test/boards/4"),
                                          backend_map=self.MAP)
        self.assertEqual(code, 0, lines)  # control: a pack declaring both operations, its map commands and pattern
        self.assertEqual(meta["status.publish-record"], ("example-status publish", "pack:example"))
        self.assertIn('ids.status-destination = "https://example\\\\.test/boards/[0-9]+"  # backend-map:example', lines)
        table = self.TABLE.replace(self.DEST, "https://example.test/boards/4")
        for manifest, enabled, want in (
                (undeclared, True, "backends.status.name: binds example, whose status.read-records is undeclared"),
                (emulated, True, "backends.status.name: binds example, whose status.publish-record is emulated (one comment)"),
                (undeclared, False, "backends.status.name: binds example, whose status.read-records is undeclared; "
                                    "a destination needs it supported")):
            text = table if enabled else table.replace("enabled = true", "enabled = false")
            code, lines, _ = self.run_pack(self.BOUND + text, manifest, self.MAP)
            self.assertEqual(code, 1, lines)
            self.assertTrue(any(want in ln for ln in lines), (want, lines))
        off = "[status]\ninstance_id = \"alpha\"\n"  # control: no destination, off: the concern is not checked
        self.assertEqual(self.run_pack(self.BOUND + off, undeclared, self.MAP)[0], 0)
        code, lines, _ = self.run_pack(self.BOUND + table, None, "[ids]\nstatus-destination = \"https://example\\\\.test/boards/[0-9]+\"\n")
        self.assertEqual(code, 1, lines)
        self.assertTrue(any("status.read-records: no command for the example status backend" in ln for ln in lines), lines)
        code, lines, _ = self.run_pack(self.BOUND + table, None, self.MAP.split("[ids]")[0])
        self.assertEqual(code, 1, lines)
        self.assertTrue(any("declares no [ids] status-destination pattern" in ln for ln in lines), lines)
        code, lines, _ = self.run_pack(self.BOUND + table, None, self.MAP.replace("example-status read", "x <dest>"))
        self.assertEqual(code, 1, lines)
        self.assertTrue(any("status.read-records: unfilled placeholder <dest>" in ln for ln in lines), lines)

    def test_manifest_status_capabilities_are_optional(self):
        ok = (0, ["crew-config: OK (crew.toml)"])
        self.assertEqual(validate(GITHUB_MANIFEST), ok)
        self.assertEqual(validate(GITHUB_MANIFEST.split("\n[capabilities.status]")[0] + "\n"), ok)  # old manifests
        code, lines = validate(GITHUB_MANIFEST.replace('read-records = "supported"\n', ""))
        self.assertEqual(code, 1, lines)
        self.assertIn("crew.toml:capabilities.status.read-records: missing required key", lines)
        self.assertNotIn("status", cc.OPERATIONS)  # not an <op:> token: bootstrap and a team's pack never bind it

    def test_team_file_status_is_team_level(self):
        table = self.TABLE.replace(self.DEST, self.DEST)
        merged, _, problems, _ = TeamFileTest.resolve(None, TEAM + "\n" + table, "#widgets")
        self.assertEqual(problems, [])  # control: [status] beside [team]
        self.assertEqual((merged["status"]["instance_id"], merged["backends"]["status"]["name"]), ("alpha", "github"))
        repo = TEAM.replace('repo = "acme/widgets"', 'repo = "acme/widgets"\nstatus = { enabled = false }')
        self.assertIn("ext.toml:repos.widgets.status: not allowed in a repo section", TeamFileTest.resolve(None, repo, "#widgets")[2][0])
        nested = TEAM.replace("[team]\n", "[team]\nstatus = { enabled = false }\n")
        self.assertEqual(TeamFileTest.resolve(None, nested, "#widgets")[2], ["ext.toml:team.status: unknown team key"])


if __name__ == "__main__":
    unittest.main()
