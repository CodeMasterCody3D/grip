"""Read-only native OpenCode event subscription, owned by the existing watcher.

Uses the discovered native event.subscribe route on the exact already-bound server
and its existing control credential (never the unrelated default CLI service).
Never stores raw events, prompts, tool arguments/results, or other sessions' data.
Only sanitized bound-session metadata reaches the shared continuation gate.
"""
import json
import subprocess
import threading
import base64
from pathlib import Path
import urllib.request
import event_hooks


def metadata(value, session_id):
    event = value.get("data") if not value.get("type") and isinstance(value.get("data"), dict) else value
    data = event.get("data") or event.get("properties", {})
    if data.get("sessionID") != session_id:
        return None
    kind = {"session.tool.called": "tool_start", "session.tool.success": "tool_end",
            "session.tool.failed": "tool_end", "session.execution.started": "turn_start",
            "session.execution.succeeded": "turn_end", "session.execution.failed": "turn_end",
             "session.agent.selected": "agent", "session.idle": "idle"}.get(event.get("type"))
    if event.get("type") == "session.execution.interrupted" and data.get("reason") == "user":
        kind = "interrupted"
    if not kind:
        return None
    result = {"session_id": session_id, "kind": kind, "event_id": event.get("id"),
              "at_ms": event.get("created")}
    if kind in ("tool_start", "tool_end"):
        result["call_id"] = data.get("id")
        if not result["call_id"]: return None
    if kind == "agent": result["agent"] = "build" if data.get("agent") == "build" else "plan"
    return result


def decode(lines):
    """CLI streams JSON values (pretty or single-line); SSE is also tolerated."""
    decoder = json.JSONDecoder()
    buffer = ""
    for line in lines:
        if line.startswith(("event:", "id:", ":")): continue
        if line.startswith("data:"): line = line[5:].lstrip()
        buffer += line
        if len(buffer) > 4 * 1024 * 1024:
            raise ValueError("Event frame exceeded bound; raw contents not retained")
        while buffer.strip():
            trimmed = buffer.lstrip()
            try: value, end = decoder.raw_decode(trimmed)
            except json.JSONDecodeError: break
            if isinstance(value, dict): yield value
            buffer = trimmed[end:]


class Observer:
    def __init__(self, state, receive, health, command=None):
        self.state, self.receive, self.health = state, receive, health
        self.command = command
        self.stop = threading.Event()
        self.process = None
        self.response = None
        self.thread = threading.Thread(target=self.run, name="grip-native-events", daemon=True)

    def start(self):
        self.thread.start()
        return self

    def run(self):
        failures = 0
        while not self.stop.is_set():
            try:
                self.health("connecting", None)
                if self.command:
                    # Explicit fixture command only; production uses the exact
                    # already-bound server, never an unrelated default service.
                    self.process = subprocess.Popen(self.command, cwd=self.state["session_directory"],
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    lines = self.process.stdout
                else:
                    secret = event_hooks.control_password(self.state)
                    request = urllib.request.Request(self.state['server_url'].rstrip('/')+'/api/event', headers={
                        'Accept': 'text/event-stream', 'Authorization': 'Basic '+base64.b64encode(('opencode:'+secret).encode()).decode()})
                    self.response = urllib.request.urlopen(request, timeout=5)
                    if self.response.headers.get_content_type() != 'text/event-stream':
                        raise ValueError('Bound server did not provide native SSE')
                    lines = (line.decode('utf-8') for line in self.response)
                for value in decode(lines):
                    event = metadata(value, self.state["session_id"])
                    if event:
                        self.receive(event)
                        self.health("observing", event["kind"])
                        failures = 0
                    if self.stop.is_set(): break
                if not self.stop.is_set():
                    failures += 1
                    self.health("disconnected", "attempt " + str(failures))
            except Exception as error:
                failures += 1
                self.health("error", type(error).__name__)
            finally:
                if self.response:
                    self.response.close()
                    self.response = None
                if self.process:
                    if self.process.poll() is None: self.process.terminate()
                    try: self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=3)
            self.stop.wait(min(30, 2 ** min(failures, 4)))

    def close(self):
        self.stop.set()
        if self.process and self.process.poll() is None: self.process.terminate()
        self.thread.join(timeout=5)
