import copy
import fcntl
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import grip


class StandbySafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'state.json'
        self.state = {'workspace': str(self.path.parent), 'session_id': 'fixture', 'session_directory': str(self.path.parent),
            'server_url': 'http://127.0.0.1:1234',
            'project_id': 'fixture', 'status': 'paused', 'tasks': [{'id': 'done', 'status': 'completed'}]}
        self.state['standby'] = {'enabled': True, 'owner': grip.finish_owner(self.state)}
        grip.atomic(self.path, self.state)

    def test_disabled_standby_never_contacts_or_restarts(self):
        self.state['standby']['enabled'] = False; grip.atomic(self.path, self.state)
        with patch.object(grip, 'watcher_status', side_effect=AssertionError('must not inspect')):
            self.assertEqual(grip.standby_step(self.path)['stage'], 'disabled')

    def test_healthy_primary_is_not_duplicated(self):
        with patch.object(grip, 'watcher_status', return_value={'alive': True, 'pid': 7}), \
             patch.object(grip, 'start_watch', side_effect=AssertionError('duplicate dispatch')):
            self.assertEqual(grip.standby_step(self.path)['stage'], 'watching')

    def test_alive_but_unhealthy_primary_requires_investigation_not_killing(self):
        self.state['consecutive_errors'] = 3; grip.atomic(self.path, self.state)
        with patch.object(grip, 'watcher_status', return_value={'alive': True, 'pid': 7}), \
             patch.object(grip, 'start_watch', side_effect=AssertionError('blind restart')):
            self.assertEqual(grip.standby_step(self.path)['stage'], 'needs_investigation')

    def test_missing_owner_and_binding_change_do_not_start_work(self):
        with patch.object(grip, 'watcher_status', return_value={'alive': False}), \
             patch.object(grip, 'start_watch', side_effect=AssertionError('unknown owner')):
            self.assertEqual(grip.standby_step(self.path)['stage'], 'needs_investigation')
        self.state['session_id'] = 'changed'; grip.atomic(self.path, self.state)
        with self.assertRaisesRegex(ValueError, 'binding changed'): grip.standby_step(self.path)

    def test_held_primary_lease_prevents_competing_recovery(self):
        with self.path.with_suffix('.watch.lock').open('a+') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(grip, 'watcher_status', return_value={'alive': False, 'pid': 7, 'state_path': str(self.path)}), \
                 patch.object(grip, 'start_watch', side_effect=AssertionError('competing primary')):
                self.assertEqual(grip.standby_step(self.path)['stage'], 'needs_investigation')

    def test_dead_primary_recovery_preserves_pause_completed_tasks_and_blocks(self):
        for status in ('paused', 'blocked', 'active', 'complete'):
            with self.subTest(status=status):
                self.state['status'] = status; grip.atomic(self.path, self.state); before = copy.deepcopy(self.state)
                with patch.object(grip, 'watcher_status', return_value={'alive': False, 'pid': 7, 'state_path': str(self.path)}), \
                     patch.object(grip.Client, 'snapshot', return_value=({'type': 'idle'}, [])), \
                     patch.object(grip, 'start_watch', return_value={'pid': 8}):
                    self.assertEqual(grip.standby_step(self.path)['stage'], 'primary_recovered')
                self.assertEqual(grip.load(self.path), before)

    def test_wrong_server_session_never_recovers_primary(self):
        with patch.object(grip, 'watcher_status', return_value={'alive': False, 'pid': 7, 'state_path': str(self.path)}), \
             patch.object(grip.Client, 'snapshot', side_effect=ValueError('wrong session')), \
             patch.object(grip, 'start_watch', side_effect=AssertionError('wrong owner')):
            with self.assertRaisesRegex(ValueError, 'wrong session'): grip.standby_step(self.path)

    def test_shared_state_lock_never_blocks_monitor_or_permits_takeover(self):
        with self.path.with_suffix('.lock').open('a+') as held:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(grip, 'watcher_status', return_value={'alive': False, 'pid': 7, 'state_path': str(self.path)}), \
                 patch.object(grip, 'start_watch', side_effect=AssertionError('bypassed dispatch gate')):
                self.assertEqual(grip.standby_step(self.path)['stage'], 'needs_investigation')
            with patch.object(grip, 'watcher_status', return_value={'alive': True, 'pid': 7}):
                self.assertEqual(grip.standby_step(self.path)['stage'], 'watching')
