"""Post-Stop desktop wake. The native hook starts one bounded worker per wake.

Reads actual composer predictions through loopback CDP, then uses the desktop's
owned local IPC route to continue the existing thread. No UI editing, new model
requests, credential reads, retries after uncertain delivery, or global poller.
Private desktop APIs are version-sensitive and fail closed on changed shapes.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import socket
import sqlite3
import stat
import struct
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent


class DesktopIpc:
    """The installed app's length-prefixed, same-user UNIX-socket protocol."""
    def __init__(self, path):
        self.path = Path(path)
        info = self.path.stat()
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise ValueError('Desktop IPC must be a socket owned by the current user')
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.settimeout(5)
        self.socket.connect(str(self.path))
        self.client = 'initializing-client'
        try:
            result = self.request('initialize', {'clientType': 'cli'}, version=0)
            self.client = result['result']['clientId']
        except Exception:
            self.close()
            raise

    def close(self):
        self.socket.close()

    def send_frame(self, value):
        payload = json.dumps(value, ensure_ascii=False).encode()
        if len(payload) > 128 * 1024:
            raise ValueError('Desktop request exceeds the bounded frame size')
        self.socket.sendall(struct.pack('<I', len(payload)) + payload)

    def take(self, length):
        result = b''
        while len(result) < length:
            chunk = self.socket.recv(length - len(result))
            if not chunk:
                raise ConnectionError('Desktop IPC closed')
            result += chunk
        return result

    def request(self, method, params, *, version, target=None):
        identifier = str(uuid.uuid4())
        request = {'type': 'request', 'requestId': identifier, 'sourceClientId': self.client,
                   'method': method, 'version': version, 'params': params, 'timeoutMs': 4000}
        if target:
            request['targetClientId'] = target
        self.send_frame(request)
        while True:
            length = struct.unpack('<I', self.take(4))[0]
            if length > 1024 * 1024:
                raise ValueError('Unexpected desktop frame size')
            value = json.loads(self.take(length))
            if value.get('type') == 'client-discovery-request':
                self.send_frame({'type': 'client-discovery-response', 'requestId': value['requestId'],
                                 'response': {'canHandle': False}})
            if value.get('requestId') == identifier and value.get('type') == 'response':
                if value.get('resultType') != 'success':
                    raise RuntimeError('Desktop request rejected: ' + str(value.get('error', 'unknown')))
                return value

    def owner(self, thread):
        reply = self.request('thread-owner-discovery', {'hostId': 'local', 'conversationId': thread}, version=1)
        return reply['handledByClientId']

    def settings(self, thread, owner):
        reply = self.request('thread-follower-read-model-settings', {'conversationId': thread}, version=1, target=owner)
        return reply['result']['settings']

    def start(self, thread, owner, text, source_turn, message_id):
        # These fields deliberately inherit model, permission and environment
        # settings. clientUserMessageId is stable for the sealed wake request.
        request = {'threadId': thread, 'clientUserMessageId': message_id,
                   'input': [{'type': 'text', 'text': text, 'text_elements': []}],
                   'turnTrigger': 'grip_continuation', 'parentTurnId': source_turn}
        return self.request('thread-follower-start-turn', {
            'conversationId': thread, 'turnStart': {'request': request, 'context': {'inheritThreadSettings': True}}},
            version=2, target=owner)


def input_marker(path):
    return Path(path).with_name(Path(path).name + '.codex-input')


def marker_signature(path):
    marker = input_marker(path)
    return hashlib.sha256(marker.read_bytes()).hexdigest() if marker.exists() else None


def desktop_read(config, thread, turn=None):
    command = [config['node'], str(ROOT / 'desktop_predictions.mjs'), '--endpoint', config['endpoint'],
               '--target-id', config['target_id'], '--thread-id', thread]
    command += ['--source-turn', turn] if turn else ['--context']
    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
    if result.returncode:
        raise RuntimeError('Desktop read failed')
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError('Unexpected desktop result')
    return value


def history_head(config, thread):
    """Read only this chat's turn metadata; never read message contents.

    This private schema is verified for the installed build. A missing/changed
    database or schema is an error, not permission to assume the turn ended.
    """
    database = Path(config['history_db']).expanduser().resolve()
    info = database.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise ValueError('Turn history must be a regular file owned by the current user')
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2)
    try:
        row = connection.execute('SELECT turn_id,status,completed_at FROM thread_turns '
            'WHERE thread_id=? ORDER BY rollout_ordinal DESC LIMIT 1', (thread,)).fetchone()
        if not row:
            raise ValueError('No saved turn metadata for the bound thread')
        return {'turn_id': row[0], 'status': row[1], 'completed_at': row[2]}
    finally:
        connection.close()


def completed_source(config, thread, source):
    head = history_head(config, thread)
    if head['turn_id'] != source:
        return False, 'new_turn_in_history'
    if head['status'] in ('failed', 'interrupted'):
        return False, 'turn_failed_or_interrupted'
    return head['status'] == 'completed' and head['completed_at'] is not None, None


def accepted_turn(reply):
    """Native startTurn returns TurnStartResponse, not the UI submit status."""
    result = (reply.get('result') or {}).get('result')
    if not isinstance(result, dict):
        return None, None
    turn = result.get('turn')
    if isinstance(turn, dict) and isinstance(turn.get('id'), str) and turn['id']:
        return 'sent', turn['id']
    # Other app builds may wrap the UI's sent/queued submission result.
    if result.get('status') in ('sent', 'queued'):
        return result['status'], result.get('turnId')
    return None, None


def guard(state, path, token):
    import codex_bridge as bridge
    import grip
    import mission
    pending = state.get('codex', {}).get('pending_desktop_wake') or {}
    if pending.get('token') != token or pending.get('phase') != 'waiting':
        return 'wake_not_waiting'
    binding = bridge.lookup(state.get('session_id'))
    if not binding or Path(binding['state_path']).resolve() != Path(path).resolve() or not bridge.state_matches(state, binding, state.get('session_id')):
        return 'binding_changed'
    if not bridge.running(state) or bridge.pause_marker(path).exists():
        return 'paused_or_inactive'
    if grip.deadline_reached(state):
        return 'deadline'
    if marker_signature(path) != pending.get('input_marker'):
        return 'new_input'
    if state.get('codex', {}).get('last_observed_turn') != pending.get('source_turn'):
        return 'new_turn'
    if state.get('hook_state', {}).get('active_tools') or state.get('hook_state', {}).get('turn_active'):
        return 'active_work'
    if not bridge.infinite_mode(state):
        mission.refresh(state)
        if state.get('status') != 'active' or mission.next_task(state) is None:
            return 'no_actionable_work'
    return None


def finish_pending(path, token, phase, **details):
    import codex_bridge as bridge
    import grip
    with grip.locked(Path(path).with_suffix('.lock')):
        state = grip.load(path)
        pending = state.get('codex', {}).get('pending_desktop_wake') or {}
        if pending.get('token') != token:
            return
        pending.update(phase=phase, updated_at=grip.stamp(), **details)
        bridge.private_write(path, state)


def run(path, token):
    import codex_bridge as bridge
    import grip
    path = Path(path).resolve()
    # A separate worker lease prevents an accidental second invocation from
    # racing the same pending wake before its dispatch phase is persisted.
    with grip.locked(path.with_name(path.name + '.desktop-worker.lock'), blocking=False):
        state = grip.load(path)
        initial_reason = guard(state, path, token)
        if initial_reason:
            if initial_reason != 'wake_not_waiting':
                finish_pending(path, token, 'suppressed', reason=initial_reason)
            return
        config = state['codex']['desktop']
        pending = state['codex']['pending_desktop_wake']
        source_turn = pending['source_turn']
        thread = state['session_id']
        # Text-only reviews need no tool progress. Space their sends without a
        # wake cap, checking pause/new input throughout this bounded worker.
        interval = bridge.INFINITE_INTERVAL if bridge.infinite_mode(state) else 0
        due = time.monotonic() + 45 + interval
        idle_since = None
        prediction = None
        while time.monotonic() < due:
            with grip.locked(path.with_suffix('.lock')):
                state = grip.load(path)
                reason = guard(state, path, token)
            if reason:
                finish_pending(path, token, 'suppressed', reason=reason)
                return
            completed, history_reason = completed_source(config, thread, source_turn)
            if history_reason:
                finish_pending(path, token, 'suppressed', reason=history_reason)
                return
            if not completed:
                time.sleep(1)
                continue
            if interval and time.time() < state['codex'].get('last_dispatch_at', 0) + interval:
                time.sleep(1)
                continue
            context = desktop_read(config, thread)
            if not context.get('available'):
                if context.get('reason') in ('different_visible_thread', 'no_unique_visible_composer'):
                    # No composer for this chat is displayed. Native turn-complete
                    # metadata and the hook's input marker still gate the normal
                    # GRIP fallback; the visible chat is never edited or sent to.
                    break
                finish_pending(path, token, 'suppressed', reason=context.get('reason', 'context_unavailable'))
                return
            if not context.get('composerEmpty'):
                finish_pending(path, token, 'suppressed', reason='human_draft')
                return
            if not context.get('idle'):
                idle_since = None
                time.sleep(1)
                continue
            idle_since = idle_since or time.monotonic()
            sample = desktop_read(config, thread, source_turn)
            if sample.get('captured'):
                if (sample.get('sourceTurnId') != source_turn or not sample.get('displayed')
                        or not sample.get('composerEmpty') or not isinstance(sample.get('text'), str)):
                    raise ValueError('Prediction identity mismatch')
                prediction = sample['text']
                break
            if sample.get('reason') == 'different_source_turn':
                finish_pending(path, token, 'suppressed', reason='different_source_turn')
                return
            if time.monotonic() - idle_since >= config.get('prediction_wait_seconds', 12):
                break
            time.sleep(1)
        else:
            finish_pending(path, token, 'suppressed', reason='thread_did_not_become_idle')
            return
        ipc = DesktopIpc(config['ipc_socket'])
        try:
            owner = ipc.owner(thread)
            settings = ipc.settings(thread, owner)
            if not settings or settings.get('mode') == 'plan':
                finish_pending(path, token, 'suppressed', reason='plan_or_unknown_mode')
                return
            # Refresh UI and durable input once more immediately before sealing.
            context = desktop_read(config, thread)
            background = not context.get('available') and context.get('reason') in ('different_visible_thread', 'no_unique_visible_composer')
            if not background and (not context.get('available') or not context.get('idle') or not context.get('composerEmpty')):
                finish_pending(path, token, 'suppressed', reason='ui_changed')
                return
            completed, history_reason = completed_source(config, thread, source_turn)
            if history_reason or not completed:
                finish_pending(path, token, 'suppressed', reason=history_reason or 'history_not_completed')
                return
            with grip.locked(path.with_suffix('.lock')):
                state = grip.load(path)
                reason = guard(state, path, token)
                if reason:
                    state['codex']['pending_desktop_wake'].update(phase='suppressed', reason=reason)
                    bridge.private_write(path, state)
                    return
                pending = state['codex']['pending_desktop_wake']
                text = bridge.wake_text(state, prediction) + '\nGRIP wake token: ' + token
                pending.update(phase='dispatching', dispatch_at=grip.stamp(),
                               source='composer_prediction' if prediction else 'grip_fallback')
                state['codex'].update(last_wake_source=pending['source'], last_dispatch_at=time.time())
                bridge.private_write(path, state)
                # After this point a timeout is uncertain delivery, never retry.
                try:
                    reply = ipc.start(thread, owner, text, source_turn, pending['message_id'])
                except Exception as exc:
                    pending.update(phase='delivery_unknown', error_type=type(exc).__name__)
                    bridge.private_write(path, state)
                    return
                app_status, turn_id = accepted_turn(reply)
                if app_status in ('sent', 'queued'):
                    pending.update(phase='ipc_accepted', accepted_at=grip.stamp(), app_status=app_status,
                                   accepted_turn_id=turn_id, response_method=reply.get('method'))
                else:
                    pending.update(phase='delivery_unknown', error_type='UnexpectedAppResponse',
                                   app_status=app_status, response_method=reply.get('method'))
                bridge.private_write(path, state)
        finally:
            ipc.close()


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: codex_desktop.py STATE TOKEN')
    try:
        run(sys.argv[1], sys.argv[2])
    except Exception as exc:
        try:
            state = json.loads(Path(sys.argv[1]).read_text())
            phase = state.get('codex', {}).get('pending_desktop_wake', {}).get('phase')
            finish_pending(sys.argv[1], sys.argv[2], 'delivery_unknown' if phase == 'dispatching' else 'worker_failed',
                           error_type=type(exc).__name__)
        except Exception:
            pass  # Keep the sealed state; never infer that uncertain delivery failed.
        raise SystemExit(1)
