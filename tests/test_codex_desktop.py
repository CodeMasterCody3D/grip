"""Post-turn dispatcher: real GRIP state gates and isolated native IPC fixtures."""
import json
import os
from pathlib import Path
import socket
import sqlite3
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import uuid

import codex_bridge as bridge
import codex_desktop as desktop


class FakeIpc:
    calls = []
    mode = 'default'
    fail_send = False
    def __init__(self, path): pass
    def close(self): pass
    def owner(self, thread): return 'existing-owner'
    def settings(self, thread, owner): return {'mode': self.mode, 'model': 'existing-model'}
    def start(self, thread, owner, text, turn, message_id):
        self.calls.append((thread, owner, text, turn, message_id))
        if self.fail_send: raise TimeoutError()
        return {'method': 'thread-follower-start-turn', 'result': {'result': {'turn': {'id': 'new-turn', 'status': 'inProgress'}}}}


class DesktopWake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.path = root / 'state.json'
        self.token = str(uuid.uuid4())
        self.env = patch.dict(os.environ, GRIP_CACHE_DIR=str(root / 'cache'))
        self.env.start()
        self.state = {'harness': 'codex', 'session_id': 'thread-fixture', 'workspace': str(root),
            'state_path': str(self.path), 'status': 'active', 'maximum_wakes': 2, 'wake_count': 1,
            'compute_target': 'fixture only', 'deadline': None, 'objective': 'Fixture', 'done_when': 'Fixture passes',
            'tasks': [{'id': 'task', 'content': 'Read fixture', 'done_when': 'Read', 'status': 'pending'}],
            'hook_state': {'active_tools': [], 'turn_active': False, 'counts': {'tool_start': 1}, 'seen': [], 'tool_starts': {}},
            'codex': {'last_observed_turn': 'turn-1', 'desktop': {'ipc_socket': str(root / 'fake.sock'), 'prediction_wait_seconds': 0},
              'pending_desktop_wake': {'token': self.token, 'message_id': str(uuid.uuid4()), 'source_turn': 'turn-1',
                                     'phase': 'waiting', 'input_marker': None}}}
        self.save()
        bridge.private_write(bridge.registry(), {'sessions': {'thread-fixture': {
            'harness': 'codex', 'workspace': str(root), 'state_path': str(self.path)}}})
        FakeIpc.calls = []
        FakeIpc.mode = 'default'
        FakeIpc.fail_send = False
        self.ipc = patch.object(desktop, 'DesktopIpc', FakeIpc)
        self.ipc.start()
        self.completed = patch.object(desktop, 'completed_source', return_value=(True, None))
        self.completed_mock = self.completed.start()

    def tearDown(self):
        self.completed.stop()
        self.ipc.stop()
        self.env.stop()
        self.tmp.cleanup()

    def save(self): bridge.private_write(self.path, self.state)
    def load(self): return json.loads(self.path.read_text())
    def pending(self): return self.load()['codex']['pending_desktop_wake']
    def read(self, config, thread, turn=None):
        if turn: return {'captured': False, 'reason': 'no_displayed_prediction'}
        return {'available': True, 'threadId': thread, 'idle': True, 'composerEmpty': True}
    def run_worker(self, reader=None):
        with patch.object(desktop, 'desktop_read', side_effect=reader or self.read):
            desktop.run(self.path, self.token)

    def make_infinite(self):
        self.state['codex'].update(continuation_mode='infinite', infinite_active=True,
            infinite_instructions='Repair the fixture; then work through its approved ideas.')
        self.state['tasks'] = []
        self.state['status'] = 'complete'
        self.state['wake_count'] = 1000
        self.state['maximum_wakes'] = 1
        self.save()

    def test_infinite_continues_new_text_only_turns_past_completion_and_budget(self):
        self.make_infinite()
        self.state['codex'].pop('pending_desktop_wake')
        self.save()
        event = {'session_id': 'thread-fixture', 'cwd': self.state['workspace'], 'permission_mode': 'default'}
        with patch.object(bridge.subprocess, 'Popen') as spawn, patch.object(bridge, 'INFINITE_INTERVAL', 0):
            spawn.return_value.pid = 123
            for n in range(3):
                turn = f'completed-turn-{n}'
                bridge.hook(dict(event, hook_event_name='UserPromptSubmit', turn_id=turn, prompt='existing instruction'))
                stop = dict(event, hook_event_name='Stop', turn_id=turn)
                self.assertEqual(bridge.hook(stop), {})
                self.token = self.pending()['token']
                self.run_worker()
                self.assertEqual(self.pending()['phase'], 'ipc_accepted')
                # Same-turn Stop is a duplicate even after the worker finishes.
                self.assertEqual(bridge.hook(stop), {})
            self.assertEqual(spawn.call_count, 3)
        state = self.load()
        self.assertEqual(state['wake_count'], 1003)
        self.assertEqual(state['status'], 'complete')
        self.assertTrue(bridge.running(state))
        self.assertEqual(len(FakeIpc.calls), 3)
        text = FakeIpc.calls[-1][2]
        self.assertIn('[GRIP INFINITE CONTINUATION]', text)
        self.assertIn('Double-check', text)
        self.assertIn('TODO/backlog', text)
        self.assertIn('debug and fix that SAME task', text)
        self.assertIn('different literal implementation', text)
        self.assertNotIn('[GRIP AUTHORIZED CONTINUATION]', text)

    def test_infinite_prediction_still_prefers_actual_grey_text(self):
        self.make_infinite()
        def read(config, thread, turn=None):
            if turn: return {'captured': True, 'sourceTurnId': turn, 'text': 'Fix that parser error',
                             'displayed': True, 'composerEmpty': True}
            return self.read(config, thread)
        self.run_worker(read)
        self.assertIn('Fix that parser error', FakeIpc.calls[0][2])
        self.assertIn('debug and fix that SAME task', FakeIpc.calls[0][2])
        self.assertEqual(self.pending()['source'], 'composer_prediction')

    def test_infinite_failed_task_is_preserved_for_repair_not_treated_as_completion(self):
        self.make_infinite()
        self.state['status'] = 'blocked'
        self.state['tasks'] = [{'id': 'parser', 'content': 'Fix parser', 'status': 'blocked',
                                'notes': 'First implementation failed the input check.'}]
        self.state['objective_guard'] = {'status': 'blocked'}
        self.save()
        self.run_worker()
        self.assertEqual(len(FakeIpc.calls), 1)
        self.assertEqual(self.load()['tasks'], self.state['tasks'])
        self.assertEqual(self.load()['objective_guard'], self.state['objective_guard'])
        self.assertIn('debug and fix that SAME task', FakeIpc.calls[0][2])

    def test_infinite_cooldown_checks_pause_before_dispatch(self):
        self.make_infinite()
        self.state['codex']['last_dispatch_at'] = 100
        self.save()
        def pause(_):
            bridge.private_write(bridge.pause_marker(self.path), {'event': 'Interrupt'})
        with patch.object(desktop.time, 'time', return_value=101), patch.object(desktop.time, 'sleep', side_effect=pause) as wait:
            self.run_worker()
        self.assertEqual(wait.call_count, 1)
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'paused_or_inactive')

    def test_infinite_cooldown_delays_without_losing_the_wake(self):
        self.make_infinite()
        self.state['codex']['last_dispatch_at'] = 100
        self.save()
        now = [110]
        def advance(seconds): now[0] += seconds
        with patch.object(desktop.time, 'time', side_effect=lambda: now[0]), patch.object(desktop.time, 'sleep', side_effect=advance):
            self.run_worker()
        self.assertEqual(len(FakeIpc.calls), 1)
        self.assertGreaterEqual(self.load()['codex']['last_dispatch_at'], 100 + bridge.INFINITE_INTERVAL)

    def test_infinite_mode_retains_transport_and_human_guards(self):
        for reason in ('pause', 'plan', 'draft', 'new_input', 'uncertain'):
            with self.subTest(reason=reason):
                self.make_infinite()
                if reason == 'pause':
                    self.state['status'] = 'paused'
                elif reason == 'plan':
                    FakeIpc.mode = 'plan'
                elif reason == 'new_input':
                    bridge.private_write(desktop.input_marker(self.path), {'turn_id': 'human-new'})
                elif reason == 'uncertain':
                    self.state['codex']['pending_desktop_wake']['phase'] = 'delivery_unknown'
                self.save()
                reader = (lambda *args: {'available': True, 'idle': True, 'composerEmpty': False}) if reason == 'draft' else None
                self.run_worker(reader)
                self.assertEqual(FakeIpc.calls, [])
                FakeIpc.mode = 'default'
                desktop.input_marker(self.path).unlink(missing_ok=True)

    def test_real_prediction_wins_and_delivery_preserves_thread_identity(self):
        def read(config, thread, turn=None):
            if turn: return {'captured': True, 'sourceTurnId': turn, 'text': 'Inspect saved result', 'displayed': True, 'composerEmpty': True}
            return self.read(config, thread)
        self.run_worker(read)
        call = FakeIpc.calls[0]
        self.assertEqual(call[0], 'thread-fixture')
        self.assertEqual(call[3], 'turn-1')
        self.assertIn('Inspect saved result', call[2])
        self.assertTrue(call[2].endswith('GRIP wake token: ' + self.token))
        self.assertEqual(self.pending()['source'], 'composer_prediction')
        self.assertEqual(self.pending()['phase'], 'ipc_accepted')
        self.assertEqual(self.pending()['accepted_turn_id'], 'new-turn')

    def test_absent_prediction_uses_normal_grip_prompt(self):
        self.run_worker()
        self.assertIn('[GRIP AUTHORIZED CONTINUATION]', FakeIpc.calls[0][2])
        self.assertEqual(self.pending()['source'], 'grip_fallback')

    def test_plan_mode_does_not_send(self):
        FakeIpc.mode = 'plan'
        self.run_worker()
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'plan_or_unknown_mode')

    def test_human_draft_does_not_send(self):
        self.run_worker(lambda *args: {'available': True, 'idle': True, 'composerEmpty': False})
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'human_draft')

    def test_other_visible_chat_uses_bound_chat_fallback_without_ui_edit(self):
        self.run_worker(lambda *args: {'available': False, 'reason': 'different_visible_thread'})
        self.assertEqual(FakeIpc.calls[0][0], 'thread-fixture')
        self.assertEqual(self.pending()['source'], 'grip_fallback')

    def test_new_turn_in_authoritative_history_suppresses_send(self):
        self.completed_mock.return_value = (False, 'new_turn_in_history')
        self.run_worker()
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'new_turn_in_history')

    def test_new_input_immediately_before_dispatch_suppresses(self):
        contexts = 0
        def read(config, thread, turn=None):
            nonlocal contexts
            if not turn:
                contexts += 1
                if contexts == 2:
                    bridge.private_write(desktop.input_marker(self.path), {'turn_id': 'new-human-turn'})
            return self.read(config, thread, turn)
        self.run_worker(read)
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'new_input')

    def test_delivery_timeout_is_not_retried(self):
        FakeIpc.fail_send = True
        self.run_worker()
        self.run_worker()
        self.assertEqual(len(FakeIpc.calls), 1)
        self.assertEqual(self.pending()['phase'], 'delivery_unknown')

    def test_pause_marker_suppresses_even_with_active_state(self):
        bridge.private_write(bridge.pause_marker(self.path), {'event': 'Interrupt'})
        self.run_worker()
        self.assertEqual(FakeIpc.calls, [])
        self.assertEqual(self.pending()['reason'], 'paused_or_inactive')

    def test_native_stop_defers_once_and_reserves_one_worker(self):
        self.state['codex'].pop('pending_desktop_wake')
        self.state['wake_count'] = 0
        self.state['maximum_wakes'] = 1
        self.save()
        event = {'session_id': 'thread-fixture', 'hook_event_name': 'Stop', 'turn_id': 'turn-1',
                 'cwd': self.state['workspace'], 'permission_mode': 'default'}
        with patch.object(bridge.subprocess, 'Popen') as spawn:
            spawn.return_value.pid = 123
            self.assertEqual(bridge.hook(event), {})
            self.assertEqual(bridge.hook(event), {})
            self.assertEqual(spawn.call_count, 1)
        state = self.load()
        self.assertEqual(state['status'], 'active')
        self.assertEqual(state['wake_count'], 1)
        self.assertEqual(self.pending()['phase'], 'waiting')

    def test_actual_matching_native_tool_event_reconciles_unknown_delivery(self):
        self.state['status'] = 'paused'
        self.state['codex']['pending_desktop_wake']['phase'] = 'delivery_unknown'
        self.save()
        bridge.private_write(desktop.input_marker(self.path), {'turn_id': 'real-next-turn', 'wake_token': self.token})
        bridge.hook({'session_id': 'thread-fixture', 'hook_event_name': 'PreToolUse', 'turn_id': 'real-next-turn',
                     'cwd': self.state['workspace'], 'permission_mode': 'default', 'tool_use_id': 'actual-tool'})
        pending = self.pending()
        self.assertEqual(pending['phase'], 'agent_started')
        self.assertEqual(pending['prior_delivery_phase'], 'delivery_unknown')
        self.assertEqual(pending['agent_turn_id'], 'real-next-turn')
        self.assertEqual(self.load()['status'], 'paused')
        self.assertEqual(FakeIpc.calls, [])


class NativeIpcWire(unittest.TestCase):
    def test_turn_response_and_unknown_response_are_distinct(self):
        self.assertEqual(desktop.accepted_turn({'result': {'result': {'turn': {'id': 'actual'}}}}), ('sent','actual'))
        self.assertEqual(desktop.accepted_turn({'result': {'result': {'unexpected': True}}}), (None,None))
    def test_history_queries_only_the_bound_threads_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'history.sqlite'
            c=sqlite3.connect(path)
            c.execute('CREATE TABLE thread_turns(thread_id TEXT,turn_id TEXT,status TEXT,completed_at INT,rollout_ordinal INT)')
            c.executemany('INSERT INTO thread_turns VALUES(?,?,?,?,?)', [('bound','source','completed',123,1),
                ('other','private-other-turn','inProgress',None,999)])
            c.commit();c.close()
            config={'history_db':str(path)}
            self.assertEqual(desktop.completed_source(config,'bound','source'),(True,None))
            self.assertEqual(desktop.completed_source(config,'bound','old'),(False,'new_turn_in_history'))
            c=sqlite3.connect(path);c.execute("INSERT INTO thread_turns VALUES('bound','new','inProgress',NULL,2)");c.commit();c.close()
            self.assertEqual(desktop.completed_source(config,'bound','source'),(False,'new_turn_in_history'))
            self.assertEqual(desktop.completed_source(config,'bound','new'),(False,None))

    def test_native_frames_route_only_to_existing_thread_without_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder) / 'desktop.sock')
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(path)
            listener.listen(1)
            requests = []
            errors = []
            def server():
                try:
                    conn, _ = listener.accept()
                    with conn:
                        def take(n):
                            b = b''
                            while len(b) < n: b += conn.recv(n-len(b))
                            return b
                        for _ in range(4):
                            size = struct.unpack('<I', take(4))[0]
                            req = json.loads(take(size)); requests.append(req)
                            if req['method'] == 'initialize': result = {'clientId': 'fixture-client'}
                            elif req['method'] == 'thread-owner-discovery': result = {'supportsUntrustedAppInput': True}
                            elif req['method'] == 'thread-follower-read-model-settings': result = {'settings': {'mode': 'default'}}
                            else: result = {'result': {'status': 'sent', 'turnId': 'next'}}
                            data = json.dumps({'type': 'response', 'requestId': req['requestId'], 'method': req['method'],
                                'resultType': 'success', 'handledByClientId': 'owner', 'result': result}).encode()
                            conn.sendall(struct.pack('<I', len(data)) + data)
                except Exception as exc: errors.append(exc)
            thread = threading.Thread(target=server, daemon=True); thread.start()
            client = desktop.DesktopIpc(path)
            try:
                owner = client.owner('same-thread')
                self.assertEqual(client.settings('same-thread', owner)['mode'], 'default')
                client.start('same-thread', owner, 'fixture prompt', 'source-turn', 'stable-message-id')
            finally: client.close(); listener.close()
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])
            last = requests[-1]
            self.assertEqual(last['version'], 2)
            self.assertEqual(last['targetClientId'], 'owner')
            request = last['params']['turnStart']['request']
            self.assertEqual(request['threadId'], 'same-thread')
            self.assertEqual(request['clientUserMessageId'], 'stable-message-id')
            self.assertNotIn('model', request)
            self.assertNotIn('approvalPolicy', request)
            self.assertNotIn('sandboxPolicy', request)


if __name__ == '__main__': unittest.main()
