import copy
from pathlib import Path
import socket
import subprocess
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

import event_hooks
import grip


def final(agent='build', complete=200):
    return [{'info': {'id': 'm', 'agent': agent, 'role': 'assistant', 'finish': 'stop',
                     'time': {'created': 100, 'completed': complete}}, 'parts': []}]


class Events(unittest.TestCase):
    def setUp(self): self.state = {'session_id': 'actual', 'status': 'active'}
    def emit(self, kind, **kwargs):
        return event_hooks.record(self.state, session_id='actual', kind=kind, at_ms=150, **kwargs)

    def test_matching_tool_start_end_and_final_gate(self):
        self.emit('tool_start', call_id='real-call', agent='build')
        self.assertEqual(event_hooks.suppress(self.state, final(complete=140)), 'hook_active_work')
        self.emit('tool_end', call_id='real-call')
        self.assertIsNone(event_hooks.suppress(self.state, final()))

    def test_lost_after_event_recovers_only_with_newer_persisted_final(self):
        self.emit('tool_start', call_id='real-call')
        self.assertIsNone(event_hooks.suppress(self.state, final()))
        m = final(); m[0]['parts'] = [{'type': 'tool', 'state': {'status': 'running'}}]
        self.assertEqual(event_hooks.suppress(self.state, m), 'hook_active_work')

    def test_tool_end_does_not_count_as_turn_end(self):
        self.emit('turn_start'); self.emit('tool_start', call_id='a'); self.emit('tool_end', call_id='a')
        self.assertEqual(event_hooks.suppress(self.state, final(complete=140)), 'hook_active_work')
        self.emit('turn_end')
        self.assertIsNone(event_hooks.suppress(self.state, final()))

    def test_idle_is_a_hint_never_an_authoritative_turn_end(self):
        self.emit('turn_start');self.emit('tool_start',call_id='real')
        event_hooks.record(self.state,session_id='actual',kind='idle',at_ms=300,event_id='idle-1')
        self.assertEqual(event_hooks.suppress(self.state,final(complete=140)),'hook_active_work')
        self.assertEqual(self.state['hook_state']['active_tools'],['real'])
        # A passive late idle must not hide a newer persisted genuine final.
        self.assertIsNone(event_hooks.suppress(self.state,final(complete=200)))
        before=copy.deepcopy(self.state)
        self.assertFalse(self.emit('idle',event_id='idle-1')['accepted'])
        self.assertEqual(before,self.state)

    def test_plan_blocks_ordinary_wake_and_progress_watchdog(self):
        self.emit('agent', agent='plan')
        m = final(agent='plan')
        self.assertEqual(event_hooks.suppress(self.state, m), 'plan_mode')
        s = {**self.state, 'tasks': [{'status': 'pending'}], 'idle_grace_seconds': 0, 'progress_watch': {'enabled': True}}
        self.assertFalse(grip.eligible(s, {'type': 'idle'}, m))
        class Fake:
            def __init__(self, _): pass
            def snapshot(self): return {'type': 'idle'}, m
        with patch.object(grip, 'Client', Fake), patch.object(grip, 'progress_intervention', side_effect=AssertionError('must not run watchdog in Plan')):
            self.assertEqual(grip.tick(s)['reason'], 'plan_mode')

    def test_foreign_sessions_unknown_events_and_missing_call_refused(self):
        for values in ({'session_id': 'foreign', 'kind': 'turn_end'}, {'session_id': 'actual', 'kind': 'unknown'},
                       {'session_id': 'actual', 'kind': 'tool_start'}):
            with self.assertRaises(ValueError): event_hooks.record(self.state, **values)

    def test_duplicate_event_never_restarts_tool(self):
        self.emit('tool_start', call_id='a', event_id='start-a')
        self.emit('tool_end', call_id='a', event_id='end-a')
        before = copy.deepcopy(self.state)
        self.assertFalse(self.emit('tool_start', call_id='a', event_id='start-a')['accepted'])
        self.assertEqual(self.state, before)

    def test_human_interruption_pauses(self):
        self.emit('interrupted')
        self.assertEqual(self.state['status'], 'paused')

    def test_real_unix_signal_is_notification_not_dispatch(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(event_hooks.Path, 'home', return_value=Path(tmp)):
            connection = event_hooks.listen(Path(tmp)/'state.json')
            self.addCleanup(connection.close)
            connection.settimeout(1)
            event_hooks.notify(Path(tmp)/'state.json')
            self.assertEqual(connection.recv(128), b'reconcile')

    def test_real_event_cli_preserves_model_task_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'state.json'
            path.write_text(json.dumps(self.state))
            result = subprocess.run([sys.executable, str(Path(__file__).parents[1]/'grip.py'),
                '--state', str(path), 'event', '--session-id', 'actual', '--kind', 'tool_start',
                '--call-id', 'actual-call', '--agent', 'plan'], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            state = json.loads(path.read_text())
            self.assertEqual(state['status'], 'active')
            self.assertEqual(state['hook_state']['active_tools'], ['actual-call'])
            self.assertEqual(state['hook_state']['agent'], 'plan')

    def test_service_credentials_require_exact_recorded_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'service.json'
            path.write_text(json.dumps({'url': 'http://127.0.0.1:1234', 'password': 'fixture-not-real'}))
            state = {'server_url': 'http://127.0.0.1:1234', 'server_service_file': str(path)}
            self.assertEqual(event_hooks.control_password(state), 'fixture-not-real')
            state['server_url'] = 'http://127.0.0.1:5678'
            with self.assertRaisesRegex(ValueError, 'endpoint changed'): event_hooks.control_password(state)

    def test_wildcard_listener_metadata_matches_same_loopback_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'service.json'
            for listener, client in [('0.0.0.0', '127.0.0.1'), ('127.0.0.1', '127.0.0.1'),
                                     ('localhost', '127.0.0.1'), ('0.0.0.0', 'localhost'),
                                     ('[::]', '[::1]'), ('[::1]', '[::1]')]:
                with self.subTest(listener=listener, client=client):
                    path.write_text(json.dumps({'url': 'http://' + listener + ':1234', 'password': 'fixture-not-real'}))
                    state = {'server_url': 'http://' + client + ':1234', 'server_service_file': str(path)}
                    self.assertEqual(event_hooks.control_password(state), 'fixture-not-real')

    def test_listener_alias_does_not_permit_changed_port_or_remote_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'service.json'
            state = {'server_url': 'http://127.0.0.1:1234', 'server_service_file': str(path)}
            for url in ('http://0.0.0.0:5678', 'http://remote.invalid:1234'):
                with self.subTest(url=url):
                    path.write_text(json.dumps({'url': url, 'password': 'fixture-not-real'}))
                    with self.assertRaises(ValueError): event_hooks.control_password(state)

    def test_loopback_normalization_is_strict_and_listener_only(self):
        self.assertEqual(event_hooks.local_endpoint('http://localhost:1234/'), 'http://127.0.0.1:1234')
        self.assertEqual(event_hooks.local_endpoint('http://[::]:1234', listener=True), 'http://[::1]:1234')
        for url in ('http://0.0.0.0:1234', 'http://[::]:1234', 'https://127.0.0.1:1234',
                    'http://remote.invalid:1234', 'http://user@127.0.0.1:1234',
                    'http://127.0.0.1:1234/?redirect=1', 'http://127.0.0.1:1234/api',
                    'http://127.0.0.1:0', 'http://127.0.0.1:70000'):
            with self.subTest(url=url):
                with self.assertRaises(ValueError): event_hooks.local_endpoint(url)

    def test_client_still_rejects_wildcard_as_connection_target(self):
        with self.assertRaisesRegex(ValueError, 'owned loopback'):
            grip.Client({'server_url': 'http://0.0.0.0:1234'})

    def test_explicit_adoption_uses_loopback_without_resuming_paused_mission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'service.json'
            path.write_text(json.dumps({'url': 'http://0.0.0.0:1234', 'password': 'fixture-not-real'}))
            state = {'session_id': 'actual', 'status': 'paused', 'server_url': 'http://127.0.0.1:5678',
                     'session_directory': tmp, 'tasks': [{'id': 'done', 'status': 'completed'}]}
            original_tasks = copy.deepcopy(state['tasks'])
            def snapshot(client):
                self.assertEqual(client.state['server_url'], 'http://127.0.0.1:1234')
                return {'type': 'idle'}, []
            with patch.object(grip, 'watcher_status', return_value={'alive': False}), \
                 patch.dict(grip.os.environ, {'OPENCODE_SESSION_ID': 'actual'}), \
                 patch.object(grip.Client, 'snapshot', snapshot):
                result = grip.adopt_server(Path(tmp)/'state.json', state, path)
            self.assertTrue(result['same_session_verified'])
            self.assertFalse(result['watcher_started'])
            self.assertEqual(state['status'], 'paused')
            self.assertEqual(state['tasks'], original_tasks)

    def test_failed_adoption_identity_check_preserves_original_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'service.json'
            path.write_text(json.dumps({'url': 'http://0.0.0.0:1234', 'password': 'fixture-not-real'}))
            state = {'session_id': 'actual', 'status': 'paused', 'server_url': 'http://127.0.0.1:5678'}
            before = copy.deepcopy(state)
            with patch.object(grip, 'watcher_status', return_value={'alive': False}), \
                 patch.dict(grip.os.environ, {'OPENCODE_SESSION_ID': 'actual'}), \
                 patch.object(grip.Client, 'snapshot', side_effect=ValueError('Session identity/directory mismatch')):
                with self.assertRaisesRegex(ValueError, 'identity/directory'):
                    grip.adopt_server(Path(tmp)/'state.json', state, path)
            self.assertEqual(state, before)

    def test_authoritative_turn_end_clears_ghost_tool_ids(self):
        self.emit('tool_start', call_id='missed-end')
        event_hooks.record(self.state, session_id='actual', kind='turn_end', at_ms=210)
        self.assertEqual(self.state['hook_state']['active_tools'], [])
        self.assertIsNone(event_hooks.suppress(self.state, final(complete=200)))

    def test_late_passive_receipt_cannot_hide_final_but_new_work_stays_protected(self):
        self.emit('tool_start', call_id='ghost')
        event_hooks.record(self.state, session_id='actual', kind='tool_end', call_id='other', at_ms=210)
        self.assertIsNone(event_hooks.suppress(self.state, final(complete=200)))
        event_hooks.record(self.state, session_id='actual', kind='tool_start', call_id='new-real-work', at_ms=300)
        event_hooks.record(self.state, session_id='actual', kind='turn_end', at_ms=250)
        self.assertIn('new-real-work', self.state['hook_state']['active_tools'])
        self.assertEqual(event_hooks.suppress(self.state, final(complete=200)), 'hook_active_work')

    def test_typed_native_stop_wins_over_busy_hook_without_aborting_tool(self):
        self.emit('tool_start', call_id='real-active-tool')
        s={**self.state,'server_api':'v2','tasks':[{'status':'pending'}]}
        user={'info':{'id':'u','role':'user','time':{'created':301}},'parts':[{'type':'text','text':'stop GRIP now'}]}
        class Fake:
            def __init__(self,state):self.state=state
            def snapshot(self):return {'type':'busy'},[user]+final(complete=200)
            def request(self,*_):raise AssertionError('must not abort human tool or send a prompt')
        with patch.object(grip,'Client',Fake):
            result=grip.tick(s)
        self.assertEqual(s['status'],'paused')
        self.assertEqual(result['stage'],'paused')
        self.assertIn('real-active-tool',s['hook_state']['active_tools'])

    def test_server_adoption_requires_this_tool_session_and_no_live_watcher(self):
        with patch.object(grip, 'watcher_status', return_value={'alive': True}):
            with self.assertRaisesRegex(ValueError, 'Stop the owned'): grip.adopt_server('/fixture', self.state, '/none')
        with patch.object(grip, 'watcher_status', return_value={'alive': False}), patch.dict(grip.os.environ, {'OPENCODE_SESSION_ID': 'foreign'}):
            with self.assertRaisesRegex(ValueError, 'exact real tool-context'): grip.adopt_server('/fixture', self.state, '/none')


if __name__ == '__main__': unittest.main()
