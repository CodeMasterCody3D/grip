"""Metadata-only hook observations. Hooks never dispatch a second agent."""
import hashlib
import json
import os
from pathlib import Path
import socket
import time
import urllib.parse

KINDS = {"tool_start", "tool_end", "turn_start", "turn_end", "idle", "interrupted", "agent", "hook_loaded", "hook_failed"}


def cache_root():
    """Shared Python/plugin location, independent of username or checkout."""
    if os.environ.get("GRIP_CACHE_DIR"):
        return Path(os.environ["GRIP_CACHE_DIR"]).expanduser().resolve()
    return (Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser() / "grip").resolve()


def local_endpoint(url, *, listener=False):
    """Compare local endpoints; wildcard bind addresses are metadata, not targets."""
    message = 'Only an owned loopback OpenCode server is supported'
    try:
        parsed = urllib.parse.urlsplit(url)
        host = parsed.hostname
        port = parsed.port if parsed.port is not None else 80
        if (parsed.scheme != 'http' or parsed.username is not None or parsed.password is not None
                or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                or not 1 <= port <= 65535):
            raise ValueError(message)
        if listener:
            host = {'0.0.0.0': '127.0.0.1', '::': '::1'}.get(host, host)
        if host == 'localhost':
            host = '127.0.0.1'
        if host not in ('127.0.0.1', '::1'):
            raise ValueError(message)
    except (TypeError, ValueError):
        raise ValueError(message) from None
    return 'http://' + ('[::1]' if host == '::1' else host) + ':' + str(port)


def control_password(state):
    """Read the existing owned control credential; never copy it into the mission."""
    if state.get('server_service_file'):
        service = json.loads(Path(state['server_service_file']).read_text())
        if local_endpoint(service.get('url', ''), listener=True) != local_endpoint(state['server_url']):
            raise ValueError('Service endpoint changed; explicitly re-adopt and verify session identity')
        return service['password']
    return Path(state['server_secret_file']).read_text().strip()


def record(state, *, session_id, kind, call_id=None, agent=None, event_id=None, at_ms=None):
    if session_id != state["session_id"] or kind not in KINDS:
        raise ValueError("Hook event must match the bound session and known kind")
    if kind in ("tool_start", "tool_end") and not call_id:
        raise ValueError("Tool event needs its actual call ID")
    memory = state.setdefault("hook_state", {"active_tools": [], "seen": []})
    if event_id and event_id in memory["seen"]:
        return {"accepted": False, "reason": "duplicate_event"}
    now = int(time.time() * 1000) if at_ms is None else at_ms
    if event_id:
        memory["seen"] = (memory["seen"] + [event_id])[-128:]
    memory["last_at_ms"] = max(now, memory.get("last_at_ms", 0))
    counts = memory.setdefault('counts', {})
    counts[kind] = counts.get(kind, 0) + 1
    if agent is not None:
        if agent not in ("build", "plan"):
            raise ValueError("Unknown current agent; cannot assume implementation permission")
        memory["agent"] = agent
    active = set(memory["active_tools"])
    starts = memory.setdefault('tool_starts', {})
    if kind == "tool_start":
        active.add(call_id)
        starts[call_id] = now
        memory['work_started_ms'] = max(now, memory.get('work_started_ms', 0))
    if kind == "tool_end":
        active.discard(call_id)
        starts.pop(call_id, None)
    memory["active_tools"] = sorted(active)
    if kind == "turn_start":
        memory["turn_active"] = True
        memory['work_started_ms'] = max(now, memory.get('work_started_ms', 0))
    if kind == "turn_end" and now >= memory.get('work_started_ms', 0):
        # Native execution.succeeded is an authoritative run boundary. Missed
        # per-tool end observations cannot keep a completed run busy forever.
        # Source timestamps prevent a delayed old boundary clearing newer work.
        memory["turn_active"] = False
        memory["active_tools"] = []
        memory['tool_starts'] = {}
    if kind == "interrupted":
        state["status"] = "paused"
        memory["interrupted"] = True
    if kind == "hook_loaded": memory["loaded_at_ms"] = now
    if kind == "hook_failed": memory["failed_at_ms"] = now
    return {"accepted": True, "kind": kind, "at_ms": now, "session_id": session_id,
            "call_id": call_id, "agent": agent}


def suppress(state, messages):
    latest = max(messages, key=lambda m: m["info"]["time"]["created"]) if messages else None
    info = latest["info"] if latest else {}
    memory = state.get("hook_state", {})
    # Persisted current agent beats an old in-memory 'build' observation.
    agent = info.get("agent") or memory.get("agent")
    if agent == "plan" or state.get("execution_agent") == "plan":
        return "plan_mode"
    persisted_tools = any(p.get("type") == "tool" and p.get("state", {}).get("status") in ("running", "pending")
                          for m in messages for p in m.get("parts", []))
    final = (info.get("role") == "assistant" and info.get("finish") == "stop"
             and info.get("time", {}).get("completed") and not info.get("error") and not persisted_tools)
    if (memory.get("active_tools") or memory.get("turn_active")) and not (
            final and info["time"]["completed"] >= memory.get("work_started_ms", memory.get("last_at_ms", 0))):
        return "hook_active_work"
    return None


def socket_path(state_path):
    # Short name avoids UNIX's path-length limit; directory is user-owned.
    root = cache_root() / "events"
    return root / (hashlib.sha256(str(Path(state_path).resolve()).encode()).hexdigest()[:24] + ".sock")


def notify(state_path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as connection:
        try: connection.sendto(b"reconcile", str(socket_path(state_path)))
        except (FileNotFoundError, ConnectionRefusedError): pass  # durable state survives until fallback poll


def listen(state_path):
    path = socket_path(state_path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        # Called only after the exclusive watcher lease is acquired.
        path.unlink()
    connection = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    connection.bind(str(path)); os.chmod(path, 0o600)
    return connection
