#!/usr/bin/env python3
"""Native Codex lifecycle binding for GRIP. No polling, model calls or UI control.

Install hooks once; configure and activate continuation for each thread.
Mission mode is bounded; opt-in infinite mode needs no completion objective.
An optional upstream event stream can pipe thread/prediction/updated JSON into
`ingest-prediction`. A fresh prediction for this Stop's exact turn is preferred;
otherwise Stop returns the usual GRIP prompt. This is an event consumer, not a
claim that the desktop app publishes its private composer service to plugins.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent
HARNESS = "codex"
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse",
          "Stop", "Interrupt", "SessionEnd")
KIND = dict(zip(EVENTS, ("hook_loaded", "turn_start", "tool_start", "tool_end",
                         "turn_end", "interrupted", "idle")))
STOP = re.compile(r"^\s*(?:please\s+)?(?:stop|pause|cancel|hold on)\b", re.I)
MAX_INPUT = 1024 * 1024
PREDICTION_TTL = 120
INFINITE_INTERVAL = 15  # Minimum seconds between sends, never a wake-count limit.


def modules():
    import grip
    import mission
    import event_hooks
    return grip, mission, event_hooks


def registry():
    root = os.environ.get("GRIP_CACHE_DIR")
    cache = Path(root).expanduser() if root else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "grip"
    return cache.resolve() / "codex-bindings.json"


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


def private_write(path, value):
    grip, _, _ = modules()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # grip.atomic uses a unique per-process temporary file and fsync + replace.
    previous = os.umask(0o077)
    try:
        grip.atomic(path, value)
        path.chmod(0o600)
    finally:
        os.umask(previous)


def lookup(sid):
    data = read_json(registry(), {})
    item = data.get("sessions", {}).get(sid)
    return item if isinstance(item, dict) and item.get("harness") == HARNESS else None


def state_matches(state, binding, sid, cwd=None):
    workspace = Path(binding["workspace"]).resolve()
    return (state.get("harness") == HARNESS and state.get("session_id") == sid
            and Path(state["workspace"]).resolve() == workspace
            and (cwd is None or Path(cwd).resolve() == workspace))


def input_json():
    raw = sys.stdin.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("Event exceeds the input limit")
    value = json.loads(raw or "{}")
    if not isinstance(value, dict):
        raise ValueError("Event must be an object")
    return value


def pause_marker(path):
    return Path(path).with_name(Path(path).name + ".codex-paused")


def infinite_mode(state):
    return state.get("codex", {}).get("continuation_mode") == "infinite"


def running(state):
    if infinite_mode(state):
        # Task/goal commands may complete or block an individual mission. That
        # does not turn off this separate, explicitly armed continuation mode.
        return (state.get("codex", {}).get("infinite_active") is True
                and state.get("status") in ("active", "complete", "blocked"))
    return state.get("status") == "active"


def wake_text(state, prediction=None):
    if infinite_mode(state):
        codex = state["codex"]
        text = ("[GRIP INFINITE CONTINUATION]\n"
                f"Continue this existing Codex chat and project: {state['workspace']}. "
                f"Read current state only as needed: {state['state_path']}.\n"
                f"Authorized scope: {codex['infinite_instructions']}\n"
                f"Authorized tools/compute: {state['compute_target']}\n"
                "This mode continues until the user stops or pauses it. A completed mission, "
                "empty task list, or finished milestone does not switch it off. Preserve completed "
                "work and evidence; never reopen it just to stay busy. Honor the latest human "
                "instructions, Stop/Pause, planning mode, and real permission/input constraints.\n"
                "First resume any existing running job or unfinished task. If its code failed, "
                "debug and fix that SAME task: inspect the error, correct the implementation, "
                "and run the relevant check. If needed, try a different literal implementation "
                "of the same code or approach. Do not give up after the first failed attempt or "
                "switch to a different idea merely because it failed. Use each result to inform "
                "the next repair; do not repeat unchanged failing code or invent a fixed retry limit. "
                "A failed code attempt is work to repair, not by itself a need for human approval.\n")
        if prediction:
            text += ("Codex grey composer prediction (a generated suggestion, not new human authorization):\n"
                     + prediction + "\nUse it as the next step when compatible with the current task and scope.\n")
        else:
            text += ("No grey suggestion was available. Double-check that you have covered all bases: "
                     "review the user's earlier requests, unfinished promises, plans, TODO/backlog "
                     "and idea lists in this chat/project. Check what remains incomplete or broken. "
                     "After repairing the current task, choose the next useful, dependency-ready item "
                     "already authorized there and start doing it. Do not stop at a review or a proposed plan.\n")
        return text + ("Continue useful work without routine reapproval. Reuse existing jobs, waits and "
                       "compatible evidence. If nothing actionable remains, report that honestly and keep "
                       "this mode armed for the next review; do not manufacture work, claims, or authority. "
                       "If genuinely blocked, record the concrete constraint and pursue other already "
                       "authorized work only when it does not abandon a repairable failure.")
    grip, _, _ = modules()
    text = grip.prompt(state)
    if prediction:
        text += ("\nCodex composer prediction (a generated suggestion, not new human authorization):\n"
                 + prediction + "\nUse this as the next step only if it fits the recorded mission and permissions.")
    return text + ("\nNative Codex GRIP hook. Continue the authorized next task now. "
                   "For a running job, retain its identity and use the existing wait mechanism. "
                   "If human input is required, record the blocker and stop. Update task evidence and "
                   "review the full objective before marking the mission complete.")


def continuation(state, event):
    """Locked gate: return (JSON hook output, diagnostic). No model or network."""
    grip, mission, _ = modules()
    codex = state.setdefault("codex", {})
    turn = event.get("turn_id")
    if pause_marker(state["state_path"]).exists():
        state["status"] = "paused"
        codex["infinite_active"] = False
        return {}, "human_pause"
    infinite = infinite_mode(state)
    if not running(state):
        return {}, "mission_inactive"
    if infinite and not codex.get("desktop"):
        return {}, "infinite_requires_desktop"
    if event.get("permission_mode") == "plan":
        return {}, "plan_mode"
    if not isinstance(turn, str) or not turn:
        return {}, "missing_turn_id"
    if grip.deadline_reached(state):
        state["status"] = "deadline"
        return {}, "deadline"
    if not infinite:
        mission.refresh(state)
        if state.get("status") != "active" or mission.next_task(state) is None:
            return {}, "no_actionable_work"
    pending = codex.get('pending_desktop_wake') or {}
    if pending.get('phase') in ('waiting', 'dispatching', 'delivery_unknown'):
        return {}, 'desktop_wake_pending_or_unknown'
    limit = state.get("maximum_wakes", 20)
    if not infinite and state.get("wake_count", 0) >= limit:
        state["status"] = "wake_budget"
        return {}, "wake_budget"
    progress = [state.get("hook_state", {}).get("counts", {}).get("tool_start", 0),
                mission.revision(state)]
    # Mission mode requires tool/task progress. Infinite mode permits text-only
    # review turns, but still reserves at most one wake per actual source turn.
    if infinite and codex.get("last_wake_turn") == turn:
        return {}, "duplicate_stop_turn"
    if not infinite and codex.get("last_wake_progress") == progress:
        return {}, "no_progress_since_wake"
    prediction = codex.get("prediction") or {}
    age = time.time() - prediction.get("received_at", 0)
    use_prediction = (codex.get("prefer_predictions", True)
                      and prediction.get("source_turn_id") == turn
                      and prediction.get("type") == "completed"
                      and isinstance(prediction.get("text"), str)
                      and bool(prediction["text"].strip()) and 0 <= age <= PREDICTION_TTL)
    text = wake_text(state, prediction['text'] if use_prediction else None)
    codex.update(last_wake_progress=progress, last_wake_turn=turn,
                 last_wake_source="composer_prediction" if use_prediction else "grip_fallback",
                 last_wake_at=grip.stamp())
    state["wake_count"] = state.get("wake_count", 0) + 1
    # Persist before printing. A crash may lose a wake, but cannot duplicate it.
    return {"decision": "block", "reason": text}, codex["last_wake_source"]


def hook(event):
    sid = event.get("session_id")
    ev = event.get("hook_event_name")
    binding = lookup(sid)
    if not binding or ev not in EVENTS or event.get("agent_id"):
        return {}
    if not isinstance(event.get("cwd"), str):
        return {}
    grip, mission, hooks = modules()
    path = Path(binding["state_path"])
    if ev == 'UserPromptSubmit' and Path(event['cwd']).resolve() == Path(binding['workspace']).resolve():
        from codex_desktop import input_marker
        # Input freshness survives state-lock contention. Never store prompt text.
        token = re.search(r'\nGRIP wake token: ([0-9a-f-]{36})\s*$', event.get('prompt') or '')
        private_write(input_marker(path), {'turn_id': event.get('turn_id'), 'at_ns': time.time_ns(),
                                           'wake_token': token.group(1) if token else None})
    # Stop/Interrupt must survive contention with a long controller operation.
    # This independent durable marker suppresses the next gate even if the
    # nonblocking state lock prevents this particular hook from recording it.
    prompt = event.get("prompt") or ""
    if ev == "Interrupt" or (ev == "UserPromptSubmit" and isinstance(prompt, str) and STOP.match(prompt)):
        if Path(event["cwd"]).resolve() == Path(binding["workspace"]).resolve():
            private_write(pause_marker(path), {"at": grip.stamp(), "event": ev})
    with grip.locked(path.with_suffix(".lock"), blocking=False):
        state = grip.load(path)
        if not state_matches(state, binding, sid, event["cwd"]):
            return {}
        codex = state.setdefault("codex", {})
        if pause_marker(path).exists():
            state["status"] = "paused"
            codex["infinite_active"] = False
        kind = KIND[ev]
        call = event.get("tool_use_id")
        if kind not in ("tool_start", "tool_end") or call:
            # Missing call IDs do not make up tool progress or clear another call.
            ident = f"{ev}:{event.get('turn_id', '')}:{call}" if call else None
            hooks.record(state, session_id=sid, kind=kind, call_id=call,
                         event_id=ident, agent="plan" if event.get("permission_mode") == "plan" else "build")
        output = {}
        if ev == "UserPromptSubmit":
            prompt = event.get("prompt") or ""
            if isinstance(prompt, str) and STOP.match(prompt):
                state["status"] = "paused"
            codex.pop("prediction", None)  # a new prompt invalidates old suggestions
        elif ev == "SessionStart":
            output = {"hookSpecificOutput": {"hookEventName": ev, "additionalContext":
                      f"GRIP Codex {codex.get('continuation_mode', 'mission')} mode is "
                      f"{'armed' if running(state) else 'inactive'}. "
                      f"State: {path}. Read current tasks and evidence before continuing. "
                      "Setup alone does not activate continuation."}}
        elif ev == "Stop":
            output, codex["last_gate"] = continuation(state, event)
            if output.get('decision') == 'block' and codex.get('desktop'):
                from codex_desktop import marker_signature
                token = str(uuid.uuid4())
                codex['pending_desktop_wake'] = {
                    'token': token, 'message_id': str(uuid.uuid4()), 'source_turn': event['turn_id'],
                    'phase': 'waiting', 'input_marker': marker_signature(path), 'created_at': grip.stamp()}
                private_write(path, state)
                try:
                    process = subprocess.Popen([sys.executable, str(ROOT / 'codex_desktop.py'), str(path), token],
                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True, close_fds=True)
                    codex['pending_desktop_wake']['pid'] = process.pid
                    codex['last_gate'] = 'desktop_waiting_for_turn_completion'
                    output = {}  # Let the final response finish so predictions can appear.
                except OSError:
                    codex['pending_desktop_wake']['phase'] = 'worker_start_failed'
                    codex['last_gate'] = 'native_fallback_after_worker_start_failure'
        codex.update(last_event=ev, last_event_at=grip.stamp())
        if event.get("turn_id"):
            codex["last_observed_turn"] = event["turn_id"]
        pending = codex.get('pending_desktop_wake') or {}
        if ev == 'PreToolUse' and pending.get('phase') in ('ipc_accepted', 'dispatching', 'delivery_unknown'):
            from codex_desktop import input_marker
            observed = read_json(input_marker(path), {})
            if (observed.get('wake_token') == pending.get('token') and observed.get('turn_id') == event.get('turn_id')
                    and event.get('turn_id') != pending.get('source_turn')):
                pending.update(prior_delivery_phase=pending['phase'], phase='agent_started', agent_turn_id=event['turn_id'],
                               agent_started_at=grip.stamp(), reconciled_by='matching_native_tool_event')
        private_write(path, state)
        return output


def ingest_prediction(event):
    """Consume native notifications or explicitly labelled desktop read samples."""
    if event.get("method") != "thread/prediction/updated":
        raise ValueError("Expected thread/prediction/updated")
    source = event.get("grip_capture_source", "app_server_event")
    if source not in ("app_server_event", "desktop_composer_cdp"):
        raise ValueError("Unknown prediction capture source")
    params = event.get("params") or {}
    sid, turn, result = params.get("threadId"), params.get("sourceTurnId"), params.get("result")
    binding = lookup(sid)
    if not binding:
        return {"accepted": False, "reason": "unbound_thread"}
    if not isinstance(turn, str) or not turn or not isinstance(result, dict):
        raise ValueError("Prediction needs a source turn and result")
    kind, text = result.get("type"), result.get("text")
    if kind not in ("completed", "failed") or (text is not None and (not isinstance(text, str) or len(text) > 8000)):
        raise ValueError("Invalid prediction result")
    grip, _, _ = modules()
    path = Path(binding["state_path"])
    with grip.locked(path.with_suffix(".lock")):
        state = grip.load(path)
        if not state_matches(state, binding, sid):
            raise ValueError("Binding identity changed")
        codex = state.setdefault("codex", {})
        # The source turn must have been seen by the native hooks. A stale or
        # unrelated stream cannot replace the current turn's prediction.
        if codex.get("last_observed_turn") != turn:
            return {"accepted": False, "reason": "stale_or_unobserved_turn"}
        codex["prediction"] = {"source_turn_id": turn, "type": kind,
                               "text": text if kind == "completed" else None,
                               "received_at": time.time(), "capture_source": source}
        private_write(path, state)
    return {"accepted": True, "thread_id": sid, "source_turn_id": turn, "result": kind, "capture_source": source}


def hook_config(command=None):
    command = command or shlex.join([sys.executable, str(ROOT / "codex_bridge.py"), "hook"])
    return {ev: [{"hooks": [{"type": "command", "command": command,
                              "timeout": 3 if ev in ("Interrupt", "SessionEnd") else 10}]}] for ev in EVENTS}


def install_hooks(target):
    """Merge once, preserve other hooks, never alter Codex hook trust."""
    grip, _, _ = modules()
    path = Path(target).expanduser().resolve()
    with grip.locked(path.with_name(path.name + ".grip.lock")):
        data = read_json(path, {})
        hooks = data.setdefault("hooks", {})
        added = []
        for ev, groups in hook_config().items():
            command = groups[0]["hooks"][0]["command"]
            have = [h.get("command") for group in hooks.get(ev, []) for h in group.get("hooks", [])]
            if command not in have:
                hooks.setdefault(ev, []).extend(groups)
                added.append(ev)
        if added:
            if path.exists():
                backup = path.with_name(path.name + f".pre-grip-{time.time_ns()}")
                backup.write_bytes(path.read_bytes())
                backup.chmod(0o600)
            private_write(path, data)
    return {"hooks_file": str(path), "added": added, "activation": "unchanged",
            "trust": "Review GRIP in Settings > Hooks (desktop) or /hooks (CLI)."}


def configure(args):
    grip, mission, _ = modules()
    path = Path(args.state).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve(strict=True)
    sid = args.thread_id or os.environ.get("CODEX_THREAD_ID")
    if not sid:
        raise ValueError("Supply the actual Codex thread ID")
    if args.max_wakes < 1:
        raise ValueError("max-wakes must be positive")
    if args.deadline:
        from datetime import datetime
        dt = datetime.fromisoformat(args.deadline)
        if dt.tzinfo is None:
            raise ValueError("deadline needs an explicit timezone")
    manifest = read_json(args.mission)
    reg = registry()
    # All multi-file changes take registry then state locks in this order.
    with grip.locked(reg.with_suffix(".lock")):
        data = read_json(reg, {"sessions": {}})
        old = data["sessions"].get(sid)
        if old and (Path(old["state_path"]).resolve() != path or Path(old["workspace"]).resolve() != workspace):
            raise ValueError("Thread is already bound elsewhere; unbind it explicitly first")
        with grip.locked(path.with_suffix(".lock")):
            state = read_json(path)
            if state is not None:
                if state.get("session_id") != sid or state.get("harness") != HARNESS or Path(state["workspace"]).resolve() != workspace:
                    raise ValueError("Cannot replace a different mission binding")
                if infinite_mode(state) and running(state):
                    raise ValueError("Pause infinite mode before switching to a mission")
                # `configure` is repeatable, not an implicit resume or new scope.
                status = state["status"]
                mission.activate(state, manifest, now=grip.stamp())
                state["status"] = status
            else:
                state = {"schema": 1, "harness": HARNESS, "session_id": sid,
                         "workspace": str(workspace), "state_path": str(path),
                         "compute_target": args.compute, "deadline": args.deadline,
                         "maximum_wakes": args.max_wakes, "wake_count": 0,
                         "tasks": [], "active_iteration": None, "codex": {"prefer_predictions": True}}
                mission.activate(state, manifest, now=grip.stamp())
                state["status"] = "paused"
            codex = state.setdefault("codex", {})
            if infinite_mode(state):
                # A fresh infinite binding has no mission budget. Switching back
                # supplies one without discarding the accumulated wake counter.
                if state.get("maximum_wakes") is None:
                    state["maximum_wakes"] = args.max_wakes
            codex.update(continuation_mode="mission", infinite_active=False)
            private_write(path, state)
            data["sessions"][sid] = {"harness": HARNESS, "state_path": str(path), "workspace": str(workspace)}
            private_write(reg, data)
    return {"state": str(path), "thread_id": sid, "status": state["status"], "bound": True}


def configure_infinite(args):
    """Bind open-ended continuation while paused, without fabricating a mission."""
    grip, _, _ = modules()
    path = Path(args.state).expanduser().resolve()
    workspace = Path(args.workspace).expanduser().resolve(strict=True)
    sid = args.thread_id or os.environ.get("CODEX_THREAD_ID")
    if not sid:
        raise ValueError("Supply the actual Codex thread ID")
    if not args.instructions.strip() or not args.compute.strip():
        raise ValueError("Record the authorized scope and compute/tools")
    reg = registry()
    with grip.locked(reg.with_suffix(".lock")):
        data = read_json(reg, {"sessions": {}})
        old = data["sessions"].get(sid)
        if old and (Path(old["state_path"]).resolve() != path or Path(old["workspace"]).resolve() != workspace):
            raise ValueError("Thread is already bound elsewhere; unbind it explicitly first")
        with grip.locked(path.with_suffix(".lock")):
            state = read_json(path)
            if state is None:
                state = {"schema": 1, "harness": HARNESS, "session_id": sid,
                         "workspace": str(workspace), "state_path": str(path),
                         "compute_target": args.compute, "deadline": None,
                         "maximum_wakes": None, "wake_count": 0,
                         "tasks": [], "active_iteration": None, "status": "paused", "codex": {}}
            else:
                if not state_matches(state, {"workspace": str(workspace)}, sid):
                    raise ValueError("Cannot replace a different Codex binding")
                if state.get("status") != "paused":
                    raise ValueError("Pause this binding before configuring infinite mode")
                pending = state.get("codex", {}).get("pending_desktop_wake") or {}
                if pending.get("phase") in ("waiting", "dispatching", "delivery_unknown"):
                    raise ValueError("Reconcile the existing pending wake before changing mode")
            state["compute_target"] = args.compute
            state.setdefault("codex", {}).update(continuation_mode="infinite", infinite_active=False,
                infinite_instructions=args.instructions.strip(), prefer_predictions=True)
            # Existing task, objective, wake and deadline evidence is retained.
            private_write(path, state)
            data["sessions"][sid] = {"harness": HARNESS, "state_path": str(path), "workspace": str(workspace)}
            private_write(reg, data)
    return {"state": str(path), "thread_id": sid, "status": "paused", "bound": True,
            "continuation_mode": "infinite", "maximum_wakes": None, "activated": False}


def state_command(args):
    grip, mission, _ = modules()
    path = Path(args.state).expanduser().resolve()
    if args.action == 'pause':
        private_write(pause_marker(path), {'at': grip.stamp(), 'event': 'pause_command'})
    with grip.locked(path.with_suffix(".lock")):
        state = grip.load(path)
        binding = lookup(state.get("session_id"))
        if not binding or Path(binding["state_path"]).resolve() != path or not state_matches(state, binding, state.get("session_id")):
            raise ValueError("Not a bound Codex mission")
        if args.action in ("activate", "pause"):
            codex = state.setdefault("codex", {})
            if args.action == "pause":
                private_write(pause_marker(path), {"at": grip.stamp(), "event": "pause_command"})
                state["status"] = "paused"
                codex["infinite_active"] = False
            else:
                if state.get("status") == "deadline" or grip.deadline_reached(state):
                    raise ValueError("Review the reached deadline before resuming")
                if not infinite_mode(state) and state.get("status") == "wake_budget":
                    raise ValueError("Review the exhausted limit before creating a new mission")
                if infinite_mode(state) and not codex.get("desktop"):
                    raise ValueError("Use configure-desktop before activating infinite mode")
                pending = codex.get("pending_desktop_wake") or {}
                if pending.get("phase") in ("waiting", "dispatching", "delivery_unknown"):
                    raise ValueError("Reconcile the existing pending wake before resuming")
                pause_marker(path).unlink(missing_ok=True)
                state["status"] = "active"
                if infinite_mode(state):
                    codex["infinite_active"] = True
                else:
                    mission.refresh(state)
            private_write(path, state)
        codex = dict(state.get("codex", {}))
        prediction = codex.pop("prediction", None)
        return {"status": state["status"], "thread_id": state["session_id"], "bound": True,
                "continuation_mode": codex.get("continuation_mode", "mission"),
                "continuation_active": running(state) and not pause_marker(path).exists(),
                "next_task": mission.next_task(state), "wake_count": state.get("wake_count", 0),
                "maximum_wakes": None if infinite_mode(state) else state.get("maximum_wakes"),
                "deadline": state.get("deadline"), "codex": codex,
                "prediction_cached": prediction is not None,
                "prediction_access": "desktop post-turn worker" if codex.get('desktop') else "native Stop fallback"}


def configure_desktop(args):
    """Configure the verified current desktop target without activating a mission."""
    from urllib.parse import urlsplit
    from codex_desktop import DesktopIpc, desktop_read, history_head
    grip, _, _ = modules()
    endpoint = urlsplit(args.endpoint)
    if (endpoint.scheme != 'http' or endpoint.hostname not in ('127.0.0.1', '::1') or not endpoint.port
            or endpoint.username or endpoint.password or endpoint.path not in ('', '/') or endpoint.query or endpoint.fragment):
        raise ValueError('Desktop debugger must be a literal loopback HTTP endpoint with a port')
    node = shutil.which(args.node) if args.node else shutil.which('node')
    if not node:
        raise ValueError('A Node runtime is required')
    path = Path(args.state).expanduser().resolve()
    state = grip.load(path)
    if running(state):
        raise ValueError('Pause the mission before configuring desktop delivery')
    config = {'endpoint': args.endpoint, 'target_id': args.target_id, 'node': str(Path(node).resolve()),
              'ipc_socket': str(Path(args.ipc_socket).expanduser().resolve()), 'prediction_wait_seconds': args.prediction_wait_seconds,
              'history_db': str(Path(args.history_db).expanduser().resolve())}
    if not 0 <= args.prediction_wait_seconds <= 30:
        raise ValueError('Prediction wait must be between 0 and 30 seconds')
    context = desktop_read(config, state['session_id'])
    visible = context.get('available') and context.get('threadId') == state['session_id']
    if not visible and context.get('reason') not in ('different_visible_thread', 'no_unique_visible_composer'):
        raise ValueError('The selected desktop page did not expose a supported composer context')
    history_head(config, state['session_id'])
    ipc = DesktopIpc(config['ipc_socket'])
    try:
        owner = ipc.owner(state['session_id'])
        settings = ipc.settings(state['session_id'], owner)
        if not settings:
            raise ValueError('The existing thread owner could not confirm settings')
    finally:
        ipc.close()
    with grip.locked(path.with_suffix('.lock')):
        current = grip.load(path)
        binding = lookup(current.get('session_id'))
        if (not binding or Path(binding['state_path']).resolve() != path or not state_matches(current, binding, state['session_id'])
                or running(current)):
            raise ValueError('Mission changed during desktop verification')
        current.setdefault('codex', {})['desktop'] = config
        private_write(path, current)
    return {'configured': True, 'activated': False, 'thread_id': state['session_id'],
            'debugger_context_verified': bool(visible), 'desktop_owner_verified': True,
            'history_metadata_verified': True, 'background_fallback_available': True}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state", help="One Codex thread's GRIP state file")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("hook")
    sub.add_parser("ingest-prediction", help="Consume a native thread/prediction/updated event on stdin")
    install = sub.add_parser("install-hooks")
    install.add_argument("--hooks-file", default=str(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "hooks.json"))
    init = sub.add_parser("configure", help="Bind a mission in paused state; do not start work")
    init.add_argument("--mission", required=True)
    init.add_argument("--thread-id")
    init.add_argument("--workspace", required=True)
    init.add_argument("--compute", required=True)
    init.add_argument("--max-wakes", type=int, default=20)
    init.add_argument("--deadline", help="ISO timestamp with explicit timezone")
    infinite = sub.add_parser("configure-infinite", help="Bind paused Codex infinite mode; no mission or finish condition")
    infinite.add_argument("--thread-id")
    infinite.add_argument("--workspace", required=True)
    infinite.add_argument("--compute", required=True)
    infinite.add_argument("--instructions", required=True, help="Existing work/idea scope authorized by the user")
    for name in ("activate", "pause", "status"):
        sub.add_parser(name)
    desktop = sub.add_parser('configure-desktop', help='Verify a loopback debugger and native desktop owner; leave mission paused')
    desktop.add_argument('--endpoint', default='http://127.0.0.1:9222')
    desktop.add_argument('--target-id', required=True)
    desktop.add_argument('--node', help='Existing Node executable, optionally an absolute path')
    desktop.add_argument('--ipc-socket', default=str(Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'ipc/ipc.sock'))
    desktop.add_argument('--history-db', default=str(Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')) / 'thread_history_1.sqlite'))
    desktop.add_argument('--prediction-wait-seconds', type=float, default=12)
    unbind = sub.add_parser("unbind")
    unbind.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
    args = ap.parse_args(argv)
    if args.action == "hook":
        try:
            result = hook(input_json())
        except Exception as exc:
            # Never expose prompt/tool content, and never interrupt a user's turn.
            print(f"GRIP Codex hook skipped: {type(exc).__name__}", file=sys.stderr)
            result = {}
    elif args.action == "ingest-prediction":
        result = ingest_prediction(input_json())
    elif args.action == "install-hooks":
        result = install_hooks(args.hooks_file)
    elif args.action == "unbind":
        grip, _, _ = modules()
        reg = registry()
        with grip.locked(reg.with_suffix(".lock")):
            data = read_json(reg, {"sessions": {}})
            removed = data["sessions"].pop(args.thread_id, None)
            private_write(reg, data)
        result = {"unbound": removed is not None}
    else:
        if not args.state:
            ap.error("--state is required")
        handlers = {"configure": configure, "configure-infinite": configure_infinite,
                    "configure-desktop": configure_desktop}
        result = handlers.get(args.action, state_command)(args)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
