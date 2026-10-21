import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import stream_events


class NativeEvents(unittest.TestCase):
    def test_idle_properties_envelope_and_source_metadata_only(self):
        event={'type':'session.idle','id':'idle-1','created':1300,
               'properties':{'sessionID':'s','messages':'PRIVATE'}}
        self.assertEqual(stream_events.metadata({'data':event},'s'),
                         {'session_id':'s','kind':'idle','event_id':'idle-1','at_ms':1300})
        self.assertIsNone(stream_events.metadata(event,'foreign'))

    def test_decode_and_filter_only_bound_metadata(self):
        values = [
            {'type': 'session.tool.called', 'id': 'e1', 'data': {'sessionID': 'actual', 'id': 'call', 'input': 'PRIVATE'}},
            {'type': 'session.tool.success', 'id': 'e2', 'data': {'sessionID': 'foreign', 'id': 'other', 'output': 'PRIVATE'}},
            {'type': 'session.execution.succeeded', 'id': 'e3', 'data': {'sessionID': 'actual'}}]
        lines = (json.dumps(v, indent=2)+'\n' for v in values)
        output = [stream_events.metadata(v, 'actual') for v in stream_events.decode(lines)]
        self.assertEqual(output[0]['kind'], 'tool_start')
        self.assertIsNone(output[1])
        self.assertEqual(output[2]['kind'], 'turn_end')
        self.assertNotIn('PRIVATE', json.dumps(output))

    def test_plan_and_human_interruption(self):
        value = {'type': 'session.agent.selected', 'data': {'sessionID': 's', 'agent': 'plan'}}
        self.assertEqual(stream_events.metadata(value, 's')['agent'], 'plan')
        value = {'type': 'session.execution.interrupted', 'data': {'sessionID': 's', 'reason': 'user'}}
        self.assertEqual(stream_events.metadata(value, 's')['kind'], 'interrupted')
        value['data']['reason'] = 'tool'
        self.assertIsNone(stream_events.metadata(value, 's'))

    def test_source_timestamp_survives_event_transport(self):
        value={'type':'session.execution.succeeded','id':'e','created':1234,'data':{'sessionID':'s'}}
        self.assertEqual(stream_events.metadata(value,'s')['at_ms'],1234)

    def test_real_owned_subprocess_stream_no_inference(self):
        received, health = [], []
        ready = threading.Event()
        event = {'type': 'session.execution.succeeded', 'id': 'fixture', 'data': {'sessionID': 's'}}
        def receive(value):
            received.append(value); ready.set()
        with tempfile.TemporaryDirectory() as root:
            observer = stream_events.Observer({'session_id': 's', 'session_directory': root}, receive,
                lambda *v: health.append(v), command=[sys.executable, '-u', '-c', 'print('+repr(json.dumps(event))+')']).start()
            try:
                self.assertTrue(ready.wait(3))
                self.assertEqual(received[0]['kind'], 'turn_end')
            finally: observer.close()
        self.assertFalse(observer.thread.is_alive())

    def test_native_sse_uses_exact_bound_server_and_filters_tool_payload(self):
        events, headers = [], []
        ready = threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_GET(self):
                headers.append((self.path, self.headers.get('Authorization')))
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                value = {'type': 'session.tool.called', 'id': 'e', 'data': {'sessionID': 's', 'id': 'call', 'input': 'PRIVATE'}}
                self.wfile.write(('event: message\ndata: '+json.dumps(value)+'\n\n').encode()); self.wfile.flush()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory() as root:
                secret = Path(root)/'secret'; secret.write_text('fixture-not-real')
                def receive(value): events.append(value); ready.set()
                observer = stream_events.Observer({'session_id': 's', 'session_directory': root,
                    'server_url': 'http://127.0.0.1:'+str(server.server_port), 'server_secret_file': str(secret)},
                    receive, lambda *_: None).start()
                try: self.assertTrue(ready.wait(3))
                finally: observer.close()
            self.assertEqual(headers[0][0], '/api/event')
            self.assertTrue(headers[0][1].startswith('Basic '))
            self.assertEqual(events[0]['call_id'], 'call')
            self.assertNotIn('PRIVATE', json.dumps(events))
        finally: server.shutdown(); server.server_close()


if __name__ == '__main__': unittest.main()
