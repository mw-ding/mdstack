"""Checked verdict process tests: fake GitHub, real disposable Git, no real review or tag writes.

Every refusal asserts nonzero CLI exit and no review/tag effect; restored input proves the positive control.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

spec = importlib.util.spec_from_file_location("ack_fixture", Path(__file__).with_name("test-crew-ack.py"))
ack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ack)
FAKE = ack.FAKE.replace("elif a[:2] == ['issue', 'view']:", """elif a[:2] == ['pr', 'edit']:
    d['effects'].append({'argv': a})
    if not os.environ.get('FAIL_TAGS'):
        labels = {l['name'] for l in d['pr']['labels']}
        for flag, label in zip(a, a[1:]):
            if flag == '--add-label': labels.add(label)
            if flag == '--remove-label': labels.discard(label)
        d['pr']['labels'] = [{'name': l} for l in sorted(labels)]
    p.write_text(json.dumps(d))
elif a[0] == 'api' and '/files' in a[1]:
    print(json.dumps(d['files']))
elif a[0] == 'api' and '/commits/' in a[1]:
    print(json.dumps({'parents': d.get('parents', [])}))
elif a[0] == 'api' and '/compare/' in a[1]:
    print(json.dumps({'status': d.get('comparison', 'identical')}))
elif a[:2] == ['issue', 'view']:""")


class Verdict(ack.Ack):
    def setUp(self):
        ack.Ack.setUp(self)
        Path(self.tmp, 'bin', 'gh').write_text(FAKE)
        self.data['files'] = [{'filename': 'src/feature.py', 'status': 'modified'}]
        self.data['issue'] = {'labels': [], 'comments': [{'author': {'login': 'acme-bot'}, 'body':
            '<!-- crew:v1 role=coordinator pass=flavor issue=7 flavor=standard default=standard -->\n— 🔥 Ash (CTO) · codex · m'}]}
        self.rec['pass'] = 'validate'
        self.rec['verdict'] = str(Path(self.state, 'verdicts', 'pr9-%s-r1-validate.md' % self.head[:7]))
        self.review_file = Path(self.state, 'verdicts', 'pr9-%s-r1-review.md' % self.head[:7])
        self.review_file.parent.mkdir(parents=True)
        self.review_file.write_text(self.section('Review', 'review'))
        Path(self.rec['verdict']).write_text(self.section('Validation', 'validate'))
        self.save()

    def section(self, heading, pass_, result='pass', extra=''):
        return '## %s\n\nVerdict: %s\n\n<!-- crew:v1 role=reviewer-validator pass=%s pr=9 sha=%s base=%s round=1 verdict=%s%s -->\n' % (
            heading, result, pass_, self.head, self.base, result, extra)

    def verdict(self, *extra, **env):
        return self.crew('verdict', '9', '--head', self.head, '--base', self.base, '--round', '1',
                         '--actor', self.actor, '--project', self.project, *extra, **env)

    def refused(self, *extra, **env):
        r = self.verdict(*extra, **env)
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('refusing', r.stdout)
        self.assertEqual(self.effects(), [])
        return r

    def test_complete_native_comment_tags_and_duplicate_refusal(self):
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        review, tags = self.effects()
        self.assertIn('event=COMMENT', review['argv'])
        self.assertIn('commit_id=' + self.head, review['argv'])
        body = review['body']
        self.assertEqual(body.count('<!-- crew:v1'), 3)
        self.assertEqual(body.split('\n\n')[1:3], ['**Status:** 🟢 passed\n**Landing risk:** 🟡 medium · runtime code changed; CI pending',
                                                 'TL;DR: pass.'])
        self.assertIn('pass=verdict pr=9 sha=%s base=%s round=1 verdict=pass' % (self.head, self.base), body)
        self.assertTrue(body.endswith('— 🔎 Vera (Reviewer-validator) · claude-code · sonnet\n'))
        self.assertIn('Run:', body)
        self.assertIn('crew:approved', tags['argv'])
        self.assertNotIn('crew:escalated', tags['argv'])
        self.assertIn('mdstack: config', r.stderr)
        if os.environ.get('MDSTACK_HELPER_TRANSCRIPT'):
            Path(os.environ['MDSTACK_HELPER_TRANSCRIPT']).write_text(
                'create: native review event=COMMENT, commit_id=<full-head>, markers=review/validate/verdict\n'
                'update: crew:approved present; crew:changes and crew:in-review absent (read back)\n'
                'duplicate: CLI exit 2; no additional review/tag writes\n'
                'No delete endpoint: these helpers post verdicts/tags; deletion is outside their command surface.\n')
        again = self.verdict()
        self.assertEqual(again.returncode, 2, again.stdout + again.stderr)
        self.assertIn('already completed', again.stdout)
        self.assertEqual(len(self.effects()), 2)

    def test_failed_validation_is_changes(self):
        Path(self.rec['verdict']).write_text(self.section('Validation', 'validate', 'changes'))
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('pass=verdict pr=9 sha=%s base=%s round=1 verdict=changes' % (self.head, self.base), self.effects()[0]['body'])
        self.assertIn('crew:changes', self.effects()[1]['argv'])

    def test_review_changes_has_two_markers_no_validation_session(self):
        self.rec['pass'] = 'review'
        self.save()
        self.review_file.write_text(self.section('Review', 'review', 'changes') + '\nskipped: review failed\n')
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.effects()[0]['body'].count('<!-- crew:v1'), 2)
        self.assertEqual(len(list(Path(self.state, 'runs').glob('*.json'))), 1)

    def test_section_and_marker_refusals_then_restored_pass(self):
        original = self.review_file.read_text()
        for invalid in ('', original + original, original.replace('pr=9', 'pr=10'),
                        original.replace(self.head, self.head[:7]), original.replace(self.base, 'b' * 40),
                        original.replace('round=1', 'round=2'), original.replace('pass=review', 'pass=verdict'),
                        original.replace('verdict=pass', 'verdict=n/a'), original.replace('## Review', '## Validation'),
                        original.replace('Verdict: pass', 'Verdict: changes')):
            with self.subTest(invalid=invalid[:80]):
                self.review_file.write_text(invalid)
                self.refused()
        self.review_file.write_text(original)
        self.assertEqual(self.verdict().returncode, 0)

    def test_missing_validation_and_invalid_review_changes_refuse(self):
        validation = Path(self.rec['verdict'])
        original = validation.read_text()
        validation.unlink()
        self.refused()
        validation.write_text(original)
        self.review_file.write_text(self.section('Review', 'review', 'changes'))
        self.refused()
        self.rec['pass'] = 'review'
        self.save()
        self.refused()

    def test_wrong_actor_run_phase_engine_and_identity_refuse(self):
        for patch in ({'role': 'builder'}, {'engine': 'codex'}, {'head': 'b' * 40}, {'pass': 'build'},
                      {'args': {'pr': 10, 'round': 1}}, {'args': {'pr': 9, 'round': 2}}):
            with self.subTest(patch=patch):
                old = dict(self.rec)
                self.rec.update(patch)
                self.save()
                self.refused()
                self.rec = old
        self.save()
        self.refused(POST_LOGIN='other')
        self.refused('--actor', 'foreign')
        self.refused('--base', 'abcdef0')
        self.refused('--base', 'b' * 40)
        self.refused('--round', '0')

    def test_live_hold_closed_pause_precheck_and_moved_head_refuse(self):
        for patch in ({'isDraft': True}, {'state': 'CLOSED'}, {'headRefOid': 'b' * 40},
                      {'labels': [{'name': 'crew:hold'}]}, {'labels': [{'name': 'crew:escalated'}]}):
            old = dict(self.data['pr'])
            self.data['pr'].update(patch)
            self.save()
            self.refused()
            self.data['pr'] = old
        self.save()
        self.refused(MOVE_HEAD='1')
        self.save()
        Path(self.state, 'pause.json').write_text('{"since":"now"}')
        self.refused()
        Path(self.state, 'pause.json').unlink()
        with open(self.project, 'a') as out:
            out.write('\n[builder.precheck]\nenabled = true\n')
        self.refused()

    def skip(self):
        self.rec['pass'] = 'review'
        self.data['files'] = [{'filename': 'docs/guide.md', 'status': 'modified'}]
        self.review_file.write_text(self.section('Review', 'review') + '\n' +
                                   self.section('Validation', 'validate', extra=' validation=skipped') +
                                   '\nskipped (flavor standard)\nReason: wording only; no observable behaviour changes.\n')
        self.save()

    def test_valid_skip_has_validation_marker_without_validator(self):
        self.skip()
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('validation=skipped', self.effects()[0]['body'])

    def test_behaviour_always_unjustified_and_failed_skip_refuse(self):
        self.skip()
        self.data['files'] = [{'filename': 'src/feature.py'}]
        self.save()
        self.refused()
        self.skip()
        original = self.review_file.read_text()
        for invalid in (original.replace('Reason:', 'Explanation:'), original.replace('verdict=pass', 'verdict=changes'),
                        original.replace('validation=skipped', 'validation=other')):
            self.review_file.write_text(invalid)
            self.refused()
        self.skip()
        self.data['issue']['comments'][0]['body'] = self.data['issue']['comments'][0]['body'].replace('flavor=standard', 'flavor=thorough')
        self.save()
        self.refused()

    def test_path_tightening_including_rename_source_refuses_skip(self):
        self.skip()
        with open(self.project, 'a') as out:
            out.write('\n[[flavor.classes]]\npaths = ["docs/private/**"]\nflavor = "thorough"\n')
        self.data['files'][0]['previous_filename'] = 'docs/private/guide.md'
        self.save()
        self.refused()

    def test_reset_and_rereview_bindings(self):
        reset = {'author': {'login': 'acme-bot'}, 'submittedAt': '2026-11-13T00:00:01Z', 'body':
            '<!-- crew:v1 role=coordinator pass=steer cmd=resume pr=9 sha=%s cmd-id=reset -->\n— 🔥 Ash (CTO) · codex · m' % self.head}
        self.data['pr']['reviews'] = [reset]
        self.save()
        self.refused()
        self.data['pr']['reviews'] = [dict(reset, body=reset['body'].replace('cmd=resume', 'cmd=rereview'))]
        self.save()
        self.refused()
        self.rec['rereview_id'] = 'reset'
        self.rec['start'] = '2026-11-13T00:00:02Z'
        self.save()
        self.assertEqual(self.verdict().returncode, 0)

    def test_fresh_reset_allows_same_head_round_one(self):
        self.data['pr']['reviews'] = [
            {'author': {'login': 'acme-reviewer'}, 'body': self.section('Review', 'verdict', 'changes') + '\n— 🔎 Vera (Reviewer-validator) · claude-code · sonnet'},
            {'author': {'login': 'acme-bot'}, 'submittedAt': '2026-11-12T23:59:59Z', 'body':
             '<!-- crew:v1 role=coordinator pass=steer cmd=resume pr=9 sha=%s cmd-id=reset -->\n— 🔥 Ash (CTO) · codex · m' % self.head}]
        self.save()
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_lost_response_readback_and_tag_failure_never_repost(self):
        r = self.verdict(LOSE_RESPONSE='1')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('confirmed by readback', r.stdout)
        self.assertEqual(len(self.effects()), 2)
        self.data['effects'] = []
        self.data['pr']['reviews'] = []
        self.save()
        r = self.verdict(FAIL_TAGS='1')
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn('tag readback failed', r.stdout)
        self.assertEqual(self.verdict().returncode, 2)
        self.assertEqual(len(self.effects()), 2)

    def test_cap_changes_escalates_in_same_tag_write(self):
        self.data['issue']['comments'][0]['body'] = self.data['issue']['comments'][0]['body'].replace('standard', 'quick')
        with open(self.project, 'a') as out:
            out.write('\n[flavor]\nname = "quick"\n[flavor.custom.quick]\nbase = "standard"\ncaps = [1, 1]\n')
        Path(self.rec['verdict']).write_text(self.section('Validation', 'validate', 'changes'))
        self.save()
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn('crew:escalated', self.effects()[1]['argv'])
        self.assertIn('\n\n**Status:** 🔴 escalated\n**Landing risk:** 🔴 high · open blocking findings; round cap reached\n\nTL;DR: changes.',
                      self.effects()[0]['body'])

    def test_summary_card_is_advisory_and_reads_label_paths_and_ci(self):
        self.data['pr']['labels'].append({'name': 'crew:sensitive'})
        self.data['pr']['statusCheckRollup'] = [{'__typename': 'CheckRun', 'status': 'COMPLETED', 'conclusion': 'SUCCESS'}]
        self.data['files'] = [{'filename': 'docs/guide.md', 'status': 'modified'}]
        self.save()
        r = self.verdict()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        review, tags = self.effects()
        self.assertIn('\n\n**Status:** 🟢 passed\n**Landing risk:** 🟡 medium · crew:sensitive\n\nTL;DR: pass.', review['body'])
        self.assertIn('<!-- crew:v1 role=reviewer-validator pass=verdict pr=9 sha=%s base=%s round=1 verdict=pass -->' % (self.head, self.base),
                      review['body'])
        self.assertIn('crew:approved', tags['argv'])

    def test_cli_negative_controls_report_no_effect(self):
        self.review_file.write_text(self.review_file.read_text().replace('round=1', 'round=2'))
        r = self.refused()
        self.review_file.write_text(self.section('Review', 'review'))
        restored = self.verdict()
        self.assertEqual(restored.returncode, 0, restored.stdout + restored.stderr)
        if os.environ.get('MDSTACK_HELPER_CONTROL'):
            Path(os.environ['MDSTACK_HELPER_CONTROL']).write_text(
                'bad input: section round=2, live round=1; CLI exit %s; review/tag writes=0\n'
                'restored: section round=1; CLI exit %s; review/tag writes=2\n' % (r.returncode, restored.returncode))

    def test_ownership_refusal_has_no_effect(self):
        path = Path(self.project)
        path.write_text(path.read_text().replace('[repo]', '[repo]\ncontrol_item = 1').replace('[runtime]', '[runtime]\ninstance = "test"'))
        self.refused()


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(Verdict(name) for name in Verdict.__dict__ if name.startswith('test_'))


if __name__ == '__main__':
    unittest.main()
