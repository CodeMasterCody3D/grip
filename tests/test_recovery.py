import copy
import json
import tempfile
import subprocess
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import grip


class CompletionRecovery(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.work = self.root/'work'; self.work.mkdir()
        self.bank = self.root/'bank'; self.bank.mkdir()
        self.state = {'workspace': str(self.work), 'backup_directory': str(self.bank), 'project_id': 'fixture',
            'server_url': 'http://127.0.0.1:1234', 'minimum_free_bytes': 0,
            'session_id': 'fixture-session', 'session_directory': str(self.work), 'github_repo': 'fixture/private',
            'status': 'blocked', 'plan_revision': 3, 'active_iteration': 'i0001',
            'tasks': [{'id': 'done', 'status': 'completed', 'evidence': [{'path': 'result.json'}]},
                      {'id': 'blocked', 'status': 'blocked', 'note': 'genuine prerequisite'}]}
        self.path = self.root/'state.json'; grip.atomic(self.path, self.state)
        (self.work/'a.py').write_text('candidate bytes\n'); (self.work/'result.json').write_text('{"passed":true}\n')
        self.folder = grip.area(self.state)/'iterations/i0001'
        grip.atomic(self.folder/'ITERATION.json', {'id': 'i0001', 'status': 'running', 'family': 'fixture',
            'what_changes': 'one causal change', 'owned_files': ['a.py'], 'before': grip.vault(self.state, ['a.py'])})
        self.args = SimpleNamespace(iteration='i0001', verdict='better', reason='verified candidate',
            evidence='result.json', best=None, metric_contract=None, family=None)

    def count_attempts(self, state=None):
        return len((state or self.state).get('families', {}).get('fixture', {}).get('attempts', []))

    def prepare_interrupted(self):
        before = copy.deepcopy(self.state)
        with patch.object(grip, 'backup', side_effect=RuntimeError('simulated interrupted push')):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'): grip.finish(self.state, self.args)
        self.assertEqual(self.state, before)
        self.assertEqual(grip.load(self.folder/'ITERATION.json')['status'], 'better')

    def test_finish_retry_after_prepare_does_not_repeat_source_work(self):
        self.prepare_interrupted()
        with patch.object(grip, 'find_finish_bank', return_value=None), patch.object(grip, 'backup', return_value='banked') as backup:
            grip.finish(self.state, self.args)
        self.assertEqual(backup.call_count, 1)
        self.assertIsNone(self.state['active_iteration']); self.assertEqual(self.count_attempts(), 1)
        self.assertEqual((self.work/'a.py').read_text(), 'candidate bytes\n')

    def test_crash_after_push_before_receipt_reuses_verified_bank(self):
        self.prepare_interrupted()
        with patch.object(grip, 'find_finish_bank', return_value='existing-bank'), \
             patch.object(grip, 'backup', side_effect=AssertionError('must not duplicate push')):
            grip.finish(self.state, self.args)
        self.assertEqual(self.state['last_iteration']['commit'], 'existing-bank')

    def test_crash_after_receipt_before_state_save_is_repeatable(self):
        old = copy.deepcopy(self.state)
        with patch.object(grip, 'backup', return_value='existing-bank'): grip.finish(self.state, self.args)
        with patch.object(grip, 'find_finish_bank', return_value='existing-bank'), \
             patch.object(grip, 'backup', side_effect=AssertionError('duplicate push')):
            grip.finish(old, self.args)
            grip.finish(old, self.args)
        self.assertEqual(old, self.state); self.assertEqual(self.count_attempts(old), 1)

    def test_failed_promotion_does_not_seal_terminal_or_modify_state(self):
        self.args.best = 'missing.pt'; self.args.metric_contract = 'fixture'; before = copy.deepcopy(self.state)
        with self.assertRaises(ValueError): grip.finish(self.state, self.args)
        self.assertEqual(self.state, before)
        self.assertEqual(grip.load(self.folder/'ITERATION.json')['status'], 'running')

    def test_changed_evidence_corrupt_vault_and_conflicting_request_are_refused(self):
        self.prepare_interrupted(); before = copy.deepcopy(self.state)
        (self.work/'result.json').write_text('changed evidence')
        with self.assertRaisesRegex(ValueError, 'evidence missing or changed'): grip.finish(self.state, self.args)
        self.assertEqual(self.state, before)
        (self.work/'result.json').write_text('{"passed":true}\n')
        changed = copy.copy(self.args); changed.reason = 'different interpretation'
        with self.assertRaisesRegex(ValueError, 'ownership/request'): grip.finish(self.state, changed)
        record = grip.load(self.folder/'ITERATION.json'); identity = record['after']['a.py']['sha256']
        (self.bank/'code_vault'/identity[:2]/identity).write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'vault is missing or corrupt'): grip.finish(self.state, self.args)

    def recovery_args(self):
        return SimpleNamespace(iteration='i0001', session_id='fixture-session', note='Explicit repair only',
            revision=3, record_sha256=grip.sha((self.folder/'ITERATION.json').read_bytes()))

    def test_explicit_legacy_recovery_preserves_pause_tasks_and_real_blocker(self):
        self.prepare_interrupted()
        record = grip.load(self.folder/'ITERATION.json'); record.pop('finish_owner'); record.pop('finish_request')
        grip.atomic(self.folder/'ITERATION.json', record)
        self.state['status'] = 'paused'; before = copy.deepcopy(self.state)
        with patch.object(grip.Client, 'snapshot', return_value=({'type': 'idle'}, [])), \
             patch.object(grip, 'backup', return_value='before-bank') as backup, \
             patch.object(grip, 'find_finish_bank', return_value='saved-completion'):
            result = grip.recover_finish(self.path, self.state, self.recovery_args())
        self.assertEqual(backup.call_count, 1)
        self.assertTrue(result['status_preserved']); self.assertTrue(result['tasks_preserved'])
        self.assertEqual(self.state['tasks'], before['tasks']); self.assertEqual(self.state['status'], 'paused')
        self.assertIsNone(self.state['active_iteration'])
        self.assertTrue(list((grip.area(self.state)/'recoveries').glob('*.json')))

    def test_recovery_requires_identity_record_hash_and_idle_owner(self):
        self.prepare_interrupted(); before = copy.deepcopy(self.state); args = self.recovery_args()
        args.session_id = 'foreign'
        with self.assertRaisesRegex(ValueError, 'explicit bound session'): grip.recover_finish(self.path, self.state, args)
        args = self.recovery_args(); args.record_sha256 = 'wrong'
        with self.assertRaisesRegex(ValueError, 'record changed'): grip.recover_finish(self.path, self.state, args)
        with patch.object(grip.Client, 'snapshot', return_value=({'type': 'busy'}, [])):
            with self.assertRaisesRegex(ValueError, 'busy'): grip.recover_finish(self.path, self.state, self.recovery_args())
        with patch.object(grip.Client, 'snapshot', side_effect=ValueError('identity mismatch')):
            with self.assertRaisesRegex(ValueError, 'identity'): grip.recover_finish(self.path, self.state, self.recovery_args())
        self.assertEqual(self.state, before)

    def test_repeated_recovery_and_newer_work_are_not_reopened(self):
        self.prepare_interrupted()
        with patch.object(grip, 'backup', return_value='saved'), patch.object(grip, 'find_finish_bank', return_value='saved'):
            grip.finish(self.state, self.args)
        with patch.object(grip.Client, 'snapshot', return_value=({'type': 'idle'}, [])), \
             patch.object(grip, 'find_finish_bank', return_value='saved'), \
             patch.object(grip, 'backup', side_effect=AssertionError('already reconciled')):
            self.assertTrue(grip.recover_finish(self.path, self.state, self.recovery_args())['already_reconciled'])
        self.state['last_iteration']['id'] = 'i0002'
        with self.assertRaisesRegex(ValueError, 'older completion'): grip.finish(self.state, self.args)

    def real_bank(self):
        remote = self.root/'fixture/private.git'; remote.parent.mkdir()
        for command, cwd in [(['git', 'init', '--bare', str(remote)], self.root),
                             (['git', 'init', '-b', 'main'], self.bank),
                             (['git', 'config', 'user.name', 'Fixture'], self.bank),
                             (['git', 'config', 'user.email', 'fixture@users.noreply.github.com'], self.bank),
                             (['git', 'remote', 'add', 'origin', str(remote)], self.bank)]:
            subprocess.run(command, cwd=cwd, check=True, capture_output=True)
        self.state['backup_branch'] = 'main'
        actual = grip.command
        def route(args, **kwargs):
            if args[0] == 'gh': return 'true'  # only provider call mocked; Git proof is real
            return actual(args, **kwargs)
        return patch.object(grip, 'command', side_effect=route)

    def test_real_git_proof_reuses_finish_without_duplicate_commit(self):
        with self.real_bank():
            first = grip.finish(self.state, self.args)
            count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=self.bank)
            second = grip.finish(self.state, self.args)
            self.assertEqual(first, second)
            self.assertEqual(subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=self.bank), count)
            self.assertEqual(self.count_attempts(), 1)

    def test_real_git_proof_recovers_push_before_receipt_without_repush(self):
        actual = grip.atomic
        def interrupted(path, value):
            if Path(path).name == 'FINISH_RECEIPT.json': raise RuntimeError('crash after push')
            return actual(path, value)
        with self.real_bank():
            before = copy.deepcopy(self.state)
            with patch.object(grip, 'atomic', side_effect=interrupted):
                with self.assertRaisesRegex(RuntimeError, 'crash after push'): grip.finish(self.state, self.args)
            self.assertEqual(self.state, before)
            count = subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=self.bank)
            with patch.object(grip, 'backup', side_effect=AssertionError('duplicate completed bank')):
                grip.finish(self.state, self.args)
            self.assertEqual(subprocess.check_output(['git', 'rev-list', '--count', 'HEAD'], cwd=self.bank), count)

    def test_receipt_with_wrong_record_hash_is_refused(self):
        with patch.object(grip, 'backup', return_value='saved'): grip.finish(self.state, self.args)
        receipt = grip.load(self.folder/'FINISH_RECEIPT.json'); receipt['record_sha256'] = 'corrupt'
        grip.atomic(self.folder/'FINISH_RECEIPT.json', receipt)
        with self.assertRaisesRegex(ValueError, 'receipt ownership/hash'): grip.finish(self.state, self.args)

    def test_new_iteration_owner_cannot_be_rebound_during_finish(self):
        record = grip.load(self.folder/'ITERATION.json'); record['owner'] = grip.finish_owner(self.state)
        record['owner']['session_id'] = 'another-session'
        grip.atomic(self.folder/'ITERATION.json', record); before = copy.deepcopy(self.state)
        with self.assertRaisesRegex(ValueError, 'Iteration owner changed'): grip.finish(self.state, self.args)
        self.assertEqual(self.state, before)
