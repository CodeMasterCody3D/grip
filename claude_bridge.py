#!/usr/bin/env python3
"""GRIP's Claude Code binding: the Claude side of GRIP, hooked into the harness the way claude-mem is (11-01; Cody: "make sure the grip
skill can use the python script to hook intoo the claude harness like how the claude-mem does. this would make it so the grip side for
cluade can work and you can continue training captureing data and info so we can make a better trainer and i learn at the same time").

OpenCode GRIP wakes its session by posting to OpenCode's loopback server. Claude Code has no such server. Its own two levers are:
  1. hooks -- every registered event runs a command with the event JSON on stdin; a Stop hook may answer {"decision": "block",
     "reason": R} and the session continues on R instead of stopping;
  2. background tasks -- a command the session starts with run_in_background wakes the session when it exits.
This bridge uses exactly those two, plus GRIP's own mission machinery unchanged (mission / objective_watch / completion, grip.prompt,
grip.locked / load / atomic / deadline_reached, event_hooks.record). It edits no GRIP file; OpenCode missions are untouched.

  hook          the ONE command every registered Claude Code hook event calls (stdin = the event JSON). An unbound session exits at once,
                silent, before GRIP is even imported. A bound session (registry <cache>/bindings.json, harness "claude-code"):
                  every event -> GRIP's native event kinds recorded in the mission state (tool_start / tool_end / turn_start / turn_end /
                                 hook_loaded / idle): the same bookkeeping the OpenCode plugin feeds
                              -> one observation line in <state dir>/claude_observations.jsonl: time, event, tool, call id, ok / failed,
                                 seconds, the Bash description or the file path. Never command text, tool output or prompt text.
                  SessionStart     -> the mission status as context, so a compaction or resume never loses the loop
                  UserPromptSubmit -> a human turn; "stop / pause / cancel / hold on" pauses the mission (GRIP's tick rule)
                  Stop             -> THE CONTINUATION GATE (below)
  wait          THE WAKE. The session runs it with run_in_background. It polls the mission state, plus an optional --until shell
                condition, and exits printing GRIP's wake prompt when the next check is due: the condition met, or the --every-min
                heartbeat. Or it exits saying why not (paused / blocked / complete / deadline). Its exit is what wakes an idle session.
                --health "<check>" (11-01 fallback): a shell health check every poll; --health-strikes failures in a row (default 3)
                wake the session at once with the check's output -- a run that died silently is caught in minutes, not at the heartbeat.
  init          create a Claude-harness mission state from a GRIP mission file (schema 1, through mission.activate) and bind it
  bind / unbind / status / observations / install-hooks

The continuation gate (Stop):
  a stop that is itself the result of a stop-hook block -> allowed (never a loop)
  mission not active, plan mode, past its deadline, wake budget spent, or no actionable task -> allowed (a blocked task waits for the human)
  the waiter is alive -> allowed (it wakes the session when the check is due)
  no tool work since the last continuation -> allowed + noted (never a spin)
  otherwise -> BLOCK with GRIP's wake prompt + the Claude addendum: continue the next task now; if it waits on a running job, arm the
               waiter for that job instead; if it needs the human, mark it blocked with the task CLI and stop.
"""
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
HARNESS = "claude-code"
STOP_RE = re.compile(r"\s*(stop|pause|cancel|hold on)\b", re.I)
EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop", "SessionEnd")
KIND = {"SessionStart": "hook_loaded", "UserPromptSubmit": "turn_start", "PreToolUse": "tool_start", "PostToolUse": "tool_end",
        "PostToolUseFailure": "tool_end", "Stop": "turn_end", "SessionEnd": "idle"}


def cache_root():
    """the same rule as event_hooks.cache_root(), without importing GRIP for an unbound session"""
    if os.environ.get("GRIP_CACHE_DIR"):
        return Path(os.environ["GRIP_CACHE_DIR"]).expanduser().resolve()
    return (Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")).expanduser() / "grip").resolve()


def registry():
    return cache_root() / "bindings.json"


def binding(session_id):
    try:
        data = json.loads(registry().read_text())
    except (OSError, ValueError):
        return None
    b = (data.get("sessions") or {}).get(session_id or "")
    return b if isinstance(b, dict) and b.get("harness") == HARNESS else None


def grip_modules():
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import grip
    import mission
    import event_hooks
    return grip, mission, event_hooks


def side(state_path, name):
    """files the bridge keeps beside the mission state: claude_<name>"""
    return Path(state_path).with_name("claude_" + name)


def waiter_alive(state_path):
    try:
        w = json.loads(side(state_path, "waiter.json").read_text())
        pid = int(w["pid"])
        os.kill(pid, 0)
        return "claude_bridge.py" in Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="replace")
    except (OSError, ValueError, KeyError):
        return False


def detail(inp):
    """metadata only: what the tool was for, never what it ran or returned"""
    tool = str(inp.get("tool_name") or "")
    ti = inp.get("tool_input") if isinstance(inp.get("tool_input"), dict) else {}
    if tool == "Bash":
        return {"description": str(ti.get("description") or "")[:240], "background": bool(ti.get("run_in_background"))}
    for key in ("file_path", "notebook_path", "path"):
        if ti.get(key):
            return {key: str(ti[key])[:300]}
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        return {"server": tool.split("__")[1]}
    return {}


def addendum(state, path, reason):
    _g, mission, _e = grip_modules()
    nt = mission.next_task(state) or {}
    py = sys.executable
    return (" Claude Code harness (no OpenCode server): this wake came from the GRIP Claude bridge (" + reason + "). "
            "If the next task waits on a running job, do not poll by hand: arm the waiter as a background task (run_in_background) -- "
            + shlex.join([py, str(HERE / "claude_bridge.py"), "--state", str(path), "wait", "--until", "<a shell check that exits 0 when "
                          "the job's next check is due>", "--every-min", "30"])
            + " -- and end the turn; its exit wakes you. If the task needs the human, mark it blocked and stop: "
            + shlex.join([py, str(HERE / "grip.py"), "--state", str(path), "task", "--id", str(nt.get("id", "TASK")), "--status", "blocked",
                          "--note", "what it waits for", "--revision", str(mission.revision(state))])
            + ". The Stop hook holds this session to an actionable task until the waiter is armed, the task is blocked or done, or the "
            "mission is paused.")


def wake_text(state, path, reason, extra=""):
    grip, _m, _e = grip_modules()
    return grip.prompt(state) + addendum(state, path, reason) + extra


# ---- hook ----------------------------------------------------------------------------------------------------------------------------
def gate(state, inp, path):
    """(reason to block or None, why) -- the continuation decision at a turn's end"""
    grip, mission, _e = grip_modules()
    if inp.get("stop_hook_active"):
        return None, "a stop-hook continuation is already running"
    if state.get("status") != "active":
        return None, "mission " + str(state.get("status"))
    if inp.get("permission_mode") == "plan":
        return None, "plan mode"
    if grip.deadline_reached(state):
        state["status"] = "deadline"
        return None, "mission deadline reached"
    nt = mission.next_task(state)
    if nt is None:
        return None, "no actionable task"
    if waiter_alive(path):
        return None, "the waiter is armed"
    mw = state.get("maximum_wakes")
    if mw is not None and state.get("wake_count", 0) >= mw:
        state["status"] = "wake_budget"
        return None, "wake budget spent"
    cl = state.setdefault("claude", {})
    tools_now = state.get("hook_state", {}).get("counts", {}).get("tool_start", 0)
    if cl.get("last_block_tools") is not None and tools_now == cl["last_block_tools"]:
        return None, "no tool work since the last continuation"
    cl["last_block_tools"] = tools_now
    cl["last_block_at"] = grip.stamp()
    state["wake_count"] = state.get("wake_count", 0) + 1
    why = f"the turn ended with task {nt.get('id')} {nt.get('status')} and no waiter armed"
    return wake_text(state, path, why), why


def context(state, path):
    _g, mission, _e = grip_modules()
    nt = mission.next_task(state) or {}
    return (f"GRIP (Claude Code) mission {state.get('mission_id')} is {state.get('status')} for this session. Objective: "
            f"{str(state.get('objective'))[:300]} | next task: {nt.get('id')} ({nt.get('status')}): {str(nt.get('content', ''))[:240]} | "
            f"waiter {'armed' if waiter_alive(path) else 'NOT armed'} | state {path} | controller: "
            + shlex.join([sys.executable, str(HERE / "grip.py"), "--state", str(path), "status"])
            + " | the Stop hook continues you while a task is actionable and no waiter is armed.")


def cmd_hook(a):
    try:
        inp = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    b = binding(inp.get("session_id"))
    ev = inp.get("hook_event_name") or a.event or ""
    if not b or ev not in EVENTS:
        return 0                                                    # unbound session or unknown event: silent, fast
    grip, mission, event_hooks = grip_modules()
    path = Path(b["state_path"])
    now_ms = int(time.time() * 1000)
    out = None
    with grip.locked(path.with_suffix(".lock")):
        state = grip.load(path)
        if state.get("session_id") != inp.get("session_id"):
            return 0
        call = inp.get("tool_use_id")
        hs = state.get("hook_state", {})
        started = (hs.get("tool_starts") or {}).get(call) if call else None
        agent = "plan" if inp.get("permission_mode") == "plan" else "build"
        kind = KIND[ev]
        if kind in ("tool_start", "tool_end") and not call:
            kind = None                                             # GRIP's record() needs the actual call id
        rec = {"at": grip.stamp(), "event": ev, "kind": kind}
        if kind:
            rec["accepted"] = event_hooks.record(state, session_id=inp["session_id"], kind=kind, call_id=call, agent=agent,
                                                 event_id=(ev + ":" + call) if call else None, at_ms=now_ms).get("accepted")
        if ev in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            rec.update(tool=inp.get("tool_name"), call_id=call, **detail(inp))
            if ev != "PreToolUse":
                rec["ok"] = ev == "PostToolUse"
                if started:
                    rec["seconds"] = round((now_ms - int(started)) / 1000, 1)
        if ev == "UserPromptSubmit":
            text = str(inp.get("prompt") or "")
            rec["human_chars"] = len(text)
            if STOP_RE.match(text) and state.get("status") == "active":
                state["status"] = "paused"
                rec["paused"] = "human stop / pause"
        if ev == "SessionStart":
            rec["source"] = inp.get("source")
            mission.refresh(state)
            out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context(state, path)}}
        if ev == "Stop":
            reason, why = gate(state, inp, path)
            rec["gate"] = why
            if reason:
                rec["continued"] = True
                out = {"decision": "block", "reason": reason}
        grip.atomic(path, state)
    with open(side(path, "observations.jsonl"), "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    if out:
        print(json.dumps(out))
    return 0


# ---- wait (the wake) -----------------------------------------------------------------------------------------------------------------
def cmd_wait(a):
    grip, mission, _e = grip_modules()
    path = Path(a.state).resolve()
    w = side(path, "waiter.json")
    me = {"pid": os.getpid(), "started": time.time(), "until": a.until, "every_min": a.every_min}
    w.write_text(json.dumps(me))
    t0, last_err, strikes = time.time(), None, 0
    try:
        while True:
            state = grip.load(path)
            st = state.get("status")
            if st != "active":
                print(f"GRIP WAITER: the mission is {st} -- no wake; do not continue it unless the human says so")
                return 3
            if grip.deadline_reached(state):
                print("GRIP WAITER: the mission deadline passed -- bank the work and stop")
                return 3
            nt = mission.next_task(state)
            if nt is None:
                print("GRIP WAITER: no actionable task (all blocked, parked or done) -- nothing to wake for")
                return 3
            due, tail = None, ""
            if a.health:                                            # 11-01 (Cody: "a fall back feature ... just in case its failed
                try:                                                # silently"): a failing health check wakes the session EARLY
                    h = subprocess.run(a.health, shell=True, capture_output=True, text=True, timeout=a.until_timeout)
                    hrc, hout = h.returncode, (h.stdout + h.stderr)[-1500:]
                except subprocess.TimeoutExpired:
                    hrc, hout = 2, f"the health check timed out after {a.until_timeout:g} s"
                strikes = strikes + 1 if hrc != 0 else 0
                if strikes >= a.health_strikes:
                    due, tail = f"HEALTH CHECK FAILED {strikes} times in a row (a silent failure?)", hout
            if due is None and a.until:
                try:
                    r = subprocess.run(a.until, shell=True, capture_output=True, text=True, timeout=a.until_timeout)
                    if r.returncode == 0:
                        due, tail = "condition met", (r.stdout + r.stderr)[-1500:]
                    last_err = None
                except subprocess.TimeoutExpired:
                    last_err = f"the --until check timed out after {a.until_timeout:g} s"
            if due is None and time.time() - t0 >= 60 * a.every_min:
                due = f"heartbeat after {a.every_min:g} min" + (f" ({last_err})" if last_err else "")
            if due:
                with grip.locked(path.with_suffix(".lock")):
                    s2 = grip.load(path)
                    s2["wake_count"] = s2.get("wake_count", 0) + 1
                    s2.setdefault("claude", {})["last_wake"] = {"at": grip.stamp(), "reason": due, "task": nt.get("id")}
                    grip.atomic(path, s2)
                with open(side(path, "observations.jsonl"), "a") as f:
                    f.write(json.dumps({"at": grip.stamp(), "event": "WaiterWake", "reason": due, "task": nt.get("id")}) + "\n")
                print(wake_text(s2, path, "waiter: " + due, extra=("\nCondition output (tail):\n" + tail) if tail else ""))
                return 0
            time.sleep(a.poll)
    finally:
        try:
            if json.loads(w.read_text()).get("pid") == os.getpid():
                w.unlink()
        except (OSError, ValueError):
            pass


# ---- init / bind / status / install-hooks --------------------------------------------------------------------------------------------
def bind(path, session_id):
    grip, _m, _e = grip_modules()
    reg = registry()
    reg.parent.mkdir(parents=True, exist_ok=True)
    with grip.locked(reg.with_suffix(".lock")):
        data = grip.load(reg) if reg.exists() else {"sessions": {}}
        old = data["sessions"].get(session_id)
        if old and old.get("state_path") != str(path):
            raise SystemExit(f"REFUSING: session {session_id} is already bound to {old.get('state_path')} (unbind it first)")
        data["sessions"][session_id] = {"state_path": str(path), "harness": HARNESS, "bound_at": grip.stamp()}
        grip.atomic(reg, data)
    return {"bound": True, "session_id": session_id, "state_path": str(path), "harness": HARNESS,
            "note": "binding is not a hook receipt: a hook_loaded / tool event in the state proves the hooks fire"}


def cmd_init(a):
    grip, mission, _e = grip_modules()
    path = Path(a.state).expanduser().resolve()
    if path.exists():
        raise SystemExit(f"REFUSING: {path} exists -- a Claude mission is created once; use the task CLI to change it")
    sid = a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if not sid:
        raise SystemExit("REFUSING: no Claude session id (pass --session-id or run from inside Claude Code)")
    manifest = json.loads(Path(a.mission).read_text())
    ws = str(Path(a.workspace).expanduser().resolve())
    state = {"workspace": ws, "project_id": manifest.get("mission_id"), "session_id": sid, "session_directory": ws, "harness": HARNESS,
             "compute_target": a.compute, "source_roots": [], "metadata_globs": [], "github_repo": None, "backup_directory": None,
             "backup_branch": None, "poll_seconds": 60, "idle_grace_seconds": 0, "maximum_packet_seconds": 1800,
             "backup_margin_seconds": 120, "minimum_method_attempts": 0, "deadline": a.deadline, "deadline_basis": a.deadline_basis,
             "maximum_wakes": a.max_wakes, "state_path": str(path), "plan_revision": 0, "task_events": []}
    skill = Path.home() / ".claude" / "skills" / "grip" / "SKILL.md"
    if skill.exists():
        state["skill_path"] = str(skill)                            # the wake prompt names the skill this harness loads
    result = mission.activate(state, manifest, now=grip.stamp())
    path.parent.mkdir(parents=True, exist_ok=True)
    with grip.locked(path.with_suffix(".lock")):
        grip.atomic(path, state)
    print(json.dumps({"created": str(path), **result, **bind(path, sid)}, indent=1, default=str))
    return 0


def cmd_bind(a):
    grip, _m, _e = grip_modules()
    path = Path(a.state).expanduser().resolve()
    state = grip.load(path)
    sid = a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    if state.get("harness") != HARNESS or state.get("session_id") != sid:
        raise SystemExit("REFUSING: only a Claude-harness mission created for this session binds here (OpenCode missions use bind-hooks)")
    print(json.dumps(bind(path, sid), indent=1))
    return 0


def cmd_unbind(a):
    grip, _m, _e = grip_modules()
    reg = registry()
    with grip.locked(reg.with_suffix(".lock")):
        data = grip.load(reg) if reg.exists() else {"sessions": {}}
        b = data["sessions"].get(a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
        if b and b.get("harness") == HARNESS:
            data["sessions"].pop(a.session_id or os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
            grip.atomic(reg, data)
            print("UNBOUND")
            return 0
    print("not bound (or not a Claude binding)")
    return 0


def cmd_status(a):
    grip, mission, _e = grip_modules()
    path = Path(a.state).expanduser().resolve()
    state = grip.load(path)
    mission.refresh(state)
    obs = side(path, "observations.jsonl")
    n = sum(1 for _ in open(obs)) if obs.exists() else 0
    nt = mission.next_task(state) or {}
    print(json.dumps({"mission": state.get("mission_id"), "status": state.get("status"), "harness": state.get("harness"),
                      "session": state.get("session_id"), "bound": bool(binding(state.get("session_id"))), "waiter": waiter_alive(path),
                      "next_task": {k: nt.get(k) for k in ("id", "status", "content")}, "wake_count": state.get("wake_count", 0),
                      "event_counts": state.get("hook_state", {}).get("counts"), "observations": n, "claude": state.get("claude")},
                     indent=1, default=str))
    return 0


def cmd_observations(a):
    obs = side(Path(a.state).expanduser().resolve(), "observations.jsonl")
    rows = [json.loads(x) for x in open(obs)] if obs.exists() else []
    for r in rows[-a.last:]:
        print(json.dumps(r, ensure_ascii=False))
    return 0


def hooks_block():
    cmd = shlex.join([sys.executable, str(HERE / "claude_bridge.py"), "hook"]) + " 2>/dev/null || true"
    h = {"type": "command", "command": cmd, "timeout": 30}
    return {ev: [dict({"matcher": "*"} if ev.endswith("ToolUse") or ev.endswith("Failure") else {}, hooks=[dict(h)])] for ev in EVENTS}


def cmd_install_hooks(a):
    """merge the bridge's hooks into a Claude Code settings file (the old file kept beside it first); idempotent"""
    target = Path(a.settings).expanduser().resolve()
    data = json.loads(target.read_text()) if target.exists() else {}
    if target.exists():
        backup = target.with_name(target.name + f".pre_grip_{time.strftime('%Y%m%d-%H%M%S')}")
        backup.write_bytes(target.read_bytes())
    hooks = data.setdefault("hooks", {})
    added = []
    for ev, groups in hooks_block().items():
        mine = groups[0]["hooks"][0]["command"]
        have = [h.get("command") for g in hooks.get(ev, []) for h in g.get("hooks", [])]
        if mine not in have:
            hooks.setdefault(ev, []).append(groups[0])
            added.append(ev)
    target.write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps({"settings": str(target), "added": added, "already": [e for e in EVENTS if e not in added]}, indent=1))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="GRIP's Claude Code binding (hooks + waiter); see the module docstring")
    ap.add_argument("--state", help="the Claude-harness GRIP mission state.json")
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("hook", help="called by every registered Claude Code hook event (stdin = the event JSON)")
    h.add_argument("--event", default="", help="fallback event name when the JSON lacks hook_event_name")
    w = sub.add_parser("wait", help="the wake: run with run_in_background; exits when the next check is due")
    w.add_argument("--until", default="", help="shell check, exit 0 = due (e.g. a job's DONE banner)")
    w.add_argument("--until-timeout", type=float, default=120.0)
    w.add_argument("--every-min", type=float, default=30.0, help="heartbeat: wake for a routine check after this long anyway")
    w.add_argument("--health", default="", help="shell health check run every poll, exit 0 = healthy (e.g. the GPU busy while the run "
                   "is unfinished, the VM reachable); --health-strikes failures in a row wake the session at once")
    w.add_argument("--health-strikes", type=int, default=3)
    w.add_argument("--poll", type=float, default=60.0)
    i = sub.add_parser("init")
    i.add_argument("--mission", required=True, help="GRIP mission file, schema 1 (mission_id, objective, done_when, "
                   "continuation_instructions, context_refs, tasks)")
    i.add_argument("--workspace", required=True)
    i.add_argument("--compute", required=True, help="the authorized compute, said in words")
    i.add_argument("--session-id", default="")
    i.add_argument("--deadline", default=None, help="ISO time; past it the gate and the waiter stop")
    i.add_argument("--deadline-basis", default="")
    i.add_argument("--max-wakes", type=int, default=200)
    for name in ("bind", "unbind"):
        s = sub.add_parser(name)
        s.add_argument("--session-id", default="")
    sub.add_parser("status")
    o = sub.add_parser("observations")
    o.add_argument("--last", type=int, default=20)
    k = sub.add_parser("install-hooks")
    k.add_argument("--settings", required=True, help="a Claude Code settings file (project .claude/settings.local.json, or "
                   "~/.claude/settings.json for every project)")
    a = ap.parse_args(argv)
    if a.cmd not in ("hook", "unbind", "install-hooks") and not a.state:
        raise SystemExit("--state is required")
    return {"hook": cmd_hook, "wait": cmd_wait, "init": cmd_init, "bind": cmd_bind, "unbind": cmd_unbind, "status": cmd_status,
            "observations": cmd_observations, "install-hooks": cmd_install_hooks}[a.cmd](a)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "hook":
        try:                                                        # a hook never breaks the session
            sys.exit(main())
        except SystemExit as e:
            sys.exit(e.code if isinstance(e.code, int) else 0)
        except Exception:
            sys.exit(0)
    sys.exit(main())
