import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

import completion
import mission


class Mode1(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root/'source.py').write_text('original')
        self.state = {'workspace': str(root), 'mission_id': 'test', 'status': 'active', 'plan_revision': 0,
            'tasks': [{'id': 'component', 'status': 'completed', 'content': 'existing component',
                       'done_when': 'component proof', 'evidence': ['old-proof.json']}]}
        self.receipt = {'path': 'proof.json', 'sha256': 'new-proof', 'bytes': 10}
        completion.configure(self.state, {'mode': 1, 'source_paths': ['source.py'],
            'requirements': [{'id': 'integration', 'done_when': 'actual workflow works'}]}, self.receipt)

    def review(self, stage='requirement', passed=True, **kwargs):
        return completion.review(self.state, stage=stage, passed=passed, note='measured evidence',
            evidence=kwargs.pop('evidence', self.receipt), report=kwargs.pop('report',
                {'passed': True, 'checks': {'real_check': True}, 'coverage': ['integration'], 'scenarios': ['real end-to-end interruption']}),
            requirement=kwargs.pop('requirement', 'integration'), **kwargs)

    def test_empty_queue_does_not_mean_project_complete(self):
        mission.refresh(self.state)
        self.assertEqual(self.state['status'], 'active')
        self.assertEqual(mission.next_task(self.state)['id'], 'grip:repair')
        self.assertEqual(self.state['tasks'][0]['status'], 'completed')

    def test_audit_then_separate_challenge_required(self):
        self.review()
        self.assertEqual(mission.next_task(self.state)['id'], 'grip:audit')
        self.review(stage='audit')
        self.assertEqual(self.state['completion']['phase'], 'provisional_green')
        self.assertEqual(mission.next_task(self.state)['id'], 'grip:challenge')
        with self.assertRaisesRegex(ValueError, 'separate evidence'):
            self.review(stage='challenge')
        self.review(stage='challenge', evidence={**self.receipt, 'sha256': 'separate-challenge'})
        mission.refresh(self.state)
        self.assertEqual(self.state['status'], 'complete')

    def test_partial_coverage_or_truthy_check_rejected(self):
        before = copy.deepcopy(self.state)
        for report in ({'passed': True, 'checks': {'x': 1}}, {'passed': True, 'checks': {}}, {'passed': False, 'checks': {'x': True}}):
            with self.assertRaises(ValueError): self.review(report=report)
            self.assertEqual(self.state, before)
        self.review()
        with self.assertRaisesRegex(ValueError, 'every requirement'):
            self.review(stage='audit', report={'passed': True, 'checks': {'x': True}, 'coverage': []})

    def test_challenge_cannot_precede_audit_or_omit_scenarios(self):
        self.review()
        with self.assertRaisesRegex(ValueError, 'provisional green'): self.review(stage='challenge')
        self.review(stage='audit')
        with self.assertRaisesRegex(ValueError, 'scenarios'):
            self.review(stage='challenge', evidence={**self.receipt, 'sha256': 'new'},
                report={'passed': True, 'checks': {'x': True}, 'coverage': ['integration']})

    def test_failure_keeps_history_and_returns_to_repair(self):
        self.review(); self.review(stage='audit')
        self.review(stage='challenge', passed=False, evidence={**self.receipt, 'sha256': 'failed'})
        self.assertEqual(self.state['completion']['phase'], 'repair')
        self.assertTrue(self.state['completion']['history'])
        self.assertEqual(mission.next_task(self.state)['id'], 'grip:repair')

    def test_source_change_invalidates_previously_green_requirements(self):
        self.review(); self.review(stage='audit')
        (Path(self.state['workspace'])/'source.py').write_text('real new source')
        completion.sync(self.state)
        self.assertEqual(self.state['completion']['requirements'][0]['status'], 'pending')
        self.assertEqual(mission.next_task(self.state)['id'], 'grip:repair')

    def test_new_gap_preserves_done_and_invalidates_green(self):
        self.review(); self.review(stage='audit')
        mission.add_task(self.state, {'id': 'missing-integration', 'status': 'pending', 'content': 'wire actual trainer',
            'done_when': 'fresh heldout proof', 'depends_on': ['component']}, now='now', expected=0)
        self.assertEqual(self.state['tasks'][0]['status'], 'completed')
        self.assertEqual(mission.next_task(self.state)['id'], 'missing-integration')
        self.assertEqual(self.state['completion']['phase'], 'repair')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            mission.add_task(self.state, self.state['tasks'][1], now='now', expected=1)

    def test_missing_spec_schedules_recovery_and_modes2_3_refused(self):
        s = {**self.state, 'completion': None}
        self.assertEqual(mission.next_task(s)['id'], 'grip:recover-spec')
        for mode in (2, 3):
            with self.assertRaisesRegex(ValueError, 'Only Mode1'): completion.configure({}, {'mode': mode}, self.receipt)

    def test_foreign_source_and_unknown_requirements_rejected(self):
        before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError): self.review(requirement='not-in-spec')
        self.assertEqual(self.state, before)
        with self.assertRaises(ValueError): completion.configure({'workspace': self.state['workspace']},
            {'mode': 1, 'source_paths': ['../foreign'], 'requirements': [{'id': 'a', 'done_when': 'proof'}]}, self.receipt)

    def test_real_cli_enforces_evidence_revision_and_separate_challenge(self):
        root = Path(self.state['workspace'])
        path = root/'state.json'
        before = {k: v for k, v in self.state.items() if k not in ('completion', 'operating_mode')}
        path.write_text(json.dumps(before))
        (root/'spec.json').write_text(json.dumps({'mode': 1, 'source_paths': ['source.py'],
            'requirements': [{'id': 'integration', 'done_when': 'actual workflow works'}]}))
        proof = {'passed': True, 'checks': {'actual_fixture': True}, 'coverage': ['integration']}
        (root/'proof.json').write_text(json.dumps(proof))
        (root/'challenge.json').write_text(json.dumps({**proof, 'scenarios': ['counterexample and recovery']}))
        def cli(*args, okay=True):
            p = subprocess.run([sys.executable, str(Path(__file__).parents[1]/'grip.py'),
                '--state', str(path), *args], text=True, capture_output=True, timeout=10)
            self.assertEqual(p.returncode == 0, okay, p.stderr)
            return json.loads(p.stdout) if okay else p.stderr
        cli('spec', '--file', 'spec.json', '--revision', '0')
        cli('review', '--stage', 'requirement', '--requirement', 'integration', '--result', 'pass',
            '--note', 'actual proof', '--evidence', 'proof.json', '--revision', '1')
        cli('review', '--stage', 'audit', '--result', 'pass', '--note', 'all requirements', '--evidence', 'proof.json', '--revision', '2')
        cli('review', '--stage', 'challenge', '--result', 'pass', '--note', 'fresh counterexample',
            '--evidence', 'proof.json', '--revision', '3', okay=False)
        cli('review', '--stage', 'challenge', '--result', 'pass', '--note', 'fresh counterexample',
            '--evidence', 'challenge.json', '--revision', '3')
        self.assertEqual(json.loads(path.read_text())['status'], 'complete')
        cli('add-task', '--id', 'new-gap', '--content', 'missing integration', '--done-when', 'real proof', '--revision', '0', okay=False)
        cli('add-task', '--id', 'new-gap', '--content', 'missing integration', '--done-when', 'real proof', '--revision', '4')
        self.assertEqual(json.loads(path.read_text())['status'], 'active')


if __name__ == '__main__': unittest.main()
