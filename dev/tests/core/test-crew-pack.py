"""Pack plug-in tests (#1236): pack.toml discovery and resolve, version refusal, floor refusal, commit pin and the
actions/ conformance kit, against the fixture pack dev/tests/core/fixtures/packs/example (a fake connector and harness)."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CREW = os.path.join(ROOT, "cli", "mdstack")
FIXTURE = os.path.join(HERE, "fixtures", "packs", "example")
FAKE_VCS = os.path.join(HERE, "fixtures", "vcs", "fake-vcs.py")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cc = load("crew_config", "core/crew-config.py")
pk = load("crew_pack", "core/crew-pack.py")
contract = load("crew_actions_contract", "actions/contract.py")
CONCERNS = [c for c in cc.OPERATIONS if c not in cc.OPTIONAL_CONCERNS]
PROJECT = """\
[repo]
owner = "example-org"
name = "widgets"

[runtime]
name = "tmux"
options = { builders = 3 }

%s

[identities]
owners = ["example-owner"]
coordinator = { gh_user = "example-bot" }
builder = { gh_user = "example-bot" }
reviewer = { gh_user = "example-reviewer" }
synthesizer = { gh_user = "example-bot" }

[engines]
coordinator = "codex"
trivial = { order = ["claude-code/sonnet"] }
default = { order = ["example-agent/model-1", "claude-code/sonnet"], effort = "medium" }
deep = { order = ["codex/gpt-6.1-sol"] }

[paths]
state_dir = "/srv/crew-state"
worktree_root = "/srv/wt"
pack = "pack"
""" % "\n".join('[backends.%s]\nname = "%s"' % (c, "example-tracker" if c == "tracker" else "github") for c in CONCERNS)


class PackCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="crew-pack-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.pack = os.path.join(self.tmp, "pack")
        shutil.copytree(FIXTURE, self.pack)
        self.project = os.path.join(self.tmp, "crew.toml")
        self.write("../crew.toml", PROJECT)

    def write(self, rel, text):
        path = os.path.join(self.pack, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def edit(self, rel, old, new):
        with open(os.path.join(self.pack, rel)) as f:
            text = f.read()
        self.assertIn(old, text)
        self.write(rel, text.replace(old, new))

    def loaded(self):
        return pk.load(self.pack, cc, cc.harnesses)


class Discovery(PackCase):
    def test_registry_lists_builtins_then_pack_items(self):
        reg, problems = pk.discover(cc, cc.harnesses, self.pack)
        self.assertEqual(problems, [])
        self.assertEqual(reg["connectors"]["github"][0], "core")
        self.assertEqual(reg["harnesses"]["claude-code"][0], "core")
        self.assertEqual(reg["skills"]["review"][0], "core")
        for kind, name in (("connectors", "example-tracker"), ("harnesses", "example-agent"),
                           ("skills", "example-review")):
            self.assertEqual(reg[kind][name][0], "pack:example", kind)
        self.assertEqual(reg["environments"]["tmux"][0], "core+pack:example")

    def test_resolve_layers_pack_connector_harness_and_environment_defaults(self):
        profile, prov, problems, layers = cc.resolve_profile(self.project)
        self.assertEqual(problems, [])
        self.assertEqual(layers, ["core", "default", "pack", "org", "project"])
        self.assertEqual(profile["backends"]["tracker"]["name"], "example-tracker")
        self.assertEqual(prov["backends.tracker.capabilities.create-item"], "pack:example-tracker")
        self.assertEqual((profile["runtime"]["options"]["idle_builder_ttl"], prov["runtime.options.idle_builder_ttl"]),
                         (900, "pack"))
        self.assertEqual((profile["flavor"]["name"], prov["flavor.name"]), ("thorough", "org"))
        self.assertIn("example-agent", cc.harnesses.LAUNCHABLE)
        self.assertEqual(cc.harnesses.ENGINE_CMD["example-agent"], "example-agent")
        self.assertNotIn("example-agent", cc.harnesses.INSTALLS)

    def test_project_layer_still_wins_over_the_pack(self):
        with open(self.project, "a") as f:
            f.write('\n[flavor]\nname = "standard"\n')
        profile, prov, problems, _ = cc.resolve_profile(self.project)
        self.assertEqual(problems, [])
        self.assertEqual((profile["flavor"]["name"], prov["flavor.name"]), ("standard", "project"))

    def test_without_the_pack_its_names_are_unknown(self):
        os.remove(os.path.join(self.pack, "pack.toml"))
        problems = cc.resolve_profile(self.project)[2]
        self.assertTrue(any("example-tracker" in p for p in problems), problems)

    def test_pack_names_never_shadow_builtins(self):
        shutil.copytree(os.path.join(self.pack, "harnesses", "example-agent"),
                        os.path.join(self.pack, "harnesses", "codex"))
        self.edit("pack.toml", 'harnesses = ["example-agent"]', 'harnesses = ["example-agent", "codex"]')
        pack, problems = self.loaded()
        self.assertIsNone(pack)
        self.assertTrue(any("'codex' shadows a built-in harness" in p for p in problems), problems)

    def test_missing_item_and_bad_skill_frontmatter_refuse(self):
        self.edit("pack.toml", 'skills = ["example-review"]', 'skills = ["example-review", "absent"]')
        self.edit("skills/example-review/SKILL.md", "name: example-review", "name: other")
        problems = self.loaded()[1]
        self.assertTrue(any("'absent': missing skills/absent/SKILL.md" in p for p in problems), problems)
        self.assertTrue(any("frontmatter needs name: example-review" in p for p in problems), problems)

    def test_crew_pack_list_cli(self):
        out = subprocess.run([sys.executable, CREW, "pack", "list", "--project", self.project],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("connectors example-tracker pack:example ", out.stdout)
        self.assertIn("harnesses claude-code core harnesses/claude-code/adapter.py", out.stdout)


class Absence(PackCase):
    """#1411: optional pack inputs left out, resolved through paths.pack discovery (never --pack-manifest)."""

    def resolve_lines(self, control_item):
        with open(self.project) as f:
            text = f.read()
        with open(self.project, "w") as f:
            f.write(text.replace("[repo]\n", "[repo]\ncontrol_item = %s\n" % control_item)
                    .replace("[runtime]\n", '[runtime]\ninstance = "laptop"\n'))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cc.main(["resolve", "--project", self.project])
        with open(self.project, "w") as f:
            f.write(text)
        return code, out.getvalue()

    def test_pack_without_profile_toml_keeps_its_items_and_the_core_flavor(self):
        os.remove(os.path.join(self.pack, "profile.toml"))
        reg, problems = pk.discover(cc, cc.harnesses, self.pack)
        self.assertEqual(problems, [])
        for kind, name in (("connectors", "example-tracker"), ("harnesses", "example-agent"),
                           ("skills", "example-review")):
            self.assertEqual(reg[kind][name][0], "pack:example", kind)
        profile, prov, problems, layers = cc.resolve_profile(self.project)
        self.assertEqual(problems, [])
        self.assertEqual(layers, ["core", "default", "pack", "project"])
        self.assertEqual(profile["backends"]["tracker"]["name"], "example-tracker")
        self.assertEqual(prov["backends.tracker.capabilities.create-item"], "pack:example-tracker")
        self.assertEqual((profile["runtime"]["options"]["idle_builder_ttl"], prov["runtime.options.idle_builder_ttl"]),
                         (900, "pack"))
        self.assertEqual((profile["flavor"]["name"], prov["flavor.name"]), ("standard", "core (unset: flagged)"))

    def test_pack_connector_without_a_render_map_keeps_default_ids(self):
        self.assertFalse(os.path.exists(os.path.join(self.pack, "render")))
        code, out = self.resolve_lines("7")
        self.assertEqual(code, 0, out)
        self.assertIn('ids.item = "[1-9][0-9]*"  # core\nids.change = "[1-9][0-9]*"  # core\n', out)
        code, out = self.resolve_lines('"OPS-1042"')
        self.assertEqual(code, 1)
        self.assertIn("repo.control_item: a string id needs the tracker backend's [ids] item pattern", out)
        self.write("render/backends/example-tracker.toml", '[ids]\nitem = "[A-Z][A-Z0-9]+-[0-9]+"\n')
        code, out = self.resolve_lines('"OPS-1042"')  # the same discovery path does read a map once present
        self.assertEqual(code, 0, out)
        self.assertIn('ids.item = "[A-Z][A-Z0-9]+-[0-9]+"  # backend-map:example-tracker\n', out)


class Version(PackCase):
    def test_framework_range(self):
        pack = self.loaded()[0]
        self.assertIsNone(pk.compatible(pack, "v5.3.0"))
        self.assertIn("v6.0.0 is incompatible", pk.compatible(pack, "v6.0.0"))
        self.assertIn("v4.9.9 is incompatible", pk.compatible(pack, "v4.9.9"))
        self.assertIn("not a stable release tag", pk.compatible(pack, "v5.3.0-rc.1"))
        self.assertIn("not a stable release tag", pk.compatible(pack, "a" * 40))

    def resolve_lines(self, *extra):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cc.main(["resolve", "--project", self.project, *extra])
        return code, out.getvalue().splitlines()

    def test_resolve_prints_pack_toml_version(self):  # #1350
        self.edit("pack.toml", 'version = "0.1.0"', 'version = "1.2.3"')
        code, lines = self.resolve_lines()
        self.assertEqual(code, 0, lines)
        self.assertEqual(lines[-1], 'pack.version = "1.2.3"  # pack:example')
        self.edit("pack.toml", 'version = "1.2.3"\n', '')
        code, lines = self.resolve_lines()
        self.assertEqual(code, 0, lines)
        self.assertFalse(any(ln.startswith("pack.version") for ln in lines), lines)

    def test_external_manifest_version_wins_else_pack_toml(self):
        manifest = os.path.join(self.tmp, "manifest.toml")
        with open(os.path.join(ROOT, "connectors", "github", "manifest.toml")) as f:
            text = f.read().replace('name = "github"', 'name = "example-ext"')

        def run(version):
            with open(manifest, "w") as f:
                f.write(text.replace("[pack]\n", '[pack]\nmdstack_version = "v5.0.0"\n%s' % version))
            code, lines = self.resolve_lines("--pack-manifest", manifest)
            self.assertEqual(code, 0, lines)
            return [ln for ln in lines if ln.startswith("pack.")]
        self.assertEqual(run('version = "9.9.9"\n'), ['pack.version = "9.9.9"  # pack:example-ext'])
        self.assertEqual(run(""), ['pack.version = "0.1.0"  # pack:example'])  # versionless external: pack.toml

    def test_malformed_framework_refuses(self):
        self.edit("pack.toml", 'framework = ">=5.0.0, <6.0.0"', 'framework = "5.x"')
        self.assertTrue(any("pack.framework: expected comparators" in p for p in self.loaded()[1]))

    def test_check_cli_refuses_an_incompatible_framework(self):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(pk.main(["check", self.pack, "--framework", "v5.3.0"]), 0)
            self.assertEqual(pk.main(["check", self.pack, "--framework", "v6.1.0"]), 1)
        self.assertIn("pack example supports mdstack >=5.0.0, <6.0.0; v6.1.0 is incompatible", out.getvalue())


class Floors(PackCase):
    def refused(self, rel, text, expect):
        self.write(rel, text)
        pack, problems = self.loaded()
        self.assertIsNone(pack)
        self.assertTrue(any(expect in p for p in problems), problems)
        self.assertTrue(any(expect in p for p in cc.resolve_profile(self.project)[2]))

    def test_tightening_is_accepted(self):
        self.write("profile.toml", '[flavor]\nname = "thorough"\n[sensitive]\npaths = ["infra/**"]\n')
        self.assertEqual(self.loaded()[1], [])

    def test_floor_control_is_refused(self):
        self.refused("environments/tmux/defaults.toml", '[runtime]\nname = "tmux"\noptions = { hold_label_blocks = false }\n',
                     "floor F5: the owner can always hold; a pack may tighten rules, never loosen a core floor")

    def test_backend_selector_named_like_a_floor_control_is_accepted(self):
        """#1325: [backends.ci] selects the CI backend; only the flavor table and runtime.options hold floor controls."""
        self.write("profile.toml", '[flavor]\nname = "thorough"\n[backends.ci]\nname = "example-tracker"\n')
        self.write("environments/tmux/defaults.toml", '[runtime]\nname = "tmux"\n[backends.ci]\nname = "example-tracker"\n')
        self.assertEqual(self.loaded()[1], [])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(pk.main(["check", self.pack]), 0)
        self.assertIn("crew-pack: OK (example", out.getvalue())

    def test_custom_flavor_ci_waiver_is_refused(self):
        self.refused("profile.toml", '[flavor]\nname = "strict"\n[flavor.custom.strict]\nbase = "thorough"\n'
                     'ci_waiver = true\n', "flavor.custom.strict.ci_waiver: floor F1: CI never waived")

    def test_merge_grant_is_refused(self):
        self.refused("profile.toml", '[runtime]\nname = "tmux"\noptions = { merge_grant = "approved" }\n',
                     "a merge grant is the owner's, never a pack's")

    def test_release_delegation_is_refused(self):
        self.refused("profile.toml", '[runtime]\nname = "tmux"\noptions = { release_delegation = "cuts https://x/1" }\n',
                     "a release delegation is the owner's, never a pack's")

    def test_lower_flavor_is_refused(self):
        self.refused("profile.toml", '[flavor]\nname = "fast"\n',
                     "flavor.name: fast loosens the core default flavor standard (validation")

    def test_lower_custom_and_class_flavor_is_refused(self):
        self.refused("profile.toml", '[flavor]\nname = "standard"\n[flavor.custom.quick]\nbase = "standard"\n'
                     'review = "light"\n[[flavor.classes]]\npaths = ["docs/**"]\nflavor = "quick"\n',
                     "flavor.custom.quick: loosens the core default flavor standard (review)")

    def test_custom_flavor_split_across_pack_layers_is_refused(self):
        """Review r1 (#1265): defined in the environment defaults, selected in profile.toml."""
        self.write("profile.toml", '[flavor]\nname = "quick"\n')
        self.refused("environments/tmux/defaults.toml", '[runtime]\nname = "tmux"\n[flavor.custom.quick]\n'
                     'base = "standard"\nvalidation = "off"\nevidence = "inline"\nmerge = "auto"\n',
                     "flavor.custom.quick: loosens the core default flavor standard (validation, evidence, merge)")

    def test_custom_flavor_defined_in_parts_is_refused(self):
        self.write("environments/tmux/defaults.toml", '[runtime]\nname = "tmux"\n[flavor.custom.quick]\nbase = "fast"\n'
                   'validation = "behaviour"\nevidence = "typed"\nmerge = "docs"\nprecheck = "on"\n'
                   'lighter_lane = "docs"\ncaps = [3, 3]\n')
        self.refused("profile.toml", '[flavor]\nname = "quick"\n[flavor.custom.quick]\nbase = "fast"\n',
                     "flavor.custom.quick: loosens the core default flavor standard")

    def test_selection_the_pack_does_not_define_is_refused(self):
        self.refused("profile.toml", '[flavor]\nname = "elsewhere"\n',
                     "flavor.name: elsewhere is neither a preset nor a flavor the pack defines")

    def test_strict_custom_flavor_split_across_layers_is_accepted(self):
        self.write("environments/tmux/defaults.toml", '[runtime]\nname = "tmux"\n[flavor.custom.strict]\n'
                   'base = "thorough"\n')
        self.write("profile.toml", '[flavor]\nname = "strict"\n')
        self.assertEqual(self.loaded()[1], [])


class CommitPin(PackCase):
    def git(self, *argv):
        subprocess.run(["git", "-C", self.pack, "-c", "user.name=t", "-c", "user.email=t@example.invalid", *argv],
                       check=True, capture_output=True)

    def test_clean_checkout_pins_its_head(self):
        with self.assertRaisesRegex(ValueError, "not a git checkout"):
            pk.commit(self.pack)
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "pack")
        head = subprocess.run(["git", "-C", self.pack, "rev-parse", "HEAD"], capture_output=True, text=True).stdout
        self.assertEqual(pk.commit(self.pack), head.strip())
        self.write("profile.toml", "")
        with self.assertRaisesRegex(ValueError, "uncommitted changes"):
            pk.commit(self.pack)

    def test_declared_vcs_pins_a_non_git_checkout(self):
        """#1326: a pack in another version control tool's working copy declares its clean check and commit read."""
        with open(os.path.join(self.pack, "pack.toml"), "a") as f:
            f.write("\n[vcs]\nclean = %s\ncommit = %s\n" % (json.dumps([sys.executable, FAKE_VCS, "status"]),
                                                             json.dumps([sys.executable, FAKE_VCS, "rev"])))
        self.assertEqual(self.loaded()[1], [])
        with self.assertRaisesRegex(ValueError, "is not a .* checkout"):
            pk.commit(self.pack)
        subprocess.run([sys.executable, FAKE_VCS, "commit"], cwd=self.pack, check=True)
        with open(os.path.join(self.pack, ".fakevcs", "state.json")) as f:
            rev = json.load(f)["rev"]
        self.assertEqual(pk.commit(self.pack), rev)
        self.write("profile.toml", "")
        with self.assertRaisesRegex(ValueError, "uncommitted changes"):
            pk.commit(self.pack)

    def test_malformed_vcs_table_is_refused(self):
        with open(os.path.join(self.pack, "pack.toml"), "a") as f:
            f.write('\n[vcs]\nclean = "hg status"\n')
        problems = self.loaded()[1]
        self.assertTrue(any("vcs.clean: expected list of strings" in p for p in problems), problems)
        self.assertTrue(any("vcs.commit: missing required key" in p for p in problems), problems)
        with self.assertRaisesRegex(ValueError, r"\[vcs\] needs clean and commit commands"):
            pk.commit(self.pack)


class ExportLock(PackCase):
    """#1962: an exported pack outside version control pins through a pack.lock that bootstrap verifies."""
    git = CommitPin.git

    def setUp(self):
        super().setUp()
        self.git("init", "-q")
        self.git("add", "-A")
        self.git("commit", "-qm", "pack")
        self.head = subprocess.run(["git", "-C", self.pack, "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip()
        self.export = os.path.join(self.tmp, "export")
        shutil.copytree(self.pack, self.export, ignore=shutil.ignore_patterns(".git"))

    def test_verified_export_pins_the_locked_commit(self):
        pk.write_lock(self.pack, self.export)
        self.assertEqual(pk.commit(self.export), self.head)

    def test_changed_added_or_removed_file_is_refused_naming_it(self):
        def append(path, mode="a"):
            with open(path, mode) as f:
                f.write("x")
        pk.write_lock(self.pack, self.export)
        for change, rel, state in ((append, "profile.toml", "changed"),
                                   (lambda p: append(p, "w"), "extra.md", "not locked"),
                                   (os.remove, "pack.toml", "missing")):
            with self.subTest(state=state):
                backup = os.path.join(self.tmp, "backup")
                shutil.copytree(self.export, backup)
                change(os.path.join(self.export, rel))
                with self.assertRaisesRegex(ValueError, "does not match its pack.lock: %s is %s" % (rel, state)):
                    pk.commit(self.export)
                shutil.rmtree(self.export)
                os.rename(backup, self.export)

    def test_plain_directory_without_a_lock_keeps_the_refusal(self):
        with self.assertRaisesRegex(ValueError, "is not a git checkout; install pins a pack at a commit"):
            pk.commit(self.export)

    def test_tampered_lock_is_refused(self):
        lock = pk.write_lock(self.pack, self.export)
        with open(lock) as f:
            text = f.read()
        with open(lock, "w") as f:
            f.write(re.sub(r'("profile.toml" = ")[0-9a-f]+', r"\g<1>" + "0" * 64, text))
        with self.assertRaisesRegex(ValueError, "pack.lock needs commit, sha256 and files matching its sha256"):
            pk.commit(self.export)

    def test_export_with_an_uninstalled_declared_vcs_verifies(self):
        with open(os.path.join(self.export, "pack.toml"), "a") as f:
            f.write('\n[vcs]\nclean = ["no-such-vcs-tool", "status"]\ncommit = ["no-such-vcs-tool", "rev"]\n')
        with self.assertRaisesRegex(ValueError, "failed to start"):
            pk.commit(self.export)
        files = pk.file_digests(self.export)
        with open(os.path.join(self.export, pk.LOCK), "w") as f:
            f.write('commit = "abc"\nsha256 = "%s"\n[files]\n%s' % (pk.tree_digest(files), "".join(
                "%s = %s\n" % (json.dumps(p), json.dumps(h)) for p, h in files.items())))
        self.assertEqual(pk.commit(self.export), "abc")

    def test_lock_cli_refuses_an_export_that_differs_from_the_checkout(self):
        with open(os.path.join(self.export, "profile.toml"), "a") as f:
            f.write("# edited\n")
        script = os.path.join(ROOT, "core", "crew-pack.py")
        bad = subprocess.run([sys.executable, script, "lock", self.pack, self.export], capture_output=True, text=True)
        self.assertEqual((bad.returncode, bad.stdout), (1, ""))
        self.assertIn("profile.toml differs from checkout", bad.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.export, pk.LOCK)))
        shutil.copy(os.path.join(self.pack, "profile.toml"), os.path.join(self.export, "profile.toml"))
        ok = subprocess.run([sys.executable, script, "lock", self.pack, self.export], capture_output=True, text=True)
        self.assertEqual((ok.returncode, ok.stderr), (0, ""), ok.stdout)
        self.assertEqual(pk.commit(self.export), self.head)


class Conformance(PackCase):
    def run_kit(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = contract.main([self.pack])
        return code, out.getvalue()

    def test_fixture_pack_passes(self):
        code, out = self.run_kit()
        self.assertEqual(code, 0, out)
        self.assertIn("ok connector example-tracker: unknown action is refused as usage", out)
        self.assertIn("ok connector example-tracker: land acquire keeps the envelope", out)
        self.assertIn("ok harness example-agent: role launch runs the executable", out)
        self.assertRegex(out, r"mdstack pack test: OK \(\d+ checks, 0 failed\)")

    def test_crew_pack_test_cli(self):
        out = subprocess.run([sys.executable, CREW, "pack", "test", self.pack],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_contract_breaks_fail(self):
        action = "connectors/example-tracker/action.py"
        for old, new, expect in (
                ('EXIT = {"completed": 0, "refused": 6,', 'EXIT = {"completed": 0, "refused": 7,',
                 "outcome 'refused' disagrees with exit 7 (failed)"),
                ('DECLARED = {"read": "supported", "claim": "emulated"}', 'DECLARED = {"read": "supported"}',
                 "--capabilities equals the declaration"),
                ('print(json.dumps(record) if', 'print("note");print(json.dumps(record) if',
                 "stdout is not exactly one JSON object")):
            with self.subTest(expect=expect):
                shutil.copy(os.path.join(FIXTURE, action), os.path.join(self.pack, action))
                self.edit(action, old, new)
                code, out = self.run_kit()
                self.assertEqual(code, 1)
                self.assertIn(expect, out)

    def test_harness_break_fails(self):
        self.edit("harnesses/example-agent/adapter.py", 'return [EXECUTABLE, "--model", model,',
                  'return ["other", "--model", model,')
        code, out = self.run_kit()
        self.assertEqual(code, 1)
        self.assertIn("FAIL harness example-agent: role launch runs the executable", out)

    def test_builtin_harness_adapters_keep_the_same_interface(self):
        for name, mod in cc.harnesses.ADAPTERS.items():
            if name in cc.harnesses.PACKED:
                continue
            with self.subTest(harness=name):
                self.assertEqual([(c, p) for c, p in contract.harness(name, mod) if p], [])

    def test_builtin_connector_manifest_passes(self):
        manifest = os.path.join(ROOT, "connectors", "github", "manifest.toml")
        self.assertEqual([(c, p) for c, p in contract.connector("github", manifest, cc) if p], [])

    def test_action_table_matches_cli_md(self):
        with open(os.path.join(ROOT, "actions", "cli.md")) as f:
            rows = re.findall(r"^\| `mdstack action ([a-z-]+)` \| ([^|]*)\|", f.read(), re.M)
        self.assertEqual({name: re.findall(r"`([a-z]+)`", ops) for name, ops in rows}, contract.ACTIONS)


if __name__ == "__main__":
    unittest.main()
